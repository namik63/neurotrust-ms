import type { ValidationMode } from "../types";

const modes: Array<{ id: ValidationMode; title: string; copy: string }> = [
  { id: "simple_demo", title: "Simple demo", copy: "One generated case. Fastest way to test the full report." },
  { id: "five_case_demo", title: "5-case demo", copy: "Prepared five-case demo batch, or a generated five-case fallback." },
  { id: "batch", title: "Batch validation", copy: "Upload one to five case-matched MRI, GT, and AI prediction sets." },
];

export function ModeSelector({ mode, onMode }: { mode: ValidationMode; onMode: (mode: ValidationMode) => void }) {
  return (
    <div className="mode-grid">
      {modes.map((item) => (
        <button key={item.id} className={`mode-card ${mode === item.id ? "active" : ""}`} onClick={() => onMode(item.id)}>
          <span>{item.title}</span>
          <p>{item.copy}</p>
        </button>
      ))}
    </div>
  );
}
