import type { ValidationResult } from "../types";
import { formatCI, wilsonInterval } from "../metrics/confidence";
import { cautionLabel, fmt, locationLabel } from "../metrics/clinicalInsights";

function pct(value: any) {
  return typeof value === "number" && value === value ? Math.max(0, Math.min(100, value * 100)) : 0;
}

export function AnatomyPanel({ result }: { result: ValidationResult }) {
  const metrics = result.subject_metrics || {};
  const cases = metrics.successful_case_count ?? metrics.case_count ?? result.model_passport?.number_of_cases_tested ?? 1;
  const rows = (result.location_metrics || []).filter((row: any) => {
    if (row.location !== "corpus_callosum") return true;
    return Number(row.location_gt_lesion_count || 0) > 0 || Number(row.location_pred_lesion_count || 0) > 0;
  });
  const topology = Object.fromEntries((result.location_topology_metrics || []).map((row: any) => [row.location, row]));
  if (!rows.length) return <div className="empty-state">Upload anatomy labels or FreeSurfer subject files to calculate location-specific capability.</div>;
  return (
    <div className="anatomy-panel">
      <div className="section-title compact-title">
        <span>Anatomy Failure Map</span>
        <h2>Location-specific behavior for radiology review.</h2>
      </div>
      <div className="capability-grid">
        {rows.map((row: any) => {
          const topo = topology[row.location] || {};
          const detectionCI = wilsonInterval(
            Number(row.location_matched_lesion_count || 0),
            Number(row.location_gt_lesion_count || 0),
            Number(cases || 1),
          );
          const volumeAgreement = typeof row.location_relative_volume_error === "number"
            ? Math.max(0, 1 - Math.min(1, row.location_relative_volume_error))
            : null;
          const label = cautionLabel(row);
          return (
            <article className="capability-card" key={row.location}>
              <div className="capability-head">
                <div>
                  <h3>{locationLabel(row.location)}</h3>
                  <span className={`caution-pill ${label.toLowerCase().replaceAll(" ", "-")}`}>{label}</span>
                </div>
                <strong>{fmt(row.location_lesion_recall)}</strong>
              </div>
              <div className="bar-metric"><span>Detection rate</span><div><i style={{ width: `${pct(row.location_lesion_recall)}%` }} /></div><b>{fmt(row.location_lesion_recall)}</b></div>
              <div className="bar-metric"><span>Extra candidates</span><div><i style={{ width: `${pct(Math.min(1, Number(row.location_fp_lesions_per_scan || 0) / 3))}%` }} /></div><b>{fmt(row.location_fp_lesions_per_scan)}</b></div>
              <dl className="mini-pairs">
                <div><dt>GT / AI lesions</dt><dd>{fmt(row.location_gt_lesion_count, 0)} / {fmt(row.location_pred_lesion_count, 0)}</dd></div>
                <div><dt>Missed / scan</dt><dd>{fmt(row.location_fn_lesions_per_scan)}</dd></div>
                <div><dt>Volume agreement</dt><dd>{fmt(volumeAgreement)}</dd></div>
                <div><dt>95% interval</dt><dd>{formatCI(detectionCI) || "not enough lesions"}</dd></div>
                <div><dt>Boundary check</dt><dd>{fmt(row.location_boundary_quality_score ?? row.location_mean_matched_lesion_dice)}</dd></div>
                <div><dt>Topology issues</dt><dd>{fmt(topo.location_complex_topology_rate)}</dd></div>
              </dl>
            </article>
          );
        })}
      </div>
    </div>
  );
}
