from __future__ import annotations

import math
from typing import Any

import numpy as np

from .metrics_lesion import size_bin


LOCATION_ALIASES = {
    "periventricular": "pv",
    "juxtacortical_or_cortical": "jc",
    "infratentorial": "it",
    "deep_white_matter_or_other": "other",
    "corpus_callosum": "cc",
}

LOCATION_ORDER = [
    "periventricular",
    "juxtacortical_or_cortical",
    "infratentorial",
    "deep_white_matter_or_other",
    "corpus_callosum",
]

SIZE_ORDER = ["tiny", "small", "medium", "large"]
RELEVANT_LOCATIONS = {"periventricular", "juxtacortical_or_cortical", "infratentorial"}


def _locs(row: dict) -> set[str]:
    values = str(row.get("all_locations") or row.get("cluster_all_locations") or row.get("primary_location") or "")
    out = set()
    for item in values.replace(",", "|").split("|"):
        loc = item.strip()
        if loc:
            out.add(loc)
    return out


def _num(row: dict, key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)) and value == value:
        return float(value)
    return 0.0


def _values(rows: list[dict], key: str) -> list[float]:
    values = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)) and value == value:
            values.append(float(value))
    return values


def _mean(rows: list[dict], key: str) -> float | None:
    values = _values(rows, key)
    return float(np.mean(values)) if values else None


def _median(rows: list[dict], key: str) -> float | None:
    values = _values(rows, key)
    return float(np.median(values)) if values else None


def _percentile(rows: list[dict], key: str, q: float) -> float | None:
    values = _values(rows, key)
    return float(np.percentile(values, q)) if values else None


def _harmonic(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a + b == 0:
        return None
    return 2 * a * b / (a + b)


def _score_boundary(mean_dice: float | None, mean_hd95: float | None) -> float | None:
    if mean_dice is None or mean_hd95 is None:
        return None
    return 0.5 * mean_dice + 0.5 * math.exp(-mean_hd95 / 10.0)


def _mean_available(values: list[float | None], min_components: int = 1) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v]
    if len(clean) < min_components:
        return None
    return float(np.mean(clean))


def _pred_size(row: dict) -> str:
    return size_bin(float(row.get("pred_volume_mm3") or 0.0))


