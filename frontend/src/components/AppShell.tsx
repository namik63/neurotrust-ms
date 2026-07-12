import type { ReactNode } from "react";
import type { AccessSession, AppView, ResultTab } from "../types";
import { SafetyLine } from "./SafetyLine";

export function AppShell({
  view,
  activeTab,
  hasResult,
  session,
  onHome,
  onValidate,
  onHistory,
  onLogout,
  onResultsTab,
  children,
}: {
  view: AppView;
  activeTab: ResultTab;
  hasResult: boolean;
  session: AccessSession;
  onHome: () => void;
  onValidate: () => void;
  onHistory: () => void;
  onLogout: () => void;
  onResultsTab: (tab: ResultTab) => void;
  children: ReactNode;
}) {
  return (
    <div className="app-frame">
      <header className="topbar">
        <button className="brand-button" onClick={onHome} aria-label="Return home">
          <span className="brand-mark">NT</span>
          <span>NeuroTrust-MS</span>
        </button>
        <nav className="topnav">
          <button className={view === "home" ? "active" : ""} onClick={onHome}>Home</button>
          <button className={view === "workspace" ? "active" : ""} onClick={onValidate}>Validate</button>
          <button className={view === "history" ? "active" : ""} onClick={onHistory}>Past Results</button>
          <button disabled={!hasResult} className={activeTab === "overview" ? "active" : ""} onClick={() => onResultsTab("overview")}>Clinical Summary</button>
          <button disabled={!hasResult} className={activeTab === "viewer" ? "active" : ""} onClick={() => onResultsTab("viewer")}>Viewer</button>
          <button disabled={!hasResult} className={activeTab === "anatomy" ? "active" : ""} onClick={() => onResultsTab("anatomy")}>Anatomy Map</button>
          <button disabled={!hasResult} className={activeTab === "watchlist" ? "active" : ""} onClick={() => onResultsTab("watchlist")}>Priorities</button>
          <button disabled={!hasResult} className={activeTab === "exports" ? "active" : ""} onClick={() => onResultsTab("exports")}>Exports</button>
          <button onClick={onLogout}>Sign out</button>
        </nav>
      </header>
      <div className="signed-in-strip">
        <span>{session.welcome_back ? "Welcome back" : "Signed in"}: {session.email}</span>
        <span>{session.recent_validations?.length || 0} saved validation run{(session.recent_validations?.length || 0) === 1 ? "" : "s"}</span>
      </div>
      {children}
      <footer className="footer">
        <SafetyLine compact />
      </footer>
    </div>
  );
}
