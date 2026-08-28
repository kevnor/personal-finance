import BackHeader from "../components/BackHeader.jsx";
import { nok } from "../lib/format.js";
import { CATEGORY_OPTIONS } from "../lib/mockData.js";

export default function Review({ queue, total, onResolve, onBack }) {
  const current = queue[0];
  const reviewed = total - queue.length;

  const counter = (
    <div style={{ font: "400 12px/1 var(--font-body)", color: "var(--color-text-muted)" }}>
      {current ? `${reviewed + 1} av ${total}` : `${total} av ${total}`}
    </div>
  );

  if (!current) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <BackHeader title="Gjennomgang" onBack={onBack} right={counter} />
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 8,
            padding: "48px 12px",
            textAlign: "center",
          }}
        >
          <div style={{ font: "500 17px/1.3 var(--font-heading)" }}>Alt gjennomgått</div>
          <div style={{ font: "400 13px/1.5 var(--font-body)", color: "var(--color-text-muted)" }}>
            Ingen flere rader trenger kategori akkurat nå.
          </div>
        </div>
      </div>
    );
  }

  const chips = [current.suggested, ...CATEGORY_OPTIONS.filter((c) => c !== current.suggested)];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <BackHeader title="Gjennomgang" onBack={onBack} right={counter} />

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ font: "500 17px/1.3 var(--font-heading)" }}>{current.name}</div>
        <div style={{ font: "400 12.5px/1.4 var(--font-body)", color: "var(--color-text-muted)" }}>{current.memo}</div>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginTop: 8 }}>
          <span style={{ font: "400 12.5px/1 var(--font-body)", color: "var(--color-text-muted)" }}>
            {new Date(current.date).toLocaleDateString("nb-NO", { day: "numeric", month: "long" })}
          </span>
          <span className="tabular" style={{ font: "500 17px/1 var(--font-heading)" }}>
            −{nok(current.amount)} kr
          </span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="eyebrow">velg kategori — foreslått er uthevet</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
          {chips.map((category) => {
            const suggested = category === current.suggested;
            return (
              <button
                key={category}
                type="button"
                onClick={() => onResolve(current.id, category)}
                style={{
                  appearance: "none",
                  padding: "8px 12px",
                  borderRadius: 8,
                  font: "400 12.5px/1.2 var(--font-body)",
                  cursor: "pointer",
                  background: suggested ? "rgba(145,132,217,.18)" : "transparent",
                  color: suggested ? "var(--accent-200)" : "var(--color-text-muted)",
                  border: `1px solid ${suggested ? "rgba(145,132,217,.5)" : "var(--color-divider-strong)"}`,
                }}
              >
                {category}
              </button>
            );
          })}
        </div>
        <div style={{ font: "400 11.5px/1.5 var(--font-body)", color: "var(--color-text-faint)" }}>
          Å velge en kategori lagrer en regel for «{current.name.toLowerCase()}», slik at neste treff kategoriseres automatisk.
        </div>
      </div>
    </div>
  );
}
