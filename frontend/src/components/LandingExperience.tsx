import { motion, useReducedMotion } from "motion/react";
import type { AccessSession, ValidationHistoryItem } from "../types";
import { SafetyLine } from "./SafetyLine";

export function LandingExperience({
  onEnter,
  onSimpleDemo,
  onFiveCaseDemo,
  onVault,
  onHistory,
  hasResult,
  busy,
  session,
  history,
}: {
  onEnter: () => void;
  onSimpleDemo: () => void;
  onFiveCaseDemo: () => void;
  onVault: () => void;
  onHistory: () => void;
  hasResult: boolean;
  busy: boolean;
  session: AccessSession;
  history: ValidationHistoryItem[];
}) {
  const reduceMotion = useReducedMotion();
  return (
    <main className="landing">
      <div className="landing-noise" />
      <motion.section
        className="landing-content"
        initial={reduceMotion ? false : { opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.75, ease: "easeOut" }}
      >
        <div className="product-kicker">Hospital MS lesion AI QA</div>
        <h1>See where the model needs a radiologist’s attention.</h1>
        <p className="landing-subtitle">
          NeuroTrust-MS converts uploaded expert masks and AI predictions into review priorities, anatomy-specific cautions, and a deployment-focused improvement plan.
        </p>
        <p className="welcome-line">
          {session.welcome_back ? `Welcome back, ${session.email}.` : `Signed in as ${session.email}.`}
          {history.length ? ` ${history.length} saved validation run${history.length === 1 ? "" : "s"} found.` : " No saved validations yet."}
        </p>
        <div className="landing-actions">
          <button className="primary glow" onClick={onEnter}>Start validation</button>
          <button className="secondary dark" onClick={onSimpleDemo} disabled={busy}>
            {busy ? "Preparing demo..." : "Run simple demo"}
          </button>
          <button className="secondary dark" onClick={onFiveCaseDemo} disabled={busy}>
            {busy ? "Preparing 5-case demo..." : "Run 5-case demo"}
          </button>
          <button className="secondary dark" onClick={onHistory}>Past results</button>
          <button className="secondary dark" onClick={onVault} disabled={!hasResult}>View method vault</button>
        </div>
        <SafetyLine compact />
      </motion.section>
    </main>
  );
}
