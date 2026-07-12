from __future__ import annotations

from pathlib import Path
import numpy as np

from app.core.io import save_nifti


def sphere(shape: tuple[int, int, int], center: tuple[int, int, int], radius: int) -> np.ndarray:
    x, y, z = np.indices(shape)
    return (x - center[0]) ** 2 + (y - center[1]) ** 2 + (z - center[2]) ** 2 <= radius**2


def create_synthetic_case(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    shape = (96, 96, 64)
    rng = np.random.default_rng(1337)
    image = rng.normal(90, 14, shape).astype(np.float32)
    brain = sphere(shape, (48, 48, 32), 38)
    image[~brain] = rng.normal(8, 3, (~brain).sum())
    gt = np.zeros(shape, dtype=np.uint8)
    pred = np.zeros(shape, dtype=np.uint8)
    expert2 = np.zeros(shape, dtype=np.uint8)
    anatomy = np.zeros(shape, dtype=np.int16)
    anatomy[brain] = 2
    cortex_shell = brain & ~sphere(shape, (48, 48, 32), 34)
    anatomy[cortex_shell] = 3
    anatomy[sphere(shape, (48, 48, 32), 7)] = 4
    anatomy[(brain) & (np.indices(shape)[2] < 18)] = 16
    anatomy[44:52, 46:50, 30:38] = 251

    # GT lesions: tiny missed, small detected, medium split, confluent/merged.
    gt_lesions = [
        ((35, 41, 30), 2),
        ((58, 49, 34), 3),
        ((46, 62, 28), 5),
        ((66, 58, 40), 6),
        ((70, 59, 40), 5),
    ]
    for center, radius in gt_lesions:
        gt |= sphere(shape, center, radius)
        expert2 |= sphere(shape, (center[0] + 1, center[1], center[2]), max(1, radius))
        image[sphere(shape, center, radius + 1)] += 85

    # Prediction deliberately demonstrates blind spots.
    pred |= sphere(shape, (58, 49, 34), 3)  # detected small
    pred |= sphere(shape, (43, 62, 28), 3)  # split/partial
    pred |= sphere(shape, (49, 62, 28), 3)  # split/partial
    pred |= sphere(shape, (68, 58, 40), 9)  # merged confluent
    pred |= sphere(shape, (24, 26, 30), 3)  # false positive

    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    paths = {
        "image": out_dir / "synthetic_flair.nii.gz",
        "ground_truth": out_dir / "expert_consensus.nii.gz",
        "prediction": out_dir / "vendor_ai_prediction.nii.gz",
        "expert_2": out_dir / "expert_2_boundary_variant.nii.gz",
        "anatomy": out_dir / "synthetic_aparc_aseg_proxy.nii.gz",
    }
    save_nifti(image, affine, paths["image"])
    save_nifti(gt, affine, paths["ground_truth"])
    save_nifti(pred, affine, paths["prediction"])
    save_nifti(expert2, affine, paths["expert_2"])
    save_nifti(anatomy, affine, paths["anatomy"])
    return paths
