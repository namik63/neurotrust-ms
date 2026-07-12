import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import type { ValidationMode } from "../types";

const stages = [
  "Upload received",
  "QC safety checks",
  "Mask alignment",
  "Lesion matching",
  "Anatomy assignment",
  "Clinical interpretation",
  "Report assembly",
];

const facts = [
  "Checking geometry, spacing, affine, mask integrity, and upload pairing.",
  "Separating missed expert lesions from prediction-only lesion candidates.",
  "Matching connected lesion components in 3D before summarizing behavior.",
  "Mapping anatomy evidence only when compatible labelmaps are present.",
  "Building the radiologist watchlist from lesion size, location, and failure mode.",
  "Preparing lightweight viewer assets only for returned subjects.",
  "Estimating confidence from the number of uploaded validation cases.",
];

export function ProcessingScreen({ mode, headline }: { mode: ValidationMode; headline?: string }) {
  const [progress, setProgress] = useState(4);
  const [factIndex, setFactIndex] = useState(0);

  useEffect(() => {
    const tick = window.setInterval(() => {
      setProgress((current) => Math.min(94, current + Math.max(0.7, (95 - current) * 0.055)));
    }, 300);
    const factTick = window.setInterval(() => {
      setFactIndex((i) => (i + 1) % facts.length);
    }, 2300);
    return () => {
      window.clearInterval(tick);
      window.clearInterval(factTick);
    };
  }, []);

  const stageIndex = useMemo(() => Math.min(stages.length - 1, Math.floor((progress / 100) * stages.length)), [progress]);
  const stage = stages[stageIndex];

  return (
    <main className="processing page-shell">
      <div className="processing-orb" />
      <section className="processing-card">
        <div className="progress-ring" style={{ "--progress": `${progress * 3.6}deg` } as CSSProperties}>
          <div>
            <strong>{Math.round(progress)}%</strong>
            <span>working</span>
          </div>
        </div>
        <p className="eyebrow">Processing {mode === "batch" ? "batch validation" : mode === "five_case_demo" ? "5-case demo" : "simple demo"}</p>
        <h1>{headline || "Building the clinical evidence profile."}</h1>
        <p className="stage-line">{stage}…</p>
        <div className="stage-list">
          {stages.map((item, index) => (
            <span key={item} className={index === stageIndex ? "active" : index < stageIndex ? "warm" : ""}>
              {item}
            </span>
          ))}
        </div>
        <blockquote>{facts[factIndex]}</blockquote>
        <p className="processing-note">Do not close this tab while validation is running.</p>
      </section>
    </main>
  );
}
