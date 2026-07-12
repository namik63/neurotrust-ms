import { useState } from "react";
import type { FormEvent } from "react";
import { loginAccess } from "../api/client";
import type { AccessSession } from "../types";

export function AccessGate({ onAccessGranted }: { onAccessGranted: (session: AccessSession) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = await loginAccess(email, password);
      onAccessGranted({
        email: payload.email,
        token: payload.token,
        expires_at: payload.expires_at,
        welcome_back: payload.welcome_back,
        login_count: payload.login_count,
        recent_validations: payload.recent_validations || [],
        safety_privacy: payload.safety_privacy || {},
      });
    } catch (err: any) {
      setError(err?.message || "Access check failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="access-gate">
      <section className="access-card">
        <div className="brand-mark large">NT</div>
        <p className="eyebrow">Protected prototype access</p>
        <h1>NeuroTrust-MS</h1>
        <p className="access-copy">
          Enter your email and password to continue. New emails create a protected account; returning emails reopen the validation history tied to that email.
        </p>
        <form onSubmit={submit} className="access-form">
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@example.com"
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Password"
              required
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          <button className="primary glow" disabled={busy || !email || !password}>
            {busy ? "Checking access…" : "Enter NeuroTrust-MS"}
          </button>
        </form>
        <p className="access-note">Your email and password protect saved validation history. Raw passwords are never stored.</p>
      </section>
    </main>
  );
}
