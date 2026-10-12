import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { money, shortDate, StatusBadge } from "../format.jsx";
import { IconAlert, IconCheck, IconInbox } from "../icons.jsx";

const OPEN = ["SUGGESTED", "NEEDS_REVIEW"];
const FILTERS = [
  { id: "open", label: "To review", match: (t) => OPEN.includes(t.status) },
  { id: "NEEDS_REVIEW", label: "Needs review", match: (t) => t.status === "NEEDS_REVIEW" },
  { id: "SUGGESTED", label: "Suggested", match: (t) => t.status === "SUGGESTED" },
  { id: "APPROVED", label: "Approved", match: (t) => t.status === "APPROVED" },
  { id: "REJECTED", label: "Rejected", match: (t) => t.status === "REJECTED" },
  { id: "IGNORED", label: "Ignored", match: (t) => t.status === "IGNORED" },
  { id: "all", label: "All", match: () => true },
];
const ACTIONABLE = ["SUGGESTED", "NEEDS_REVIEW", "REJECTED"];

export default function TransactionReview({ version, onChanged }) {
  const [filterId, setFilterId] = useState("open");
  const [transactions, setTransactions] = useState([]);
  const [calls, setCalls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.transactions(), api.capitalCalls()])
      .then(([txs, cc]) => {
        if (cancelled) return;
        setTransactions(txs);
        setCalls(cc);
        setError("");
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [version]);

  const counts = useMemo(
    () => Object.fromEntries(FILTERS.map((f) => [f.id, transactions.filter(f.match).length])),
    [transactions]
  );
  const filter = FILTERS.find((f) => f.id === filterId);
  // Items needing attention first; the API already orders by date and sort is stable.
  const visible = transactions
    .filter(filter.match)
    .sort((a, b) => Number(b.status === "NEEDS_REVIEW") - Number(a.status === "NEEDS_REVIEW"));

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Payment review</h2>
          <p className="card-sub">Confirm, correct or dismiss each incoming payment before it updates investor balances.</p>
        </div>
      </div>

      <div className="segmented" role="tablist">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            role="tab"
            aria-selected={f.id === filterId}
            className={`segment ${f.id === filterId ? "active" : ""}`}
            onClick={() => setFilterId(f.id)}
          >
            {f.label}
            <span className="segment-count">{counts[f.id] ?? 0}</span>
          </button>
        ))}
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {loading ? (
        <div className="skeleton-list">
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      ) : visible.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">
            <IconInbox size={22} />
          </div>
          <div className="empty-title">
            {filterId === "open" ? "You're all caught up" : "Nothing here"}
          </div>
          <div className="empty-text">
            {transactions.length === 0
              ? "Import a bank statement to start reconciling payments."
              : "No transactions match this filter."}
          </div>
        </div>
      ) : (
        <div className="txn-list">
          {visible.map((tx) => (
            <TransactionCard key={tx.id} tx={tx} calls={calls} onChanged={onChanged} />
          ))}
        </div>
      )}
    </section>
  );
}

function Confidence({ value }) {
  const tone = value >= 60 ? "high" : value >= 40 ? "mid" : "low";
  return (
    <div className={`confidence confidence-${tone}`} title="Match confidence">
      <div className="confidence-track">
        <div style={{ width: `${value}%` }} />
      </div>
      <span>{value}%</span>
    </div>
  );
}

