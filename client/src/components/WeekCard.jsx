import { useState } from "react";
import { nok } from "../lib/format.js";

const MAX_BAR = 1200;

function barFill(day) {
  if (day.amount === 0) return "var(--neutral-900)";
  if (day.isToday) return "var(--accent-500)";
  return day.amount > day.rate ? "var(--accent-700)" : "var(--accent-800)";
}

export default function WeekCard({ weekLabel, remaining, envelope, rate, days }) {
  const [open, setOpen] = useState(false);
  const spent = envelope - remaining;
  const pct = Math.min(100, Math.max(0, (spent / envelope) * 100));
  const rateLineBottom = Math.round((rate / MAX_BAR) * 96) + 17;

  return (
    <div
      className="card"
      style={{ cursor: "pointer", display: "flex", flexDirection: "column", gap: 12 }}
      role="button"
      tabIndex={0}
      onClick={() => setOpen((v) => !v)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setOpen((v) => !v)}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="eyebrow">igjen denne uken</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginTop: 6 }}>
            <span className="tabular" style={{ font: "500 25px/1 var(--font-heading)", letterSpacing: "-.02em" }}>
              {nok(remaining)}
            </span>
            <span style={{ font: "400 12.5px/1 var(--font-body)", color: "var(--color-text-muted)" }}>
              av {nok(envelope)} kr
            </span>
          </div>
        </div>
        <div
          style={{
            font: "400 20px/1 var(--font-body)",
            color: "var(--color-text-faint)",
            transform: open ? "rotate(180deg)" : "none",
            transition: "transform .2s ease",
          }}
        >
          ⌄
        </div>
      </div>
      <div style={{ height: 5, borderRadius: 9999, background: "var(--neutral-900)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: "var(--accent-500)", borderRadius: 9999 }} />
      </div>
      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 9, paddingTop: 4 }}>
          <div style={{ position: "relative", display: "flex", alignItems: "flex-end", gap: 8, height: 104, paddingTop: 4 }}>
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
                style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6, justifyContent: "flex-end", height: "100%" }}
              >
                <div
                  style={{
                    width: "100%",
                    maxWidth: 26,
                    height: Math.max(3, Math.round((d.amount / MAX_BAR) * 96)),
                    borderRadius: "4px 4px 2px 2px",
                    background: barFill({ ...d, rate }),
                  }}
                />
                <div style={{ font: "400 10.5px/1 var(--font-body)", color: d.isToday ? "var(--accent-300)" : "var(--color-text-muted)" }}>
                  {d.label}
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 7, font: "400 11px/1.4 var(--font-body)", color: "var(--color-text-muted)" }}>
            <span style={{ width: 14, height: 1, background: "var(--accent-500)", display: "inline-block" }} />
            dagsrate {nok(rate)} kr
          </div>
        </div>
      )}
    </div>
  );
}
