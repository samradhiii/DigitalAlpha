import { useRef, useState } from "react";
import { api } from "../api.js";
import { IconFile, IconUpload, IconX } from "../icons.jsx";
import ImportSummary from "./ImportSummary.jsx";

function formatSize(bytes) {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

export default function UploadPanel({ summary, onImported, onDismissSummary }) {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function choose(selected) {
    setError("");
    if (!selected) return;
    if (!selected.name.toLowerCase().endsWith(".csv")) {
      setError("Please choose a .csv file.");
      return;
    }
    setFile(selected);
  }

  function clear() {
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function upload() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      onImported(await api.uploadStatement(file));
      clear();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Import bank statement</h2>
          <p className="card-sub">
            CSV with columns <code>date</code> <code>description</code> <code>amount</code> <code>type</code>{" "}
            <code>reference</code> · dates as YYYY-MM-DD · max 5 MB
          </p>
        </div>
      </div>

      {file ? (
        <div className="file-row">
          <div className="file-icon">
            <IconFile size={20} />
          </div>
          <div className="file-info">
            <div className="file-name">{file.name}</div>
            <div className="file-size">{formatSize(file.size)} · ready to import</div>
          </div>
          <button className="btn btn-ghost" onClick={clear} disabled={busy}>
            <IconX size={16} /> Remove
          </button>
          <button className="btn btn-primary" onClick={upload} disabled={busy}>
            {busy ? <span className="spinner" /> : <IconUpload size={16} />}
            {busy ? "Importing…" : "Import & match"}
          </button>
        </div>
      ) : (
        <label
          className={`dropzone ${dragging ? "dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            choose(e.dataTransfer.files[0]);
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            className="visually-hidden"
            onChange={(e) => choose(e.target.files[0])}
          />
          <div className="dropzone-icon">
            <IconUpload size={22} />
          </div>
          <div className="dropzone-title">
            <span className="link">Choose a CSV file</span> or drag it here
          </div>
          <div className="dropzone-hint">Rows are validated, de-duplicated and matched automatically.</div>
        </label>
      )}

      {error && <div className="alert alert-error">{error}</div>}
      {summary && <ImportSummary data={summary} onDismiss={onDismissSummary} />}
    </section>
  );
}
