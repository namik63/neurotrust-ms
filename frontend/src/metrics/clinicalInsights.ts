import type { ValidationResult } from "../types";

export function numeric(value: any): number | null {
  return typeof value === "number" && value === value ? value : null;
}

export function fmt(value: any, digits = 2) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return value.toFixed(Math.abs(value) > 10 ? 1 : digits);
  return String(value).replaceAll("_", " ");
}

export function locationLabel(value: string) {
  return String(value || "unknown")
    .replace("periventricular", "periventricular")
    .replace("juxtacortical_or_cortical", "juxtacortical/cortical")
    .replace("deep_white_matter_or_other", "deep white matter / other")
    .replace("infratentorial", "infratentorial")
    .replace("corpus_callosum", "corpus callosum");
}

export function recommendationStatus(result: ValidationResult) {
  const raw = String(result.deployment_recommendation?.status || "").toLowerCase();
  const metrics = result.subject_metrics || {};
  const cases = metrics.successful_case_count ?? metrics.case_count ?? 1;
  if (cases < 3) return "validation evidence limited; focused review required";
  if (raw.includes("restricted") || raw.includes("conditional")) return "validation evidence acceptable with focused review";
  if (raw.includes("provisional")) return "validation evidence limited; focused review required";
  if (raw.includes("fail")) return "evidence insufficient for deployment decision";
  return "validation evidence strong with review";
}

export function strongestLocation(result: ValidationResult) {
  const rows = (result.location_metrics || []).filter((row: any) => numeric(row.location_overall_capability_score) !== null || numeric(row.location_lesion_recall) !== null);
  if (!rows.length) return null;
  return [...rows].sort((a: any, b: any) => (numeric(b.location_overall_capability_score) ?? numeric(b.location_lesion_recall) ?? -1) - (numeric(a.location_overall_capability_score) ?? numeric(a.location_lesion_recall) ?? -1))[0];
}

export function weakestLocation(result: ValidationResult) {
  const rows = (result.location_metrics || []).filter((row: any) => Number(row.location_gt_lesion_count || 0) > 0);
  if (!rows.length) return null;
  return [...rows].sort((a: any, b: any) => (numeric(a.location_overall_capability_score) ?? numeric(a.location_lesion_recall) ?? 99) - (numeric(b.location_overall_capability_score) ?? numeric(b.location_lesion_recall) ?? 99))[0];
}

export function cautionLabel(row: any) {
  const gt = Number(row.location_gt_lesion_count || 0);
  if (!gt) return "Evidence limited";
  const recall = numeric(row.location_lesion_recall);
  const fp = numeric(row.location_fp_lesions_per_scan) ?? 0;
  if ((recall !== null && recall < 0.65) || fp >= 2) return "High review priority";
  if ((recall !== null && recall < 0.82) || fp >= 1) return "Review with caution";
  return "Reliable in this sample";
}

export function clinicalSummary(result: ValidationResult) {
  const metrics = result.subject_metrics || {};
  const cases = metrics.successful_case_count ?? metrics.case_count ?? result.model_passport?.number_of_cases_tested ?? 1;
  const strongest = strongestLocation(result);
  const weakest = weakestLocation(result);
  const fingerprint = result.failure_fingerprint?.primary_failure_fingerprint || result.failure_fingerprint?.primary?.tag || "Balanced";
  const fp = numeric(metrics.fp_lesions_per_scan);
  const recall = numeric(metrics.lesion_recall);
  const highRisk = numeric(metrics.high_risk_location_miss_rate);
  const reviewFocus = [];
  if (fp !== null && fp >= 2) reviewFocus.push("prediction-only lesion candidates");
  if (highRisk !== null && highRisk > 0.25) reviewFocus.push("tiny/small lesions in MS-relevant locations");
  if (weakest) reviewFocus.push(`${locationLabel(weakest.location)} lesions`);
  if (result.dice_trap_detector?.active) reviewFocus.push("cases where overlap looks acceptable but lesion evidence disagrees");
  if (!reviewFocus.length) reviewFocus.push("watchlist targets and any prediction-only regions");
  const uncertainty = cases < 5
    ? "The estimate is very uncertain because the validation set is small."
    : cases < 10
      ? "The estimate is still cohort-limited; intervals may remain wide."
      : "The estimate is supported by a larger validation set.";

  return {
    headline: `Clinical pattern: ${fingerprint.replaceAll("_", " ")}.`,
    mainTakeaway: `Across ${cases} validation case${cases === 1 ? "" : "s"}, the model shows lesion detection ${recall !== null ? `around ${recall.toFixed(2)}` : "that should be reviewed"} with a primary review focus on ${reviewFocus.slice(0, 3).join(", ")}.`,
    strongest: strongest ? `${locationLabel(strongest.location)} (${fmt(strongest.location_lesion_recall)} detection rate)` : "No anatomy location has enough evidence yet.",
    weakest: weakest ? `${locationLabel(weakest.location)} (${cautionLabel(weakest)})` : "No location-specific weakness could be estimated.",
    reviewFocus,
    uncertainty,
  };
}

export type ImprovementItem = {
  priority: "high" | "medium" | "low";
  failurePattern: string;
  observedEvidence: string;
  possibleCauses: string[];
  modelImprovementActions: string[];
  dataImprovementActions: string[];
  deploymentSafeguards: string[];
  metricsToRecheck: string[];
};

