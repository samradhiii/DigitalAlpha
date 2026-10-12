import { useState } from "react";
import { api } from "../api.js";
import { dateTime } from "../format.jsx";
import { IconHistory } from "../icons.jsx";
import ImportSummary from "./ImportSummary.jsx";
import useApiData from "./useApiData.js";

export default function ImportHistory({ version }) {
  const { data, error, loading } = useApiData(api.imports, version);
  const [selected, setSelected] = useState(null);
  const [detailError, setDetailError] = useState("");

  async function open(id) {
    if (selected?.id === id) {
      setSelected(null);
      return;
    }
    setDetailError("");
    try {
      setSelected(await api.importDetail(id));
    } catch (err) {
      setDetailError(err.message);
    }
  }

  return (
    <>
      <section className="card card-flush">
        {error && <div className="alert alert-error">{error}</div>}
        {loading && !data ? (
          <div className="skeleton-list pad">
            <div className="skeleton" />
          </div>
        ) : data?.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">
              <IconHistory size={22} />
            </div>
            <div className="empty-title">No imports yet</div>
            <div className="empty-text">Uploaded bank statements will appear here.</div>
          </div>
        ) : (
          data && (
            <div className="table-wrap">
              <table className="table table-hover">
                <thead>
                  <tr>
                    <th>Import</th>
                    <th>Uploaded</th>
                    <th>By</th>
                    <th className="num">Rows</th>
                    <th className="num">Imported</th>
                    <th className="num">Suggested</th>
                    <th className="num">Review</th>
                    <th className="num">Duplicates</th>
                    <th className="num">Invalid</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.map((imp) => (
                    <tr key={imp.id} className={selected?.id === imp.id ? "selected" : ""} onClick={() => open(imp.id)}>
                      <td>
                        <div className="strong">{imp.file_name}</div>
                        <div className="muted small">#{imp.id}</div>
                      </td>
                      <td className="nowrap muted">{dateTime(imp.uploaded_at)}</td>
                      <td className="muted">{imp.uploaded_by}</td>
                      <td className="num">{imp.total_rows}</td>
                      <td className="num">{imp.imported_rows}</td>
                      <td className="num">{imp.suggested_matches}</td>
                      <td className="num">{imp.needs_review}</td>
                      <td className={`num ${imp.duplicate_rows ? "text-danger" : ""}`}>{imp.duplicate_rows}</td>
                      <td className={`num ${imp.invalid_rows ? "text-danger" : ""}`}>{imp.invalid_rows}</td>
                      <td className="num">
                        <button className="btn btn-ghost btn-sm">{selected?.id === imp.id ? "Hide" : "Details"}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </section>
      {detailError && <div className="alert alert-error">{detailError}</div>}
      {selected && (
        <section className="card">
          <ImportSummary data={selected} onDismiss={() => setSelected(null)} />
        </section>
      )}
    </>
  );
}
