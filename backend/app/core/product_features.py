from __future__ import annotations

from typing import Any


def failure_fingerprint(subject_metrics: dict, lesion_rows: list[dict], pred_rows: list[dict], cluster_rows: list[dict]) -> dict[str, Any]:
    tags: list[dict] = []
    fp = subject_metrics.get("fp_lesions_per_scan")
    fn = subject_metrics.get("fn_lesions_per_scan")
    high_risk_location_miss = subject_metrics.get("high_risk_location_miss_rate")
    if fp is not None and fp >= 2:
        tags.append({"tag": "FP-heavy", "severity": "medium", "evidence": f"{fp:.2f} predicted-only lesions per scan."})
    if fn is not None and fn >= 2:
        tags.append({"tag": "FN-heavy", "severity": "high", "evidence": f"{fn:.2f} missed lesions per scan."})
    if high_risk_location_miss is not None and high_risk_location_miss > 0.30:
        tags.append({"tag": "Small-location blind", "severity": "high", "evidence": f"High-risk location miss rate is {high_risk_location_miss:.2f}."})
    for metric, tag in [
        ("pv_recall", "Tiny-PV blind"),
        ("jc_recall", "JC/cortical blind"),
        ("it_recall", "Infratentorial blind"),
    ]:
        value = subject_metrics.get(metric)
        if value is not None and value < 0.70:
            tags.append({"tag": tag, "severity": "high" if metric == "it_recall" else "medium", "evidence": f"{metric} is {value:.2f}."})
    if (subject_metrics.get("tiny_lesion_recall") is not None and subject_metrics.get("tiny_lesion_recall") < 0.60) or (
        subject_metrics.get("small_lesion_recall") is not None and subject_metrics.get("small_lesion_recall") < 0.70
    ):
        tags.append({"tag": "Small-lesion blind", "severity": "high", "evidence": "Tiny/small lesion recall is low."})
    if subject_metrics.get("matched_lesion_mean_hd95_mm") is not None and subject_metrics.get("matched_lesion_mean_hd95_mm") > 8:
        tags.append({"tag": "Boundary-sloppy", "severity": "medium", "evidence": "Matched lesion HD95 is high."})
    rel_vol = subject_metrics.get("relative_volume_error")
    signed = subject_metrics.get("signed_volume_error_mm3")
    if rel_vol is not None and rel_vol > 0.30:
        tag = "Volume-underestimating" if (signed or 0) < 0 else "Volume-overestimating"
        tags.append({"tag": tag, "severity": "medium", "evidence": "Relative volume error exceeds 30%."})
    complex_clusters = [row for row in cluster_rows if row.get("cluster_type") and row.get("cluster_type") != "one-to-one"]
    if complex_clusters:
        tags.append({"tag": "Topology-unstable", "severity": "low", "evidence": f"{len(complex_clusters)} split/merge cluster(s)."})
    if subject_metrics.get("dis_proxy_false_negative"):
        tags.append({"tag": "Evidence-undercalling", "severity": "high", "evidence": "Brain topography evidence proxy false negative."})
    if subject_metrics.get("dis_proxy_false_positive"):
        tags.append({"tag": "Evidence-overcalling", "severity": "medium", "evidence": "Brain topography evidence proxy false positive."})
    if subject_metrics.get("dice_voxel") is not None and subject_metrics.get("dice_voxel") >= 0.70 and (
        (subject_metrics.get("lesion_recall") is not None and subject_metrics.get("lesion_recall") < 0.75)
        or (high_risk_location_miss is not None and high_risk_location_miss > 0.30)
    ):
        tags.append({"tag": "Dice-trap", "severity": "high", "evidence": "Dice is acceptable while lesion/location evidence is weak."})
    if subject_metrics.get("anatomy_available") is False or subject_metrics.get("anatomy_status") == "missing":
        tags.append({"tag": "Anatomy-limited", "severity": "medium", "evidence": "Anatomy-aware metrics unavailable."})
    if subject_metrics.get("overall_reliability") == "unstable" or subject_metrics.get("unstable_metric_list"):
        tags.append({"tag": "Case-unstable", "severity": "medium", "evidence": "Case-level reliability spread is unstable."})
    if not tags:
        tags.append({"tag": "Balanced", "severity": "low", "evidence": "Configured failure triggers were not reached."})
    primary = tags[0]
    return {
        "tags": tags,
        "primary": primary,
        "primary_failure_fingerprint": primary["tag"],
        "secondary_failure_fingerprints": [tag["tag"] for tag in tags[1:]],
        "fingerprint_evidence": [tag["evidence"] for tag in tags],
        "fingerprint_summary_sentence": f"Primary failure mode: {primary['tag']}. {primary['evidence']}",
        "generated_from": "voxel, lesion, topology, anatomy, hard-case, and reliability metrics",
    }


def trust_gap_summary(subject_metrics: dict, fingerprint: dict) -> str:
    primary = (fingerprint.get("primary") or {}).get("tag", "Evidence-thin")
    if primary == "Small-lesion blind":
        return "Main trust gap: missed tiny/small lesions."
    if primary == "FP-heavy":
        return "Main trust gap: predicted-only lesion burden."
    if primary in {"Evidence-undercalling", "Evidence-overcalling"}:
        return "Main trust gap: brain-location evidence distortion."
    if primary == "Small-location blind":
        return "Main trust gap: tiny/small misses in MS-relevant brain locations."
    if primary == "Boundary-sloppy":
        return "Main trust gap: matched lesion boundaries."
    if subject_metrics.get("anatomy_status") == "missing":
        return "Main trust gap: anatomy labels were not supplied."
    return "Main trust gap: no single dominant failure mode in configured checks."