def compute_location_capability(
    *,
    lesion_rows: list[dict],
    prediction_rows: list[dict],
    cluster_rows: list[dict],
    case_count: int = 1,
) -> dict[str, Any]:
    case_count = max(1, int(case_count or 1))
    all_fp_count = sum(1 for row in prediction_rows if row.get("false_positive"))
    all_fn_count = sum(1 for row in lesion_rows if not row.get("lesion_detected"))
    all_fp_per_scan = all_fp_count / case_count
    all_fn_per_scan = all_fn_count / case_count
    total_pred_volume = sum(_num(row, "pred_volume_mm3") for row in prediction_rows)
    total_gt_volume = sum(_num(row, "lesion_volume_mm3") for row in lesion_rows)
    total_fp_volume = sum(_num(row, "pred_volume_mm3") for row in prediction_rows if row.get("false_positive"))
    total_fn_volume = sum(_num(row, "lesion_volume_mm3") for row in lesion_rows if not row.get("lesion_detected"))

    location_rows = []
    summary_fields: dict[str, Any] = {}
    for location in LOCATION_ORDER:
        gt_rows = [row for row in lesion_rows if location in _locs(row)]
        pred_rows = [row for row in prediction_rows if location in _locs(row)]
        matched_rows = [row for row in gt_rows if row.get("lesion_detected")]
        fp_rows = [row for row in pred_rows if row.get("false_positive")]
        fn_rows = [row for row in gt_rows if not row.get("lesion_detected")]
        gt_count = len(gt_rows)
        pred_count = len(pred_rows)
        matched_count = len(matched_rows)
        fp_count = len(fp_rows)
        fn_count = len(fn_rows)
        recall = matched_count / gt_count if gt_count else None
        precision = (pred_count - fp_count) / pred_count if pred_count else None
        f1 = _harmonic(recall, precision)
        gt_volume = sum(_num(row, "lesion_volume_mm3") for row in gt_rows)
        pred_volume = sum(_num(row, "pred_volume_mm3") for row in pred_rows)
        fp_volume = sum(_num(row, "pred_volume_mm3") for row in fp_rows)
        fn_volume = sum(_num(row, "lesion_volume_mm3") for row in fn_rows)
        signed_error = pred_volume - gt_volume
        abs_error = abs(signed_error)
        rel_error = abs_error / gt_volume if gt_volume else None
        volume_ratio = pred_volume / gt_volume if gt_volume else None
        mean_dice = _mean(matched_rows, "lesion_dice")
        median_dice = _median(matched_rows, "lesion_dice")
        mean_hd95 = _mean(matched_rows, "lesion_hd95_mm")
        boundary_quality = _score_boundary(mean_dice, mean_hd95)
        burden_fidelity = 1.0 - min(rel_error, 1.0) if rel_error is not None else None
        detection_balance = f1
        capability = _mean_available([detection_balance, burden_fidelity, boundary_quality], min_components=2)
        row = {
            "location": location,
            "location_gt_lesion_count": gt_count,
            "location_pred_lesion_count": pred_count,
            "location_matched_lesion_count": matched_count,
            "location_lesion_recall": recall,
            "location_lesion_precision": precision,
            "location_lesion_f1": f1,
            "location_fn_lesions_total": fn_count,
            "location_fp_lesions_total": fp_count,
            "location_fn_lesions_per_scan": fn_count / case_count,
            "location_fp_lesions_per_scan": fp_count / case_count,
            "location_missed_lesion_fraction": fn_count / gt_count if gt_count else None,
            "location_false_discovery_fraction": fp_count / pred_count if pred_count else None,
            "location_matched_lesion_mean_dice": mean_dice,
            "location_matched_lesion_median_dice": median_dice,
            "location_matched_lesion_p25_dice": _percentile(matched_rows, "lesion_dice", 25),
            "location_matched_lesion_p75_dice": _percentile(matched_rows, "lesion_dice", 75),
            "location_matched_lesion_mean_hd95_mm": mean_hd95,
            "location_matched_lesion_median_hd95_mm": _median(matched_rows, "lesion_hd95_mm"),
            "location_matched_lesion_mean_assd_mm": _mean(matched_rows, "lesion_assd_mm"),
            "location_matched_lesion_median_assd_mm": _median(matched_rows, "lesion_assd_mm"),
            "location_gt_volume_mm3": gt_volume,
            "location_pred_volume_mm3": pred_volume,
            "location_signed_volume_error_mm3": signed_error,
            "location_absolute_volume_error_mm3": abs_error,
            "location_relative_volume_error": rel_error,
            "location_volume_ratio": volume_ratio,
            "location_volume_underestimation_flag": bool(volume_ratio is not None and volume_ratio < 0.80),
            "location_volume_overestimation_flag": bool(volume_ratio is not None and volume_ratio > 1.20),
            "location_fp_volume_mm3": fp_volume,
            "location_fp_lesion_count": fp_count,
            "location_fp_small_lesion_count": sum(1 for row in fp_rows if _pred_size(row) in {"tiny", "small"}),
            "location_fp_medium_large_lesion_count": sum(1 for row in fp_rows if _pred_size(row) in {"medium", "large"}),
            "location_pred_only_burden_fraction": fp_volume / total_pred_volume if total_pred_volume else None,
            "location_fp_dominance_score": (fp_count / case_count) / all_fp_per_scan if all_fp_per_scan else None,
            "location_fn_volume_mm3": fn_volume,
            "location_fn_lesion_count": fn_count,
            "location_fn_tiny_lesion_count": sum(1 for row in fn_rows if row.get("lesion_size_bin") == "tiny"),
            "location_fn_small_lesion_count": sum(1 for row in fn_rows if row.get("lesion_size_bin") == "small"),
            "location_fn_medium_large_lesion_count": sum(1 for row in fn_rows if row.get("lesion_size_bin") in {"medium", "large"}),
            "location_missed_burden_fraction": fn_volume / total_fn_volume if total_fn_volume else None,
            "location_fn_dominance_score": (fn_count / case_count) / all_fn_per_scan if all_fn_per_scan else None,
            "location_detection_balance": detection_balance,
            "location_burden_fidelity": burden_fidelity,
            "location_boundary_quality_score": boundary_quality,
            "location_overall_capability_score": capability,
            "method_formula_boundary_quality": "0.5 * mean_dice + 0.5 * exp(-mean_hd95_mm / 10)",
        }
        location_rows.append(row)
        alias = LOCATION_ALIASES.get(location)
        if alias:
            summary_fields[f"{alias}_recall"] = recall
            summary_fields[f"{alias}_precision"] = precision
            summary_fields[f"{alias}_f1"] = f1
            summary_fields[f"{alias}_fp_per_scan"] = row["location_fp_lesions_per_scan"]
            summary_fields[f"{alias}_fn_per_scan"] = row["location_fn_lesions_per_scan"]
            summary_fields[f"{alias}_capability_score"] = capability

    size_location_rows = []
    for location in LOCATION_ORDER:
        for bin_name in SIZE_ORDER:
            gt_rows = [row for row in lesion_rows if location in _locs(row) and row.get("lesion_size_bin") == bin_name]
            pred_rows = [row for row in prediction_rows if location in _locs(row) and _pred_size(row) == bin_name]
            matched_rows = [row for row in gt_rows if row.get("lesion_detected")]
            missed_rows = [row for row in gt_rows if not row.get("lesion_detected")]
            fp_rows = [row for row in pred_rows if row.get("false_positive")]
            recall = len(matched_rows) / len(gt_rows) if gt_rows else None
            precision = (len(pred_rows) - len(fp_rows)) / len(pred_rows) if pred_rows else None
            gt_volume = sum(_num(row, "lesion_volume_mm3") for row in gt_rows)
            pred_volume = sum(_num(row, "pred_volume_mm3") for row in pred_rows)
            abs_err = abs(pred_volume - gt_volume)
            row = {
                "location": location,
                "size_bin": bin_name,
                "gt_lesion_count": len(gt_rows),
                "pred_lesion_count": len(pred_rows),
                "matched_lesion_count": len(matched_rows),
                "lesion_recall": recall,
                "lesion_precision": precision,
                "lesion_f1": _harmonic(recall, precision),
                "missed_count": len(missed_rows),
                "false_positive_count": len(fp_rows),
                "missed_per_scan": len(missed_rows) / case_count,
                "fp_per_scan": len(fp_rows) / case_count,
                "mean_matched_dice": _mean(matched_rows, "lesion_dice"),
                "median_matched_dice": _median(matched_rows, "lesion_dice"),
                "mean_matched_hd95_mm": _mean(matched_rows, "lesion_hd95_mm"),
                "median_matched_hd95_mm": _median(matched_rows, "lesion_hd95_mm"),
                "gt_volume_mm3": gt_volume,
                "pred_volume_mm3": pred_volume,
                "absolute_volume_error_mm3": abs_err,
                "relative_volume_error": abs_err / gt_volume if gt_volume else None,
            }
            size_location_rows.append(row)
            loc_alias = {
                "periventricular": "periventricular",
                "juxtacortical_or_cortical": "juxtacortical_cortical",
                "infratentorial": "infratentorial",
            }.get(location)
            if loc_alias and bin_name in {"tiny", "small"}:
                summary_fields[f"{bin_name}_{loc_alias}_recall"] = recall

    high_risk = [
        row
        for row in lesion_rows
        if row.get("lesion_size_bin") in {"tiny", "small"} and _locs(row) & RELEVANT_LOCATIONS
    ]
    high_risk_missed = [row for row in high_risk if not row.get("lesion_detected")]
    summary_fields.update(
        {
            "high_risk_location_gt_count": len(high_risk),
            "high_risk_location_missed_count": len(high_risk_missed),
            "high_risk_location_miss_rate": (len(high_risk_missed) / len(high_risk)) if high_risk else None,
            "high_risk_location_recall": (1 - len(high_risk_missed) / len(high_risk)) if high_risk else None,
            "high_risk_location_missed_per_scan": len(high_risk_missed) / case_count,
        }
    )

    topology_rows = compute_location_topology(cluster_rows, case_count=case_count)
    return {
        "location_metrics": location_rows,
        "size_location_metrics": size_location_rows,
        "location_topology_metrics": topology_rows,
        "subject_fields": summary_fields,
    }


