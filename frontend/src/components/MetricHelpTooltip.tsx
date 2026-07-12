import { useState } from "react";
import { getMetricDefinition } from "../metrics/metricDefinitions";
import type { ConfidenceInterval } from "../metrics/confidence";

export function MetricHelpTooltip({ metricKey, ci }: { metricKey: string; ci?: ConfidenceInterval | null }) {
  const [open, setOpen] = useState(false);
  const definition = getMetricDefinition(metricKey);
  if (!definition) return null;
  return (
    <span className="metric-help">
      <button
        type="button"
        aria-label={`Explain ${definition.displayName}`}
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onBlur={() => setOpen(false)}
      >
        ?
      </button>
      {open && (
        <span className="metric-popover" role="tooltip">
          <strong>{definition.clinicianName}</strong>
          <span><b>Plain meaning:</b> {definition.plainMeaning}</span>
          <span><b>Clinical meaning:</b> {definition.clinicalWhyItMatters}</span>
          <span><b>Interpretation:</b> {definition.interpretation}</span>
          <span><b>Limitation:</b> {definition.limitation}</span>
          <span><b>Confidence interval:</b> {ci ? `${ci.lower.toFixed(2)}–${ci.upper.toFixed(2)} (${ci.uncertaintyLabel})` : definition.showCI ? "Shown when enough count data is available." : "Not shown for this metric."}</span>
        </span>
      )}
    </span>
  );
}
