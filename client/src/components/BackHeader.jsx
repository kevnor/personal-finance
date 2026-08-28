export default function BackHeader({ title, onBack, right }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button
          type="button"
          onClick={onBack}
          aria-label="Tilbake"
          style={{
            appearance: "none",
            background: "none",
            border: "none",
            padding: "8px 6px 8px 0",
            margin: "-8px 0 -8px -6px",
            cursor: "pointer",
            font: "400 20px/1 var(--font-body)",
            color: "var(--color-text-muted)",
          }}
        >
          ←
        </button>
        <div style={{ font: "500 22px/1.15 var(--font-heading)", letterSpacing: "-.015em" }}>{title}</div>
      </div>
      {right}
    </div>
  );
}
