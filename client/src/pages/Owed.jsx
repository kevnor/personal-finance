import BackHeader from "../components/BackHeader.jsx";
import { nok } from "../lib/format.js";

export default function Owed({ items, onSettle, onBack }) {
  const total = items.reduce((sum, item) => sum + item.amount, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <BackHeader title="Utestående" onBack={onBack} />

      {items.length === 0 ? (
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
          <div style={{ font: "500 17px/1.3 var(--font-heading)" }}>Ingenting utestående</div>
          <div style={{ font: "400 13px/1.5 var(--font-body)", color: "var(--color-text-muted)" }}>
            Alle refusjoner er mottatt.
          </div>
        </div>
      ) : (
        <>
          <div style={{ font: "400 12.5px/1.4 var(--font-body)", color: "var(--color-text-muted)" }}>
            <span className="tabular" style={{ font: "500 22px/1 var(--font-heading)", color: "var(--color-text)" }}>
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
                  {item.name[0]}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ font: "400 13.5px/1.3 var(--font-body)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {item.name}
                  </div>
                  <div style={{ font: "400 11.5px/1.3 var(--font-body)", color: "var(--color-text-muted)", marginTop: 2 }}>
                    {item.expectedFrom} · {nok(item.amount)} kr · kjøpt{" "}
                    {new Date(item.date).toLocaleDateString("nb-NO", { day: "numeric", month: "long" })}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onSettle(item.id)}
                  style={{
                    appearance: "none",
                    flex: "none",
                    padding: "7px 11px",
                    borderRadius: 8,
                    border: "1px solid var(--accent-500)",
                    background: "none",
                    font: "400 11.5px/1.2 var(--font-body)",
                    color: "var(--accent-300)",
                    cursor: "pointer",
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
