from __future__ import annotations

import numpy as np

from app.config import settings
from .metrics_voxel import voxel_metrics
from .lesion_matching import connected_components, component_table, greedy_matches, cluster_graph


def size_bin(volume_mm3: float) -> str:
    for name, (lo, hi) in settings.size_bins_mm3.items():
        if volume_mm3 >= lo and (hi is None or volume_mm3 < hi):
            return name
    return "unknown"


def _mean(values: list[float | None]) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not clean:
        return None
    return float(np.mean(clean))


def _median(values: list[float | None]) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not clean:
        return None
    return float(np.median(clean))


def lesion_metrics(gt: np.ndarray, pred: np.ndarray, spacing: tuple[float, float, float], model_name: str = "AI model") -> dict:
    gt_labels, gt_count = connected_components(gt, settings.connectivity)
    pred_labels, pred_count = connected_components(pred, settings.connectivity)
    matches = greedy_matches(gt_labels, pred_labels)
    matched_pred_ids = set(matches.values())
    gt_components = component_table(gt_labels, spacing, "lesion")
    pred_components = component_table(pred_labels, spacing, "pred_lesion")

    lesion_rows = []
    for comp in gt_components:
        lesion_id = comp["lesion_id"]
        pred_id = matches.get(lesion_id)
        gt_mask = gt_labels == lesion_id
        pred_mask = pred_labels == pred_id if pred_id is not None else np.zeros_like(gt, dtype=bool)
        vm = voxel_metrics(gt_mask, pred_mask, spacing) if pred_id is not None else {}
        lesion_rows.append(
            {
                "model_name": model_name,
                "lesion_id": lesion_id,
                "lesion_volume_voxels": comp["volume_voxels"],
                "lesion_volume_mm3": comp["volume_mm3"],
                "lesion_size_bin": size_bin(comp["volume_mm3"]),
                "lesion_location_label": "unknown",
                "centroid_x": comp["centroid_x"],
                "centroid_y": comp["centroid_y"],
                "centroid_z": comp["centroid_z"],
                "matched_pred_id": pred_id,
                "lesion_detected": bool(pred_id is not None),
                "lesion_dice": vm.get("dice_voxel"),
                "lesion_hd95_mm": vm.get("hd95_mm"),
                "lesion_assd_mm": vm.get("assd_mm"),
                "lesion_abs_vol_error_mm3": vm.get("absolute_volume_error_mm3"),
                "lesion_rel_vol_error": vm.get("relative_volume_error"),
                "high_risk_flag": comp["volume_mm3"] < 50.0,
                "expert_disagreement_flag": False,
            }
        )

    pred_rows = []
    for comp in pred_components:
        pid = comp["pred_lesion_id"]
        matched_gt = next((gid for gid, mid in matches.items() if mid == pid), None)
        pred_rows.append(
            {
                **comp,
                "model_name": model_name,
                "pred_lesion_id": pid,
                "pred_volume_voxels": comp["volume_voxels"],
                "pred_volume_mm3": comp["volume_mm3"],
                "matched_gt_id": matched_gt,
                "false_positive": pid not in matched_pred_ids,
                "location_label_if_available": "unknown",
            }
        )

    recall = 1.0 if gt_count == 0 and pred_count == 0 else (len(matches) / gt_count if gt_count else 0.0)
    precision = 1.0 if gt_count == 0 and pred_count == 0 else (len(matched_pred_ids) / pred_count if pred_count else 0.0)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    fn = gt_count - len(matches)
    fp = pred_count - len(matched_pred_ids)
    clusters = cluster_graph(gt_labels, pred_labels)
    cluster_rows = []
    for c in clusters:
        gt_union = np.isin(gt_labels, c["gt_ids"])
        pred_union = np.isin(pred_labels, c["pred_ids"])
        vm = voxel_metrics(gt_union, pred_union, spacing)
        cluster_rows.append(
            {
                "model_name": model_name,
                "cluster_id": c["cluster_id"],
                "cluster_type": c["cluster_type"],
                "cluster_gt_ids": c["gt_ids"],
                "cluster_pred_ids": c["pred_ids"],
                "cluster_gt_count": len(c["gt_ids"]),
                "cluster_pred_count": len(c["pred_ids"]),
                "cluster_gt_volume_mm3": float(gt_union.sum() * np.prod(spacing)),
                "cluster_pred_volume_mm3": float(pred_union.sum() * np.prod(spacing)),
                "cluster_agg_dice": vm["dice_voxel"],
                "cluster_hd95_mm": vm["hd95_mm"],
                "cluster_assd_mm": vm["assd_mm"],
                "cluster_abs_vol_error_mm3": vm["absolute_volume_error_mm3"],
                "cluster_rel_vol_error": vm["relative_volume_error"],
                "cluster_location_label": "unknown",
                "warning_type": c["cluster_type"],
            }
        )
    size_summary: dict[str, float | int | None] = {"size_bin_config": str(settings.size_bins_mm3)}
    for bin_name in settings.size_bins_mm3:
        gt_bin = [row for row in lesion_rows if row["lesion_size_bin"] == bin_name]
        pred_bin = [
            row
            for row in pred_rows
            if size_bin(float(row.get("pred_volume_mm3") or 0.0)) == bin_name
        ]
        matched_bin = [row for row in gt_bin if row.get("lesion_detected")]
        missed_bin = [row for row in gt_bin if not row.get("lesion_detected")]
        fp_bin = [row for row in pred_bin if row.get("false_positive")]
        size_summary[f"{bin_name}_gt_lesion_count"] = len(gt_bin)
        size_summary[f"{bin_name}_lesion_recall"] = (len(matched_bin) / len(gt_bin)) if gt_bin else None
        size_summary[f"{bin_name}_lesion_precision"] = ((len(pred_bin) - len(fp_bin)) / len(pred_bin)) if pred_bin else None
        size_summary[f"missed_{bin_name}_lesion_count"] = len(missed_bin)
        size_summary[f"fp_{bin_name}_lesion_count"] = len(fp_bin)
        size_summary[f"{bin_name}_matched_mean_dice"] = _mean([row.get("lesion_dice") for row in matched_bin])
        size_summary[f"{bin_name}_matched_mean_abs_volume_error_mm3"] = _mean(
            [row.get("lesion_abs_vol_error_mm3") for row in matched_bin]
        )

    matched_rows = [row for row in lesion_rows if row.get("lesion_detected")]
    boundary_summary = {
        "matched_lesion_mean_dice": _mean([row.get("lesion_dice") for row in matched_rows]),
        "matched_lesion_median_dice": _median([row.get("lesion_dice") for row in matched_rows]),
        "matched_lesion_mean_hd95_mm": _mean([row.get("lesion_hd95_mm") for row in matched_rows]),
        "matched_lesion_median_hd95_mm": _median([row.get("lesion_hd95_mm") for row in matched_rows]),
        "matched_lesion_mean_assd_mm": _mean([row.get("lesion_assd_mm") for row in matched_rows]),
        "matched_lesion_median_assd_mm": _median([row.get("lesion_assd_mm") for row in matched_rows]),
    }
    return {
        "summary": {
            "gt_lesion_count": gt_count,
            "pred_lesion_count": pred_count,
            "lesion_count_error": pred_count - gt_count,
            "lesion_recall": recall,
            "lesion_precision": precision,
            "lesion_f1": f1,
            "fp_lesions_per_scan": fp,
            "fn_lesions_per_scan": fn,
            "matched_lesion_count": len(matches),
            **size_summary,
            **boundary_summary,
        },
        "lesions": lesion_rows,
        "predictions": pred_rows,
        "clusters": cluster_rows,
    }
