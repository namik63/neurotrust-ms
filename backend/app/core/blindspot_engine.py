from __future__ import annotations

from app.config import settings


def warning_level(value: str) -> str:
    return value


def generate_blindspots(subject_metrics: dict, lesion_rows: list[dict], cluster_rows: list[dict], qc: dict) -> list[dict]:
    blindspots: list[dict] = []

    if qc.get("status") == "failed":
        blindspots.append(
            {
                "severity": "critical",
                "title": "Data integrity failure blocks metric output",
                "metric_evidence": "; ".join(qc.get("errors", [])),
                "clinical_meaning": "Metric output is blocked until image/mask mismatch is corrected.",
                "manual_review_action": "Fix data alignment or file integrity before interpretation.",
            }
        )

    gt_count = subject_metrics.get("gt_lesion_count")
    pred_count = subject_metrics.get("pred_lesion_count")
    if gt_count == 0 and pred_count == 0:
        blindspots.append(
            {
                "severity": "low",
                "title": "No-lesion validation case",
                "metric_evidence": "GT lesion count and prediction lesion count are both zero.",
                "clinical_meaning": "This case supports false-positive control but does not stress lesion detection.",
                "manual_review_action": "Use with lesion-positive cases before interpreting detection strength.",
            }
        )
    elif isinstance(gt_count, (int, float)) and gt_count < 3:
        blindspots.append(
            {
                "severity": "low",
                "title": "Low lesion-count evidence",
                "metric_evidence": f"GT lesion count is {gt_count}.",
                "clinical_meaning": "Single/few-lesion cases can make recall and Dice unstable.",
                "manual_review_action": "Review the case-level watchlist and add more lesion-positive validation cases when possible.",
            }
        )

    recall = subject_metrics.get("lesion_recall")
    if recall is not None and recall < settings.poor_lesion_recall:
        blindspots.append(
            {
                "severity": "high",
                "title": "Low lesion-wise recall",
                "metric_evidence": f"Lesion recall {recall:.2f}; threshold {settings.poor_lesion_recall:.2f}.",
                "clinical_meaning": "The model missed a concerning fraction of expert-labeled lesions.",
                "manual_review_action": "Review the full scan for missed lesions before trusting lesion count.",
            }
        )
    elif recall is not None and recall < settings.concerning_lesion_recall:
        blindspots.append(
            {
                "severity": "medium",
                "title": "Borderline lesion-wise recall",
                "metric_evidence": f"Lesion recall {recall:.2f}.",
                "clinical_meaning": "The model may be usable with targeted manual review.",
                "manual_review_action": "Review small and low-contrast lesion regions.",
            }
        )

    fpp = subject_metrics.get("fp_lesions_per_scan")
    if fpp is not None and fpp >= 2:
        blindspots.append(
            {
                "severity": "medium",
                "title": "False-positive lesion burden",
                "metric_evidence": f"False-positive lesions per scan: {fpp}.",
                "clinical_meaning": "AI-derived lesion count may overstate lesion burden.",
                "manual_review_action": "Inspect prediction-only amber regions before accepting count.",
            }
        )

    rel_vol = subject_metrics.get("relative_volume_error")
    if rel_vol is not None and rel_vol > settings.high_relative_volume_error:
        blindspots.append(
            {
                "severity": "medium",
                "title": "High lesion-volume error",
                "metric_evidence": f"Relative volume error {rel_vol:.1%}; threshold {settings.high_relative_volume_error:.0%}.",
                "clinical_meaning": "Volume-based monitoring may be unreliable for this validation set.",
                "manual_review_action": "Use manual/reader-verified volume if treatment monitoring depends on burden change.",
            }
        )

    high_risk_location_miss = subject_metrics.get("high_risk_location_miss_rate")
    if high_risk_location_miss is not None and high_risk_location_miss > 0.30:
        blindspots.append(
            {
                "severity": "high",
                "title": "High-risk location miss rate elevated",
                "metric_evidence": f"High-risk location miss rate {high_risk_location_miss:.2f}.",
                "clinical_meaning": "Tiny/small lesions in MS-relevant brain locations are being missed.",
                "manual_review_action": "Review periventricular, juxtacortical/cortical, and infratentorial missed-lesion targets.",
            }
        )

    missed_small = [r for r in lesion_rows if (not r.get("lesion_detected")) and r.get("lesion_size_bin") in {"tiny", "small"}]
    if missed_small:
        blindspots.append(
            {
                "severity": "high",
                "title": "Small-lesion miss risk",
                "metric_evidence": f"{len(missed_small)} tiny/small GT lesions were missed.",
                "clinical_meaning": "Small lesion misses can affect lesion count and brain-location evidence summaries.",
                "manual_review_action": "Manually review small periventricular and juxtacortical/cortical candidates.",
            }
        )

    complex_clusters = [c for c in cluster_rows if c.get("cluster_type") not in {"one-to-one"}]
    if complex_clusters:
        blindspots.append(
            {
                "severity": "low",
                "title": "Split/merge topology behavior",
                "metric_evidence": f"{len(complex_clusters)} non-one-to-one lesion clusters detected.",
                "clinical_meaning": "Confluent lesions or fragmented predictions can distort lesion count even when volume is acceptable.",
                "manual_review_action": "Review cluster overlays before using AI lesion count.",
            }
        )

    for metric, title in [
        ("pv_recall", "Periventricular miss risk"),
        ("jc_recall", "Juxtacortical/cortical miss risk"),
        ("it_recall", "Infratentorial miss risk"),
    ]:
        value = subject_metrics.get(metric)
        if value is not None and value < 0.70:
            blindspots.append(
                {
                    "severity": "high" if metric == "it_recall" else "medium",
                    "title": title,
                    "metric_evidence": f"{metric} = {value:.2f}.",
                    "clinical_meaning": "Performance is weaker in a clinically relevant brain location.",
                    "manual_review_action": "Inspect the Anatomy Capability and Watchlist tabs for case-level targets.",
                }
            )

    if subject_metrics.get("dis_proxy_false_negative"):
        blindspots.append(
            {
                "severity": "high",
                "title": "Brain topography evidence undercalled",
                "metric_evidence": subject_metrics.get("evidence_distortion_summary", "Relevant brain-location evidence was missed."),
                "clinical_meaning": "The predicted mask does not preserve the expert brain-location evidence pattern.",
                "manual_review_action": "Review missed relevant-location lesions before accepting this model output.",
            }
        )

    if subject_metrics.get("dis_proxy_false_positive"):
        blindspots.append(
            {
                "severity": "medium",
                "title": "Brain topography evidence overcalled",
                "metric_evidence": subject_metrics.get("evidence_distortion_summary", "Extra relevant brain-location evidence was created."),
                "clinical_meaning": "Predicted-only lesions may create location evidence not present in the expert mask.",
                "manual_review_action": "Review false-positive lesions in relevant locations.",
            }
        )

    dice = subject_metrics.get("dice_voxel")
    recall = subject_metrics.get("lesion_recall")
    dis_fn = subject_metrics.get("dis_proxy_false_negative_rate", 0) or int(bool(subject_metrics.get("dis_proxy_false_negative")))
    relevant_recalls = [subject_metrics.get(k) for k in ["pv_recall", "jc_recall", "it_recall"] if subject_metrics.get(k) is not None]
    if dice is not None and dice >= 0.70 and (
        (recall is not None and recall < 0.75)
        or (high_risk_location_miss is not None and high_risk_location_miss > 0.30)
        or any(v < 0.70 for v in relevant_recalls)
        or dis_fn
    ):
        blindspots.append(
            {
                "severity": "high",
                "title": "Dice trap: overlap looks acceptable, lesion evidence does not",
                "metric_evidence": f"Dice {dice:.2f} with lesion/location evidence weakness.",
                "clinical_meaning": "Global Dice may understate missed lesions or location-level evidence loss.",
                "manual_review_action": "Inspect missed lesion and topography watchlist before accepting this output.",
            }
        )

    if not blindspots:
        blindspots.append(
            {
                "severity": "low",
                "title": "No major configured blind spot detected",
                "metric_evidence": "Configured thresholds were not triggered.",
                "clinical_meaning": "This validation sample did not expose a major configured blind spot.",
                "manual_review_action": "Use the watchlist and reliability tabs for targeted review.",
            }
        )
    return blindspots


def deployment_recommendation(subject_metrics: dict, blindspots: list[dict], case_count: int = 1) -> dict:
    severities = {b["severity"] for b in blindspots}
    if "critical" in severities:
        status = "fail"
    elif "high" in severities:
        status = "restricted use"
    elif "medium" in severities:
        status = "conditional pass"
    else:
        status = "pass"
    if case_count < settings.minimum_cases_for_deployment_call and status == "pass":
        status = "provisional pass"
    confidence = min(0.95, max(0.35, 0.35 + 0.08 * max(case_count, 1)))
    interval_width = max(0.05, 0.35 / max(case_count, 1) ** 0.5)
    reasons = [b["title"] for b in blindspots[:3]]
    return {
        "status": status,
        "confidence_level": round(confidence, 3),
        "confidence_interval": [
            round(max(0.0, confidence - interval_width), 3),
            round(min(1.0, confidence + interval_width), 3),
        ],
        "confidence_basis": f"Confidence reflects {case_count} uploaded validation case(s) and configured blindspot severity.",
        "reasons": reasons,
    }
