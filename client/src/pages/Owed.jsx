import BackHeader from "../components/BackHeader.jsx";
import { Empty, ErrorState, InlineError, Loading } from "../components/States.jsx";
import { useAction, useResource } from "../hooks/useResource.js";
import { api } from "../lib/api.js";
import { shortDate } from "../lib/dates.js";
import { nok } from "../lib/format.js";

export default function Owed({ revision, onChanged, onBack, onUnauthorized }) {
  const owed = useResource(() => api.reimbursements.list(), [revision], { onUnauthorized });
  const settle = useAction({ onUnauthorized });

  if (owed.error) return <ErrorState error={owed.error} onRetry={owed.reload} />;
  if (!owed.data) return <Loading />;

  const items = owed.data;
  const total = items.reduce((sum, item) => sum + item.expected_amount, 0);

  const markSettled = async (id) => {
    const result = await settle.run(() => api.reimbursements.settle(id));
    if (result) {
      owed.reload();
      onChanged();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <BackHeader title="Utestående" onBack={onBack} />
      <InlineError error={settle.error} />

      {items.length === 0 ? (
        <Empty title="Ingenting utestående" hint="Alle refusjoner er mottatt." />
      ) : (
        <>
          <div style={{ font: "400 12.5px/1.4 var(--font-body)", color: "var(--color-text-muted)" }}>
            <span
              className="tabular"
              style={{ font: "500 22px/1 var(--font-heading)", color: "var(--color-text)" }}
            >
              {nok(total, 0)} kr
            </span>{" "}
            totalt utestående
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {items.map((item) => (
              <div
                key={item.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 0",
                  borderBottom: "1px solid var(--color-divider)",
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: "var(--accent-400)",
                    flex: "none",
                    display: "grid",
                    placeItems: "center",
                    font: "500 12px var(--font-heading)",
                    color: "#161826",
                  }}
                >
                  {item.description[0]}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      font: "400 13.5px/1.3 var(--font-body)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {item.description}
                  </div>
                  <div
                    style={{
                      font: "400 11.5px/1.3 var(--font-body)",
                      color: "var(--color-text-muted)",
                      marginTop: 2,
                    }}
                  >
                    {item.expected_from} · {nok(item.expected_amount)} kr · kjøpt {shortDate(item.date)}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => markSettled(item.id)}
                  disabled={settle.pending}
                  style={{
                    appearance: "none",
                    flex: "none",
                    padding: "7px 11px",
                    borderRadius: 8,
                    border: "1px solid var(--accent-500)",
                    background: "none",
                    font: "400 11.5px/1.2 var(--font-body)",
                    color: "var(--accent-300)",
                    cursor: settle.pending ? "not-allowed" : "pointer",
                    opacity: settle.pending ? 0.5 : 1,
                    whiteSpace: "nowrap",
                  }}
                >
                  merk mottatt
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
