import { nok } from "../lib/format.js";

export default function AttentionBanner({ reviewCount, owed, onDismiss, onReviewClick, onOwedClick }) {
  if (reviewCount === 0 && owed === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 11,
        padding: "11px 12px",
        borderRadius: 8,
        background: "var(--accent-900)",
        border: "1px solid rgba(145,132,217,.3)",
      }}
    >
      <div
        style={{
          width: 6,
          height: 6,
          borderRadius: 9999,
          background: "var(--accent-500)",
          flex: "none",
          boxShadow: "0 0 8px 2px rgba(145,132,217,.5)",
        }}
      />
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
        {reviewCount > 0 && (
          <button
            type="button"
            onClick={onReviewClick}
            style={{
              appearance: "none",
              background: "none",
              border: "none",
              padding: 0,
              textAlign: "left",
              cursor: "pointer",
              font: "500 12.5px/1.3 var(--font-heading)",
              color: "var(--accent-200)",
            }}
          >
            {reviewCount} {reviewCount === 1 ? "rad trenger" : "rader trenger"} gjennomgang
          </button>
        )}
        {owed > 0 && (
          <button
            type="button"
            onClick={onOwedClick}
            style={{
              appearance: "none",
              background: "none",
              border: "none",
              padding: 0,
              textAlign: "left",
              cursor: "pointer",
              font: "400 11.5px/1.35 var(--font-body)",
              color: "var(--color-text-muted)",
            }}
          >
            {reviewCount > 0 ? "og " : ""}
            {nok(owed, 0)} kr står utestående fra arbeidsgiver
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Lukk"
        style={{
          appearance: "none",
          background: "none",
          border: "none",
          width: 44,
          height: 44,
          margin: "-11px -8px -11px 0",
          display: "grid",
          placeItems: "center",
          cursor: "pointer",
          color: "var(--color-text-muted)",
          fontSize: 17,
        }}
      >
        ✕
      </button>
    </div>
  );
}
