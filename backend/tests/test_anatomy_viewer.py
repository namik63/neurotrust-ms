import numpy as np
from uuid import uuid4
from fastapi.testclient import TestClient

from app.core.anatomy import anatomy_analysis
from app.core.io import Volume, save_nifti
from app.core.metrics_lesion import lesion_metrics
from app.core.viewer_assets import write_viewer_assets
from app.main import app


def _volume(shape=(24, 24, 24)):
    return Volume(data=np.zeros(shape), affine=np.eye(4), spacing=(1, 1, 1), shape=shape, source="toy")


def test_anatomy_assigns_periventricular_lesion(tmp_path):
    image = _volume()
    gt = np.zeros(image.shape, dtype=bool)
    pred = np.zeros(image.shape, dtype=bool)
    gt[9:11, 12:14, 12:14] = True
    pred[9:11, 12:14, 12:14] = True
    atlas = np.zeros(image.shape, dtype=np.int16)
    atlas[12:14, 12:14, 12:14] = 4
    atlas[0:3, :, :] = 16
    atlas[2:-2, 2:-2, 2:-2] = np.where(atlas[2:-2, 2:-2, 2:-2] == 0, 2, atlas[2:-2, 2:-2, 2:-2])
    atlas[1:-1, 1:-1, 1:-1] = np.where(atlas[1:-1, 1:-1, 1:-1] == 0, 3, atlas[1:-1, 1:-1, 1:-1])
    path = tmp_path / "aparc_aseg_proxy.nii.gz"
    save_nifti(atlas, np.eye(4), path)
    lesions = lesion_metrics(gt, pred, image.spacing)
    result = anatomy_analysis(
        image=image,
        gt_mask=gt,
        pred_mask=pred,
        lesion_rows=lesions["lesions"],
        prediction_rows=lesions["predictions"],
        cluster_rows=lesions["clusters"],
        anatomy_path=path,
    )
    assert result["available"] is True
    assert lesions["lesions"][0]["primary_location"] == "periventricular"
    assert result["subject_fields"]["periventricular_recall"] == 1.0


def test_anatomy_missing_is_safe():
    image = _volume()
    lesions = lesion_metrics(np.zeros(image.shape, dtype=bool), np.zeros(image.shape, dtype=bool), image.spacing)
    result = anatomy_analysis(
        image=image,
        gt_mask=np.zeros(image.shape, dtype=bool),
        pred_mask=np.zeros(image.shape, dtype=bool),
        lesion_rows=lesions["lesions"],
        prediction_rows=lesions["predictions"],
        cluster_rows=lesions["clusters"],
        anatomy_path=None,
    )
    assert result["available"] is False
    assert result["subject_fields"]["anatomy_status"] == "missing"


def test_viewer_manifest_writes_derived_niftis(tmp_path):
    image = _volume()
    gt = np.zeros(image.shape, dtype=bool)
    pred = np.zeros(image.shape, dtype=bool)
    gt[2:4, 2:4, 2:4] = True
    pred[3:5, 3:5, 3:5] = True
    lesions = lesion_metrics(gt, pred, image.spacing)
    base_path = tmp_path / "flair.nii.gz"
    save_nifti(image.data, image.affine, base_path)

    def static(path):
        return f"/static/{path.name}"

    manifest, zip_path = write_viewer_assets(
        image=image,
        gt_mask=gt,
        pred_mask=pred,
        out_dir=tmp_path / "viewer",
        base_volumes=[{"key": "flair", "label": "FLAIR", "url": "/static/flair.nii.gz"}],
        static_url=static,
        lesion_rows=lesions["lesions"],
        prediction_rows=lesions["predictions"],
    )
    assert manifest["mode"] == "niivue_3d"
    assert (tmp_path / "viewer" / "missed_mask.nii.gz").is_file()
    assert zip_path.is_file()
    assert manifest["overlays"]


def test_batch_accepts_freesurfer_subject_folder_files(tmp_path):
    image = _volume()
    gt = np.zeros(image.shape, dtype=np.uint8)
    pred = np.zeros(image.shape, dtype=np.uint8)
    gt[9:11, 12:14, 12:14] = 1
    pred[9:11, 12:14, 12:14] = 1
    atlas = np.zeros(image.shape, dtype=np.int16)
    atlas[12:14, 12:14, 12:14] = 4
    paths = {
        "image": tmp_path / "subject_004_FLAIR.nii.gz",
        "gt": tmp_path / "subject_004.nii.gz",
        "pred": tmp_path / "subject_004_pred.nii.gz",
        "aparc": tmp_path / "aparc+aseg.mgz",
        "aseg": tmp_path / "aseg.mgz",
        "brainmask": tmp_path / "brainmask.mgz",
    }
    save_nifti(image.data, image.affine, paths["image"])
    save_nifti(gt, image.affine, paths["gt"])
    save_nifti(pred, image.affine, paths["pred"])
    save_nifti(atlas, image.affine, paths["aparc"])
    save_nifti(atlas, image.affine, paths["aseg"])
    save_nifti(gt, image.affine, paths["brainmask"])

    client = TestClient(app)
    login = client.post("/api/access/login", json={"email": f"viewer-test-{uuid4().hex}@example.com", "password": "viewer-test-pass"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    with (
        open(paths["image"], "rb") as image_file,
        open(paths["gt"], "rb") as gt_file,
        open(paths["pred"], "rb") as pred_file,
        open(paths["aparc"], "rb") as aparc_file,
        open(paths["aseg"], "rb") as aseg_file,
        open(paths["brainmask"], "rb") as brainmask_file,
    ):
        response = client.post(
            "/api/validation/upload-batch-run",
            headers=headers,
            data={"project_name": "fs folder smoke", "model_name": "model"},
            files=[
                ("raw_mris", ("subject_004_FLAIR.nii.gz", image_file, "application/gzip")),
                ("gts", ("subject_004.nii.gz", gt_file, "application/gzip")),
                ("predictions", ("subject_004.nii.gz", pred_file, "application/gzip")),
                ("freesurfer_files", ("eval_004/mri/brainmask.mgz", brainmask_file, "application/octet-stream")),
                ("freesurfer_files", ("eval_004/mri/aseg.mgz", aseg_file, "application/octet-stream")),
                ("freesurfer_files", ("eval_004/mri/aparc+aseg.mgz", aparc_file, "application/octet-stream")),
            ],
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["subject_metrics"]["anatomy_available_case_count"] == 1
    assert payload["viewer"]["mode"] == "niivue_3d"
