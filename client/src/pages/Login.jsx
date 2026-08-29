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
// Why the app bounced back from Entra, in the user's language. `required` is
// not a failure: a silent renewal could not be completed without showing them
// something, which is exactly when they should be asked to sign in.
const NOTICES = {
  required: "Økten er utløpt. Logg inn på nytt.",
  denied: "Innloggingen ble avvist.",
  expired: "Innloggingen tok for lang tid. Prøv på nytt.",
};

export default function Login({ configured, entraAvailable, notice, onSignedIn }) {
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
        {NOTICES[notice] && <InlineError error={{ detail: NOTICES[notice] }} />}
        <InlineError error={error} />

        <button type="submit" className="btn-primary" disabled={!canSubmit}>
          {pending ? "Vent…" : firstRun ? "Sett kode" : "Logg inn"}
        </button>
      </form>

      {entraAvailable && !firstRun && (
        <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
          <div
            style={{
              font: "400 12px/1.5 var(--font-body)",
              color: "var(--color-text-muted)",
              textAlign: "center",
            }}
          >
            eller
          </div>
          {/*
            A link rather than a button with a fetch: the sign-in has to
            happen as a top-level navigation. Entra refuses to be framed, and
            an XHR cannot show a login page or an MFA prompt.
          */}
          {/*
            `.btn-outline` is written for a <button>, which is block-level;
            an <a> is inline, so it would ignore the width and min-height.
            Set here rather than in the shared rule so no existing button
            changes shape.
          */}
          <a
            className="btn-outline"
            href={entraHref()}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxSizing: "border-box",
              textDecoration: "none",
            }}
          >
            Logg inn med Microsoft
          </a>
          <div
            style={{
              font: "400 12px/1.5 var(--font-body)",
              color: "var(--color-text-muted)",
              textAlign: "center",
            }}
          >
            Koden over virker fortsatt hvis Microsoft ikke er tilgjengelig.
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Where "sign in with Microsoft" goes.
 *
 * `next` carries the path the user was on, so a session that lapsed on the
 * history screen comes back to the history screen. Any `?signin=` notice is
 * dropped from it: keeping it would re-show "your session expired" on the
 * page they land on after successfully signing in.
 */
function entraHref() {
  const here = new URL(window.location.href);
  here.searchParams.delete("signin");
  const next = here.pathname + here.search;
  return `/api/auth/entra/login?next=${encodeURIComponent(next)}`;
}
