import { nok } from "../lib/format.js";
import { WEEK_TOTALS, WEEK_ENVELOPE, TOP_CATEGORIES } from "../lib/mockData.js";

const MAX_WEEK_BAR = 4800;

function weekFill(w) {
  if (w.isCurrent) return "var(--accent-500)";
  return w.amount > WEEK_ENVELOPE ? "var(--accent-700)" : "var(--accent-800)";
}

const CATEGORY_COLORS = ["var(--accent-500)", "var(--accent-600)", "var(--accent-700)", "var(--accent-800)", "var(--accent-800)", "var(--accent-800)"];

export default function Stats() {
  const envelopeLineBottom = Math.round((WEEK_ENVELOPE / MAX_WEEK_BAR) * 74) + 16;
  const overWeeks = WEEK_TOTALS.filter((w) => w.amount > WEEK_ENVELOPE);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div>
        <div style={{ font: "500 22px/1.15 var(--font-heading)", letterSpacing: "-.015em" }}>Statistikk</div>
        <div style={{ font: "400 12.5px/1.4 var(--font-body)", color: "var(--color-text-muted)", marginTop: 3 }}>
          variabelt forbruk · siste 30 dager
        </div>
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 11 }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <span className="eyebrow">uke for uke</span>
          <span style={{ font: "400 12px/1 var(--font-body)", color: "var(--color-text-muted)" }}>
            ramme {nok(WEEK_ENVELOPE)} kr
          </span>
        </div>
        <div style={{ position: "relative", display: "flex", alignItems: "flex-end", gap: 9, height: 96 }}>
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: envelopeLineBottom,
              height: 1,
              background: "linear-gradient(to right, rgba(145,132,217,.15), rgba(145,132,217,.55), rgba(145,132,217,.15))",
            }}
          />
          {WEEK_TOTALS.map((w) => (
            <div key={w.label} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", alignItems: "center", gap: 6, height: "100%" }}>
              <div
                style={{
                  width: "100%",
                  maxWidth: 30,
                  height: Math.round((w.amount / MAX_WEEK_BAR) * 74),
                  borderRadius: "4px 4px 2px 2px",
                  background: weekFill(w),
                }}
              />
              <div style={{ font: "400 10px/1 var(--font-body)", color: w.isCurrent ? "var(--accent-300)" : "var(--color-text-muted)" }}>
                {w.label}
              </div>
            </div>
          ))}
        </div>
        {overWeeks.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 7, font: "400 11px/1.4 var(--font-body)", color: "var(--color-text-muted)" }}>
            <span style={{ width: 14, height: 1, background: "var(--accent-500)", display: "inline-block" }} />
            {overWeeks.length === 1 ? "en uke over rammen" : `${overWeeks.length} uker over rammen`} —{" "}
            {overWeeks.map((w) => nok(w.amount)).join(" og ")}
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
        <div className="eyebrow">største kategorier</div>
        {TOP_CATEGORIES.map((c, i) => (
          <div key={c.name} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", font: "400 12.5px/1.3 var(--font-body)" }}>
              <span>{c.name}</span>
              <span className="tabular" style={{ color: "rgba(233,233,237,.7)" }}>
                {nok(c.value)}
              </span>
            </div>
            <div style={{ height: 5, borderRadius: 9999, background: "var(--color-surface)", overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${c.pct}%`, borderRadius: 9999, background: CATEGORY_COLORS[i] }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
