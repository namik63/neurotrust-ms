import { useState } from "react";
import type { ValidationResult } from "../types";
import { BatchCaseTable } from "./BatchCaseTable";

function display(value: any) {
  if (value === null || value === undefined || value === "") return "not available";
  if (typeof value === "number") return value.toFixed(Math.abs(value) > 10 ? 1 : 3);
  return String(value);
}

export function LesionAnalysisPanel({ result }: { result: ValidationResult }) {
  const metrics = result.subject_metrics || {};
  const clusters = result.cluster_metrics || [];
  const [filter, setFilter] = useState("all");
  const complexClusters = clusters.filter((c) => c.cluster_type && c.cluster_type !== "one-to-one").length;
  const items = [
    ["GT lesion count", metrics.gt_lesion_count],
    ["Predicted lesion count", metrics.pred_lesion_count],
    ["Matched lesion count", metrics.matched_lesion_count],
    ["Missed lesions / scan", metrics.fn_lesions_per_scan],
    ["False-positive lesions / scan", metrics.fp_lesions_per_scan],
    ["Lesion recall", metrics.lesion_recall],
    ["Lesion precision", metrics.lesion_precision],
    ["Lesion F1", metrics.lesion_f1],
    ["Split/merge topology warnings", complexClusters || metrics.topology_warning_count],
  ];

  return (
    <div className="lesion-panel">
      <div className="lesion-grid">
        {items.map(([label, value]) => (
          <article className="lesion-stat" key={label as string}>
            <span>{label}</span>
            <strong>{display(value)}</strong>
          </article>
        ))}
      </div>
      {result.mode === "batch" ? <BatchCaseTable result={result} /> : <LesionTable result={result} filter={filter} onFilter={setFilter} />}
    </div>
  );
}

function LesionTable({ result, filter, onFilter }: { result: ValidationResult; filter: string; onFilter: (value: string) => void }) {
  const gt = (result.lesion_metrics || []).map((row: any) => ({ ...row, row_type: "GT" }));
  const pred = (result.prediction_lesions || []).map((row: any) => ({ ...row, row_type: "Prediction" }));
  const rows = [...gt, ...pred].filter((row) => {
    if (filter === "missed") return row.row_type === "GT" && !row.lesion_detected;
    if (filter === "fp") return row.row_type === "Prediction" && row.false_positive;
    if (filter === "small") return ["tiny", "small"].includes(row.lesion_size_bin);
    if (["periventricular", "juxtacortical_or_cortical", "infratentorial"].includes(filter)) return String(row.all_locations || "").includes(filter);
    if (filter === "high-risk") return row.high_risk_flag;
    return true;
  });
  if (!gt.length && !pred.length) return <div className="empty-state subtle">No lesion-level rows returned.</div>;
  return (
    <section className="batch-panel">
      <div className="batch-toolbar">
        <h3>Lesion table</h3>
        <select value={filter} onChange={(e) => onFilter(e.target.value)}>
          <option value="all">All</option>
          <option value="missed">Missed only</option>
          <option value="fp">False positives</option>
          <option value="small">Tiny/small</option>
          <option value="periventricular">Periventricular</option>
          <option value="juxtacortical_or_cortical">JC/cortical</option>
          <option value="infratentorial">Infratentorial</option>
          <option value="high-risk">High-risk</option>
        </select>
      </div>
      <div className="table-wrap">
        <table className="case-table">
          <thead><tr><th>Type</th><th>ID</th><th>Status</th><th>Volume</th><th>Location</th><th>Dice</th></tr></thead>
          <tbody>
            {rows.slice(0, 80).map((row: any, index: number) => (
              <tr key={`${row.row_type}-${row.lesion_id || row.pred_lesion_id}-${index}`}>
                <td>{row.row_type}</td>
                <td>{row.lesion_id || row.pred_lesion_id}</td>
                <td>{row.row_type === "GT" ? (row.lesion_detected ? "detected" : "missed") : (row.false_positive ? "FP" : "matched")}</td>
                <td>{display(row.lesion_volume_mm3 ?? row.pred_volume_mm3)}</td>
                <td>{String(row.primary_location || row.location_label_if_available || "unknown").replaceAll("_", " ")}</td>
                <td>{display(row.lesion_dice)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
