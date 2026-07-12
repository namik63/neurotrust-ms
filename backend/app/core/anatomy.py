from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from nibabel.processing import resample_from_to
from scipy import ndimage as ndi

from app.config import settings
from .clinical_evidence import clinical_evidence_summary
from .io import Volume
from .lesion_matching import connected_components
from .metrics_location_capability import compute_location_capability
from .metrics_voxel import voxel_metrics


LOCATION_CATEGORIES = [
    "periventricular",
    "juxtacortical_or_cortical",
    "infratentorial",
    "corpus_callosum",
    "deep_white_matter_or_other",
    "unknown",
]


def _config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "anatomy_label_mappings.json"


def load_label_mapping() -> dict[str, Any]:
    return json.loads(_config_path().read_text(encoding="utf-8"))


def parse_freesurfer_lut(path: Path | None) -> dict[int, str]:
    if path is None or not path.is_file():
        return {}
    labels: dict[int, str] = {}
    for line in path.read_text(errors="ignore", encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        try:
            labels[int(parts[0])] = parts[1]
        except ValueError:
            continue
    return labels


def _label_ids_for_group(labels: np.ndarray, group: dict[str, Any], lut: dict[int, str]) -> set[int]:
    present = set(int(v) for v in np.unique(labels) if int(v) != 0)
    selected = set(int(v) for v in group.get("label_ids", []) if int(v) in present)
    for lo, hi in group.get("label_id_ranges", []):
        selected.update(v for v in present if int(lo) <= v <= int(hi))
    patterns = [re.compile(str(pattern), re.I) for pattern in group.get("name_patterns", [])]
    for label_id, name in lut.items():
        if label_id in present and any(pattern.search(name) for pattern in patterns):
            selected.add(label_id)
    return selected


def _mask_from_group(labels: np.ndarray, group: dict[str, Any], lut: dict[int, str]) -> np.ndarray:
    ids = _label_ids_for_group(labels, group, lut)
    if not ids:
        return np.zeros(labels.shape, dtype=bool)
    return np.isin(labels, list(ids))


def _load_anatomy_labels(path: Path, target: Volume) -> tuple[np.ndarray, dict[str, Any]]:
    img = nib.load(str(path))
    original_shape = tuple(int(v) for v in img.shape[:3])
    original_affine = np.asarray(img.affine)
    status = "uploaded_in_subject_space"
    resampled = False
    if original_shape != target.shape or not np.allclose(original_affine, target.affine, atol=1e-3):
        img = resample_from_to(img, (target.shape, target.affine), order=0)
        status = "resampled_to_mask_space"
        resampled = True
    labels = np.asarray(np.rint(img.get_fdata()), dtype=np.int32)
    return labels, {
        "status": status,
        "resampled": resampled,
        "original_shape": list(original_shape),
        "target_shape": list(target.shape),
        "affine_matched_initially": bool(np.allclose(original_affine, target.affine, atol=1e-3)),
        "source": str(path),
    }


def _distance(mask: np.ndarray, spacing: tuple[float, float, float]) -> np.ndarray | None:
    if mask.any():
        return ndi.distance_transform_edt(~mask.astype(bool), sampling=spacing)
    return None


def _tags_for_component(
    component: np.ndarray,
    *,
    category_masks: dict[str, np.ndarray],
    ventricle_distance: np.ndarray | None,
    cortex_distance: np.ndarray | None,
    spacing: tuple[float, float, float],
) -> dict[str, Any]:
    tags: set[str] = set()
    vent_mm = None
    cortex_mm = None
    overlaps_cortex = bool((component & category_masks["cortex"]).any())
    overlaps_it = bool((component & category_masks["infratentorial"]).any())
    overlaps_cc = bool((component & category_masks["corpus_callosum"]).any())
    if ventricle_distance is not None and component.any():
        vent_mm = float(np.min(ventricle_distance[component]))
        if vent_mm <= settings.periventricular_distance_mm:
            tags.add("periventricular")
    if cortex_distance is not None and component.any():
        cortex_mm = float(np.min(cortex_distance[component]))
        if cortex_mm <= settings.juxtacortical_distance_mm or overlaps_cortex:
            tags.add("juxtacortical_or_cortical")
    if overlaps_it:
        tags.add("infratentorial")
    if overlaps_cc:
        tags.add("corpus_callosum")
    if not tags:
        tags.add("deep_white_matter_or_other")
    priority = load_label_mapping().get("primary_location_priority", LOCATION_CATEGORIES)
    primary = next((item for item in priority if item in tags), "unknown")
    return {
        "all_locations": sorted(tags),
        "primary_location": primary,
        "distance_to_ventricle_mm": vent_mm,
        "distance_to_cortex_mm": cortex_mm,
        "overlaps_cortex": overlaps_cortex,
        "overlaps_infratentorial": overlaps_it,
        "overlaps_corpus_callosum": overlaps_cc,
        "location_assignment_method": (
            f"FreeSurfer/SynthSeg label proxy; PV <= {settings.periventricular_distance_mm:g} mm; "
            f"JC/cortical <= {settings.juxtacortical_distance_mm:g} mm or cortex overlap"
        ),
    }


def _empty_result(reason: str) -> dict[str, Any]:
    qc = {
        "status": "missing",
        "reason": reason,
        "warnings": ["Anatomy-aware metrics skipped."],
        "resampled": False,
    }
    return {
        "available": False,
        "anatomy_qc": qc,
        "subject_fields": {
            **clinical_evidence_summary(anatomy_available=False),
            "anatomy_status": "missing",
            "anatomy_available": False,
            "anatomy_resampled": False,
            "periventricular_recall": None,
            "juxtacortical_cortical_recall": None,
            "infratentorial_recall": None,
            "deep_white_matter_other_recall": None,
        },
        "location_metrics": [],
        "size_location_metrics": [],
        "location_topology_metrics": [],
        "assignments": [],
        "method_card": {
            "status": "unavailable",
            "reason": reason,
            "wording": "Anatomy localization was not calculated because no usable labelmap was supplied.",
        },
        "location_masks": {},
    }


def anatomy_analysis(
    *,
    image: Volume,
    gt_mask: np.ndarray,
    pred_mask: np.ndarray,
    lesion_rows: list[dict],
    prediction_rows: list[dict],
    cluster_rows: list[dict],
    anatomy_path: Path | None = None,
    lut_path: Path | None = None,
) -> dict[str, Any]:
    if anatomy_path is None:
        return _empty_result("No anatomy labelmap uploaded.")
    try:
        labels, provenance = _load_anatomy_labels(anatomy_path, image)
        lut = parse_freesurfer_lut(lut_path)
        config = load_label_mapping()
        groups = config["locations"]
        category_masks = {
            "ventricular_system": _mask_from_group(labels, groups["ventricular_system"], lut),
            "cortex": _mask_from_group(labels, groups["cortex"], lut),
            "infratentorial": _mask_from_group(labels, groups["infratentorial"], lut),
            "corpus_callosum": _mask_from_group(labels, groups["corpus_callosum"], lut),
        }
        warnings = []
        if not category_masks["ventricular_system"].any():
            warnings.append("No ventricle labels found; periventricular assignment may be unavailable.")
        if not category_masks["cortex"].any():
            warnings.append("No cortical labels found; juxtacortical/cortical assignment may be unavailable.")
        if not category_masks["infratentorial"].any():
            warnings.append("No infratentorial labels found.")
        if provenance["resampled"]:
            warnings.append("Anatomy labelmap was resampled to mask space using nearest-neighbor interpolation.")
        if not np.any(labels):
            return _empty_result("Anatomy labelmap contains only zero labels.")
    except Exception as exc:
        result = _empty_result(f"Anatomy labelmap failed to load: {exc}")
        result["anatomy_qc"]["status"] = "failed"
        return result

    ventricle_distance = _distance(category_masks["ventricular_system"], image.spacing)
    cortex_distance = _distance(category_masks["cortex"], image.spacing)
    gt_labels, _ = connected_components(gt_mask, settings.connectivity)
    pred_labels, _ = connected_components(pred_mask, settings.connectivity)

    gt_location_by_id: dict[int, dict[str, Any]] = {}
    pred_location_by_id: dict[int, dict[str, Any]] = {}
    assignments: list[dict] = []
    anatomy_confidence = "resampled" if provenance["resampled"] else "available"

    for row in lesion_rows:
        lesion_id = int(row["lesion_id"])
        component = gt_labels == lesion_id
        info = _tags_for_component(
            component,
            category_masks=category_masks,
            ventricle_distance=ventricle_distance,
            cortex_distance=cortex_distance,
            spacing=image.spacing,
        )
        gt_location_by_id[lesion_id] = info
        row.update(
            {
                **info,
                "all_locations": "|".join(info["all_locations"]),
                "anatomy_confidence": anatomy_confidence,
                "lesion_location_label": info["primary_location"],
            }
        )
        assignments.append(
            {
                "object_type": "ground_truth_lesion",
                "object_id": lesion_id,
                **row,
            }
        )

    for row in prediction_rows:
        pred_id = int(row["pred_lesion_id"])
        component = pred_labels == pred_id
        info = _tags_for_component(
            component,
            category_masks=category_masks,
            ventricle_distance=ventricle_distance,
            cortex_distance=cortex_distance,
            spacing=image.spacing,
        )
        pred_location_by_id[pred_id] = info
        row.update(
            {
                **info,
                "all_locations": "|".join(info["all_locations"]),
                "false_positive_location": info["primary_location"] if row.get("false_positive") else None,
                "anatomy_confidence": anatomy_confidence,
                "location_label_if_available": info["primary_location"],
            }
        )
        assignments.append(
            {
                "object_type": "predicted_lesion",
                "object_id": pred_id,
                **row,
            }
        )

    for row in cluster_rows:
        gt_tags = set()
        pred_tags = set()
        for lesion_id in row.get("cluster_gt_ids", []) or []:
            gt_tags.update(gt_location_by_id.get(int(lesion_id), {}).get("all_locations", []))
        for pred_id in row.get("cluster_pred_ids", []) or []:
            pred_tags.update(pred_location_by_id.get(int(pred_id), {}).get("all_locations", []))
        all_tags = sorted(gt_tags | pred_tags)
        priority = load_label_mapping().get("primary_location_priority", LOCATION_CATEGORIES)
        primary = next((item for item in priority if item in all_tags), "unknown")
        has_relevant = bool({"periventricular", "juxtacortical_or_cortical", "infratentorial"} & set(all_tags))
        row.update(
            {
                "cluster_all_locations": "|".join(all_tags) if all_tags else "unknown",
                "cluster_primary_location": primary,
                "cluster_location_category": primary,
                "cluster_has_relevant_location": has_relevant,
                "cluster_contains_pv": "periventricular" in all_tags,
                "cluster_contains_jc_cortical": "juxtacortical_or_cortical" in all_tags,
                "cluster_contains_it": "infratentorial" in all_tags,
                "cluster_contains_high_risk_location": has_relevant,
                "cluster_split_in_relevant_location": has_relevant and "split" in str(row.get("cluster_type", "")).lower(),
                "cluster_merge_in_relevant_location": has_relevant and "merge" in str(row.get("cluster_type", "")).lower(),
                "cluster_location_mismatch": bool(gt_tags and pred_tags and gt_tags.isdisjoint(pred_tags)),
                "cluster_location_label": primary,
            }
        )

    gt_locations = {row["primary_location"] for row in lesion_rows if row.get("primary_location") != "unknown"}
    pred_locations = {row["primary_location"] for row in prediction_rows if row.get("primary_location") != "unknown"}
    capability = compute_location_capability(
        lesion_rows=lesion_rows,
        prediction_rows=prediction_rows,
        cluster_rows=cluster_rows,
        case_count=1,
    )
    location_metrics = capability["location_metrics"]
    subject_fields = {
        **clinical_evidence_summary(gt_locations, pred_locations, anatomy_available=True),
        **_specific_location_fields(location_metrics),
        **capability["subject_fields"],
        "anatomy_status": provenance["status"],
        "anatomy_available": True,
        "anatomy_resampled": provenance["resampled"],
        "anatomy_location_count": len(gt_locations),
    }
    location_masks = {
        "periventricular_gt": _components_for_location(gt_labels, lesion_rows, "periventricular"),
        "periventricular_pred": _components_for_location(pred_labels, prediction_rows, "periventricular", id_key="pred_lesion_id"),
        "juxtacortical_cortical_gt": _components_for_location(gt_labels, lesion_rows, "juxtacortical_or_cortical"),
        "juxtacortical_cortical_pred": _components_for_location(pred_labels, prediction_rows, "juxtacortical_or_cortical", id_key="pred_lesion_id"),
        "infratentorial_gt": _components_for_location(gt_labels, lesion_rows, "infratentorial"),
        "infratentorial_pred": _components_for_location(pred_labels, prediction_rows, "infratentorial", id_key="pred_lesion_id"),
    }
    return {
        "available": True,
        "anatomy_qc": {
            **provenance,
            "warnings": warnings,
            "status": "warning" if warnings else "pass",
            "lut_loaded": bool(lut),
            "ventricle_labels_found": bool(category_masks["ventricular_system"].any()),
            "cortex_labels_found": bool(category_masks["cortex"].any()),
            "infratentorial_labels_found": bool(category_masks["infratentorial"].any()),
        },
        "subject_fields": subject_fields,
        "location_metrics": location_metrics,
        "size_location_metrics": capability["size_location_metrics"],
        "location_topology_metrics": capability["location_topology_metrics"],
        "assignments": assignments,
        "method_card": {
            "status": "available",
            "labelmap_source": str(anatomy_path),
            "lut_source": str(lut_path) if lut_path else None,
            "periventricular_threshold_mm": settings.periventricular_distance_mm,
            "juxtacortical_threshold_mm": settings.juxtacortical_distance_mm,
            "wording": "QA localization proxy based on uploaded anatomy labels. Not diagnostic criteria.",
        },
        "location_masks": location_masks,
    }


def _components_for_location(labels: np.ndarray, rows: list[dict], location: str, id_key: str = "lesion_id") -> np.ndarray:
    ids = [
        int(row[id_key])
        for row in rows
        if location in str(row.get("all_locations", "")).split("|") and row.get(id_key) is not None
    ]
    return np.isin(labels, ids)


def _location_metrics(
    lesion_rows: list[dict],
    prediction_rows: list[dict],
    gt_mask: np.ndarray,
    pred_mask: np.ndarray,
    spacing: tuple[float, float, float],
) -> list[dict]:
    rows = []
    for location in LOCATION_CATEGORIES[:-1]:
        gt_rows = [row for row in lesion_rows if location in str(row.get("all_locations", "")).split("|")]
        pred_rows = [row for row in prediction_rows if location in str(row.get("all_locations", "")).split("|")]
        matched_gt = [row for row in gt_rows if row.get("lesion_detected")]
        fp_rows = [row for row in pred_rows if row.get("false_positive")]
        fn_rows = [row for row in gt_rows if not row.get("lesion_detected")]
        recall = (len(matched_gt) / len(gt_rows)) if gt_rows else None
        precision = ((len(pred_rows) - len(fp_rows)) / len(pred_rows)) if pred_rows else None
        f1 = None if recall is None or precision is None or recall + precision == 0 else 2 * recall * precision / (recall + precision)
        gt_vol = float(sum(float(row.get("lesion_volume_mm3") or 0.0) for row in gt_rows))
        pred_vol = float(sum(float(row.get("pred_volume_mm3") or 0.0) for row in pred_rows))
        abs_err = abs(pred_vol - gt_vol)
        rel_err = None if gt_vol == 0 else abs_err / gt_vol
        dice_values = [row.get("lesion_dice") for row in matched_gt if isinstance(row.get("lesion_dice"), (int, float))]
        hd_values = [row.get("lesion_hd95_mm") for row in matched_gt if isinstance(row.get("lesion_hd95_mm"), (int, float))]
        assd_values = [row.get("lesion_assd_mm") for row in matched_gt if isinstance(row.get("lesion_assd_mm"), (int, float))]
        rows.append(
            {
                "location": location,
                "location_gt_lesion_count": len(gt_rows),
                "location_pred_lesion_count": len(pred_rows),
                "location_matched_lesion_count": len(matched_gt),
                "location_lesion_recall": recall,
                "location_lesion_precision": precision,
                "location_lesion_f1": f1,
                "location_fp_lesions_per_scan": len(fp_rows),
                "location_fn_lesions_per_scan": len(fn_rows),
                "location_gt_volume_mm3": gt_vol,
                "location_pred_volume_mm3": pred_vol,
                "location_absolute_volume_error_mm3": abs_err,
                "location_relative_volume_error": rel_err,
                "location_mean_matched_lesion_dice": float(np.mean(dice_values)) if dice_values else None,
                "location_mean_matched_lesion_hd95_mm": float(np.mean(hd_values)) if hd_values else None,
                "location_mean_matched_lesion_assd_mm": float(np.mean(assd_values)) if assd_values else None,
            }
        )
    return rows


def _specific_location_fields(location_metrics: list[dict]) -> dict[str, Any]:
    by_location = {row["location"]: row for row in location_metrics}

    def values(location: str, prefix: str) -> dict[str, Any]:
        row = by_location.get(location, {})
        return {
            f"{prefix}_recall": row.get("location_lesion_recall"),
            f"{prefix}_precision": row.get("location_lesion_precision"),
            f"{prefix}_f1": row.get("location_lesion_f1"),
        }

    return {
        **values("periventricular", "periventricular"),
        **values("juxtacortical_or_cortical", "juxtacortical_cortical"),
        **values("infratentorial", "infratentorial"),
        **values("deep_white_matter_or_other", "deep_white_matter_other"),
    }


def case_difficulty_signature(
    *,
    image: Volume,
    gt_mask: np.ndarray,
    lesion_rows: list[dict],
    anatomy_subject_fields: dict[str, Any],
) -> dict[str, Any]:
    volumes = [float(row.get("lesion_volume_mm3") or 0.0) for row in lesion_rows]
    tiny_small = [v for row, v in zip(lesion_rows, volumes) if row.get("lesion_size_bin") in {"tiny", "small"}]
    spacing = np.asarray(image.spacing, dtype=float)
    total_voxels = int(np.prod(gt_mask.shape))
    lesion_voxels = int(gt_mask.sum())
    return {
        "difficulty_total_lesion_volume_mm3": float(sum(volumes)),
        "difficulty_lesion_count": len(lesion_rows),
        "difficulty_median_lesion_size_mm3": float(np.median(volumes)) if volumes else None,
        "difficulty_tiny_small_lesion_fraction": (len(tiny_small) / len(volumes)) if volumes else None,
        "difficulty_topographic_region_count": anatomy_subject_fields.get("gt_topography_count"),
        "difficulty_infratentorial_present": bool(anatomy_subject_fields.get("infratentorial_recall") is not None),
        "difficulty_juxtacortical_cortical_present": bool(anatomy_subject_fields.get("juxtacortical_cortical_recall") is not None),
        "difficulty_periventricular_present": bool(anatomy_subject_fields.get("periventricular_recall") is not None),
        "difficulty_image_spacing": "|".join(f"{v:g}" for v in image.spacing),
        "difficulty_anisotropy_ratio": float(spacing.max() / max(spacing.min(), 1e-6)),
        "difficulty_mask_sparsity": 1.0 - (lesion_voxels / total_voxels if total_voxels else 0.0),
        "difficulty_lesion_burden_percentage": 100.0 * lesion_voxels / total_voxels if total_voxels else None,
    }


def confidence_metrics(
    *,
    probability: Volume | None,
    uncertainty: Volume | None,
    gt_mask: np.ndarray,
    pred_mask: np.ndarray,
) -> dict[str, Any]:
    if probability is None:
        return {}
    prob = np.asarray(probability.data, dtype=float)
    tp = gt_mask & pred_mask
    fp = ~gt_mask & pred_mask
    fn = gt_mask & ~pred_mask
    result: dict[str, Any] = {
        "probability_threshold_used": 0.5,
        "lesion_probability_mean_tp_voxels": float(np.nanmean(prob[tp])) if tp.any() else None,
        "probability_mean_fp_voxels": float(np.nanmean(prob[fp])) if fp.any() else None,
        "probability_mean_fn_voxels": float(np.nanmean(prob[fn])) if fn.any() else None,
        "high_confidence_false_positive_voxel_count": int(np.count_nonzero(fp & (prob >= 0.90))),
        "low_confidence_true_positive_voxel_count": int(np.count_nonzero(tp & (prob < 0.50))),
    }
    if uncertainty is not None:
        unc = np.asarray(uncertainty.data, dtype=float)
        err = np.logical_xor(gt_mask, pred_mask).astype(float)
        result.update(
            {
                "uncertainty_mean": float(np.nanmean(unc)),
                "uncertainty_mean_error_voxels": float(np.nanmean(unc[err.astype(bool)])) if err.any() else None,
                "uncertainty_mean_correct_voxels": float(np.nanmean(unc[~err.astype(bool)])) if (~err.astype(bool)).any() else None,
            }
        )
    return result
