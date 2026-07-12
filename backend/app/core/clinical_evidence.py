from __future__ import annotations

from typing import Iterable


RELEVANT_BRAIN_LOCATIONS = {"periventricular", "juxtacortical_or_cortical", "infratentorial"}


def _normalize(locations: Iterable[str] | None) -> set[str]:
    normalized: set[str] = set()
    for item in locations or []:
        value = str(item or "").strip().lower()
        if not value:
            continue
        value = value.replace("juxtacortical/cortical", "juxtacortical_or_cortical")
        value = value.replace("jc/cortical", "juxtacortical_or_cortical")
        value = value.replace("deep_white_matter_or_other", "deep_wm_other")
        if value == "deep_wm_other":
            normalized.add("deep_white_matter_or_other")
        else:
            normalized.add(value)
    return normalized


def clinical_evidence_summary(
    gt_locations: set[str] | None = None,
    pred_locations: set[str] | None = None,
    *,
    anatomy_available: bool = True,
) -> dict:
    """Brain MRI topography evidence preservation proxy for QA reporting."""
    if not anatomy_available:
        return {
            "gt_locations_present": [],
            "pred_locations_present": [],
            "gt_topography_count": None,
            "pred_topography_count": None,
            "preserved_location_count": None,
            "missed_relevant_locations": [],
            "falsely_created_relevant_locations": [],
            "clinical_topography_preservation_ratio": None,
            "clinical_evidence_preservation_ratio": None,
            "topography_overcall_count": None,
            "topography_undercall_count": None,
            "topography_jaccard": None,
            "topography_exact_match": None,
            "gt_dis_like_proxy": None,
            "pred_dis_like_proxy": None,
            "dis_proxy_match": None,
            "dis_proxy_false_negative": None,
            "dis_proxy_false_positive": None,
            "evidence_distortion_type": "ambiguous_no_anatomy",
            "evidence_distortion_severity": "unknown",
            "evidence_distortion_summary": "Anatomy labels were unavailable, so brain MRI topography evidence preservation was not scored.",
            "interpretation": "Brain MRI topography evidence preservation proxy; not a diagnosis and not McDonald criteria.",
        }

    gt = _normalize(gt_locations) & RELEVANT_BRAIN_LOCATIONS
    pred = _normalize(pred_locations) & RELEVANT_BRAIN_LOCATIONS
    preserved = gt & pred
    missed = gt - pred
    created = pred - gt
    union = gt | pred
    ratio = (len(preserved) / len(gt)) if gt else None
    jaccard = (len(preserved) / len(union)) if union else None
    gt_dis = len(gt) >= 2
    pred_dis = len(pred) >= 2
    exact = gt == pred

    if exact:
        distortion = "preserved"
    elif missed and not created:
        distortion = "undercalled"
    elif created and not missed:
        distortion = "overcalled"
    else:
        distortion = "shifted"

    dis_mismatch = gt_dis != pred_dis
    if dis_mismatch or "infratentorial" in missed:
        severity = "high"
    elif missed:
        severity = "medium"
    elif created:
        severity = "low"
    else:
        severity = "none"

    if distortion == "preserved":
        summary = "Predicted brain-location evidence preserved the expert location pattern."
    elif distortion == "undercalled":
        summary = f"Prediction missed expert location evidence in: {', '.join(sorted(missed))}."
    elif distortion == "overcalled":
        summary = f"Prediction created extra location evidence in: {', '.join(sorted(created))}."
    else:
        summary = (
            f"Prediction both missed ({', '.join(sorted(missed))}) and added "
            f"({', '.join(sorted(created))}) brain-location evidence."
        )

    return {
        "gt_locations_present": sorted(gt),
        "pred_locations_present": sorted(pred),
        "gt_topography_count": len(gt),
        "pred_topography_count": len(pred),
        "preserved_location_count": len(preserved),
        "missed_relevant_locations": sorted(missed),
        "falsely_created_relevant_locations": sorted(created),
        "clinical_topography_preservation_ratio": ratio,
        "clinical_evidence_preservation_ratio": ratio,
        "topography_overcall_count": len(created),
        "topography_undercall_count": len(missed),
        "topography_jaccard": jaccard,
        "topography_exact_match": exact,
        "gt_dis_like_proxy": gt_dis,
        "pred_dis_like_proxy": pred_dis,
        "dis_proxy_match": gt_dis == pred_dis,
        "dis_proxy_false_negative": gt_dis and not pred_dis,
        "dis_proxy_false_positive": pred_dis and not gt_dis,
        "evidence_distortion_type": distortion,
        "evidence_distortion_severity": severity,
        "evidence_distortion_summary": summary,
        "interpretation": "Brain MRI topography evidence preservation proxy; not a diagnosis and not McDonald criteria.",
    }
