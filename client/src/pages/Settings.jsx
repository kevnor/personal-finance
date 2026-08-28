import { nok } from "../lib/format.js";
import { POOL_ROWS, DAILY_RATE, WEEK_ENVELOPE } from "../lib/mockData.js";

export default function Settings() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ font: "500 22px/1.15 var(--font-heading)", letterSpacing: "-.015em" }}>Innstillinger</div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 11 }}>
        <div className="eyebrow">månedens pott</div>
        {POOL_ROWS.map((p) => (
          <div
            key={p.label}
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              font: "400 13px/1.3 var(--font-body)",
              color: p.highlight ? "var(--accent-300)" : "rgba(233,233,237,.75)",
            }}
          >
            <span>{p.label}</span>
            <span className="tabular">
              {p.value < 0 ? "−" : ""}
              {nok(Math.abs(p.value))}
            </span>
          </div>
        ))}
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            font: "400 13px/1.3 var(--font-body)",
            color: "var(--accent-300)",
          }}
        >
          <span>Per dag / per uke</span>
          <span className="tabular">
            {nok(DAILY_RATE)} / {nok(WEEK_ENVELOPE)}
          </span>
        </div>
      </div>

      <div style={{ font: "400 12px/1.55 var(--font-body)", color: "var(--color-text-faint)" }}>
        Inntekt og faste utgifter er satt manuelt inntil én hel kalendermåned finnes, deretter beregnes de av
        snittet. Sparemål og kategoribehandling redigeres her.
      </div>
    </div>
  );
}
