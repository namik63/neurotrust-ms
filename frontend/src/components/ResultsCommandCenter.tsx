import type { ResultTab, ValidationResult } from "../types";
import { useEffect, useMemo, useState } from "react";
import { AnatomyPanel } from "./AnatomyPanel";
import { EdgeCaseLogicPanel } from "./EdgeCaseLogicPanel";
import { ExportCenter } from "./ExportCenter";
import { HardCasesPanel } from "./HardCasesPanel";
import { InteractiveOverlayViewer } from "./InteractiveOverlayViewer";
import { ImprovementPlanPanel } from "./ImprovementPlanPanel";
import { LesionAnalysisPanel } from "./LesionAnalysisPanel";
import { MethodVault } from "./MethodVault";
import { MetricStrip } from "./MetricStrip";
import { ReliabilityPanel } from "./ReliabilityPanel";
import { SizeLocationPanel } from "./SizeLocationPanel";
import { WatchlistPanel } from "./WatchlistPanel";
import { clinicalSummary, fmt, locationLabel, recommendationStatus } from "../metrics/clinicalInsights";

const tabLabels: Record<ResultTab, string> = {
  overview: "Clinical Summary",
  watchlist: "Review Priorities",
  anatomy: "Anatomy Failure Map",
  sizeLocation: "Size × Location",
  hardCases: "Hard Cases",
  reliability: "Hospital Reliability",
  improvement: "Improvement Plan",
  edgeCases: "Safety / Edge / Privacy",
  lesions: "Lesions",
  viewer: "3D Viewer",
  vault: "Research Appendix",
  exports: "Exports",
  modelComparison: "Model Comparison",
};

export function ResultsCommandCenter({
  result,
  activeTab,
  onTab,
  onHome,
  onValidate,
}: {
  result: ValidationResult;
  activeTab: ResultTab;
  onTab: (tab: ResultTab) => void;
  onHome: () => void;
  onValidate: () => void;
}) {
  const [mode, setMode] = useState<"clinician" | "research">("clinician");
  const clinicianTabs: ResultTab[] = ["overview", "watchlist", "anatomy", "reliability", "improvement", "edgeCases", "viewer", "vault", "exports", "modelComparison"];
  const researchTabs: ResultTab[] = ["overview", "watchlist", "anatomy", "sizeLocation", "hardCases", "reliability", "improvement", "edgeCases", "lesions", "viewer", "vault", "exports", "modelComparison"];
  const tabs = (mode === "clinician" ? clinicianTabs : researchTabs).filter((tab) => {
    if (tab === "viewer") return Boolean(result.viewer || result.downloads?.preview_png || result.downloads?.first_case_preview_png);
    if (tab === "watchlist") return Boolean(result.radiologist_watchlist?.length || result.blindspots?.length);
    if (tab === "exports") return Boolean(Object.keys(result.downloads || {}).length);
    if (tab === "sizeLocation") return Boolean(result.size_location_metrics?.length);
    if (tab === "hardCases") return Boolean(result.hard_case_metrics?.length);
    if (tab === "reliability") return Boolean(result.reliability_metrics?.length);
    if (tab === "modelComparison") return Boolean(result.model_comparison);
    return true;
  });
  const summary = useMemo(() => clinicalSummary(result), [result]);
  useEffect(() => {
    if (!tabs.includes(activeTab)) {
      onTab("overview");
    }
  }, [activeTab, onTab, tabs]);

  return (
    <main className="results page-shell">
      <section className="results-hero">
        <div>
          <p className="eyebrow">Hospital model behavior profile</p>
          <h1>{summary.headline}</h1>
          <p>{summary.mainTakeaway}</p>
        </div>
        <div className="result-actions">
          <div className="view-toggle" aria-label="Result view mode">
            <button className={mode === "clinician" ? "active" : ""} onClick={() => setMode("clinician")}>Clinician view</button>
            <button className={mode === "research" ? "active" : ""} onClick={() => setMode("research")}>Research view</button>
          </div>
          <button className="secondary dark" onClick={onValidate}>Validate another set</button>
          <button className="secondary dark" onClick={onHome}>Return home</button>
        </div>
      </section>

      <div className="tabs" role="tablist" aria-label="Result sections">
        {tabs.map((tab) => (
          <button key={tab} role="tab" aria-selected={activeTab === tab} className={activeTab === tab ? "active" : ""} onClick={() => onTab(tab)}>
            {tabLabels[tab]}
          </button>
        ))}
      </div>

      <section className="tab-panel">
        {activeTab === "overview" && <Overview result={result} />}
        {activeTab === "watchlist" && <WatchlistPanel result={result} onViewer={() => onTab("viewer")} />}
        {activeTab === "anatomy" && <AnatomyPanel result={result} />}
        {activeTab === "sizeLocation" && <SizeLocationPanel result={result} />}
        {activeTab === "hardCases" && <HardCasesPanel result={result} />}
        {activeTab === "reliability" && <ReliabilityPanel result={result} />}
        {activeTab === "improvement" && <ImprovementPlanPanel result={result} />}
        {activeTab === "edgeCases" && <EdgeCaseLogicPanel result={result} />}
        {activeTab === "lesions" && <LesionAnalysisPanel result={result} />}
        {activeTab === "viewer" && <InteractiveOverlayViewer result={result} />}
        {activeTab === "vault" && <MethodVault result={result} />}
        {activeTab === "exports" && <ExportCenter result={result} />}
        {activeTab === "modelComparison" && <ModelComparisonPanel result={result} />}
      </section>
    </main>
  );
}