def compute_location_topology(cluster_rows: list[dict], *, case_count: int = 1) -> list[dict]:
    case_count = max(1, int(case_count or 1))
    rows = []
    for location in LOCATION_ORDER:
        clusters = [row for row in cluster_rows if location in _locs(row)]
        one = [row for row in clusters if row.get("cluster_type") == "one-to-one"]
        split = [row for row in clusters if "split" in str(row.get("cluster_type", "")).lower()]
        merge = [row for row in clusters if "merge" in str(row.get("cluster_type", "")).lower()]
        unmatched_gt = [row for row in clusters if "unmatched gt" in str(row.get("cluster_type", "")).lower()]
        unmatched_pred = [row for row in clusters if "unmatched prediction" in str(row.get("cluster_type", "")).lower()]
        complex_rows = [row for row in clusters if row.get("cluster_type") != "one-to-one"]
        denom = len(clusters)
        rows.append(
            {
                "location": location,
                "location_one_to_one_cluster_count": len(one),
                "location_split_cluster_count": len(split),
                "location_merge_cluster_count": len(merge),
                "location_complex_cluster_count": len(complex_rows),
                "location_unmatched_gt_cluster_count": len(unmatched_gt),
                "location_unmatched_pred_cluster_count": len(unmatched_pred),
                "location_split_rate": len(split) / denom if denom else None,
                "location_merge_rate": len(merge) / denom if denom else None,
                "location_complex_topology_rate": len(complex_rows) / denom if denom else None,
                "location_complex_clusters_per_scan": len(complex_rows) / case_count,
            }
        )
    return rows
