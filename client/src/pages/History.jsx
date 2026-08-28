import { useMemo, useState } from "react";
import TransactionRow from "../components/TransactionRow.jsx";
import { nok } from "../lib/format.js";
import { HISTORY_GROUPS, WEEK_ENVELOPE, SPENT_THIS_WEEK } from "../lib/mockData.js";

const FILTERS = ["Alle", "I rammen", "Utenfor"];

export default function History() {
  const [filter, setFilter] = useState("Alle");

  const groups = useMemo(() => {
    if (filter === "Alle") return HISTORY_GROUPS;
    const wantOutside = filter === "Utenfor";
    return HISTORY_GROUPS.map((g) => ({
      ...g,
      rows: g.rows.filter((r) => Boolean(r.outside) === wantOutside),
    })).filter((g) => g.rows.length > 0);
  }, [filter]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <div style={{ font: "500 22px/1.15 var(--font-heading)", letterSpacing: "-.015em" }}>Historikk</div>
        <div style={{ font: "400 12.5px/1.4 var(--font-body)", color: "var(--color-text-muted)", marginTop: 3 }}>
          uke 35 · brukt {nok(SPENT_THIS_WEEK)} av {nok(WEEK_ENVELOPE)} kr
        </div>
      </div>

      <div style={{ display: "flex", border: "1px solid var(--color-divider-strong)", borderRadius: 8, overflow: "hidden" }}>
        {FILTERS.map((f) => {
          const active = filter === f;
          return (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              style={{
                appearance: "none",
                flex: 1,
                textAlign: "center",
                padding: "9px 4px",
                font: "400 12.5px/1.3 var(--font-body)",
                cursor: "pointer",
                background: active ? "rgba(145,132,217,.18)" : "transparent",
                color: active ? "var(--accent-300)" : "var(--color-text-muted)",
                border: "none",
              }}
            >
              {f}
            </button>
          );
        })}
      </div>

      {groups.length === 0 && (
        <div style={{ font: "400 13px/1.5 var(--font-body)", color: "var(--color-text-muted)", textAlign: "center", padding: "24px 0" }}>
          Ingen transaksjoner i dette filteret.
        </div>
      )}

      {groups.map((g) => (
        <div key={g.day} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "6px 0 4px" }}>
            <span className="eyebrow">{g.day}</span>
            <span style={{ font: "400 11.5px/1 var(--font-body)", color: "var(--color-text-muted)" }}>{nok(g.total)} kr</span>
          </div>
          {g.rows.map((row, i) => (
            <TransactionRow key={`${row.name}-${i}`} row={row} />
          ))}
        </div>
      ))}
    </div>
  );
}