function Overview({ result }: { result: ValidationResult }) {
  const metrics = result.subject_metrics || {};
  const recommendation = result.deployment_recommendation;
  const ci = recommendation?.confidence_interval;
  const summary = clinicalSummary(result);
  return (
    <div className="overview-grid">
      <section className="clinical-summary-grid">
        <article className="clinical-card lead">
          <span>Main takeaway</span>
          <h3>{summary.mainTakeaway}</h3>
          <p>{summary.uncertainty}</p>
        </article>
        <article className="clinical-card">
          <span>Where it looks strongest</span>
          <strong>{summary.strongest}</strong>
          <p>Use this as uploaded validation evidence, not as a guarantee for future cases.</p>
        </article>
        <article className="clinical-card">
          <span>Where to be most careful</span>
          <strong>{summary.weakest}</strong>
          <p>{summary.reviewFocus.join(", ")}</p>
        </article>
        <article className="clinical-card">
          <span>Validation guidance</span>
          <strong>{recommendationStatus(result)}</strong>
          <p>{ci ? `Recommendation confidence interval ${ci[0]}–${ci[1]}.` : "Confidence grows with more validation cases and lesion events."}</p>
        </article>
      </section>
      <MetricStrip result={result} />
      <section className="overview-card">
        <h3>Confidence / uncertainty</h3>
        <strong>{recommendation?.confidence_level !== undefined ? `${Math.round(recommendation.confidence_level * 100)}%` : "pending"}</strong>
        <p>{ci ? `Interval ${ci[0]}–${ci[1]}, based on ${metrics.successful_case_count ?? metrics.case_count ?? 1} uploaded validation case(s).` : "Run a validation batch to estimate recommendation confidence."}</p>
      </section>
      {result.failure_fingerprint?.tags?.length > 0 && (
        <section className="overview-card">
          <h3>Failure fingerprint</h3>
          <strong>{result.failure_fingerprint.primary_failure_fingerprint || result.failure_fingerprint.primary?.tag || "not available"}</strong>
          <p>{result.failure_fingerprint.fingerprint_summary_sentence || result.failure_fingerprint.primary?.evidence || "No dominant failure mode."}</p>
        </section>
      )}
      <section className="overview-card">
        <h3>Primary review focus</h3>
        <strong>{result.trust_gap_summary || "No dominant gap"}</strong>
        <p>{result.dice_trap_detector?.active ? "Overlap looks acceptable, but lesion/location evidence disagrees. Review watchlist targets first." : "No overlap-vs-lesion evidence conflict was triggered in this summary."}</p>
      </section>
      <section className="overview-card">
        <h3>Research snapshot</h3>
        <details>
          <summary>Voxel, surface, and volume audit metrics</summary>
          <p>Dice {metrics.dice_voxel?.toFixed?.(3) ?? "—"} · HD95 {metrics.hd95_mm?.toFixed?.(2) ?? metrics.mean_hd95_mm?.toFixed?.(2) ?? "—"} · ASSD {metrics.assd_mm?.toFixed?.(2) ?? metrics.mean_assd_mm?.toFixed?.(2) ?? "—"} · IoU {metrics.iou_voxel?.toFixed?.(3) ?? "—"}</p>
        </details>
      </section>
      {result.location_metrics?.length ? (
        <section className="overview-card">
          <h3>Location cautions</h3>
          <p>{result.location_metrics.filter((row: any) => Number(row.location_gt_lesion_count || 0) > 0).slice(0, 4).map((row: any) => `${locationLabel(row.location)}: detection ${fmt(row.location_lesion_recall)}`).join(" · ")}</p>
        </section>
      ) : null}
    </div>
  );
}

function ModelComparisonPanel({ result }: { result: ValidationResult }) {
  const comparison = result.model_comparison;
  if (!comparison) return <div className="empty-state">Upload comparable outputs from more than one model to enable model comparison.</div>;
  return (
    <section className="overview-card">
      <h3>Model comparison</h3>
      <pre className="json-preview">{JSON.stringify(comparison, null, 2)}</pre>
    </section>
  );
}
