import { useMemo, useState } from "react";
import { ErrorState, Empty, Loading } from "../components/States.jsx";
import TransactionRow from "../components/TransactionRow.jsx";
import { useAppData } from "../context/AppData.jsx";
import { useResource } from "../hooks/useResource.js";
import { api } from "../lib/api.js";
import { addDays, longDate } from "../lib/dates.js";
import { nok } from "../lib/format.js";
import { groupByDay, isOutsideEnvelope, toRow } from "../lib/rows.js";

const FILTERS = [
  { id: "all", label: "Alle" },
  { id: "inside", label: "I rammen" },
  { id: "outside", label: "Utenfor" },
];

const WINDOW_DAYS = 60;

export default function History({ revision, onUnauthorized }) {
  const [filter, setFilter] = useState("all");
  const { labelFor } = useAppData();

  const budget = useResource(() => api.budget.get(), [revision], { onUnauthorized });
  const day = budget.data?.day;

  const history = useResource(
    () =>
      day
        ? api.transactions.list({ from: addDays(day, -WINDOW_DAYS), to: day, limit: 500 })
        : Promise.resolve(null),
    [revision, day],
    { onUnauthorized },
  );

  const groups = useMemo(() => {
    const rows = history.data ?? [];
    const filtered =
      filter === "all"
        ? rows
        : rows.filter((tx) => isOutsideEnvelope(tx) === (filter === "outside"));
    return groupByDay(filtered);
  }, [history.data, filter]);

  if (budget.error) return <ErrorState error={budget.error} onRetry={budget.reload} />;
  if (history.error) return <ErrorState error={history.error} onRetry={history.reload} />;
  if (!history.data) return <Loading />;

  const figures = budget.data.figures;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <div style={{ font: "500 22px/1.15 var(--font-heading)", letterSpacing: "-.015em" }}>
          Historikk
        </div>
        <div
          style={{ font: "400 12.5px/1.4 var(--font-body)", color: "var(--color-text-muted)", marginTop: 3 }}
        >
          denne uken · brukt {nok(figures.week_spent)} av {nok(figures.week_envelope)} kr
        </div>
      </div>

      <div
        role="tablist"
        style={{
          display: "flex",
          border: "1px solid var(--color-divider-strong)",
          borderRadius: 8,
          overflow: "hidden",
        }}
      >
        {FILTERS.map((f) => {
          const active = filter === f.id;
          return (
            <button
              key={f.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setFilter(f.id)}
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
              {f.label}
            </button>
          );
        })}
      </div>

      {groups.length === 0 && (
        <Empty
          title="Ingen transaksjoner"
          hint={
            filter === "all"
              ? `Ingenting registrert de siste ${WINDOW_DAYS} dagene.`
              : "Ingen transaksjoner i dette filteret."
          }
        />
      )}

      {groups.map((group) => (
        <div key={group.date} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              padding: "6px 0 4px",
            }}
          >
            <span className="eyebrow">{longDate(group.date)}</span>
            <span style={{ font: "400 11.5px/1 var(--font-body)", color: "var(--color-text-muted)" }}>
              {nok(Math.abs(group.total))} kr
            </span>
          </div>
          {group.rows.map((tx) => (
            <TransactionRow key={tx.id} row={toRow(tx, labelFor)} />
          ))}
        </div>
      ))}
    </div>
  );
}
