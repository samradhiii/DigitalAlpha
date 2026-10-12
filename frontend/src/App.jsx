import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api.js";
import { IconFile, IconHistory, IconInbox, IconLogo, IconLogout, IconUsers } from "./icons.jsx";
import Login from "./components/Login.jsx";
import PortfolioStats from "./components/PortfolioStats.jsx";
import UploadPanel from "./components/UploadPanel.jsx";
import TransactionReview from "./components/TransactionReview.jsx";
import CapitalCalls from "./components/CapitalCalls.jsx";
import Investors from "./components/Investors.jsx";
import ImportHistory from "./components/ImportHistory.jsx";

const PAGES = [
  {
    id: "reconcile",
    label: "Reconciliation",
    icon: IconInbox,
    title: "Bank reconciliation",
    subtitle: "Import bank statements and match incoming payments to capital calls.",
  },
  {
    id: "calls",
    label: "Capital calls",
    icon: IconFile,
    title: "Capital calls",
    subtitle: "Funding progress for every capital call notice.",
  },
  {
    id: "investors",
    label: "Investors",
    icon: IconUsers,
    title: "Investors",
    subtitle: "Called, funded and outstanding amounts per investor.",
  },
  {
    id: "imports",
    label: "Import history",
    icon: IconHistory,
    title: "Import history",
    subtitle: "Every bank statement uploaded for this organization.",
  },
];

function initials(name) {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(Boolean(getToken()));
  const [pageId, setPageId] = useState("reconcile");
  const [lastImport, setLastImport] = useState(null);
  const [openCount, setOpenCount] = useState(null);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);
  // Bumped after any change so every view refetches fresh balances.
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  const notify = useCallback((message, tone = "success") => {
    clearTimeout(toastTimer.current);
    setToast({ message, tone });
    toastTimer.current = setTimeout(() => setToast(null), 4000);
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
    setLastImport(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(signOut);
    if (!getToken()) return;
    api
      .me()
      .then(setUser)
      .catch(signOut)
      .finally(() => setChecking(false));
  }, [signOut]);

  useEffect(() => {
    if (!user) return;
    api
      .transactions()
      .then((txs) => setOpenCount(txs.filter((t) => t.status === "SUGGESTED" || t.status === "NEEDS_REVIEW").length))
      .catch(() => setOpenCount(null));
  }, [user, version]);

  async function handleLogout() {
    try {
      await api.logout();
    } catch {
      // Token may already be invalid; sign out locally regardless.
    }
    signOut();
  }

  if (checking) return <div className="splash">Loading…</div>;
  if (!user) {
    return (
      <Login
        onLogin={(data) => {
          setToken(data.token);
          setUser(data);
          setPageId("reconcile");
        }}
      />
    );
  }

  const page = PAGES.find((p) => p.id === pageId);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="logo-mark">
            <IconLogo size={18} />
          </div>
          <div>
            <div className="brand-name">FundRecon</div>
            <div className="brand-sub">Capital call reconciliation</div>
          </div>
        </div>

        <div className="org-card">
          <div className="org-avatar">{initials(user.organization.name)}</div>
          <div className="org-text">
            <div className="org-label">Organization</div>
            <div className="org-name">{user.organization.name}</div>
          </div>
        </div>

        <nav className="nav">
          {PAGES.map((p) => {
            const Icon = p.icon;
            return (
              <button
                key={p.id}
                className={`nav-item ${p.id === pageId ? "active" : ""}`}
                onClick={() => setPageId(p.id)}
              >
                <Icon />
                <span>{p.label}</span>
                {p.id === "reconcile" && openCount > 0 && <span className="nav-count">{openCount}</span>}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="user-chip">
            <div className="user-avatar">{initials(user.username.replace(/_/g, " "))}</div>
            <span className="user-name">{user.username}</span>
          </div>
          <button className="icon-btn" onClick={handleLogout} title="Sign out" aria-label="Sign out">
            <IconLogout />
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="page-header">
          <div>
            <h1>{page.title}</h1>
            <p>{page.subtitle}</p>
          </div>
        </header>

        <main className="page-body">
          {pageId === "reconcile" && (
            <>
              <PortfolioStats version={version} />
              <UploadPanel
                summary={lastImport}
                onImported={(data) => {
                  setLastImport(data);
                  refresh();
                  notify(`Imported ${data.imported_rows} of ${data.total_rows} rows from ${data.file_name}.`);
                }}
                onDismissSummary={() => setLastImport(null)}
              />
              <TransactionReview
                version={version}
                onChanged={(message) => {
                  refresh();
                  notify(message);
                }}
              />
            </>
          )}
          {pageId === "calls" && <CapitalCalls version={version} />}
          {pageId === "investors" && <Investors version={version} />}
          {pageId === "imports" && <ImportHistory version={version} />}
        </main>
      </div>

      {toast && (
        <div className={`toast toast-${toast.tone}`} role="status">
          {toast.message}
        </div>
      )}
    </div>
  );
}
