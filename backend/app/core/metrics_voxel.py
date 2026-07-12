from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi


def _safe_div(num: float, den: float, empty_value: float | None = None) -> float | None:
    if den == 0:
        return empty_value
    return float(num / den)


def confusion(gt: np.ndarray, pred: np.ndarray) -> dict[str, int]:
    gt = gt.astype(bool)
    pred = pred.astype(bool)
    tp = int(np.logical_and(gt, pred).sum())
    fp = int(np.logical_and(~gt, pred).sum())
    fn = int(np.logical_and(gt, ~pred).sum())
    tn = int(np.logical_and(~gt, ~pred).sum())
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def voxel_metrics(gt: np.ndarray, pred: np.ndarray, spacing: tuple[float, float, float]) -> dict[str, float | None]:
    c = confusion(gt, pred)
    tp, fp, fn, tn = c["tp"], c["fp"], c["fn"], c["tn"]
    dice = _safe_div(2 * tp, 2 * tp + fp + fn, 1.0 if gt.sum() == 0 and pred.sum() == 0 else 0.0)
    iou = _safe_div(tp, tp + fp + fn, 1.0 if gt.sum() == 0 and pred.sum() == 0 else 0.0)
    sensitivity = _safe_div(tp, tp + fn, 1.0 if gt.sum() == 0 else 0.0)
    specificity = _safe_div(tn, tn + fp, None)
    precision = _safe_div(tp, tp + fp, 1.0 if pred.sum() == 0 else 0.0)
    npv = _safe_div(tn, tn + fn, None)
    balanced = None if sensitivity is None or specificity is None else (sensitivity + specificity) / 2
    voxel_volume = float(np.prod(spacing))
    gt_vol = float(gt.sum() * voxel_volume)
    pred_vol = float(pred.sum() * voxel_volume)
    signed = pred_vol - gt_vol
    abs_err = abs(signed)
    rel_err = None if gt_vol == 0 else abs_err / gt_vol
    vol_ratio = None if gt_vol == 0 else pred_vol / gt_vol
    hd95, assd = surface_distances(gt, pred, spacing)
    return {
        **c,
        "dice_voxel": dice,
        "iou_voxel": iou,
        "sensitivity_voxel": sensitivity,
        "specificity_voxel": specificity,
        "ppv_voxel": precision,
        "npv_voxel": npv,
        "balanced_accuracy": balanced,
        "hd95_mm": hd95,
        "assd_mm": assd,
        "gt_volume_mm3": gt_vol,
        "pred_volume_mm3": pred_vol,
        "signed_volume_error_mm3": signed,
        "absolute_volume_error_mm3": abs_err,
        "relative_volume_error": rel_err,
        "volume_ratio": vol_ratio,
    }


def surface(mask: np.ndarray) -> np.ndarray:
    mask = mask.astype(bool)
    if not mask.any():
        return mask
    structure = ndi.generate_binary_structure(3, 1)
    eroded = ndi.binary_erosion(mask, structure=structure, border_value=0)
    return np.logical_and(mask, ~eroded)


def surface_distances(gt: np.ndarray, pred: np.ndarray, spacing: tuple[float, float, float]) -> tuple[float | None, float | None]:
    gt = gt.astype(bool)
    pred = pred.astype(bool)
    if not gt.any() or not pred.any():
        return None, None
    union = gt | pred
    coords = np.argwhere(union)
    if coords.size:
        lo = np.maximum(coords.min(axis=0) - 1, 0)
        hi = np.minimum(coords.max(axis=0) + 2, np.asarray(gt.shape))
        slices = tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))
        gt = gt[slices]
        pred = pred[slices]
    gt_surface = surface(gt)
    pred_surface = surface(pred)
    if not gt_surface.any() or not pred_surface.any():
        return None, None
    dist_to_pred = ndi.distance_transform_edt(~pred_surface, sampling=spacing)
    dist_to_gt = ndi.distance_transform_edt(~gt_surface, sampling=spacing)
    d1 = dist_to_pred[gt_surface]
    d2 = dist_to_gt[pred_surface]
    all_d = np.concatenate([d1, d2])
    if all_d.size == 0:
        return None, None
    return float(np.percentile(all_d, 95)), float(np.mean(all_d))
