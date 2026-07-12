from __future__ import annotations

from typing import Any

import numpy as np


def classify_hard_case(subject_metrics: dict, lesion_rows: list[dict], cluster_rows: list[dict]) -> list[str]:
    gt_count = int(subject_metrics.get("gt_lesion_count") or 0)
    gt_volume = float(subject_metrics.get("gt_volume_mm3") or 0.0)
    tiny = int(subject_metrics.get("tiny_gt_lesion_count") or 0)
    small = int(subject_metrics.get("small_gt_lesion_count") or 0)
    large = int(subject_metrics.get("large_gt_lesion_count") or 0)
    groups: set[str] = set()
    if gt_count == 0:
        groups.add("no_lesion_scan")
    if gt_count <= 3 or gt_volume < 500:
        groups.add("very_low_lesion_burden")
    if gt_count <= 10 or gt_volume < 2000:
        groups.add("low_lesion_burden")
    if gt_count >= 30 or gt_volume > 10000:
        groups.add("high_lesion_burden")
    if tiny >= 5:
        groups.add("many_tiny_lesions")
    if tiny + small >= 10:
        groups.add("many_small_lesions")
    if gt_count and tiny + small == gt_count:
        groups.add("only_small_lesions")
    if large or any(float(row.get("cluster_gt_volume_mm3") or 0.0) > 1000 and row.get("cluster_type") != "one-to-one" for row in cluster_rows):
        groups.add("large_confluent_lesions")
    topo = subject_metrics.get("gt_topography_count")
    if topo == 1 or (topo == 2 and gt_count <= 5):
        groups.add("near_dis_like_threshold")
    if topo == 1:
        groups.add("single_relevant_location_only")
    if subject_metrics.get("infratentorial_recall") is not None or subject_metrics.get("it_recall") is not None:
        groups.add("infratentorial_present")
    if subject_metrics.get("juxtacortical_cortical_recall") is not None or subject_metrics.get("jc_recall") is not None:
        groups.add("juxtacortical_cortical_present")
    if subject_metrics.get("periventricular_recall") is not None or subject_metrics.get("pv_recall") is not None:
        groups.add("periventricular_present")
    if subject_metrics.get("anatomy_resampled"):
        groups.add("anatomy_resampled")
    spacing_text = str(subject_metrics.get("difficulty_image_spacing") or "")
    spacing = []
    for item in spacing_text.split("|"):
        try:
            spacing.append(float(item))
        except ValueError:
            pass
    if spacing and max(spacing) / max(min(spacing), 1e-6) > 1.5:
        groups.add("anisotropic_spacing")
    if float(subject_metrics.get("fp_lesions_per_scan") or 0.0) >= 5:
        groups.add("high_fp_case")
    if float(subject_metrics.get("fn_lesions_per_scan") or 0.0) >= 3:
        groups.add("high_fn_case")
    return sorted(groups)


def _mean(rows: list[dict], key: str) -> float | None:
    values = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)) and value == value:
            values.append(float(value))
    return float(np.mean(values)) if values else None


def _rate(rows: list[dict], key: str, expected: bool = True) -> float | None:
    values = [row.get(key) for row in rows if row.get(key) is not None]
    if not values:
        return None
    return sum(1 for value in values if bool(value) is expected) / len(values)


def hard_case_metrics(subject_rows: list[dict]) -> list[dict[str, Any]]:
    by_group: dict[str, list[dict]] = {}
    for row in subject_rows:
        groups = str(row.get("hard_case_groups") or "").split("|")
        for group in [g for g in groups if g]:
            by_group.setdefault(group, []).append(row)
    out = []
    for group, rows in sorted(by_group.items()):
        out.append(
            {
                "hard_case_group": group,
                "subject_count": len(rows),
                "mean_dice_voxel": _mean(rows, "dice_voxel"),
                "mean_lesion_recall": _mean(rows, "lesion_recall"),
                "mean_lesion_precision": _mean(rows, "lesion_precision"),
                "mean_lesion_f1": _mean(rows, "lesion_f1"),
                "mean_fp_lesions_per_scan": _mean(rows, "fp_lesions_per_scan"),
                "mean_fn_lesions_per_scan": _mean(rows, "fn_lesions_per_scan"),
                "mean_relative_volume_error": _mean(rows, "relative_volume_error"),
                "mean_high_risk_location_miss_rate": _mean(rows, "high_risk_location_miss_rate"),
                "mean_clinical_topography_preservation_ratio": _mean(rows, "clinical_topography_preservation_ratio"),
                "dis_proxy_match_rate": _rate(rows, "dis_proxy_match", True),
                "dis_proxy_false_negative_rate": _rate(rows, "dis_proxy_false_negative", True),
                "dis_proxy_false_positive_rate": _rate(rows, "dis_proxy_false_positive", True),
            }
        )
    return out


def hard_case_chips(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {}

    def valid(key: str):
        return [row for row in rows if row.get(key) is not None]

    worst = min(valid("mean_lesion_f1") or rows, key=lambda r: r.get("mean_lesion_f1") if r.get("mean_lesion_f1") is not None else 99)
    best = max(valid("mean_lesion_f1") or rows, key=lambda r: r.get("mean_lesion_f1") if r.get("mean_lesion_f1") is not None else -1)
    highest_fp = max(rows, key=lambda r: r.get("mean_fp_lesions_per_scan") or 0)
    highest_miss = max(rows, key=lambda r: r.get("mean_high_risk_location_miss_rate") or 0)
    unstable = max(rows, key=lambda r: (r.get("mean_fp_lesions_per_scan") or 0) + (r.get("mean_fn_lesions_per_scan") or 0))
    return {
        "worst_group": worst.get("hard_case_group"),
        "best_group": best.get("hard_case_group"),
        "most_unstable_group": unstable.get("hard_case_group"),
        "highest_fp_group": highest_fp.get("hard_case_group"),
        "highest_missed_location_group": highest_miss.get("hard_case_group"),
    }