export function improvementPlan(result: ValidationResult): ImprovementItem[] {
  const metrics = result.subject_metrics || {};
  const tags = new Set<string>((result.failure_fingerprint?.tags || []).map((tag: any) => tag.tag));
  const items: ImprovementItem[] = [];
  const add = (item: ImprovementItem) => items.push(item);

  if (tags.has("FP-heavy") || Number(metrics.fp_lesions_per_scan || 0) >= 2) {
    add({
      priority: "high",
      failurePattern: "FP-heavy",
      observedEvidence: `Extra AI lesion candidates are ${fmt(metrics.fp_lesions_per_scan)} per scan.`,
      possibleCauses: ["probability threshold may be too permissive", "training data may lack hard-negative examples", "artifacts may resemble lesions", "post-processing may allow tiny isolated components"],
      modelImprovementActions: ["tune threshold on local validation data", "add hard-negative mining", "evaluate connected-component filtering", "stratify false positives by anatomy region"],
      dataImprovementActions: ["add local artifact/mimic cases", "include non-lesion hyperintensity examples", "stratify validation by scanner or protocol"],
      deploymentSafeguards: ["review prediction-only overlays before accepting lesion count", "track FP/scan after threshold changes"],
      metricsToRecheck: ["FP lesions / scan", "lesion precision", "location FP dominance", "watchlist size"],
    });
  }

  if (tags.has("Small-lesion blind") || tags.has("Tiny-PV blind") || tags.has("JC/cortical blind") || Number(metrics.high_risk_location_miss_rate || 0) > 0.25) {
    add({
      priority: "high",
      failurePattern: "Small-location blind",
      observedEvidence: `High-risk tiny/small location miss rate is ${fmt(metrics.high_risk_location_miss_rate)}.`,
      possibleCauses: ["small lesions may be underrepresented", "patch sampling may favor larger lesions", "resolution or contrast may limit subtle-lesion detection"],
      modelImprovementActions: ["oversample small lesions", "add lesion-aware or small-object loss", "train/evaluate higher-resolution patches where feasible", "add synthetic small-lesion augmentation"],
      dataImprovementActions: ["add more low-burden and tiny-lesion cases", "include more PV and JC/cortical examples", "review uncertain tiny lesions with a second expert when available"],
      deploymentSafeguards: ["prioritize tiny/small PV and JC/cortical review in the viewer", "do not accept lesion count without checking missed-lesion targets"],
      metricsToRecheck: ["tiny/small recall", "high-risk location miss rate", "PV recall", "JC/cortical recall"],
    });
  }

  if (tags.has("Infratentorial blind") || (numeric(metrics.it_recall) !== null && Number(metrics.it_recall) < 0.7)) {
    add({
      priority: "high",
      failurePattern: "Infratentorial weak",
      observedEvidence: `Infratentorial detection rate is ${fmt(metrics.it_recall)}.`,
      possibleCauses: ["fewer infratentorial training examples", "small structures and artifacts may reduce contrast", "anatomy imbalance may bias sampling"],
      modelImprovementActions: ["increase infratentorial examples", "use region-aware sampling", "validate brainstem/cerebellar performance separately"],
      dataImprovementActions: ["add more infratentorial-positive validation cases", "check scanner/protocol effects in posterior fossa regions"],
      deploymentSafeguards: ["manual review should inspect brainstem and cerebellar regions"],
      metricsToRecheck: ["IT recall", "IT missed lesions / scan", "IT FP burden"],
    });
  }

  if (tags.has("Volume-underestimating") || tags.has("Volume-overestimating") || Number(metrics.relative_volume_error || 0) > 0.3) {
    add({
      priority: "medium",
      failurePattern: "Volume burden mismatch",
      observedEvidence: `Relative volume error is ${fmt(metrics.relative_volume_error)}.`,
      possibleCauses: ["threshold calibration may be off", "boundaries may be eroded or overexpanded", "missed small lesions can distort burden"],
      modelImprovementActions: ["calibrate threshold on validation data", "review boundary loss or post-processing", "recheck volume after connected-component filtering"],
      dataImprovementActions: ["include cases across low, moderate, and high lesion burden"],
      deploymentSafeguards: ["confirm volume trend manually before using burden changes"],
      metricsToRecheck: ["relative volume error", "volume ratio", "matched lesion boundary metrics"],
    });
  }

  if (tags.has("Topology-unstable")) {
    add({
      priority: "medium",
      failurePattern: "Topology-unstable",
      observedEvidence: "Split/merge clusters were detected in the validation outputs.",
      possibleCauses: ["connected-component fragmentation", "holes in thresholded masks", "confluent lesions handled inconsistently"],
      modelImprovementActions: ["evaluate morphology post-processing", "review cluster-level threshold rules", "validate confluent/high-burden cases separately"],
      dataImprovementActions: ["include confluent and high-burden cases in validation"],
      deploymentSafeguards: ["review lesion count in high-burden or confluent cases"],
      metricsToRecheck: ["split rate", "merge rate", "complex topology rate"],
    });
  }

  if (!items.length) {
    add({
      priority: "low",
      failurePattern: "Balanced",
      observedEvidence: "No dominant configured failure pattern was triggered.",
      possibleCauses: ["current sample may not stress all clinically relevant edge cases"],
      modelImprovementActions: ["continue monitoring with larger and more diverse validation cases"],
      dataImprovementActions: ["add low-burden, infratentorial, artifact-heavy, and scanner-diverse cases"],
      deploymentSafeguards: ["keep watchlist review enabled during local rollout"],
      metricsToRecheck: ["lesion recall", "FP lesions / scan", "location capability", "reliability spread"],
    });
  }
  return items;
}
