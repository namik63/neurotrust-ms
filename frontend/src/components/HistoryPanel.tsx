import type { AccessSession, ValidationHistoryItem } from "../types";
import { fmt } from "../metrics/clinicalInsights";

function dateLabel(value?: string) {
  if (!value) return "unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function summaryLine(item: ValidationHistoryItem) {
  const summary = item.summary || {};
  const lesionRecall = summary.lesion_recall;
  const precision = summary.lesion_precision;
  const cases = summary.case_count || summary.successful_case_count || summary.number_of_cases_tested;
  return [
    cases ? `${cases} case${Number(cases) === 1 ? "" : "s"}` : null,
    lesionRecall !== undefined ? `recall ${fmt(lesionRecall)}` : null,
    precision !== undefined ? `precision ${fmt(precision)}` : null,
    summary.recommendation_status ? String(summary.recommendation_status).replaceAll("_", " ") : null,
  ].filter(Boolean).join(" · ") || "Clinical summary available when the result file is still retained.";
}

export function HistoryPanel({
  history,
  session,
  error,
  busy,
  onOpen,
  onValidate,
  onRefresh,
}: {
  history: ValidationHistoryItem[];
  session: AccessSession;
  error?: string;
  busy?: boolean;
  onOpen: (runId: string) => void;
  onValidate: () => void;
  onRefresh: () => void;
}) {
  const demoRuns = history.filter((item) => String(item.source || "").includes("demo")).length;
  const batchRuns = history.filter((item) => String(item.source || "").includes("batch")).length;
  const lastRun = history[0];
  return (
    <main className="history-page page-shell">
      <section className="results-hero history-hero">
        <div>
          <p className="eyebrow">Password-protected validation history</p>
          <h1>{session.welcome_back ? "Welcome back." : "Your validation vault is ready."}</h1>
          <p>
            Saved runs are linked to this email after password verification, so recent reports can be reopened while raw passwords stay out of storage.
          </p>
        </div>
        <div className="result-actions">
          <button className="secondary dark" onClick={onRefresh}>Refresh</button>
          <button className="primary glow" onClick={onValidate}>Start new validation</button>
        </div>
      </section>

      {error && <p className="form-error">{error}</p>}

      <section className="history-stats clinical-summary-grid">
        <article className="clinical-card lead">
          <span>Signed in as</span>
          <h3>{session.email}</h3>
          <p>Session expires automatically; closing the browser tab does not expose the access password.</p>
        </article>
        <article className="clinical-card">
          <span>Total runs</span>
          <strong>{history.length}</strong>
          <p>Saved validation records visible to this login.</p>
        </article>
        <article className="clinical-card">
          <span>Demo / batch</span>
          <strong>{demoRuns} / {batchRuns}</strong>
          <p>Prepared demo evidence and uploaded batch evidence stay separated.</p>
        </article>
        <article className="clinical-card">
          <span>Last activity</span>
          <strong>{lastRun ? dateLabel(lastRun.created_at) : "No runs yet"}</strong>
          <p>{lastRun?.project_id || "Run the 5-case demo or upload a batch to populate analytics."}</p>
        </article>
      </section>

      <section className="history-list glass-section">
        <div className="section-title">
          <span>Past validations</span>
          <h2>Open retained results</h2>
        </div>
        {!history.length ? (
          <div className="empty-state">No validation records are saved for this email yet.</div>
        ) : (
          <div className="history-grid">
            {history.map((item) => (
              <article className="history-card" key={item.run_id}>
                <div>
                  <span>{item.source?.replaceAll("_", " ") || "validation run"}</span>
                  <h3>{item.project_id || item.case_id || item.run_id}</h3>
                  <p>{summaryLine(item)}</p>
                </div>
                <dl>
                  <div><dt>Created</dt><dd>{dateLabel(item.created_at)}</dd></div>
                  <div><dt>Model</dt><dd>{item.model_name || "Uploaded AI model"}</dd></div>
                  <div><dt>Status</dt><dd>{item.status || "completed"}</dd></div>
                </dl>
                <button className="primary small" disabled={busy} onClick={() => onOpen(item.run_id)}>Open result</button>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
