const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const compactCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

export function money(value) {
  if (value === null || value === undefined || value === "") return "—";
  return currency.format(Number(value));
}

export function moneyCompact(value) {
  return compactCurrency.format(Number(value || 0));
}

export function dateTime(value) {
  return value
    ? new Date(value).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })
    : "—";
}

export function shortDate(value) {
  if (!value) return "—";
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export const STATUS_LABELS = {
  SUGGESTED: "Suggested",
  NEEDS_REVIEW: "Needs review",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  IGNORED: "Ignored",
  PENDING: "Pending",
  PARTIALLY_FUNDED: "Partially funded",
  FUNDED: "Funded",
  INVALID: "Invalid",
  DUPLICATE: "Duplicate",
};

export function StatusBadge({ status }) {
  return (
    <span className={`badge badge-${status.toLowerCase()}`}>
      <span className="badge-dot" />
      {STATUS_LABELS[status] || status}
    </span>
  );
}

export function Progress({ value, total }) {
  const pct = Number(total) > 0 ? Math.min(100, (Number(value) / Number(total)) * 100) : 0;
  const tone = pct >= 100 ? "done" : pct > 0 ? "partial" : "none";
  return (
    <div className="progress-wrap">
      <div className="progress">
        <div className={`progress-bar progress-${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="progress-label">{Math.round(pct)}%</span>
    </div>
  );
}
