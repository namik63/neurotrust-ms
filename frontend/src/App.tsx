import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { logoutAccess, openValidation, runDemo, runFiveCaseDemo, uploadBatchRun, validationHistory } from "./api/client";
import { AccessGate } from "./components/AccessGate";
import { AppShell } from "./components/AppShell";
import { HistoryPanel } from "./components/HistoryPanel";
import { LandingExperience } from "./components/LandingExperience";
import { ProcessingScreen } from "./components/ProcessingScreen";
import { ResultsCommandCenter } from "./components/ResultsCommandCenter";
import { ValidationWorkspace } from "./components/ValidationWorkspace";
import type { AccessSession, AppView, ResultTab, ValidationHistoryItem, ValidationMode, ValidationResult } from "./types";

function App() {
  const [view, setView] = useState<AppView>("home");
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [activeTab, setActiveTab] = useState<ResultTab>("overview");
  const [processingMode, setProcessingMode] = useState<ValidationMode>("simple_demo");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [session, setSession] = useState<AccessSession | null>(null);
  const [history, setHistory] = useState<ValidationHistoryItem[]>([]);

  async function refreshHistory(token = session?.token) {
    if (!token) return;
    try {
      const payload = await validationHistory(token);
      setHistory(payload.validations || []);
      setSession((current) => current ? { ...current, recent_validations: payload.validations || [], safety_privacy: payload.safety_privacy || current.safety_privacy } : current);
    } catch {
      // The next protected action will ask the user to sign in again if needed.
    }
  }

  async function runWithProcessing(mode: ValidationMode, runner: () => Promise<ValidationResult>) {
    if (!session?.token) {
      setError("Please sign in again before running validation.");
      setSession(null);
      return;
    }
    setBusy(true);
    setError("");
    setProcessingMode(mode);
    setView("processing");
    const startedAt = Date.now();
    try {
      const payload = await runner();
      const elapsed = Date.now() - startedAt;
      if (elapsed < 700) {
        await new Promise((resolve) => window.setTimeout(resolve, 700 - elapsed));
      }
      setResult(payload);
      setActiveTab(mode === "five_case_demo" ? "vault" : "overview");
      setView("results");
      await refreshHistory();
    } catch (err: any) {
      setError(err?.message || "Validation failed");
      setView("workspace");
    } finally {
      setBusy(false);
    }
  }

  function handleSimpleDemo() {
    if (!session?.token) return;
    runWithProcessing("simple_demo", () => runDemo(session.token));
  }

  function handleFiveCaseDemo() {
    if (!session?.token) return;
    runWithProcessing("five_case_demo", () => runFiveCaseDemo(session.token));
  }

  function handleBatch(form: FormData) {
    if (!session?.token) return;
    runWithProcessing("batch", () => uploadBatchRun(form, session.token));
  }

  function goHome() {
    setView("home");
  }

  function goValidate() {
    setView("workspace");
  }

  function goHistory() {
    refreshHistory();
    setView("history");
  }

  function goResultsTab(tab: ResultTab) {
    if (!result) return;
    setActiveTab(tab);
    setView("results");
  }

  function handleAccessGranted(next: AccessSession) {
    setSession(next);
    setHistory(next.recent_validations || []);
    setView("home");
  }

  async function handleLogout() {
    if (session?.token) await logoutAccess(session.token);
    setSession(null);
    setHistory([]);
    setResult(null);
    setView("home");
  }

  async function handleOpenHistory(runId: string) {
    if (!session?.token) return;
    setBusy(true);
    setError("");
    try {
      const payload = await openValidation(runId, session.token);
      setResult(payload);
      setActiveTab("overview");
      setView("results");
    } catch (err: any) {
      setError(err?.message || "Could not open stored validation.");
      setView("history");
    } finally {
      setBusy(false);
    }
  }

  if (!session) {
    return <AccessGate onAccessGranted={handleAccessGranted} />;
  }

  if (view === "home") {
    return (
      <LandingExperience
        busy={busy}
        onEnter={goValidate}
        onSimpleDemo={handleSimpleDemo}
        onFiveCaseDemo={handleFiveCaseDemo}
        onVault={() => goResultsTab("vault")}
        onHistory={goHistory}
        hasResult={Boolean(result)}
        session={session}
        history={history}
      />
    );
  }

  return (
    <AppShell
      view={view}
      activeTab={activeTab}
      hasResult={Boolean(result)}
      session={session}
      onHome={goHome}
      onValidate={goValidate}
      onHistory={goHistory}
      onLogout={handleLogout}
      onResultsTab={goResultsTab}
    >
      <AnimatePresence mode="wait">
        {view === "workspace" && (
          <motion.div
            key="workspace"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.28 }}
          >
            <ValidationWorkspace
              onRunSimpleDemo={handleSimpleDemo}
              onRunFiveCaseDemo={handleFiveCaseDemo}
              onRunBatch={handleBatch}
              error={error}
            />
          </motion.div>
        )}
        {view === "processing" && (
          <motion.div
            key="processing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
          >
            <ProcessingScreen mode={processingMode} />
          </motion.div>
        )}
        {view === "history" && (
          <motion.div
            key="history"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.28 }}
          >
            <HistoryPanel history={history} session={session} error={error} busy={busy} onOpen={handleOpenHistory} onValidate={goValidate} onRefresh={() => refreshHistory()} />
          </motion.div>
        )}
        {view === "results" && result && (
          <motion.div
            key="results"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.28 }}
          >
            <ResultsCommandCenter
              result={result}
              activeTab={activeTab}
              onTab={setActiveTab}
              onHome={goHome}
              onValidate={goValidate}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </AppShell>
  );
}

export default App;
