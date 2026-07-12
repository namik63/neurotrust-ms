import type { ValidationResult } from "../types";

function listValue(value: any) {
  if (Array.isArray(value)) return value.join(", ");
  return value || "not available";
}

export function ModelPassportPanel({ result }: { result: ValidationResult }) {
  const passport = result.model_passport;
  if (!passport) return <div className="empty-state">No model passport was returned for this run.</div>;
  const notValidated = passport.not_validated_for || [];
  return (
    <div className="passport-panel">
      <div className="passport-hero">
        <div>
          <span>Model/vendor</span>
          <h2>{passport.model_vendor_name || "not available"}</h2>
          <p>{passport.governance_wording || "Local QA summary. Qualified review required."}</p>
        </div>
        <strong>{passport.deployment_recommendation?.status || "not available"}</strong>
      </div>
      <div className="passport-grid">
        <article><span>Cases tested</span><strong>{passport.number_of_cases_tested ?? "not available"}</strong></article>
        <article><span>Intended use</span><strong>{passport.intended_use || "not available"}</strong></article>
        <article><span>Ground truth strategy</span><strong>{passport.ground_truth_strategy || "not available"}</strong></article>
        <article><span>Modalities tested</span><strong>{listValue(passport.modalities_tested)}</strong></article>
      </div>
      <section className="not-validated">
        <h3>Not validated for</h3>
        {notValidated.length ? (
          <ul>{notValidated.map((item: string) => <li key={item}>{item}</li>)}</ul>
        ) : (
          <p className="muted">No explicit not-validated-for list was returned.</p>
        )}
      </section>
    </div>
  );
}