def radiologist_watchlist(
    lesion_rows: list[dict],
    pred_rows: list[dict],
    cluster_rows: list[dict],
    viewer_manifest: dict | None,
) -> list[dict]:
    items: list[dict] = []
    jumps = viewer_manifest.get("jump_targets", []) if viewer_manifest else []

    def jump_for(reason: str, lesion_id: Any | None = None) -> dict | None:
        for jump in jumps:
            if jump.get("reason") == reason and (lesion_id is None or jump.get("lesion_id") == lesion_id):
                return jump
        return None

    missed = [row for row in lesion_rows if not row.get("lesion_detected")]
    if missed:
        smallest = sorted(missed, key=lambda r: float(r.get("lesion_volume_mm3") or 0.0))[0]
        largest = sorted(missed, key=lambda r: float(r.get("lesion_volume_mm3") or 0.0), reverse=True)[0]
        items.append(_watch("high", "Smallest missed lesion", smallest, "Small missed lesions are easy to lose in global scores.", jump_for("missed_lesion", smallest.get("lesion_id"))))
        items.append(_watch("high", "Largest missed lesion", largest, "Largest missed expert lesion deserves review.", jump_for("missed_lesion", largest.get("lesion_id"))))
    false_pos = [row for row in pred_rows if row.get("false_positive")]
    if false_pos:
        largest_fp = sorted(false_pos, key=lambda r: float(r.get("pred_volume_mm3") or 0.0), reverse=True)[0]
        items.append(_watch("medium", "Largest false positive", largest_fp, "Predicted-only lesion may inflate burden.", jump_for("false_positive", largest_fp.get("pred_lesion_id"))))
    poor = [
        row
        for row in lesion_rows
        if row.get("lesion_detected") and isinstance(row.get("lesion_dice"), (int, float))
    ]
    if poor:
        worst = sorted(poor, key=lambda r: float(r.get("lesion_dice") or 1.0))[0]
        items.append(_watch("medium", "Worst matched boundary", worst, "Detected lesion has weak overlap/boundary agreement.", jump_for("low_matched_lesion_dice", worst.get("lesion_id"))))
    for location in ["infratentorial", "juxtacortical_or_cortical", "periventricular"]:
        loc_miss = [row for row in missed if location in str(row.get("all_locations", ""))]
        if loc_miss:
            row = sorted(loc_miss, key=lambda r: float(r.get("lesion_volume_mm3") or 0.0), reverse=True)[0]
            items.append(_watch("high", f"{location.replace('_', ' ')} miss", row, "Anatomy-specific miss for targeted review.", jump_for("missed_lesion", row.get("lesion_id"))))
    complex_clusters = [row for row in cluster_rows if row.get("cluster_type") and row.get("cluster_type") != "one-to-one"]
    if complex_clusters:
        row = complex_clusters[0]
        items.append({"severity": "low", "title": "Split/merge cluster", "reason": row.get("cluster_type"), "jump_target": None, "evidence": row})
    return items[:10]


def _watch(severity: str, title: str, row: dict, reason: str, jump: dict | None) -> dict:
    return {"severity": severity, "title": title, "reason": reason, "jump_target": jump, "evidence": row}


def method_badges(report: dict) -> list[str]:
    badges = ["Voxel-tested", "Lesion-tested", "Surface-tested", "Viewer-ready"]
    if report.get("mode") == "batch":
        badges.append("Batch-tested")
    if report.get("expert_variability"):
        badges.append("Expert-variability-aware")
    if (report.get("subject_metrics") or {}).get("anatomy_available"):
        badges.append("Anatomy-aware")
    return badges


def dice_trap(subject_metrics: dict) -> dict | None:
    dice = subject_metrics.get("dice_voxel")
    recall = subject_metrics.get("lesion_recall")
    high_risk = subject_metrics.get("high_risk_miss_rate")
    high_risk_location = subject_metrics.get("high_risk_location_miss_rate")
    relevant_recalls = [subject_metrics.get(k) for k in ["pv_recall", "jc_recall", "it_recall"] if subject_metrics.get(k) is not None]
    if dice is not None and dice >= 0.70 and (
        (recall is not None and recall < 0.75)
        or (high_risk is not None and high_risk > 0.20)
        or (high_risk_location is not None and high_risk_location > 0.30)
        or any(v < 0.70 for v in relevant_recalls)
        or subject_metrics.get("dis_proxy_false_negative")
    ):
        return {
            "active": True,
            "message": "Dice looks acceptable, but lesion-wise evidence disagrees.",
            "evidence": {"dice_voxel": dice, "lesion_recall": recall, "high_risk_miss_rate": high_risk, "high_risk_location_miss_rate": high_risk_location},
        }
    return None


def prediction_only_burden_detector(subject_metrics: dict) -> dict | None:
    fp = subject_metrics.get("fp_lesions_per_scan")
    if fp is not None and fp >= 2:
        return {
            "active": True,
            "message": "False-positive burden is high; review predicted-only regions before accepting lesion count.",
            "evidence": {"fp_lesions_per_scan": fp},
        }
    return None
