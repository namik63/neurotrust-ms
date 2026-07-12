import type { ValidationResult } from "../types";

function fmt(value: any) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return value.toFixed(Math.abs(value) > 10 ? 1 : 3);
  return String(value).replaceAll("_", " ");
}

export function ReliabilityPanel({ result }: { result: ValidationResult }) {
  const rows = result.reliability_metrics || [];
  const summary = result.reliability_summary || {};
  const metrics = result.subject_metrics || {};
  const cases = metrics.successful_case_count ?? metrics.case_count ?? result.model_passport?.number_of_cases_tested ?? 1;
  const widest = [...rows].sort((a: any, b: any) => Number(b.iqr ?? 0) - Number(a.iqr ?? 0))[0];
  const worstRecall = rows.find((row: any) => row.metric === "lesion_recall");
  const sampleStatement = cases < 5
    ? "Very small validation sample; treat intervals and worst-case behavior as high-priority review signals."
    : cases < 10
      ? "Small validation sample; reliability should be updated as more cases are added."
      : "Local sample size supports more stable reliability estimates.";
  if (!rows.length) return <div className="empty-state">Reliability spread appears after batch validation with at least one successful case.</div>;
  return (
    <div className="reliability-panel">
      <section className="guidance-grid">
        <article className="clinical-card lead">
          <span>Hospital reliability</span>
          <h3>{fmt(summary.overall_reliability)}</h3>
          <p>{sampleStatement}</p>
        </article>
        <article className="clinical-card">
          <span>Worst-case detection</span>
          <strong>{worstRecall?.worst_case_id || "—"}</strong>
          <p>{worstRecall ? `Lesion detection dropped to ${fmt(worstRecall.worst_case_value)} in this case.` : "No lesion recall spread returned."}</p>
        </article>
        <article className="clinical-card">
          <span>Most variable metric</span>
          <strong>{widest ? fmt(widest.metric) : "—"}</strong>
          <p>{widest ? `Middle-case spread ${fmt(widest.p25)}–${fmt(widest.p75)}.` : "No variability estimate returned."}</p>
        </article>
      </section>
      <details className="method-card reliability-details">
        <summary>Research table: average, best case, worst case</summary>
        <div className="table-wrap">
          <table className="case-table">
            <thead><tr><th>Metric</th><th>Band</th><th>Mean</th><th>Worst case</th><th>Worst</th><th>Best case</th><th>Best</th><th>P25–P75</th></tr></thead>
            <tbody>
              {rows.map((row: any) => (
                <tr key={row.metric}>
                  <td>{fmt(row.metric)}</td>
                  <td>{fmt(row.reliability_band)}</td>
                  <td>{fmt(row.mean)}</td>
                  <td>{row.worst_case_id}</td>
                  <td>{fmt(row.worst_case_value)}</td>
                  <td>{row.best_case_id}</td>
                  <td>{fmt(row.best_case_value)}</td>
                  <td>{fmt(row.p25)}–{fmt(row.p75)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
