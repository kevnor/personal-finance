import { nok } from "../lib/format.js";

export default function TransactionRow({ row }) {
  const sign = row.sign ?? "−";
  const amountColor = row.amountColor ?? "var(--color-text)";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "10px 0",
        borderBottom: "1px solid var(--color-divider)",
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          background: row.dot ?? "var(--accent-400)",
          flex: "none",
          display: "grid",
          placeItems: "center",
          font: "500 12px var(--font-heading)",
          color: "#161826",
        }}
      >
        {row.name[0]}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ font: "400 13.5px/1.3 var(--font-body)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {row.name}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 3 }}>
          <span style={{ font: "400 11.5px/1.2 var(--font-body)", color: "var(--color-text-muted)" }}>{row.category}</span>
          {row.outside && (
            <span
              style={{
                font: "400 10px/1 var(--font-body)",
                letterSpacing: ".02em",
                padding: "3px 7px",
                borderRadius: 6,
                background: "var(--neutral-900)",
                color: "rgba(233,233,237,.6)",
              }}
            >
              utenfor rammen
            </span>
          )}
          {row.flagged && (
            <span
              style={{
                font: "400 10px/1 var(--font-body)",
                padding: "3px 7px",
                borderRadius: 6,
                background: "var(--accent-800)",
                color: "var(--accent-200)",
              }}
            >
              gjennomgås
            </span>
          )}
        </div>
      </div>
      <div className="tabular" style={{ font: "500 13.5px/1 var(--font-heading)", whiteSpace: "nowrap", color: amountColor }}>
        {sign}
        {nok(row.amount)}
      </div>
    </div>
  );
}
