from app.core.clinical_evidence import clinical_evidence_summary
from app.core.metrics_hard_cases import classify_hard_case, hard_case_metrics
from app.core.metrics_location_capability import compute_location_capability
from app.core.metrics_reliability import reliability_metrics
from app.core.radiologist_watchlist import generate_radiologist_watchlist


def test_location_capability_and_size_location_rows():
    lesions = [
        {
            "lesion_id": 1,
            "lesion_detected": True,
            "lesion_size_bin": "tiny",
            "lesion_volume_mm3": 8,
            "all_locations": "periventricular",
            "lesion_dice": 0.8,
            "lesion_hd95_mm": 2.0,
        },
        {
            "lesion_id": 2,
            "lesion_detected": False,
            "lesion_size_bin": "small",
            "lesion_volume_mm3": 24,
            "all_locations": "infratentorial",
        },
    ]
    preds = [
        {"pred_lesion_id": 1, "false_positive": False, "pred_volume_mm3": 9, "all_locations": "periventricular"},
        {"pred_lesion_id": 2, "false_positive": True, "pred_volume_mm3": 12, "all_locations": "juxtacortical_or_cortical"},
    ]
    clusters = [{"cluster_id": 1, "cluster_type": "one-to-one", "cluster_all_locations": "periventricular"}]
    out = compute_location_capability(lesion_rows=lesions, prediction_rows=preds, cluster_rows=clusters, case_count=1)
    by_loc = {row["location"]: row for row in out["location_metrics"]}
    assert by_loc["periventricular"]["location_lesion_recall"] == 1.0
    assert by_loc["infratentorial"]["location_fn_lesions_total"] == 1
    assert out["subject_fields"]["high_risk_location_miss_rate"] == 0.5
    assert len(out["size_location_metrics"]) == 20


def test_evidence_proxy_and_watchlist():
    evidence = clinical_evidence_summary({"periventricular", "infratentorial"}, {"periventricular"})
    assert evidence["dis_proxy_false_negative"] is True
    lesions = [
        {
            "lesion_id": 4,
            "lesion_detected": False,
            "lesion_size_bin": "small",
            "lesion_volume_mm3": 20,
            "all_locations": "infratentorial",
            "primary_location": "infratentorial",
        }
    ]
    watchlist = generate_radiologist_watchlist(
        subject_id="subject_004",
        subject_metrics={**evidence, "high_risk_location_miss_rate": 1.0},
        lesion_rows=lesions,
        pred_rows=[],
        cluster_rows=[],
        viewer_manifest={"jump_targets": [{"reason": "missed_lesion", "lesion_id": 4, "centroid_voxel": [1, 2, 3]}]},
    )
    assert watchlist[0]["subject_id"] == "subject_004"
    assert any(item["target_type"] == "infratentorial_missed_lesion" for item in watchlist)


def test_hard_case_and_reliability_rows():
    subject_rows = [
        {
            "case_id": "a",
            "dice_voxel": 0.9,
            "lesion_recall": 1.0,
            "lesion_precision": 0.8,
            "lesion_f1": 0.88,
            "fp_lesions_per_scan": 1,
            "fn_lesions_per_scan": 0,
            "relative_volume_error": 0.1,
            "gt_lesion_count": 1,
            "high_risk_location_miss_rate": 0.0,
            "hard_case_groups": "very_low_lesion_burden|periventricular_present",
        },
        {
            "case_id": "b",
            "dice_voxel": 0.55,
            "lesion_recall": 0.2,
            "lesion_precision": 0.5,
            "lesion_f1": 0.28,
            "fp_lesions_per_scan": 4,
            "fn_lesions_per_scan": 5,
            "relative_volume_error": 0.8,
            "gt_lesion_count": 12,
            "high_risk_location_miss_rate": 0.75,
            "hard_case_groups": "high_lesion_burden|high_fn_case|high_fp_case",
        },
    ]
    assert "very_low_lesion_burden" in classify_hard_case(subject_rows[0], [], [])
    groups = hard_case_metrics(subject_rows)
    assert any(row["hard_case_group"] == "high_fn_case" for row in groups)
    reliability = reliability_metrics(subject_rows)
    assert reliability["rows"]
    assert reliability["summary"]["overall_reliability"] in {"stable", "unstable"}
