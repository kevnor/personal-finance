import { useState } from "react";
import { MERCHANTS } from "../lib/mockData.js";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", ",", "0", "⌫"];

export default function AddSheet({ open, onClose, onSave }) {
  const [amount, setAmount] = useState("");
  const [merchant, setMerchant] = useState("REMA 1000");

  if (!open) return null;

  const close = () => {
    setAmount("");
    onClose();
  };

  const pressKey = (key) => {
    if (key === "⌫") {
      setAmount((a) => a.slice(0, -1));
    } else {
      setAmount((a) => (a + key).slice(0, 7));
    }
  };

  const suggestion = MERCHANTS[merchant];

  return (
    <>
      <div
        style={{ position: "absolute", inset: 0, background: "rgba(14,15,24,.72)", zIndex: 70 }}
        onClick={close}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 80,
          background: "var(--color-sheet)",
          borderRadius: "18px 18px 0 0",
          boxShadow: "var(--shadow-sheet)",
          padding: "12px 18px 34px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <div style={{ width: 38, height: 4, borderRadius: 9999, background: "rgba(233,233,237,.22)", margin: "2px auto 4px" }} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <button
            type="button"
            onClick={close}
            style={{ appearance: "none", background: "none", border: "none", font: "400 13.5px var(--font-body)", color: "var(--color-text-muted)", cursor: "pointer", padding: "8px 4px" }}
          >
            Avbryt
          </button>
          <div style={{ font: "500 13.5px var(--font-heading)" }}>Ny utgift</div>
          <div style={{ font: "400 13.5px var(--font-body)", color: "var(--color-text-faint)", padding: "8px 4px" }}>i dag</div>
        </div>

        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "center", gap: 6, padding: "6px 0 2px" }}>
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

        <div style={{ display: "flex", gap: 7, overflowX: "auto" }}>
          {Object.keys(MERCHANTS).map((m) => {
            const active = merchant === m;
            return (
              <button
                key={m}
                type="button"
                onClick={() => setMerchant(m)}
                style={{
                  appearance: "none",
                  padding: "8px 11px",
                  borderRadius: 8,
                  font: "400 12px/1.2 var(--font-body)",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                  background: active ? "rgba(145,132,217,.18)" : "transparent",
                  color: active ? "var(--accent-200)" : "var(--color-text-muted)",
                  border: `1px solid ${active ? "rgba(145,132,217,.5)" : "var(--color-divider-strong)"}`,
                }}
              >
                {m}
              </button>
            );
          })}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "10px 12px", borderRadius: 8, background: "var(--color-surface)", boxShadow: "var(--shadow-card)" }}>
          <div style={{ width: 7, height: 7, borderRadius: 9999, background: "var(--accent-500)", flex: "none" }} />
          <div style={{ flex: 1, minWidth: 0, font: "400 12.5px/1.35 var(--font-body)", color: "rgba(233,233,237,.75)" }}>
            Foreslått: {suggestion.category} — regelen «{suggestion.rule}» traff
          </div>
          <button type="button" style={{ appearance: "none", background: "none", border: "none", font: "400 11.5px var(--font-body)", color: "var(--accent-500)", cursor: "pointer", whiteSpace: "nowrap" }}>
            endre
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
          {KEYS.map((key) => (
            <button
              key={key}
              type="button"
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
          onClick={() => {
            const value = Number(amount.replace(",", "."));
            if (amount !== "" && !Number.isNaN(value) && value > 0) {
              onSave?.({ amount: value, merchant, category: suggestion.category });
            }
            close();
          }}
          style={{
            appearance: "none",
            height: 50,
            borderRadius: 8,
            border: "1px solid var(--accent-500)",
            background: "none",
            display: "grid",
            placeItems: "center",
            font: "500 15px var(--font-heading)",
            color: "var(--accent-300)",
            cursor: "pointer",
            marginTop: 2,
          }}
        >
          Lagre utgift
        </button>
      </div>
    </>
  );
}
