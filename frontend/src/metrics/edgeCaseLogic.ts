import type { ValidationResult } from "../types";
import { fmt, locationLabel, weakestLocation } from "./clinicalInsights";

export type EdgeCaseLogicCard = {
  title: string;
  status: "handled" | "review" | "not_applicable";
  trigger: string;
  howHandled: string;
  whereShown: string;
  currentSignal: string;
};

function warningCount(result: ValidationResult) {
  const qc = result.qc || {};
  return [
    ...(qc.errors || []),
    ...(qc.warnings || []),
    ...(qc.geometry || []),
    ...(qc.masks || []),
    ...(qc.files || []),
    ...(qc.anatomy || []),
    ...(qc.batch || []),
    ...(qc.viewer || []),
    ...(qc.export || []),
  ].length;
}

function hasMetric(result: ValidationResult, keys: string[]) {
  const metrics = result.subject_metrics || {};
  return keys.some((key) => metrics[key] !== undefined && metrics[key] !== null);
}

export function edgeCaseLogic(result: ValidationResult): EdgeCaseLogicCard[] {
  const metrics = result.subject_metrics || {};
  const qcText = JSON.stringify(result.qc || {}).toLowerCase();
  const cases = Number(metrics.successful_case_count ?? metrics.case_count ?? result.model_passport?.number_of_cases_tested ?? 1);
  const failedCases = Number(metrics.qc_failed_case_count ?? 0);
  const gtCount = Number(metrics.gt_lesion_count ?? 0);
  const predCount = Number(metrics.pred_lesion_count ?? 0);
  const warnings = warningCount(result);
  const batchSignals = [...(result.qc?.batch || []), ...(result.case_results || []).filter((row: any) => row?.status === "qc_failed")];
  const anatomyStatus = String(result.anatomy_qc?.status || metrics.anatomy_status || "not returned");
  const anatomyAvailable = Boolean(metrics.anatomy_available || result.subject_metrics?.anatomy_available_case_count);
  const locationRows = result.location_metrics || [];
  const weakest = weakestLocation(result);
  const hasConfidenceMap = hasMetric(result, [
    "probability_threshold_used",
    "lesion_probability_mean_tp_voxels",
    "probability_mean_fp_voxels",
    "probability_mean_fn_voxels",
    "uncertainty_mean",
    "uncertainty_mean_error_voxels",
  ]);
  const hasSecondExpert = Boolean(result.expert_variability?.length);
  const viewerCount = result.case_viewers?.length || (result.viewer ? 1 : 0);
  const tags = (result.failure_fingerprint?.tags || []).map((tag: any) => String(tag.tag || tag).toLowerCase());
  const smallLesionSignal = tags.some((tag: string) => tag.includes("small") || tag.includes("tiny")) || Number(metrics.high_risk_location_miss_rate ?? metrics.high_risk_miss_rate ?? 0) > 0.25;
  const fpBurden = Number(metrics.fp_lesions_per_scan ?? 0);

  return [
    {
      title: "Password-protected validation history",
      status: "handled",
      trigger: "A repeat user signs in and wants to reopen recent validation results.",
      howHandled: "The backend stores email-linked run metadata and protected result paths. Raw passwords are not stored; sessions use server-side hashed tokens.",
      whereShown: "Access gate and Past Results.",
      currentSignal: "Database-backed login and history are active for this session.",
    },
    {
      title: "Temporary result cleanup",
      status: "handled",
      trigger: "Old result folders expire after the configured retention window.",
      howHandled: "History records remain visible, but expired report files return a clear regenerate message instead of a broken result.",
      whereShown: "Past Results.",
      currentSignal: "If a retained file is gone, the app asks the user to rerun validation.",
    },
    {
      title: "Manual filename pairing",
      status: batchSignals.length ? "review" : "handled",
      trigger: "Raw MRI, GT, and prediction names do not match by case ID.",
      howHandled: "The frontend previews pairing problems. The backend groups by normalized basename and excludes unpaired cases from aggregate metrics.",
      whereShown: "Upload safety check and batch QC.",
      currentSignal: batchSignals.length ? `${batchSignals.length} pairing/QC signal(s) returned.` : "No batch pairing problem returned.",
    },
    {
      title: "Wrong file in the wrong field",
      status: qcText.includes("nonbinary") || qcText.includes("large_gt_fraction") || qcText.includes("large_prediction_fraction") ? "review" : "handled",
      trigger: "A user drops an MRI, anatomy labelmap, or broad non-lesion mask into a GT/prediction slot.",
      howHandled: "The backend checks mask discreteness, empty masks, unusually large mask fractions, nonfinite values, and geometry before computing metrics.",
      whereShown: "QC export and Safety / Edge / Privacy.",
      currentSignal: qcText.includes("nonbinary") || qcText.includes("large_gt_fraction") || qcText.includes("large_prediction_fraction") ? "Mask sanity warning returned." : "No wrong-slot mask sanity warning returned.",
    },
    {
      title: "Geometry and metadata QC",
      status: warnings || failedCases ? "review" : "handled",
      trigger: "Shape mismatch, invalid spacing, affine mismatch, thick slices, anisotropy, NaN/Inf values, or failed subject QC.",
      howHandled: "Blocking errors stop computation. Nonblocking risks are preserved as warnings so the metrics remain auditable.",
      whereShown: "QC export, Research Appendix, and reports.",
      currentSignal: warnings || failedCases ? `${warnings} QC warning/error signal(s); ${failedCases} failed case(s).` : "No QC warning signal returned.",
    },
    {
      title: "Very small validation cohort",
      status: cases < 5 ? "review" : "handled",
      trigger: "Fewer than 5 successful cases are available.",
      howHandled: "The app still reports metrics, but confidence language is tied to the number of validation cases rather than overclaiming general performance.",
      whereShown: "Clinical Summary and Hospital Reliability.",
      currentSignal: `${cases} successful case${cases === 1 ? "" : "s"} analyzed.`,
    },
    {
      title: "Empty or no-lesion masks",
      status: gtCount === 0 || predCount === 0 ? "review" : "handled",
      trigger: "GT has no lesions, prediction has no lesions, or both masks are empty.",
      howHandled: "Voxel and lesion metrics use explicit empty-mask behavior; lesion counts remain visible rather than hidden behind Dice.",
      whereShown: "Clinical Summary, Lesions, and QC export.",
      currentSignal: `GT lesions ${gtCount}; AI lesions ${predCount}.`,
    },
    {
      title: "FreeSurfer/anatomy evidence",
      status: anatomyAvailable ? "handled" : "review",
      trigger: "Anatomy-aware PV/JC/IT/DWM metrics require a usable uploaded FreeSurfer/SynthSeg labelmap.",
      howHandled: "The app selects a labelmap from uploaded FreeSurfer files, resamples it to lesion-mask space with nearest-neighbor interpolation, and skips anatomy metrics if labels are unusable.",
      whereShown: "Anatomy Failure Map, 3D Viewer location overlays, and Research Appendix.",
      currentSignal: `Anatomy status: ${anatomyStatus}; location rows ${locationRows.length}.`,
    },
    {
      title: "Weakest location signal",
      status: weakest ? "review" : "not_applicable",
      trigger: "A brain location has enough GT lesions and lower detection than other locations.",
      howHandled: "The app reports the weakest location as a review target instead of relying only on global Dice.",
      whereShown: "Clinical Summary and Anatomy Failure Map.",
      currentSignal: weakest ? `${locationLabel(weakest.location)} detection ${fmt(weakest.location_lesion_recall)}.` : "No location denominator available.",
    },
    {
      title: "Small-lesion miss risk",
      status: smallLesionSignal ? "review" : "handled",
      trigger: "Tiny/small lesion recall or high-risk location miss rate is concerning.",
      howHandled: "Size-bin and watchlist outputs separate small-lesion misses from global overlap.",
      whereShown: "Review Priorities, Lesions, and Improvement Plan.",
      currentSignal: `High-risk miss rate ${fmt(metrics.high_risk_location_miss_rate ?? metrics.high_risk_miss_rate)}.`,
    },
    {
      title: "Prediction-only burden",
      status: fpBurden >= 2 ? "review" : "handled",
      trigger: "AI produces lesion components without expert-mask overlap.",
      howHandled: "Prediction-only components are counted, exported, and shown as a separate overlay in the viewer.",
      whereShown: "Clinical Summary, Review Priorities, 3D Viewer, and exports.",
      currentSignal: `${fmt(metrics.fp_lesions_per_scan)} prediction-only lesion(s) per scan.`,
    },
    {
      title: "Probability and uncertainty maps",
      status: hasConfidenceMap ? "handled" : "not_applicable",
      trigger: "Probability or uncertainty maps are uploaded and match the MRI geometry.",
      howHandled: "Confidence-map metrics are calculated only when compatible maps exist. Binary-mask validation still runs without them.",
      whereShown: "Research Appendix and exports.",
      currentSignal: hasConfidenceMap ? "Compatible probability/uncertainty metrics returned." : "No compatible confidence map used.",
    },
    {
      title: "Second expert context",
      status: hasSecondExpert ? "handled" : "not_applicable",
      trigger: "A second expert mask is uploaded.",
      howHandled: "Expert-vs-expert agreement is calculated separately from AI-vs-GT metrics so reader variability is not confused with model error.",
      whereShown: "Research Appendix and expert variability export.",
      currentSignal: hasSecondExpert ? `${result.expert_variability?.length} reader-variability row(s) returned.` : "No second expert mask used.",
    },
    {
      title: "3D viewer fallback",
      status: viewerCount ? "handled" : "review",
      trigger: "Interactive WebGL/NiiVue loading fails or a browser cannot render a volume.",
      howHandled: "The app shows a static overlay preview first, lazy-loads interactive 3D on request, and keeps PNG fallback available.",
      whereShown: "3D Viewer.",
      currentSignal: viewerCount ? `${viewerCount} viewer manifest(s) returned.` : "No viewer manifest returned.",
    },
  ];
}
