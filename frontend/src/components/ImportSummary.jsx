import { dateTime, StatusBadge } from "../format.jsx";
import { IconX } from "../icons.jsx";

const STATS = [
  ["total_rows", "Rows in file", ""],
  ["imported_rows", "Imported", ""],
  ["suggested_matches", "Suggested", "info"],
  ["needs_review", "Needs review", "warn"],
  ["ignored_rows", "Ignored", "muted"],
  ["duplicate_rows", "Duplicates", "danger"],
  ["invalid_rows", "Invalid", "danger"],
];

export default function ImportSummary({ data, onDismiss }) {
  const issues = data.issues || [];
  return (
    <div className="summary">
      <div className="summary-head">
        <div>
          <div className="summary-title">Import #{data.id} · {data.file_name}</div>
          <div className="summary-sub">
            {dateTime(data.uploaded_at)}
            {data.uploaded_by ? ` · ${data.uploaded_by}` : ""}
          </div>
        </div>
        {onDismiss && (
          <button className="icon-btn" onClick={onDismiss} title="Dismiss summary" aria-label="Dismiss summary">
            <IconX size={16} />
          </button>
        )}
      </div>

      <div className="stats">
        {STATS.map(([key, label, tone]) => (
          <div key={key} className={`stat ${data[key] > 0 && tone ? `stat-${tone}` : ""}`}>
            <div className="stat-value">{data[key]}</div>
            <div className="stat-label">{label}</div>
          </div>
        ))}
      </div>

      {issues.length > 0 && (
        <details className="issues" open={issues.length <= 5}>
          <summary>
            {issues.length} row{issues.length === 1 ? "" : "s"} not imported
          </summary>
          <div className="table-wrap">
            <table className="table table-compact">
              <thead>
                <tr>
                  <th>Line</th>
                  <th>Issue</th>
                  <th>Problem</th>
                  <th>Date</th>
                  <th>Description</th>
                  <th className="num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {issues.map((issue) => (
                  <tr key={`${issue.row_number}-${issue.issue_type}`}>
                    <td className="mono muted">{issue.row_number}</td>
                    <td>
                      <StatusBadge status={issue.issue_type} />
                    </td>
                    <td className="problem">{issue.messages.join(" ")}</td>
                    <td className="mono nowrap">{issue.raw_data.date ?? "—"}</td>
                    <td className="truncate" title={issue.raw_data.description}>
                      {issue.raw_data.description?.trim() || "—"}
                    </td>
                    <td className="num mono nowrap">{issue.raw_data.amount ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
