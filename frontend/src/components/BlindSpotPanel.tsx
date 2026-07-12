import type { ValidationResult } from "../types";

export function BlindSpotPanel({ result }: { result: ValidationResult }) {
  const blindspots = result.blindspots || [];
  if (!blindspots.length) return <div className="empty-state">No blind-spot report was returned for this run.</div>;
  return (
    <div className="blindspot-command-grid">
      {blindspots.map((spot, index) => (
        <article className={`blindspot-card ${spot.severity || "low"}`} key={`${spot.title}-${index}`}>
          <div className="blindspot-head">
            <span>{spot.severity || "review"}</span>
            <h3>{spot.title || "Untitled blind spot"}</h3>
          </div>
          <p className="evidence">{spot.metric_evidence || "No metric evidence supplied."}</p>
          <p>{spot.clinical_meaning || "Clinical interpretation not available."}</p>
          <div className="review-action">Manual review: {spot.manual_review_action || "qualified review required."}</div>
        </article>
      ))}
    </div>
  );
}
