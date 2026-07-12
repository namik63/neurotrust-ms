import type { ValidationResult } from "../types";

const groups = [
  { id: "reports", title: "Clinical reports", match: ["html", "json", "report"] },
  { id: "metrics", title: "Research tables", match: ["csv", "metrics", "summary"] },
  { id: "governance", title: "Model evidence package", match: ["passport", "governance"] },
  { id: "visuals", title: "Viewer assets", match: ["png", "preview", "viewer", "image"] },
];

function label(key: string) {
  return key.replaceAll("_", " ");
}

function groupFor(key: string) {
  const lower = key.toLowerCase();
  return groups.find((group) => group.match.some((token) => lower.includes(token)))?.id || "reports";
}

export function ExportCenter({ result }: { result: ValidationResult }) {
  const entries = Object.entries(result.downloads || {});
  if (!entries.length) return <div className="empty-state">No downloadable outputs were returned.</div>;
  return (
    <div className="export-grid">
      {groups.map((group) => {
        const groupEntries = entries.filter(([key]) => groupFor(key) === group.id);
        if (!groupEntries.length) return null;
        return (
          <section className="export-group" key={group.id}>
            <h3>{group.title}</h3>
            <div>
              {groupEntries.map(([key, url]) => (
                <a href={url} download key={key}>
                  <span>{label(key)}</span>
                  <small>download</small>
                </a>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
