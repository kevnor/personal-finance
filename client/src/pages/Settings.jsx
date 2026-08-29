import { useState } from "react";
import { ErrorState, InlineError, Loading } from "../components/States.jsx";
import StatementUpload from "../components/StatementUpload.jsx";
import { useAppData } from "../context/AppData.jsx";
import { useAction, useResource } from "../hooks/useResource.js";
import { api } from "../lib/api.js";
import { nok } from "../lib/format.js";

const TREATMENTS = [
  { id: "variable", label: "I rammen" },
  { id: "fixed", label: "Fast" },
  { id: "exceptional", label: "Unntak" },
];

export default function Settings({ revision, onChanged, onSignedOut, onUnauthorized }) {
  const { categories, labelFor } = useAppData();

  const budget = useResource(() => api.budget.get(), [revision], { onUnauthorized });
  const config = useResource(() => api.budget.config(), [revision], { onUnauthorized });

  if (budget.error) return <ErrorState error={budget.error} onRetry={budget.reload} />;
  if (config.error) return <ErrorState error={config.error} onRetry={config.reload} />;
  if (!budget.data || !config.data) return <Loading />;

  // The pool for the month the current day falls in. A week straddling a
  // boundary carries two, but this panel explains "this month's pot", and
  // the day the app is showing decides which month that is.
  const month = budget.data.day.slice(0, 7);
  const pool = budget.data.pools[month] ?? Object.values(budget.data.pools)[0];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ font: "500 22px/1.15 var(--font-heading)", letterSpacing: "-.015em" }}>
        Innstillinger
      </div>

      <PoolPanel pool={pool} figures={budget.data.figures} estimated={budget.data.estimated} />

      <SavingsTarget
        current={config.data.savings_target}
        onSaved={() => {
          config.reload();
          budget.reload();
          onChanged();
        }}
        onUnauthorized={onUnauthorized}
      />

      <CategoryTreatments
        categories={categories}
        labelFor={labelFor}
        onSaved={onChanged}
        onUnauthorized={onUnauthorized}
      />

      <StatementUpload onImported={onChanged} onUnauthorized={onUnauthorized} />

      <SignOut onSignedOut={onSignedOut} onUnauthorized={onUnauthorized} />
    </div>
  );
}

function PoolPanel({ pool, figures, estimated }) {
  const rows = [
    { label: "Inntekt", value: pool.income },
    { label: "Faste utgifter", value: -pool.fixed },
    { label: "Bundne overføringer", value: -pool.committed },
    { label: "Sparemål", value: -pool.savings },
    { label: "Pott denne måneden", value: pool.amount, highlight: true },
  ];

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 11 }}>
      <div className="eyebrow">månedens pott</div>
      {rows.map((row) => (
        <div
          key={row.label}
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            font: "400 13px/1.3 var(--font-body)",
            color: row.highlight ? "var(--accent-300)" : "rgba(233,233,237,.75)",
          }}
        >
          <span>{row.label}</span>
          <span className="tabular">
            {row.value < 0 ? "−" : ""}
            {nok(Math.abs(row.value))}
          </span>
        </div>
      ))}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          font: "400 13px/1.3 var(--font-body)",
          color: "var(--accent-300)",
        }}
      >
        <span>Per dag / per uke</span>
        <span className="tabular">
          {nok(figures.week_envelope / 7)} / {nok(figures.week_envelope)}
        </span>
      </div>
      {estimated && (
        <div style={{ font: "400 11.5px/1.5 var(--font-body)", color: "var(--color-text-faint)" }}>
          Inntekt og faste utgifter er satt manuelt til det finnes en hel kalendermåned med data.
        </div>
      )}
    </div>
  );
}

