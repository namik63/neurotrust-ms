from __future__ import annotations

from pathlib import Path
import zipfile

import numpy as np

from .io import Volume, save_nifti


OVERLAY_STYLE = {
    "gt_mask": {"label": "Expert GT", "color": "#009e73", "colormap": "green", "opacity": 0.46},
    "prediction_mask": {"label": "AI prediction", "color": "#0072b2", "colormap": "blue", "opacity": 0.42},
    "overlap_mask": {"label": "Overlap", "color": "#f0e442", "colormap": "warm", "opacity": 0.64},
    "missed_mask": {"label": "Missed GT", "color": "#d55e00", "colormap": "red", "opacity": 0.82},
    "false_positive_mask": {"label": "Prediction-only", "color": "#e69f00", "colormap": "warm", "opacity": 0.74},
    "periventricular_gt": {"label": "PV GT", "color": "#004d40", "colormap": "green", "opacity": 0.50},
    "periventricular_pred": {"label": "PV prediction", "color": "#56b4e9", "colormap": "blue2cyan", "opacity": 0.46},
    "juxtacortical_cortical_gt": {"label": "JC/cortical GT", "color": "#117733", "colormap": "green", "opacity": 0.50},
    "juxtacortical_cortical_pred": {"label": "JC/cortical prediction", "color": "#cc79a7", "colormap": "violet", "opacity": 0.46},
    "infratentorial_gt": {"label": "IT GT", "color": "#7f4f24", "colormap": "green2orange", "opacity": 0.50},
    "infratentorial_pred": {"label": "IT prediction", "color": "#f4a261", "colormap": "redyell", "opacity": 0.46},
}


def write_viewer_assets(
    *,
    image: Volume,
    gt_mask: np.ndarray,
    pred_mask: np.ndarray,
    out_dir: Path,
    base_volumes: list[dict],
    static_url,
    lesion_rows: list[dict],
    prediction_rows: list[dict],
    location_masks: dict[str, np.ndarray] | None = None,
) -> tuple[dict, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    masks: dict[str, np.ndarray] = {
        "gt_mask": gt_mask,
        "prediction_mask": pred_mask,
        "overlap_mask": gt_mask & pred_mask,
        "missed_mask": gt_mask & ~pred_mask,
        "false_positive_mask": pred_mask & ~gt_mask,
    }
    for key, mask in (location_masks or {}).items():
        if mask is not None and np.asarray(mask).any():
            masks[key] = np.asarray(mask, dtype=bool)

    overlay_paths: dict[str, Path] = {}
    for key, mask in masks.items():
        path = out_dir / f"{key}.nii.gz"
        save_nifti(np.asarray(mask, dtype=np.uint8), image.affine, path)
        overlay_paths[key] = path

    zip_path = out_dir / "derived_overlay_masks.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for key, path in overlay_paths.items():
            zf.write(path, arcname=path.name)

    overlays = []
    for key, path in overlay_paths.items():
        style = OVERLAY_STYLE.get(key, {"label": key.replace("_", " "), "color": "#ffffff", "colormap": "gray", "opacity": 0.4})
        overlays.append(
            {
                "key": key,
                "label": style["label"],
                "url": static_url(path),
                "color": style["color"],
                "colormap": style["colormap"],
                "opacity": style["opacity"],
            }
        )

    first_base = base_volumes[0] if base_volumes else {"url": "", "label": "MRI"}
    manifest = {
        "mode": "niivue_3d",
        "label": "NiiVue 3D/orthogonal medical viewer using derived NIfTI overlays.",
        "base_volume_url": first_base.get("url"),
        "base_volumes": base_volumes,
        "overlays": overlays,
        "jump_targets": _jump_targets(lesion_rows, prediction_rows),
        "controls": ["axial", "coronal", "sagittal", "render", "opacity", "jump_to_lesion"],
    }
    return manifest, zip_path


def _jump_targets(lesion_rows: list[dict], prediction_rows: list[dict]) -> list[dict]:
    targets = []

    def centroid(row: dict, prefix: str = "centroid") -> list[int]:
        return [
            int(round(float(row.get(f"{prefix}_x") or 0))),
            int(round(float(row.get(f"{prefix}_y") or 0))),
            int(round(float(row.get(f"{prefix}_z") or 0))),
        ]

    missed = [row for row in lesion_rows if not row.get("lesion_detected")]
    for row in sorted(missed, key=lambda r: float(r.get("lesion_volume_mm3") or 0.0), reverse=True)[:3]:
        c = centroid(row)
        targets.append(
            {
                "label": f"Missed GT lesion {row.get('lesion_id')}",
                "lesion_id": row.get("lesion_id"),
                "slice": c[2],
                "centroid_voxel": c,
                "reason": "missed_lesion",
                "severity": "high" if row.get("high_risk_flag") else "medium",
            }
        )
    fp = [row for row in prediction_rows if row.get("false_positive")]
    for row in sorted(fp, key=lambda r: float(r.get("pred_volume_mm3") or 0.0), reverse=True)[:3]:
        c = [
            int(round(float(row.get("centroid_x") or 0))),
            int(round(float(row.get("centroid_y") or 0))),
            int(round(float(row.get("centroid_z") or 0))),
        ]
        targets.append(
            {
                "label": f"False positive {row.get('pred_lesion_id')}",
                "lesion_id": row.get("pred_lesion_id"),
                "slice": c[2],
                "centroid_voxel": c,
                "reason": "false_positive",
                "severity": "medium",
            }
        )
    poor_boundary = [
        row for row in lesion_rows if row.get("lesion_detected") and isinstance(row.get("lesion_dice"), (int, float))
    ]
    for row in sorted(poor_boundary, key=lambda r: float(r.get("lesion_dice") or 1.0))[:2]:
        c = centroid(row)
        targets.append(
            {
                "label": f"Boundary review lesion {row.get('lesion_id')}",
                "lesion_id": row.get("lesion_id"),
                "slice": c[2],
                "centroid_voxel": c,
                "reason": "low_matched_lesion_dice",
                "severity": "low",
            }
        )
    return targets[:8]
