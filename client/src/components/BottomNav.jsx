const TABS_LEFT = [
  { id: "home", label: "Hjem", radius: "9999px" },
  { id: "history", label: "Historikk", radius: "3px" },
];

const TABS_RIGHT = [
  { id: "stats", label: "Statistikk", radius: "3px 3px 9px 9px" },
  { id: "settings", label: "Innstillinger", radius: "3px 9px 3px 9px" },
];

function Tab({ tab, active, onSelect }) {
  const color = active ? "var(--accent-300)" : "var(--color-text-muted)";
  return (
    <button
      type="button"
      onClick={() => onSelect(tab.id)}
      style={{
        appearance: "none",
        background: "none",
        border: "none",
        padding: 0,
        width: 60,
        minHeight: 46,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 5,
        cursor: "pointer",
        color,
      }}
    >
      <span
        style={{
          width: 18,
          height: 18,
          borderRadius: tab.radius,
          border: `1.6px solid ${color}`,
          background: active ? "rgba(145,132,217,.35)" : "transparent",
        }}
      />
      <span style={{ font: "400 10.5px/1 var(--font-body)" }}>{tab.label}</span>
    </button>
  );
}

export default function BottomNav({ active, onSelect, onAdd }) {
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 65,
        height: 84,
        background: "var(--color-surface-raised)",
        boxShadow: "var(--shadow-nav)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        padding: "9px 26px 0",
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", gap: 6 }}>
        {TABS_LEFT.map((tab) => (
          <Tab key={tab.id} tab={tab} active={active === tab.id} onSelect={onSelect} />
        ))}
      </div>
      <button
        type="button"
        onClick={onAdd}
        aria-label="Ny utgift"
        style={{
          appearance: "none",
          position: "absolute",
          left: "50%",
          top: 9,
          transform: "translateX(-50%)",
          width: 46,
          height: 46,
          borderRadius: 9999,
          background: "var(--color-sheet)",
          border: "1px solid var(--accent-500)",
          boxShadow: "0 0 18px rgba(145,132,217,.3)",
          display: "grid",
          placeItems: "center",
          font: "400 24px/1 var(--font-body)",
          color: "var(--accent-300)",
          cursor: "pointer",
        }}
      >
        +
      </button>
      <div style={{ display: "flex", gap: 6 }}>
        {TABS_RIGHT.map((tab) => (
          <Tab key={tab.id} tab={tab} active={active === tab.id} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
