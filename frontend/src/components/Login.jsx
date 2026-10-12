import { useState } from "react";
import { api } from "../api.js";
import { IconCheck, IconLogo } from "../icons.jsx";

const DEMO_ACCOUNTS = [
  { username: "northwind_admin", org: "Northwind Ventures" },
  { username: "bluebird_admin", org: "Bluebird Capital" },
];

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(await api.login(username, password));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-brand">
        <div className="sidebar-brand">
          <div className="logo-mark">
            <IconLogo size={18} />
          </div>
          <div className="brand-name">FundRecon</div>
        </div>
        <div className="login-pitch">
          <h1>Reconcile capital calls in minutes, not days.</h1>
          <ul>
            <li>
              <IconCheck size={16} /> Validate and de-duplicate bank statements on import
            </li>
            <li>
              <IconCheck size={16} /> Match payments by reference, investor name and amount
            </li>
            <li>
              <IconCheck size={16} /> Approve with confidence — balances update instantly
            </li>
          </ul>
        </div>
        <div className="login-foot">Fund administration · Bank reconciliation</div>
      </div>

      <div className="login-panel">
        <form className="login-form" onSubmit={submit}>
          <h2>Sign in</h2>
          <p className="muted">Access your organization's reconciliation workspace.</p>

          <label className="field">
            <span>Username</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error && <div className="alert alert-error">{error}</div>}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy && <span className="spinner" />}
            {busy ? "Signing in…" : "Sign in"}
          </button>

          <div className="demo">
            <div className="demo-title">
              Demo accounts · password <code>demo12345</code>
            </div>
            {DEMO_ACCOUNTS.map((a) => (
              <button type="button" key={a.username} className="demo-account" onClick={() => setUsername(a.username)}>
                <span className="strong">{a.org}</span>
                <span className="mono muted">{a.username}</span>
              </button>
            ))}
          </div>
        </form>
      </div>
    </div>
  );
}
