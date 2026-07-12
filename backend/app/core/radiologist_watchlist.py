from __future__ import annotations

from typing import Any


def _locations(row: dict) -> set[str]:
    values = str(row.get("all_locations") or row.get("primary_location") or row.get("cluster_all_locations") or "")
    return {item.strip() for item in values.replace(",", "|").split("|") if item.strip()}


def _jump(viewer_manifest: dict | None, reason: str, lesion_id: int | None = None) -> dict | None:
    for target in (viewer_manifest or {}).get("jump_targets", []) or []:
        if target.get("reason") == reason and (lesion_id is None or target.get("lesion_id") == lesion_id):
            return target
    return None


def _item(
    *,
    severity: str,
    subject_id: str,
    target_type: str,
    reason: str,
    recommended_action: str,
    row: dict,
    jump_target: dict | None = None,
    metric_trigger: str = "",
) -> dict[str, Any]:
    lesion_id = row.get("lesion_id")
    pred_id = row.get("pred_lesion_id")
    cluster_id = row.get("cluster_id")
    volume = row.get("lesion_volume_mm3", row.get("pred_volume_mm3", row.get("cluster_gt_volume_mm3")))
    return {
        "priority_rank": 0,
        "severity": severity,
        "subject_id": subject_id,
        "target_type": target_type,
        "lesion_id": lesion_id,
        "pred_lesion_id": pred_id,
        "cluster_id": cluster_id,
        "primary_location": row.get("primary_location") or row.get("location_label_if_available") or row.get("cluster_primary_location") or "unknown",
        "size_bin": row.get("lesion_size_bin") or "unknown",
        "volume_mm3": volume,
        "metric_trigger": metric_trigger or target_type,
        "reason": reason,
        "viewer_jump_target": jump_target,
        "recommended_action": recommended_action,
        "title": reason,
    }


