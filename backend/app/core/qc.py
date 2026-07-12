from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from app.config import settings
from .io import Volume


@dataclass
class QCResult:
    status: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    categories: dict[str, list[dict]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {"status": self.status, "warnings": self.warnings, "errors": self.errors}
        for key in ["geometry", "files", "masks", "anatomy", "prediction_sanity", "batch", "viewer", "export"]:
            payload[key] = self.categories.get(key, [])
        return payload


def _entry(status: str, code: str, message: str, detail: dict | None = None) -> dict:
    return {"status": status, "code": code, "message": message, "detail": detail or {}}


def validate_case(image: Volume, ground_truth: Volume, prediction: Volume, expert_2: Volume | None = None) -> QCResult:
    errors: list[str] = []
    warnings: list[str] = []
    categories: dict[str, list[dict]] = {
        "geometry": [],
        "files": [],
        "masks": [],
        "anatomy": [],
        "prediction_sanity": [],
        "batch": [],
        "viewer": [],
        "export": [],
    }

    for label, vol in [("ground truth", ground_truth), ("prediction", prediction), ("expert 2", expert_2)]:
        if vol is None:
            continue
        if image.shape != vol.shape:
            msg = f"{label} mask shape {vol.shape} does not match image shape {image.shape}."
            errors.append(msg)
            categories["geometry"].append(_entry("fail", "shape_mismatch", msg, {"label": label, "image_shape": image.shape, "mask_shape": vol.shape}))
        if not np.allclose(image.affine, vol.affine, atol=1e-3):
            msg = f"{label} affine differs from image affine; metrics may be invalid unless data are aligned."
            warnings.append(msg)
            categories["geometry"].append(_entry("warning", "affine_mismatch", msg, {"label": label}))
        if any(v <= 0 or not np.isfinite(v) for v in vol.spacing):
            msg = f"{label} has invalid voxel spacing {vol.spacing}."
            errors.append(msg)
            categories["geometry"].append(_entry("fail", "invalid_spacing", msg, {"label": label, "spacing": vol.spacing}))
        values = np.unique(vol.data[np.isfinite(vol.data)])
        if values.size and not set(np.round(values).astype(int)).issubset({0, 1}):
            msg = f"{label} contains labels outside 0/1; nonzero voxels will be treated as lesion."
            warnings.append(msg)
            categories["masks"].append(_entry("warning", "nonbinary_mask", msg, {"label": label, "unique_value_count": int(values.size)}))
        if not np.isfinite(vol.data).all():
            msg = f"{label} mask contains NaN or infinite values."
            errors.append(msg)
            categories["masks"].append(_entry("fail", "nonfinite_mask", msg, {"label": label}))

    if not np.isfinite(image.data).all():
        msg = "MRI image contains NaN or infinite values."
        errors.append(msg)
        categories["files"].append(_entry("fail", "nonfinite_image", msg))
    if any(v <= 0 or not np.isfinite(v) for v in image.spacing):
        msg = f"MRI has invalid voxel spacing {image.spacing}."
        errors.append(msg)
        categories["geometry"].append(_entry("fail", "invalid_image_spacing", msg, {"spacing": image.spacing}))
    spacing = np.asarray(image.spacing, dtype=float)
    if spacing.max() / max(spacing.min(), 1e-6) >= settings.anisotropy_warning_ratio:
        msg = f"Voxel spacing is anisotropic ({tuple(float(v) for v in spacing)})."
        warnings.append(msg)
        categories["geometry"].append(_entry("warning", "anisotropy_warning", msg, {"spacing": image.spacing}))
    if spacing.max() >= settings.thick_slice_warning_mm:
        msg = f"Thick-slice geometry detected ({spacing.max():.2f} mm maximum spacing)."
        warnings.append(msg)
        categories["geometry"].append(_entry("warning", "thick_slice_warning", msg, {"spacing": image.spacing}))
    if np.count_nonzero(ground_truth.data > 0) == 0:
        msg = "Ground-truth mask is empty; this is treated as a no-lesion scan."
        warnings.append(msg)
        categories["masks"].append(_entry("warning", "empty_ground_truth", msg))
    if np.count_nonzero(prediction.data > 0) == 0:
        msg = "AI prediction mask is empty."
        warnings.append(msg)
        categories["masks"].append(_entry("warning", "empty_prediction", msg))
    if np.count_nonzero(ground_truth.data > 0) == 0 and np.count_nonzero(prediction.data > 0) == 0:
        categories["masks"].append(_entry("warning", "both_masks_empty", "Ground truth and prediction are both empty."))
    pred_fraction = float(np.count_nonzero(prediction.data > 0) / prediction.data.size)
    if pred_fraction > 0.10:
        msg = f"Prediction lesion volume is unusually large ({pred_fraction:.1%} of voxels)."
        warnings.append(msg)
        categories["prediction_sanity"].append(_entry("warning", "large_prediction_fraction", msg, {"fraction": pred_fraction}))
    gt_fraction = float(np.count_nonzero(ground_truth.data > 0) / ground_truth.data.size)
    if gt_fraction > 0.10:
        msg = f"Ground-truth lesion volume is unusually large ({gt_fraction:.1%} of voxels)."
        warnings.append(msg)
        categories["masks"].append(_entry("warning", "large_gt_fraction", msg, {"fraction": gt_fraction}))
    if image.shape == ground_truth.shape and np.array_equal(ground_truth.data > 0, prediction.data > 0):
        msg = "Prediction is identical to ground truth; verify this is not an accidental duplicate upload."
        warnings.append(msg)
        categories["prediction_sanity"].append(_entry("warning", "prediction_identical_to_gt", msg))

    status = "failed" if errors else ("warnings" if warnings else "passed")
    return QCResult(status=status, warnings=warnings, errors=errors, categories=categories)
