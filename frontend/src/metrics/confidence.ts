export type ConfidenceInterval = {
  estimate: number;
  lower: number;
  upper: number;
  method: "wilson";
  level: 0.95;
  n: number;
  uncertaintyLabel: "low uncertainty" | "moderate uncertainty" | "high uncertainty" | "very high uncertainty";
};

export function uncertaintyLabel(nCases: number, denominator: number) {
  if (nCases < 5 || denominator < 10) return "very high uncertainty";
  if (nCases < 10 || denominator < 25) return "high uncertainty";
  if (denominator < 100) return "moderate uncertainty";
  return "low uncertainty";
}

export function wilsonInterval(successes: number | null | undefined, trials: number | null | undefined, nCases = 1): ConfidenceInterval | null {
  if (successes === null || successes === undefined || trials === null || trials === undefined || trials <= 0) return null;
  const z = 1.959963984540054;
  const n = trials;
  const phat = Math.max(0, Math.min(1, successes / n));
  const z2 = z * z;
  const denom = 1 + z2 / n;
  const center = (phat + z2 / (2 * n)) / denom;
  const margin = (z * Math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n)) / denom;
  return {
    estimate: phat,
    lower: Math.max(0, center - margin),
    upper: Math.min(1, center + margin),
    method: "wilson",
    level: 0.95,
    n,
    uncertaintyLabel: uncertaintyLabel(nCases, n),
  };
}

export function ciForMetric(key: string, metrics: Record<string, any>): ConfidenceInterval | null {
  const nCases = Number(metrics.successful_case_count ?? metrics.case_count ?? 1);
  if (key === "lesion_recall") {
    return wilsonInterval(metrics.matched_lesion_count, metrics.gt_lesion_count, nCases);
  }
  if (key === "lesion_precision") {
    return wilsonInterval(metrics.matched_lesion_count, metrics.pred_lesion_count, nCases);
  }
  if (key === "high_risk_location_miss_rate") {
    const total = metrics.high_risk_location_gt_count;
    const missed = metrics.high_risk_location_missed_count;
    if (total === null || total === undefined || missed === null || missed === undefined) return null;
    return wilsonInterval(missed, total, nCases);
  }
  return null;
}

export function formatCI(ci: ConfidenceInterval | null) {
  if (!ci) return "";
  return `95% CI ${ci.lower.toFixed(2)}–${ci.upper.toFixed(2)}`;
}
