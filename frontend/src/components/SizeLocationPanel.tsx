import { useState } from "react";
import type { ValidationResult } from "../types";

const locations = ["periventricular", "juxtacortical_or_cortical", "infratentorial", "deep_white_matter_or_other"];
const sizes = ["tiny", "small", "medium", "large"];
const options = [
  ["lesion_recall", "Recall"],
  ["lesion_precision", "Precision"],
  ["missed_per_scan", "Missed / scan"],
  ["fp_per_scan", "FP / scan"],
  ["mean_matched_dice", "Mean matched Dice"],
];

function fmt(value: any) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return value.toFixed(Math.abs(value) > 10 ? 1 : 3);
  return String(value);
}

function locLabel(value: string) {
  return value.replace("periventricular", "PV").replace("juxtacortical_or_cortical", "JC/cortical").replace("infratentorial", "IT").replace("deep_white_matter_or_other", "DWM/other");
}

export function SizeLocationPanel({ result }: { result: ValidationResult }) {
  const [metric, setMetric] = useState("lesion_recall");
  const rows = result.size_location_metrics || [];
  const byKey = Object.fromEntries(rows.map((row: any) => [`${row.location}|${row.size_bin}`, row]));
  if (!rows.length) return <div className="empty-state">Size × location metrics require anatomy labels and lesion masks.</div>;
  return (
    <div className="matrix-panel">
      <div className="batch-toolbar">
        <div>
          <h3>Size × location matrix</h3>
          <p>Small lesions in important locations are shown separately from global averages.</p>
        </div>
        <select value={metric} onChange={(e) => setMetric(e.target.value)}>
          {options.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </div>
      <div className="matrix-grid" style={{ "--cols": sizes.length } as React.CSSProperties}>
        <strong>Location</strong>
        {sizes.map((size) => <strong key={size}>{size}</strong>)}
        {locations.flatMap((location) => [
          <strong key={`${location}-label`}>{locLabel(location)}</strong>,
          ...sizes.map((size) => {
            const row = byKey[`${location}|${size}`] || {};
            return <span key={`${location}-${size}`}>{fmt(row[metric])}<small>{fmt(row.gt_lesion_count)} GT</small></span>;
          }),
        ])}
      </div>
    </div>
  );
}
