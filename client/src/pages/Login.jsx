import { useState } from "react";
import { InlineError } from "../components/States.jsx";
import { useAction } from "../hooks/useResource.js";
import { api } from "../lib/api.js";

/**
 * First run and sign-in, which are the same screen in two modes.
 *
 * `configured` comes from /api/auth/status, which is unauthenticated
 * precisely so the client can make this choice. On first run there is
 * nothing to authenticate against, so setting the passcode is also what
 * signs you in; afterwards that endpoint is closed and this is a login.
 */
export default function Login({ configured, onSignedIn }) {
  const [passcode, setPasscode] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [mismatch, setMismatch] = useState(false);
  const { run, pending, error } = useAction();

  const firstRun = !configured;
  const canSubmit = passcode.length > 0 && (!firstRun || confirmation.length > 0) && !pending;

  const submit = async (event) => {
    event.preventDefault();
    setMismatch(false);
    if (firstRun && passcode !== confirmation) {
      // Checked here rather than server-side: the server never sees the
      // confirmation, and a typo in a passcode you are setting for the first
      // time locks you out of your own data.
      setMismatch(true);
      return;
    }
    const result = await run(() =>
      firstRun ? api.auth.setPasscode(passcode) : api.auth.login(passcode),
    );
    if (result) onSignedIn();
  };

  return (
    <div
      style={{
        minHeight: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 22,
        padding: "0 6px",
      }}
    >
      <div style={{ textAlign: "center" }}>
        <div style={{ font: "500 24px/1.15 var(--font-heading)", letterSpacing: "-.015em" }}>
          Husholdning
        </div>
        <div
          style={{
            font: "400 13px/1.5 var(--font-body)",
            color: "var(--color-text-muted)",
            marginTop: 8,
            maxWidth: 300,
            marginInline: "auto",
          }}
        >
          {firstRun
            ? "Velg en kode. Den settes én gang og kreves for å åpne appen på denne enheten."
            : "Skriv inn koden for å fortsette."}
        </div>
      </div>

      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 11 }}>
        <label className="field">
          <span className="field-label">Kode</span>
          <input
            className="field-input"
            type="password"
            autoComplete={firstRun ? "new-password" : "current-password"}
            value={passcode}
            onChange={(e) => setPasscode(e.target.value)}
            autoFocus
          />
        </label>

        {firstRun && (
          <label className="field">
            <span className="field-label">Gjenta koden</span>
            <input
              className="field-input"
              type="password"
              autoComplete="new-password"
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
            />
          </label>
        )}

        {mismatch && <InlineError error={{ detail: "Kodene er ikke like." }} />}
        <InlineError error={error} />

        <button type="submit" className="btn-primary" disabled={!canSubmit}>
          {pending ? "Vent…" : firstRun ? "Sett kode" : "Logg inn"}
        </button>
      </form>
    </div>
  );
}
