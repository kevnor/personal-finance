import { useRef, useState } from "react";
import { useAppData } from "../context/AppData.jsx";
import { useAction } from "../hooks/useResource.js";
import { api } from "../lib/api.js";
import { InlineError } from "./States.jsx";

/**
 * Upload a statement: preview, then commit.
 *
 * Two steps because the server requires two, and for the same reason -- a
 * silent half-duplicating import is painful to unpick. The preview is what
 * the person approves; nothing is written until they press the second
 * button.
 */
export default function StatementUpload({ onImported, onUnauthorized }) {
  const { accounts } = useAppData();
  const [account, setAccount] = useState(accounts[0]?.name ?? "");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const input = useRef(null);
  const { run, pending, error } = useAction({ onUnauthorized });

  const reset = () => {
    setFile(null);
    setPreview(null);
    if (input.current) input.current.value = "";
  };

  const choose = (event) => {
    setFile(event.target.files?.[0] ?? null);
    setPreview(null);
    setResult(null);
  };

  const doPreview = async () => {
    const body = await run(() => api.imports.preview(file, account));
    if (body) setPreview(body);
  };

  const doCommit = async () => {
    const body = await run(() => api.imports.commit(file, account));
    if (body) {
      setResult(body);
      reset();
      onImported();
    }
  };

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 11 }}>
      <div className="eyebrow">importer kontoutdrag</div>

      <label className="field">
        <span className="field-label">Konto</span>
        <select
          className="field-select"
          value={account}
          onChange={(e) => {
            setAccount(e.target.value);
            setPreview(null);
          }}
        >
          {accounts.map((a) => (
            <option key={a.name} value={a.name}>
              {a.name}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span className="field-label">Fil (.xlsx)</span>
        <input
          ref={input}
          className="field-input"
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={choose}
        />
      </label>

      <InlineError error={error} />

      {preview && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 4,
            font: "400 12.5px/1.5 var(--font-body)",
            color: "rgba(233,233,237,.75)",
            borderTop: "1px solid var(--color-divider)",
            paddingTop: 9,
          }}
        >
          <div>
            <strong className="tabular">{preview.new}</strong> nye rader,{" "}
            <strong className="tabular">{preview.existing}</strong> allerede importert.
          </div>
          {preview.needs_review > 0 && (
            <div style={{ color: "var(--color-text-muted)" }}>
              {preview.needs_review} av de nye trenger gjennomgang.
            </div>
          )}
          {preview.new === 0 && (
            <div style={{ color: "var(--color-text-muted)" }}>
              Ingenting å importere — dette utdraget er allerede lest inn.
            </div>
          )}
        </div>
      )}

      {result && (
        <div style={{ font: "400 12.5px/1.5 var(--font-body)", color: "var(--accent-300)" }}>
          Importert: {result.inserted} nye, {result.skipped} fantes fra før
          {result.derived > 0 ? `, ${result.derived} avledede rader` : ""}.
        </div>
      )}

      {!preview ? (
        <button type="button" className="btn-outline" disabled={!file || !account || pending} onClick={doPreview}>
          {pending ? "Leser…" : "Forhåndsvis"}
        </button>
      ) : (
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="btn-outline" disabled={pending} onClick={reset}>
            Avbryt
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={pending || preview.new === 0}
            onClick={doCommit}
          >
            {pending ? "Importerer…" : `Importer ${preview.new}`}
          </button>
        </div>
      )}
    </div>
  );
}
