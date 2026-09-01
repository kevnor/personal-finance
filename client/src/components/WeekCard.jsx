import { nok } from "../lib/format.js";

const MAX_BAR = 1200;

function barFill(day, rate) {
  if (day.amount === 0) return "var(--neutral-900)";
  if (day.isToday) return "var(--accent-500)";
  return day.amount > rate ? "var(--accent-700)" : "var(--accent-800)";
}

export default function WeekCard({ weekLabel, rate, days }) {
  const rateLineBottom = Math.round((rate / MAX_BAR) * 96) + 17;

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 11 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <span className="eyebrow">{weekLabel}</span>
        <span style={{ font: "400 12px/1 var(--font-body)", color: "var(--color-text-muted)" }}>
          dagsrate {nok(rate)} kr
        </span>
      </div>
      <div style={{ position: "relative", display: "flex", alignItems: "flex-end", gap: 7, height: 70 }}>
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: rateLineBottom,
            height: 1,
            background:
              "linear-gradient(to right, rgba(145,132,217,.15), rgba(145,132,217,.55), rgba(145,132,217,.15))",
          }}
        />
        {days.map((d) => (
          <div
            key={d.label}
            style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", alignItems: "center", gap: 5, height: "100%" }}
          >
            <div
              style={{
                width: "100%",
                maxWidth: 24,
                height: Math.max(3, Math.round((d.amount / MAX_BAR) * 70)),
                borderRadius: 3,
                background: barFill(d, rate),
              }}
            />
            <div style={{ font: "400 10px/1 var(--font-body)", color: d.isToday ? "var(--accent-300)" : "var(--color-text-muted)" }}>
              {d.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
