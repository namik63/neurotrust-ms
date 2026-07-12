import type { ValidationResult } from "../types";

function fmt(value: any) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return value.toFixed(Math.abs(value) > 10 ? 1 : 3);
  return String(value).replaceAll("_", " ");
}

export function HardCasesPanel({ result }: { result: ValidationResult }) {
  const rows = result.hard_case_metrics || [];
  const summary = result.hard_case_summary || {};
  if (!rows.length) return <div className="empty-state">No hard-case groups were triggered for this upload.</div>;
  const chips = [
    ["Worst group", summary.worst_group],
    ["Best group", summary.best_group],
    ["Most unstable", summary.most_unstable_group],
    ["Highest FP", summary.highest_fp_group],
    ["Highest missed-location", summary.highest_missed_location_group],
  ].filter(([, value]) => value);
  return (
    <div className="hardcase-panel">
      <div className="chip-row">{chips.map(([label, value]) => <span key={label}><b>{label}</b>{fmt(value)}</span>)}</div>
      <div className="capability-grid">
        {rows.map((row: any) => (
          <article className="capability-card" key={row.hard_case_group}>
            <div className="capability-head">
              <h3>{fmt(row.hard_case_group)}</h3>
              <strong>{row.subject_count}</strong>
            </div>
            <dl className="mini-pairs">
              <div><dt>Dice</dt><dd>{fmt(row.mean_dice_voxel)}</dd></div>
              <div><dt>Recall</dt><dd>{fmt(row.mean_lesion_recall)}</dd></div>
              <div><dt>Precision</dt><dd>{fmt(row.mean_lesion_precision)}</dd></div>
              <div><dt>FP/scan</dt><dd>{fmt(row.mean_fp_lesions_per_scan)}</dd></div>
              <div><dt>FN/scan</dt><dd>{fmt(row.mean_fn_lesions_per_scan)}</dd></div>
              <div><dt>High-risk miss</dt><dd>{fmt(row.mean_high_risk_location_miss_rate)}</dd></div>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}