function TransactionCard({ tx, calls, onChanged }) {
  const isCredit = tx.transaction_type === "CREDIT";
  const actionable = ACTIONABLE.includes(tx.status) && isCredit;
  const defaultCall = tx.status === "REJECTED" ? "" : String(tx.suggested_capital_call ?? "");
  const [callId, setCallId] = useState(defaultCall);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => setCallId(defaultCall), [defaultCall]);

  async function act(action) {
    setBusy(action);
    setError("");
    try {
      const payload = action === "approve" && callId ? { capital_call_id: Number(callId) } : {};
      const result = await api.act(tx.id, action, payload);
      const messages = {
        approve: `Approved ${money(tx.amount)} to ${result.suggested_capital_call_reference} (${result.suggested_investor_name}).`,
        reject: `Rejected the suggested match for ${money(tx.amount)}.`,
        ignore: `Ignored ${money(tx.amount)} payment.`,
      };
      onChanged(messages[action]);
    } catch (err) {
      setError(err.message);
      setBusy("");
    }
  }

  const openCalls = calls.filter((c) => Number(c.remaining_amount) > 0 || String(c.id) === callId);
  const selectedCall = calls.find((c) => String(c.id) === callId);
  const hasMatch = Boolean(tx.suggested_capital_call_reference);

  return (
    <article className={`txn txn-${tx.status.toLowerCase()}`}>
      <div className="txn-payment">
        <div className="txn-amount-row">
          <span className={`txn-amount ${isCredit ? "" : "txn-debit"}`}>{money(tx.amount)}</span>
          <StatusBadge status={tx.status} />
        </div>
        <div className="txn-desc">{tx.description}</div>
        <div className="txn-meta">
          <span>{shortDate(tx.transaction_date)}</span>
          {tx.bank_reference && <span className="mono">{tx.bank_reference}</span>}
          <span>
            Import #{tx.statement_import} · line {tx.row_number}
          </span>
        </div>
      </div>

      <div className="txn-match">
        {hasMatch ? (
          <div className="match-head">
            <span className="ref-pill">{tx.suggested_capital_call_reference}</span>
            <span className="match-investor">{tx.suggested_investor_name}</span>
            {isCredit && tx.status !== "APPROVED" && <Confidence value={tx.confidence} />}
          </div>
        ) : (
          <div className="match-head muted">{isCredit ? "No matching capital call" : "Not a capital call receipt"}</div>
        )}
        <ul className="reasons">
          {tx.review_reasons.map((r) => (
            <li key={r} className="reason reason-warn">
              <IconAlert size={14} />
              <span>{r}</span>
            </li>
          ))}
          {tx.match_reasons.map((r) => (
            <li key={r} className="reason reason-ok">
              <IconCheck size={14} />
              <span>{r}</span>
            </li>
          ))}
        </ul>
        {tx.reviewed_by && (
          <div className="reviewed">
            {tx.status === "APPROVED" ? "Approved" : "Reviewed"} by {tx.reviewed_by}
            {tx.review_note ? ` — “${tx.review_note}”` : ""}
          </div>
        )}
      </div>

      <div className="txn-actions">
        {actionable ? (
          <>
            <label className="field-label" htmlFor={`call-${tx.id}`}>
              Apply to capital call
            </label>
            <select id={`call-${tx.id}`} value={callId} onChange={(e) => setCallId(e.target.value)} disabled={!!busy}>
              <option value="">Select a capital call…</option>
              {openCalls.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.reference} — {c.investor_name}
                </option>
              ))}
            </select>
            {selectedCall && (
              <div className={`call-hint ${Number(tx.amount) > Number(selectedCall.remaining_amount) ? "call-hint-warn" : ""}`}>
                {money(selectedCall.remaining_amount)} outstanding of {money(selectedCall.amount_called)}
              </div>
            )}
            <div className="btn-row">
              <button className="btn btn-success" disabled={!!busy || !callId} onClick={() => act("approve")}>
                {busy === "approve" ? <span className="spinner" /> : <IconCheck size={15} />}
                Approve
              </button>
              {tx.status !== "REJECTED" && (
                <button className="btn btn-outline-danger" disabled={!!busy} onClick={() => act("reject")}>
                  Reject
                </button>
              )}
              <button className="btn btn-ghost" disabled={!!busy} onClick={() => act("ignore")}>
                Ignore
              </button>
            </div>
            {error && <div className="alert alert-error alert-sm">{error}</div>}
          </>
        ) : (
          <div className="txn-final">
            {tx.status === "APPROVED" && <span className="final-ok">Applied to {tx.suggested_capital_call_reference}</span>}
            {tx.status === "IGNORED" && <span className="muted">No action needed</span>}
          </div>
        )}
      </div>
    </article>
  );
}