def generate_radiologist_watchlist(
    *,
    subject_id: str,
    subject_metrics: dict,
    lesion_rows: list[dict],
    pred_rows: list[dict],
    cluster_rows: list[dict],
    viewer_manifest: dict | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    missed = [row for row in lesion_rows if not row.get("lesion_detected")]
    false_pos = [row for row in pred_rows if row.get("false_positive")]
    matched = [row for row in lesion_rows if row.get("lesion_detected")]

    if subject_metrics.get("dis_proxy_false_negative") or subject_metrics.get("evidence_distortion_type") in {"undercalled", "shifted"}:
        items.append(
            _item(
                severity="high",
                subject_id=subject_id,
                target_type="dis_proxy_mismatch_case",
                reason=subject_metrics.get("evidence_distortion_summary") or "Brain MRI topography evidence was undercalled.",
                recommended_action="Review missed lesions in relevant locations before accepting the model output.",
                row={"primary_location": "|".join(subject_metrics.get("missed_relevant_locations") or [])},
                metric_trigger="brain_mri_topography_evidence_proxy",
            )
        )

    for location, target_type, title in [
        ("infratentorial", "infratentorial_missed_lesion", "Infratentorial missed lesion"),
        ("periventricular", "tiny_pv_missed_lesion", "Tiny/small periventricular missed lesion"),
        ("juxtacortical_or_cortical", "tiny_jc_missed_lesion", "Tiny/small juxtacortical/cortical missed lesion"),
    ]:
        candidates = [row for row in missed if location in _locations(row)]
        if location != "infratentorial":
            candidates = [row for row in candidates if row.get("lesion_size_bin") in {"tiny", "small"}]
        if candidates:
            row = sorted(candidates, key=lambda r: float(r.get("lesion_volume_mm3") or 0.0), reverse=True)[0]
            items.append(
                _item(
                    severity="high",
                    subject_id=subject_id,
                    target_type=target_type,
                    reason=title,
                    recommended_action="Open the viewer at this lesion and compare GT/prediction overlays.",
                    row=row,
                    jump_target=_jump(viewer_manifest, "missed_lesion", row.get("lesion_id")),
                    metric_trigger=f"{location}_miss",
                )
            )

    high_risk = [row for row in missed if row.get("lesion_size_bin") in {"tiny", "small"} and _locations(row) & {"periventricular", "juxtacortical_or_cortical", "infratentorial"}]
    if high_risk:
        row = sorted(high_risk, key=lambda r: float(r.get("lesion_volume_mm3") or 0.0), reverse=True)[0]
        items.append(
            _item(
                severity="high",
                subject_id=subject_id,
                target_type="missed_high_risk_lesion",
                reason="Missed tiny/small lesion in an MS-relevant brain location",
                recommended_action="Prioritize this for radiologist review; it affects location-aware evidence.",
                row=row,
                jump_target=_jump(viewer_manifest, "missed_lesion", row.get("lesion_id")),
                metric_trigger="high_risk_location_miss",
            )
        )

    if missed:
        row = sorted(missed, key=lambda r: float(r.get("lesion_volume_mm3") or 0.0), reverse=True)[0]
        items.append(
            _item(
                severity="medium",
                subject_id=subject_id,
                target_type="largest_missed_lesion",
                reason="Largest missed expert lesion",
                recommended_action="Confirm whether this is a true model miss or a label/registration issue.",
                row=row,
                jump_target=_jump(viewer_manifest, "missed_lesion", row.get("lesion_id")),
            )
        )

    if false_pos:
        relevant_fp = [row for row in false_pos if _locations(row) & {"periventricular", "juxtacortical_or_cortical", "infratentorial"}]
        row = sorted(relevant_fp or false_pos, key=lambda r: float(r.get("pred_volume_mm3") or 0.0), reverse=True)[0]
        items.append(
            _item(
                severity="medium",
                subject_id=subject_id,
                target_type="false_positive_in_relevant_location" if relevant_fp else "largest_false_positive",
                reason="Largest predicted-only lesion",
                recommended_action="Review prediction-only overlay; this can inflate lesion count and location evidence.",
                row=row,
                jump_target=_jump(viewer_manifest, "false_positive", row.get("pred_lesion_id")),
                metric_trigger="predicted_only_burden",
            )
        )

    poor_boundary = [row for row in matched if isinstance(row.get("lesion_hd95_mm"), (int, float))]
    if poor_boundary:
        row = sorted(poor_boundary, key=lambda r: float(r.get("lesion_hd95_mm") or 0.0), reverse=True)[0]
        items.append(
            _item(
                severity="medium",
                subject_id=subject_id,
                target_type="worst_boundary_match",
                reason="Worst matched lesion boundary",
                recommended_action="Review boundary agreement; detected lesions may still have poor contour quality.",
                row=row,
                jump_target=_jump(viewer_manifest, "low_matched_lesion_dice", row.get("lesion_id")),
                metric_trigger="matched_lesion_hd95",
            )
        )

    complex_clusters = [row for row in cluster_rows if row.get("cluster_type") and row.get("cluster_type") != "one-to-one"]
    if complex_clusters:
        row = sorted(complex_clusters, key=lambda r: float(r.get("cluster_abs_vol_error_mm3") or 0.0), reverse=True)[0]
        items.append(
            _item(
                severity="medium",
                subject_id=subject_id,
                target_type="split_merge_cluster",
                reason=f"Split/merge topology cluster: {row.get('cluster_type')}",
                recommended_action="Check whether lesion count is distorted by fragmented or merged predictions.",
                row=row,
                metric_trigger="topology_cluster",
            )
        )

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "review": 4}
    typed_order = {
        "dis_proxy_mismatch_case": 0,
        "infratentorial_missed_lesion": 1,
        "tiny_pv_missed_lesion": 2,
        "tiny_jc_missed_lesion": 3,
        "missed_high_risk_lesion": 4,
        "largest_missed_lesion": 5,
        "false_positive_in_relevant_location": 6,
        "largest_false_positive": 7,
        "split_merge_cluster": 8,
        "worst_boundary_match": 9,
    }
    unique: list[dict[str, Any]] = []
    seen = set()
    for item in sorted(items, key=lambda x: (severity_order.get(x["severity"], 9), typed_order.get(x["target_type"], 99))):
        key = (item.get("subject_id"), item.get("target_type"), item.get("lesion_id"), item.get("pred_lesion_id"), item.get("cluster_id"))
        if key in seen:
            continue
        seen.add(key)
        item["priority_rank"] = len(unique) + 1
        unique.append(item)
    return unique[:10]
