import type { ValidationResult } from "../types";
import { edgeCaseLogic } from "../metrics/edgeCaseLogic";

const statusLabel = {
  handled: "Handled",
  review: "Review signal",
  not_applicable: "Not applicable",
};

export function EdgeCaseLogicPanel({ result }: { result: ValidationResult }) {
  const cards = edgeCaseLogic(result);
  return (
    <div className="edgecase-panel">
      <section className="clinical-card lead">
        <span>Responsible AI controls</span>
        <h3>Safety, edge-case, privacy, and failure-mode handling.</h3>
        <p>This tab lists the implemented safeguards, including rules that did not trigger for this uploaded dataset. The current-result line shows whether each safeguard was active, triggered, or not applicable here.</p>
      </section>
      <div className="edgecase-grid">
        {cards.map((card) => (
          <article className={`edgecase-card ${card.status}`} key={card.title}>
            <div className="edgecase-head">
              <span>{statusLabel[card.status]}</span>
              <h3>{card.title}</h3>
            </div>
            <dl className="edgecase-pairs">
              <div><dt>Trigger</dt><dd>{card.trigger}</dd></div>
              <div><dt>Current result</dt><dd>{card.currentSignal}</dd></div>
              <div><dt>How it is handled</dt><dd>{card.howHandled}</dd></div>
              <div><dt>Where it appears</dt><dd>{card.whereShown}</dd></div>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}
