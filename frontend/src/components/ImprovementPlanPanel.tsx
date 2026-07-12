import type { ValidationResult } from "../types";
import { improvementPlan, recommendationStatus, clinicalSummary } from "../metrics/clinicalInsights";

export function ImprovementPlanPanel({ result }: { result: ValidationResult }) {
  const items = improvementPlan(result);
  const summary = clinicalSummary(result);
  const metrics = result.subject_metrics || {};
  const cases = metrics.successful_case_count ?? metrics.case_count ?? result.model_passport?.number_of_cases_tested ?? 1;
  return (
    <div className="improvement-panel">
      <section className="clinical-card lead">
        <span>Deployment guidance</span>
        <h3>{recommendationStatus(result)}</h3>
        <p>{summary.uncertainty}</p>
        <div className="guidance-grid">
          <div><b>Human review level</b><p>{items.some((item) => item.priority === "high") ? "Focused review" : "Routine review with watchlist"}</p></div>
          <div><b>Cases tested</b><p>{cases}</p></div>
          <div><b>Primary review focus</b><p>{summary.reviewFocus.slice(0, 3).join(", ")}</p></div>
          <div><b>Next validation</b><p>{cases < 10 ? "Add more validation cases, especially edge-case regions." : "Continue scanner/protocol-stratified monitoring."}</p></div>
        </div>
      </section>
      {items.map((item) => (
        <article className={`improvement-card ${item.priority}`} key={item.failurePattern}>
          <div className="improvement-head">
            <span>{item.priority} priority</span>
            <h3>{item.failurePattern}</h3>
          </div>
          <p className="evidence">{item.observedEvidence}</p>
          <div className="improvement-columns">
            <ListBlock title="Possible causes" items={item.possibleCauses} />
            <ListBlock title="Model/data improvement" items={[...item.modelImprovementActions, ...item.dataImprovementActions]} />
            <ListBlock title="Deployment safeguard" items={item.deploymentSafeguards} />
            <ListBlock title="Recheck after change" items={item.metricsToRecheck} />
          </div>
        </article>
      ))}
    </div>
  );
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <b>{title}</b>
      <ul>
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}
