import { useEffect, useState } from "react";
import { useAppData } from "../context/AppData.jsx";
import { useAction } from "../hooks/useResource.js";
import { api } from "../lib/api.js";
import { InlineError } from "./States.jsx";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", ",", "0", "⌫"];

/**
 * Hand entry: amount pad first, three taps for the common case.
 *
 * The category is left to the server unless the user picks one. It runs the
 * same `categorise` the importer runs, learned rules included, so typing a
 * merchant the user has already taught gets that merchant's category -- and
 * the client does not need its own copy of the rules to guess with.
 */
export default function AddSheet({ open, onClose, onSaved, onUnauthorized }) {
  const { accounts, expenseCategories, labelFor } = useAppData();
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [account, setAccount] = useState(accounts[0]?.name ?? "");
  const [category, setCategory] = useState("");
  const { run, pending, error, clearError } = useAction({ onUnauthorized });

  // Cleared on open rather than on close, so a failed save leaves what the
  // user typed on screen to correct rather than throwing it away.
  useEffect(() => {
    if (open) {
      setAmount("");
      setDescription("");
      setCategory("");
      setAccount(accounts[0]?.name ?? "");
      clearError();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const value = Number(amount.replace(",", "."));
  const valid = amount !== "" && Number.isFinite(value) && value > 0 && description.trim() !== "";

  const pressKey = (key) => {
    if (key === "⌫") setAmount((a) => a.slice(0, -1));
    else setAmount((a) => (a + key).slice(0, 9));
  };

  const save = async () => {
    if (!valid) return;
    const created = await run(() =>
      api.transactions.create({
        date: new Date().toLocaleDateString("sv-SE"), // sv-SE renders as YYYY-MM-DD
        description: description.trim(),
        // Signed: an expense is money out. The pad collects a magnitude,
        // because "how much did it cost" is the question being asked.
        amount: -value,
        account,
        category: category || undefined,
      }),
    );
    if (created) {
      onSaved();
      onClose();
    }
  };

  return (
    <>
      <div
        style={{ position: "absolute", inset: 0, background: "rgba(14,15,24,.72)", zIndex: 70 }}
        onClick={pending ? undefined : onClose}
      />
      <div
        role="dialog"
        aria-label="Ny utgift"
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 80,
          maxHeight: "92%",
          overflowY: "auto",
          background: "var(--color-sheet)",
          borderRadius: "18px 18px 0 0",
          boxShadow: "var(--shadow-sheet)",
          padding: "12px 18px 34px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <div
          style={{
            width: 38,
            height: 4,
            borderRadius: 9999,
            background: "rgba(233,233,237,.22)",
            margin: "2px auto 4px",
          }}
        />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            style={{
              appearance: "none",
              background: "none",
              border: "none",
              font: "400 13.5px var(--font-body)",
              color: "var(--color-text-muted)",
              cursor: "pointer",
              padding: "8px 4px",
            }}
          >
            Avbryt
          </button>
          <div style={{ font: "500 13.5px var(--font-heading)" }}>Ny utgift</div>
          <div
            style={{
              font: "400 13.5px var(--font-body)",
              color: "var(--color-text-faint)",
              padding: "8px 4px",
            }}
          >
            i dag
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "center",
            gap: 6,
            padding: "6px 0 2px",
          }}
        >
          <span
            className="tabular"
            style={{
              font: "500 46px/1 var(--font-heading)",
              letterSpacing: "-.03em",
              color: amount === "" ? "var(--color-text-faint)" : "var(--color-text)",
            }}
          >
            {amount === "" ? "0" : amount}
          </span>
          <span style={{ font: "400 16px/1 var(--font-body)", color: "var(--color-text-muted)" }}>kr</span>
        </div>

        <label className="field">
          <span className="field-label">Hva</span>
          <input
            className="field-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="F.eks. Rema 1000"
          />
        </label>

        <div style={{ display: "flex", gap: 8 }}>
          <label className="field" style={{ flex: 1 }}>
            <span className="field-label">Konto</span>
            <select className="field-select" value={account} onChange={(e) => setAccount(e.target.value)}>
              {accounts.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field" style={{ flex: 1 }}>
            <span className="field-label">Kategori</span>
            <select className="field-select" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Foreslå selv</option>
              {expenseCategories.map((c) => (
                <option key={c.name} value={c.name}>
                  {labelFor(c.name)}
                </option>
              ))}
            </select>
          </label>
        </div>

        <InlineError error={error} />

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
          {KEYS.map((key) => (
            <button
              key={key}
              type="button"
              aria-label={key === "⌫" ? "Slett siffer" : key}
              onClick={() => pressKey(key)}
              style={{
                appearance: "none",
                height: 52,
                borderRadius: 8,
                background: "var(--color-surface)",
                boxShadow: "var(--shadow-card)",
                display: "grid",
                placeItems: "center",
                font: "500 21px/1 var(--font-heading)",
                color: key === "⌫" ? "rgba(233,233,237,.55)" : "var(--color-text)",
                cursor: "pointer",
                userSelect: "none",
                border: "none",
              }}
            >
              {key}
            </button>
          ))}
        </div>

        <button
          type="button"
          className="btn-primary"
          disabled={!valid || pending}
          onClick={save}
          style={{ marginTop: 2 }}
        >
          {pending ? "Lagrer…" : "Lagre utgift"}
        </button>
      </div>
    </>
  );
}
