from __future__ import annotations

from typing import Any

import numpy as np


KEY_METRICS = [
    "dice_voxel",
    "lesion_recall",
    "lesion_precision",
    "lesion_f1",
    "fp_lesions_per_scan",
    "fn_lesions_per_scan",
    "relative_volume_error",
    "high_risk_location_miss_rate",
    "clinical_topography_preservation_ratio",
    "pv_recall",
    "jc_recall",
    "it_recall",
]

LOWER_IS_BETTER = {"fp_lesions_per_scan", "fn_lesions_per_scan", "relative_volume_error", "high_risk_location_miss_rate"}


def _values(rows: list[dict], key: str) -> list[tuple[str, float]]:
    out = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)) and value == value:
            out.append((str(row.get("case_id") or row.get("subject_id") or "case"), float(value)))
    return out


def _band(key: str, mean: float, std: float, minimum: float, maximum: float) -> str:
    if key in LOWER_IS_BETTER:
        if maximum <= 0.20 or (key.endswith("per_scan") and maximum <= 1.0):
            return "stable"
        if std <= max(0.10, abs(mean) * 0.35):
            return "variable"
        return "unstable"
    if minimum >= 0.75 and std <= 0.10:
        return "stable"
    if minimum >= 0.50 and std <= 0.20:
        return "variable"
    return "unstable"


def reliability_metrics(rows: list[dict], keys: list[str] | None = None) -> dict[str, Any]:
    keys = keys or KEY_METRICS
    metric_rows = []
    unstable = []
    for key in keys:
        pairs = _values(rows, key)
        if not pairs:
            continue
        values = np.asarray([v for _, v in pairs], dtype=float)
        lower = key in LOWER_IS_BETTER
        best_pair = min(pairs, key=lambda x: x[1]) if lower else max(pairs, key=lambda x: x[1])
        worst_pair = max(pairs, key=lambda x: x[1]) if lower else min(pairs, key=lambda x: x[1])
        mean = float(np.mean(values))
        std = float(np.std(values, ddof=0))
        band = _band(key, mean, std, float(np.min(values)), float(np.max(values)))
        if band == "unstable":
            unstable.append(key)
        metric_rows.append(
            {
                "metric": key,
                "mean": mean,
                "median": float(np.median(values)),
                "std": std,
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "p25": float(np.percentile(values, 25)),
                "p75": float(np.percentile(values, 75)),
                "worst_case_id": worst_pair[0],
                "worst_case_value": worst_pair[1],
                "best_case_id": best_pair[0],
                "best_case_value": best_pair[1],
                "reliability_band": band,
            }
        )
    worst = next((row for row in metric_rows if row["metric"] == "lesion_recall"), metric_rows[0] if metric_rows else None)
    best = next((row for row in metric_rows if row["metric"] == "lesion_f1"), metric_rows[0] if metric_rows else None)
    return {
        "rows": metric_rows,
        "summary": {
            "unstable_metric_list": unstable,
            "worst_case_summary": (
                f"Worst lesion-recall case: {worst['worst_case_id']} ({worst['worst_case_value']:.3f})."
                if worst else "No reliability metrics available."
            ),
            "best_case_summary": (
                f"Best lesion-F1 case: {best['best_case_id']} ({best['best_case_value']:.3f})."
                if best else "No reliability metrics available."
            ),
            "overall_reliability": "unstable" if unstable else "stable",
        },
    }
