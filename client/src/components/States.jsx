// Loading, error and empty states.
//
// Shared rather than written per screen, because the three of them are what
// separates "the app is working and there is nothing here" from "the app is
// broken and is showing you nothing". Rendering an empty list for a failed
// request tells the user their week was free.

export function Loading({ label = "Laster…" }) {
  return (
    <div
      role="status"
      style={{
        display: "grid",
        placeItems: "center",
        padding: "56px 12px",
        font: "400 13px/1.5 var(--font-body)",
        color: "var(--color-text-muted)",
      }}
    >
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div
      role="alert"
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 10,
        padding: "40px 12px",
        textAlign: "center",
      }}
    >
      <div style={{ font: "500 15px/1.3 var(--font-heading)" }}>Noe gikk galt</div>
      <div style={{ font: "400 12.5px/1.5 var(--font-body)", color: "var(--color-text-muted)", maxWidth: 320 }}>
        {error?.detail ?? error?.message ?? "Ukjent feil."}
      </div>
      {onRetry && (
        <button type="button" className="btn-outline" onClick={onRetry} style={{ marginTop: 4 }}>
          Prøv igjen
        </button>
      )}
    </div>
  );
}

export function Empty({ title, hint }) {
  return (
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
      <div style={{ font: "500 17px/1.3 var(--font-heading)" }}>{title}</div>
      {hint && (
        <div style={{ font: "400 13px/1.5 var(--font-body)", color: "var(--color-text-muted)" }}>{hint}</div>
      )}
    </div>
  );
}

/**
 * A form-level error message.
 *
 * Distinct from ErrorState: that one replaces a screen that could not load,
 * this one sits beside a control the user can correct and try again.
 */
export function InlineError({ error }) {
  if (!error) return null;
  return (
    <div
      role="alert"
      style={{
        font: "400 12px/1.4 var(--font-body)",
        color: "var(--accent-200)",
        background: "var(--accent-900)",
        border: "1px solid rgba(145,132,217,.3)",
        borderRadius: 8,
        padding: "9px 11px",
      }}
    >
      {error?.detail ?? error?.message ?? "Ukjent feil."}
    </div>
  );
}

/**
 * A standing notice that the device is offline.
 *
 * The offline behaviour is deliberately asymmetric — reads fall back to the
 * last cached response, writes fail outright — so without this the app looks
 * normal while silently refusing to save anything.
 */
export function OfflineBar() {
  return (
    <div
      role="status"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 12px",
        borderRadius: 8,
        background: "var(--neutral-900)",
        border: "1px solid var(--color-divider-strong)",
        font: "400 11.5px/1.4 var(--font-body)",
        color: "var(--color-text-muted)",
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: 9999,
          background: "var(--color-text-faint)",
          flex: "none",
        }}
      />
      Ingen forbindelse — viser sist lagrede tall. Nye utgifter kan ikke lagres nå.
    </div>
  );
}
