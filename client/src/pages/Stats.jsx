import { useMemo } from "react";
import { ErrorState, Empty, Loading } from "../components/States.jsx";
import { useAppData } from "../context/AppData.jsx";
import { useResource } from "../hooks/useResource.js";
import { api } from "../lib/api.js";
import { addDays, isoWeek } from "../lib/dates.js";
import { nok } from "../lib/format.js";
import { isOutsideEnvelope } from "../lib/rows.js";

const WEEKS = 5;
const CATEGORY_COLOURS = [
  "var(--accent-500)",
  "var(--accent-600)",
  "var(--accent-700)",
  "var(--accent-800)",
  "var(--accent-800)",
  "var(--accent-800)",
];

/**
 * Weekly totals and the biggest categories, computed here from the rows.
 *
 * The server has no aggregate endpoint and does not need one for this: five
 * weeks is at most a few hundred rows, and the alternative is an endpoint
 * whose bucketing could disagree with `/api/budget`. The filter mirrors the
 * server's `_variable_spent` exactly -- expense categories on `variable`
 * treatment -- so the bars are the same money the envelope counts.
 */
function summarise(rows, weekStart) {
  const weeks = [];
  for (let i = WEEKS - 1; i >= 0; i -= 1) {
    const start = addDays(weekStart, -7 * i);
    weeks.push({ start, end: addDays(start, 6), amount: 0, isCurrent: i === 0 });
  }

  const categories = new Map();
  for (const tx of rows) {
    if (isOutsideEnvelope(tx) || tx.category_kind !== "expense") continue;
    const amount = -tx.amount;
    const week = weeks.find((w) => tx.date >= w.start && tx.date <= w.end);
    if (week) week.amount += amount;
    categories.set(tx.category, (categories.get(tx.category) ?? 0) + amount);
  }

  const top = [...categories.entries()]
    .map(([name, value]) => ({ name, value }))
    .filter((c) => c.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);
  const largest = top[0]?.value ?? 0;

  return {
    weeks: weeks.map((w) => ({ ...w, amount: Math.max(0, w.amount) })),
    top: top.map((c) => ({ ...c, pct: largest > 0 ? (c.value / largest) * 100 : 0 })),
  };
}

export default function Stats({ revision, onUnauthorized }) {
  const { labelFor } = useAppData();
  const budget = useResource(() => api.budget.get(), [revision], { onUnauthorized });
  const weekStart = budget.data?.week_start;

  const history = useResource(
    () =>
      weekStart
        ? api.transactions.list({
            from: addDays(weekStart, -7 * (WEEKS - 1)),
            to: addDays(weekStart, 6),
            limit: 500,
          })
        : Promise.resolve(null),
    [revision, weekStart],
    { onUnauthorized },
  );

  const summary = useMemo(
    () => (history.data && weekStart ? summarise(history.data, weekStart) : null),
    [history.data, weekStart],
  );

  if (budget.error) return <ErrorState error={budget.error} onRetry={budget.reload} />;
  if (history.error) return <ErrorState error={history.error} onRetry={history.reload} />;
  if (!summary) return <Loading />;

  const envelope = budget.data.figures.week_envelope;
  // Scaled to the tallest bar or the envelope line, whichever is higher, so
  // an overspent week is visibly over the line rather than clipped at it.
  const ceiling = Math.max(envelope, ...summary.weeks.map((w) => w.amount)) || 1;
  const barHeight = (amount) => Math.round((amount / ceiling) * 74);
  const overWeeks = summary.weeks.filter((w) => w.amount > envelope);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div>
        <div style={{ font: "500 22px/1.15 var(--font-heading)", letterSpacing: "-.015em" }}>
          Statistikk
        </div>
        <div
          style={{ font: "400 12.5px/1.4 var(--font-body)", color: "var(--color-text-muted)", marginTop: 3 }}
        >
          variabelt forbruk · siste {WEEKS} uker
        </div>
      </div>

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 11 }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <span className="eyebrow">uke for uke</span>
          <span style={{ font: "400 12px/1 var(--font-body)", color: "var(--color-text-muted)" }}>
            ramme {nok(envelope)} kr
          </span>
        </div>
        <div
          style={{ position: "relative", display: "flex", alignItems: "flex-end", gap: 9, height: 96 }}
        >
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: barHeight(envelope) + 16,
              height: 1,
              background:
                "linear-gradient(to right, rgba(145,132,217,.15), rgba(145,132,217,.55), rgba(145,132,217,.15))",
            }}
          />
          {summary.weeks.map((week) => (
            <div
              key={week.start}
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                justifyContent: "flex-end",
                alignItems: "center",
                gap: 6,
                height: "100%",
              }}
            >
              <div
                style={{
                  width: "100%",
                  maxWidth: 30,
                  height: Math.max(2, barHeight(week.amount)),
                  borderRadius: "4px 4px 2px 2px",
                  background: week.isCurrent
                    ? "var(--accent-500)"
                    : week.amount > envelope
                      ? "var(--accent-700)"
                      : "var(--accent-800)",
                }}
              />
              <div
                style={{
                  font: "400 10px/1 var(--font-body)",
                  color: week.isCurrent ? "var(--accent-300)" : "var(--color-text-muted)",
                }}
              >
                u{isoWeek(week.start)}
              </div>
            </div>
          ))}
        </div>
        {overWeeks.length > 0 && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              font: "400 11px/1.4 var(--font-body)",
              color: "var(--color-text-muted)",
            }}
          >
            <span style={{ width: 14, height: 1, background: "var(--accent-500)", display: "inline-block" }} />
            {overWeeks.length === 1 ? "en uke over rammen" : `${overWeeks.length} uker over rammen`} —{" "}
            {overWeeks.map((w) => nok(w.amount)).join(" og ")}
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
        <div className="eyebrow">største kategorier</div>
        {summary.top.length === 0 ? (
          <Empty title="Ingen data ennå" hint="Importer et kontoutdrag eller legg inn en utgift." />
        ) : (
          summary.top.map((category, index) => (
            <div key={category.name} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  font: "400 12.5px/1.3 var(--font-body)",
                }}
              >
                <span>{labelFor(category.name)}</span>
                <span className="tabular" style={{ color: "rgba(233,233,237,.7)" }}>
                  {nok(category.value)}
                </span>
              </div>
              <div
                style={{ height: 5, borderRadius: 9999, background: "var(--color-surface)", overflow: "hidden" }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${category.pct}%`,
                    borderRadius: 9999,
                    background: CATEGORY_COLOURS[index],
                  }}
                />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
