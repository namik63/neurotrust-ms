import type { ValidationResult } from "../types";
import { MetricHelpTooltip } from "./MetricHelpTooltip";
import { ciForMetric, formatCI } from "../metrics/confidence";
import { getMetricDefinition } from "../metrics/metricDefinitions";
import { recommendationStatus } from "../metrics/clinicalInsights";

function metricValue(value: any) {
  if (value === null || value === undefined || value === "") return "not available";
  if (typeof value === "number") return value.toFixed(Math.abs(value) > 10 ? 1 : 3);
  return String(value);
}

export function MetricStrip({ result }: { result: ValidationResult }) {
  const metrics = result.subject_metrics || {};
  const isBatch = result.mode === "batch";
  const cases = metrics.successful_case_count ?? metrics.case_count ?? result.model_passport?.number_of_cases_tested ?? 1;
  const recommendation = result.deployment_recommendation;
  const confidence = recommendation?.confidence_level !== undefined ? `${Math.round(recommendation.confidence_level * 100)}% confidence` : "confidence pending";
  const items: Array<{
    label: string;
    value: any;
    helper: string;
    tone: string;
    key: string;
  }> = [
    {
      label: "Recommendation",
      value: recommendationStatus(result),
      helper: confidence,
      tone: "amber",
      key: "deployment_status",
    },
    {
      label: isBatch ? "Mean lesion recall" : "Lesion recall",
      value: metrics.lesion_recall,
      helper: "Expert lesions detected.",
      tone: "cyan",
      key: "lesion_recall",
    },
    {
      label: "Lesion precision",
      value: metrics.lesion_precision,
      helper: "Predicted lesions confirmed.",
      tone: "cyan",
      key: "lesion_precision",
    },
    {
      label: "FP lesions / scan",
      value: metrics.fp_lesions_per_scan,
      helper: "Predicted-only burden.",
      tone: "blue",
      key: "fp_lesions_per_scan",
    },
    {
      label: "FN lesions / scan",
      value: metrics.fn_lesions_per_scan,
      helper: "Missed expert lesions.",
      tone: "red",
      key: "fn_lesions_per_scan",
    },
    {
      label: "Relative volume error",
      value: metrics.relative_volume_error,
      helper: "Burden error.",
      tone: "violet",
      key: "relative_volume_error",
    },
    {
      label: "High-risk location miss",
      value: metrics.high_risk_location_miss_rate ?? metrics.high_risk_miss_rate,
      helper: "Tiny/small misses in MS-relevant locations.",
      tone: "red",
      key: "high_risk_location_miss_rate",
    },
    {
      label: "Topography preservation",
      value: metrics.clinical_topography_preservation_ratio ?? metrics.clinical_evidence_preservation_ratio,
      helper: "Brain MRI evidence proxy.",
      tone: "neutral",
      key: "clinical_topography_preservation_ratio",
    },
    {
      label: "Cases tested",
      value: cases,
      helper: isBatch ? "Successful cases analyzed." : "Case-level evidence.",
      tone: "neutral",
      key: "confidence_interval",
    },
  ];
  return (
    <div className="metric-strip">
      {items.map((item) => (
        <article className={`mini-metric ${item.tone}`} key={item.label}>
          <span>{getMetricDefinition(item.key)?.clinicianName || item.label}<MetricHelpTooltip metricKey={item.key} ci={ciForMetric(item.key, metrics)} /></span>
          <strong>{metricValue(item.value)}</strong>
          <small>{formatCI(ciForMetric(item.key, metrics)) || item.helper}</small>
        </article>
      ))}
    </div>
  );
}
