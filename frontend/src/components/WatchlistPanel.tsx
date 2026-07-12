import type { ValidationResult } from "../types";

function fmt(value: any) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return value.toFixed(Math.abs(value) > 10 ? 1 : 3);
  return String(value).replaceAll("_", " ");
}

function severityRank(value: string) {
  const ranks: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, review: 4 };
  return ranks[value] ?? 9;
}

function targetMeaning(type: string) {
  const map: Record<string, string> = {
    dis_proxy_mismatch_case: "The predicted mask changed the brain-location evidence pattern.",
    infratentorial_missed_lesion: "A missed infratentorial lesion; this location should be reviewed closely.",
    tiny_pv_missed_lesion: "A tiny/small periventricular lesion was missed.",
    tiny_jc_missed_lesion: "A tiny/small juxtacortical or cortical lesion was missed.",
    missed_high_risk_lesion: "A small lesion in an MS-relevant brain location was missed.",
    largest_missed_lesion: "The largest expert lesion not captured by the prediction.",
    false_positive_in_relevant_location: "A prediction-only lesion in a relevant brain location.",
    largest_false_positive: "The largest prediction-only lesion.",
    worst_boundary_match: "A detected lesion with the weakest boundary agreement.",
    split_merge_cluster: "A topology issue where predictions split or merge lesion components.",
  };
  return map[type] || "A validation target selected for manual review.";
}

export function WatchlistPanel({ result, onViewer }: { result: ValidationResult; onViewer: () => void }) {
  const items = [...(result.radiologist_watchlist || [])].sort((a: any, b: any) => {
    return severityRank(a.severity) - severityRank(b.severity) || String(a.subject_id || "").localeCompare(String(b.subject_id || ""));
  });
  const fallbackBlindspots = result.blindspots || [];
  if (!items.length && !fallbackBlindspots.length) return <div className="empty-state">No review priorities were returned for this validation set.</div>;

  if (!items.length) {
    return (
      <div className="watchlist-grid">
        {fallbackBlindspots.slice(0, 8).map((spot: any, index: number) => (
          <article className={`watch-card ${spot.severity || "low"}`} key={`${spot.title}-${index}`}>
            <span>{spot.severity || "review"}</span>
            <h3>{spot.title}</h3>
            <p>{spot.metric_evidence || spot.clinical_meaning || "Review recommended."}</p>
            <div className="watch-actions">
              <button onClick={onViewer}>Jump to viewer</button>
              {result.downloads?.edge_case_report_json && <a href={result.downloads.edge_case_report_json} download>Export evidence</a>}
            </div>
          </article>
        ))}
      </div>
    );
  }

  const grouped = items.reduce<Record<string, any[]>>((acc, item: any) => {
    const key = item.subject_id || "current_case";
    acc[key] = acc[key] || [];
    acc[key].push(item);
    return acc;
  }, {});

  return (
    <div className="subject-watchlist">
      {Object.entries(grouped).map(([subject, rows]) => (
        <section className="subject-watch-section" key={subject}>
          <div className="subject-watch-head">
            <span>Subject</span>
            <h3>{subject}</h3>
            <small>{rows.length} review target{rows.length === 1 ? "" : "s"}</small>
          </div>
          <div className="watchlist-grid compact">
            {rows.slice(0, 6).map((item: any, index: number) => (
              <article className={`watch-card ${item.severity || "low"}`} key={`${subject}-${item.target_type}-${item.lesion_id || item.pred_lesion_id || item.cluster_id || index}`}>
                <span>{item.severity || "review"}</span>
                <h3>{item.title || item.reason || item.target_type}</h3>
                <p>{item.reason || targetMeaning(item.target_type)}</p>
                <dl className="mini-pairs">
                  <div><dt>Meaning</dt><dd>{targetMeaning(item.target_type)}</dd></div>
                  <div><dt>Location</dt><dd>{fmt(item.primary_location)}</dd></div>
                  <div><dt>Size</dt><dd>{fmt(item.size_bin)}</dd></div>
                  <div><dt>Volume mm³</dt><dd>{fmt(item.volume_mm3)}</dd></div>
                  <div><dt>Trigger</dt><dd>{fmt(item.metric_trigger)}</dd></div>
                  <div><dt>ID</dt><dd>{fmt(item.lesion_id ?? item.pred_lesion_id ?? item.cluster_id)}</dd></div>
                </dl>
                <p className="review-action">{item.recommended_action || "Review this case in the viewer."}</p>
                <details className="watch-method">
                  <summary>Show method</summary>
                  <p>{targetMeaning(item.target_type)} The item is generated from the uploaded GT/prediction masks and the case-level validation tables.</p>
                </details>
                <div className="watch-actions">
                  <button disabled={!item.viewer_jump_target} onClick={onViewer}>Jump to viewer</button>
                  {result.downloads?.batch_radiologist_watchlist_json && <a href={result.downloads.batch_radiologist_watchlist_json} download>Export batch watchlist</a>}
                  {result.downloads?.radiologist_watchlist_json && <a href={result.downloads.radiologist_watchlist_json} download>Export watchlist</a>}
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