function SavingsTarget({ current, onSaved, onUnauthorized }) {
  const [value, setValue] = useState(String(current));
  const [saved, setSaved] = useState(false);
  const { run, pending, error } = useAction({ onUnauthorized });

  const parsed = Number(value.replace(",", "."));
  const valid = value !== "" && Number.isFinite(parsed) && parsed >= 0;
  const changed = valid && parsed !== current;

  const submit = async (event) => {
    event.preventDefault();
    setSaved(false);
    const result = await run(() => api.budget.saveConfig({ savings_target: parsed }));
    if (result) {
      setSaved(true);
      onSaved();
    }
  };

  return (
    <form onSubmit={submit} className="card" style={{ display: "flex", flexDirection: "column", gap: 11 }}>
      <div className="eyebrow">sparemål per måned</div>
      <label className="field">
        <span className="field-label">Kroner</span>
        <input
          className="field-input tabular"
          inputMode="decimal"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setSaved(false);
          }}
        />
      </label>
      <InlineError error={error} />
      <button type="submit" className="btn-outline" disabled={!changed || pending}>
        {pending ? "Lagrer…" : saved ? "Lagret" : "Lagre"}
      </button>
      <div style={{ font: "400 11.5px/1.5 var(--font-body)", color: "var(--color-text-faint)" }}>
        Endringen gjelder fra i dag. Tidligere uker beregnes ikke på nytt.
      </div>
    </form>
  );
}

function CategoryTreatments({ categories, labelFor, onSaved, onUnauthorized }) {
  const [open, setOpen] = useState(false);
  const { run, pending, error } = useAction({ onUnauthorized });
  const [pendingName, setPendingName] = useState(null);

  // Only expense categories have a meaningful budget treatment: for income
  // and transfers the column is ignored, and offering it would suggest
  // otherwise.
  const editable = categories.filter((c) => c.kind === "expense");

  const change = async (name, treatment) => {
    setPendingName(name);
    const result = await run(() => api.categories.setTreatment(name, treatment));
    setPendingName(null);
    if (result) onSaved();
  };

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 11 }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          appearance: "none",
          background: "none",
          border: "none",
          padding: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
          color: "inherit",
        }}
      >
        <span className="eyebrow">kategoribehandling</span>
        <span style={{ font: "400 16px/1 var(--font-body)", color: "var(--color-text-faint)" }}>
          {open ? "−" : "+"}
        </span>
      </button>

      {open && (
        <>
          <div style={{ font: "400 11.5px/1.5 var(--font-body)", color: "var(--color-text-faint)" }}>
            «I rammen» teller mot ukesrammen. «Fast» er faste regninger, «Unntak» er store
            enkeltkjøp — begge holdes utenfor.
          </div>
          <InlineError error={error} />
          {editable.map((category) => (
            <div
              key={category.name}
              style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 4 }}
            >
              <span style={{ font: "400 12.5px/1.3 var(--font-body)" }}>{labelFor(category.name)}</span>
              <div style={{ display: "flex", gap: 6 }}>
                {TREATMENTS.map((treatment) => {
                  const active = category.budget_treatment === treatment.id;
                  const busy = pending && pendingName === category.name;
                  return (
                    <button
                      key={treatment.id}
                      type="button"
                      onClick={() => change(category.name, treatment.id)}
                      disabled={busy || active}
                      style={{
                        appearance: "none",
                        flex: 1,
                        padding: "7px 6px",
                        borderRadius: 8,
                        font: "400 11.5px/1.2 var(--font-body)",
                        cursor: active || busy ? "default" : "pointer",
                        opacity: busy ? 0.5 : 1,
                        background: active ? "rgba(145,132,217,.18)" : "transparent",
                        color: active ? "var(--accent-200)" : "var(--color-text-muted)",
                        border: `1px solid ${active ? "rgba(145,132,217,.5)" : "var(--color-divider-strong)"}`,
                      }}
                    >
                      {treatment.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function SignOut({ onSignedOut, onUnauthorized }) {
  const { run, pending } = useAction({ onUnauthorized });
  return (
    <button
      type="button"
      className="btn-outline"
      disabled={pending}
      onClick={async () => {
        await run(() => api.auth.logout());
        onSignedOut();
      }}
    >
      Logg ut
    </button>
  );
}
