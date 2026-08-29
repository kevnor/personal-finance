import BackHeader from "../components/BackHeader.jsx";
import { Empty, ErrorState, InlineError, Loading } from "../components/States.jsx";
import { useAppData } from "../context/AppData.jsx";
import { useAction, useResource } from "../hooks/useResource.js";
import { api } from "../lib/api.js";
import { shortDate } from "../lib/dates.js";
import { nok } from "../lib/format.js";
import { displayName } from "../lib/rows.js";

export default function Review({ revision, onChanged, onBack, onUnauthorized }) {
  const { expenseCategories, labelFor } = useAppData();
  const queue = useResource(
    () => api.transactions.list({ needs_review: true, limit: 500 }),
    [revision],
    { onUnauthorized },
  );
  const resolve = useAction({ onUnauthorized });

  if (queue.error) return <ErrorState error={queue.error} onRetry={queue.reload} />;
  if (!queue.data) return <Loading />;

  const rows = queue.data;
  const current = rows[0];

  const counter = (
    <div style={{ font: "400 12px/1 var(--font-body)", color: "var(--color-text-muted)" }}>
      {rows.length === 0 ? "ferdig" : `${rows.length} igjen`}
    </div>
  );

  if (!current) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <BackHeader title="Gjennomgang" onBack={onBack} right={counter} />
        <Empty title="Alt gjennomgått" hint="Ingen flere rader trenger kategori akkurat nå." />
      </div>
    );
  }

  // Teaching a rule from the counterparty when there is one, and from the
  // whole description otherwise. A full statement description carries dates
  // and reference numbers that never recur verbatim, so a rule keyed on one
  // would match exactly the row it came from and nothing else -- which is
  // the same as not teaching at all.
  const pattern = current.counterparty?.trim() || current.description.trim();
  const teachable = pattern.length >= 3 && pattern.length <= 60;

  const choose = async (category) => {
    const result = await resolve.run(() =>
      api.transactions.patch(current.id, {
        category,
        teach: teachable,
        teach_pattern: teachable ? pattern.toLowerCase() : undefined,
      }),
    );
    if (result) {
      queue.reload();
      onChanged();
    }
  };

  // The row's current guess first, then the rest: the guess is right often
  // enough that confirming it should be the shortest path.
  const suggested = current.category;
  const options = [
    ...(suggested ? [suggested] : []),
    ...expenseCategories.map((c) => c.name).filter((name) => name !== suggested),
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <BackHeader title="Gjennomgang" onBack={onBack} right={counter} />
      <InlineError error={resolve.error} />

      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ font: "500 17px/1.3 var(--font-heading)" }}>{displayName(current)}</div>
        <div
          style={{
            font: "400 12.5px/1.4 var(--font-body)",
            color: "var(--color-text-muted)",
            wordBreak: "break-word",
          }}
        >
          {current.description}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginTop: 8,
          }}
        >
          <span style={{ font: "400 12.5px/1 var(--font-body)", color: "var(--color-text-muted)" }}>
            {shortDate(current.date)} · {current.account}
          </span>
          <span className="tabular" style={{ font: "500 17px/1 var(--font-heading)" }}>
            {current.amount >= 0 ? "+" : "−"}
            {nok(Math.abs(current.amount))} kr
          </span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="eyebrow">velg kategori — foreslått er uthevet</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
          {options.map((name) => {
            const isSuggested = name === suggested;
            return (
              <button
                key={name}
                type="button"
                onClick={() => choose(name)}
                disabled={resolve.pending}
                style={{
                  appearance: "none",
                  padding: "8px 12px",
                  borderRadius: 8,
                  font: "400 12.5px/1.2 var(--font-body)",
                  cursor: resolve.pending ? "not-allowed" : "pointer",
                  opacity: resolve.pending ? 0.5 : 1,
                  background: isSuggested ? "rgba(145,132,217,.18)" : "transparent",
                  color: isSuggested ? "var(--accent-200)" : "var(--color-text-muted)",
                  border: `1px solid ${isSuggested ? "rgba(145,132,217,.5)" : "var(--color-divider-strong)"}`,
                }}
              >
                {labelFor(name)}
              </button>
            );
          })}
        </div>
        <div style={{ font: "400 11.5px/1.5 var(--font-body)", color: "var(--color-text-faint)" }}>
          {teachable
            ? `Valget lagrer en regel for «${pattern.toLowerCase()}», slik at neste treff kategoriseres automatisk.`
            : "Valget gjelder bare denne raden."}
        </div>
      </div>
    </div>
  );
}
