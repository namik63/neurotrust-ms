import { useMemo, useState } from "react";
import type { ValidationResult } from "../types";

function format(value: any) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return value.toFixed(3);
  const numeric = Number(value);
  return Number.isNaN(numeric) ? String(value) : numeric.toFixed(3);
}

export function BatchCaseTable({ result }: { result: ValidationResult }) {
  const [query, setQuery] = useState("");
  const rows = result.case_results || [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => String(row.case_id || "").toLowerCase().includes(q));
  }, [query, rows]);
  const visible = filtered.slice(0, 50);

  if (!rows.length) return null;
  return (
    <section className="batch-panel">
      <div className="batch-toolbar">
        <div>
          <h3>Batch case table</h3>
          <p>{filtered.length} of {rows.length} cases shown by current filter. Export CSV for the full table.</p>
        </div>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search case ID…" />
      </div>
      <div className="table-wrap">
        <table className="case-table">
          <thead>
            <tr>
              <th>Case</th>
              <th>Status</th>
              <th>Dice</th>
              <th>Lesion recall</th>
              <th>Lesion precision</th>
              <th>HTML</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.case_id}>
                <td>{row.case_id}</td>
                <td>{row.status || "computed"}</td>
                <td>{format(row.dice_voxel)}</td>
                <td>{format(row.lesion_recall)}</td>
                <td>{format(row.lesion_precision)}</td>
                <td>{row.case_html ? <a href={row.case_html} target="_blank" rel="noreferrer">open</a> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length > 50 && <p className="table-note">Showing first 50 filtered cases. Download the batch CSV for all rows.</p>}
    </section>
  );
}
