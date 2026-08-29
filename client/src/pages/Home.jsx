import { useState } from "react";
import AttentionBanner from "../components/AttentionBanner.jsx";
import RingProgress from "../components/RingProgress.jsx";
import { ErrorState, Loading } from "../components/States.jsx";
import TransactionRow from "../components/TransactionRow.jsx";
import WeekCard from "../components/WeekCard.jsx";
import { useAppData } from "../context/AppData.jsx";
import { useResource } from "../hooks/useResource.js";
import { api } from "../lib/api.js";
import { daysBetween, isoWeek, longDate, weekdayLabel } from "../lib/dates.js";
import { nok } from "../lib/format.js";
import { toRow, variableSpend } from "../lib/rows.js";

function greeting() {
  const hour = new Date().getHours();
  if (hour < 10) return "God morgen";
  if (hour < 17) return "God ettermiddag";
  return "God kveld";
}

/**
 * How the week is going, in one sentence.
 *
 * Derived rather than fixed copy: the mock said "Du ligger godt an" whatever
 * the numbers were, which is the one thing a budget app must not do.
 */
function verdict(figures) {
  if (figures.week_remaining < 0) {
    return `Du er ${nok(Math.abs(figures.week_remaining), 0)} kr over rammen for uken.`;
  }
  if (figures.today_remaining < 0) {
    return `Dagens ramme er brukt opp — ${nok(Math.abs(figures.today_remaining), 0)} kr over, men ${nok(figures.week_remaining, 0)} kr igjen av uken.`;
  }
  return `${nok(figures.week_remaining, 0)} kr igjen av uken, fordelt på ${figures.days_left} ${figures.days_left === 1 ? "dag" : "dager"}.`;
}

export default function Home({ revision, onReviewClick, onOwedClick, onUnauthorized }) {
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const { labelFor } = useAppData();

  // One request for the budget, then the week's rows and the two attention
  // counts. The week's rows are fetched whole and bucketed per day here
  // rather than asked for day by day: seven requests for what is at most a
  // few dozen rows is the wrong trade on a phone with poor signal.
  const budget = useResource(() => api.budget.get(), [revision], { onUnauthorized });
  const week = budget.data?.week_start;

  const details = useResource(
    () =>
      week
        ? Promise.all([
            api.transactions.list({ from: week, to: budget.data.week_end, limit: 500 }),
            api.transactions.list({ needs_review: true, limit: 500 }),
            api.reimbursements.list(),
          ])
        : Promise.resolve(null),
    [revision, week, budget.data?.week_end],
    { onUnauthorized },
  );

  if (budget.loading && !budget.data) return <Loading />;
  if (budget.error) return <ErrorState error={budget.error} onRetry={budget.reload} />;
  if (details.error) return <ErrorState error={details.error} onRetry={details.reload} />;
  if (!details.data) return <Loading />;

  const [weekRows, flagged, owed] = details.data;
  const { day, week_start: weekStart, week_end: weekEnd, figures, estimated } = budget.data;

  const byDay = new Map();
  for (const tx of weekRows) {
    byDay.set(tx.date, [...(byDay.get(tx.date) ?? []), tx]);
  }
  const days = daysBetween(weekStart, weekEnd).map((date) => ({
    label: weekdayLabel(date),
    amount: Math.max(0, variableSpend(byDay.get(date) ?? [])),
    isToday: date === day,
  }));

  const todayRows = (byDay.get(day) ?? []).map((tx) => toRow(tx, labelFor));
  const owedTotal = owed.reduce((sum, item) => sum + item.expected_amount, 0);
  // The allowance is fixed when the day starts, so a zero allowance means
  // the week is spent — dividing by it would give Infinity.
  const fraction = figures.today_allowance > 0 ? figures.today_spent / figures.today_allowance : 1;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <div style={{ font: "500 22px/1.15 var(--font-heading)", letterSpacing: "-.015em" }}>
            {greeting()}
          </div>
          <div
            style={{
              font: "400 12.5px/1.4 var(--font-body)",
              color: "var(--color-text-muted)",
              marginTop: 3,
            }}
          >
            {longDate(day)} · uke {isoWeek(day)}
          </div>
        </div>
      </div>

      {!bannerDismissed && (
        <AttentionBanner
          reviewCount={flagged.length}
          owed={owedTotal}
          onDismiss={() => setBannerDismissed(true)}
          onReviewClick={onReviewClick}
          onOwedClick={onOwedClick}
        />
      )}

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 2,
          padding: "6px 0 2px",
        }}
      >
        <RingProgress fraction={fraction} size={252} radius={104} strokeWidth={16}>
          <div className="eyebrow">igjen i dag</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginTop: 6 }}>
            <span
              className="tabular"
              style={{ font: "500 52px/1 var(--font-heading)", letterSpacing: "-.03em" }}
            >
              {nok(figures.today_remaining, 0)}
            </span>
            <span style={{ font: "400 17px/1 var(--font-body)", color: "var(--color-text-muted)" }}>
              kr
            </span>
          </div>
          <div
            style={{
              font: "400 12px/1.4 var(--font-body)",
              color: "var(--color-text-muted)",
              marginTop: 9,
            }}
          >
            av {nok(figures.today_allowance, 0)} kr · brukt {nok(figures.today_spent, 0)} kr
          </div>
        </RingProgress>
      </div>

      <div
        style={{
          font: "400 13.5px/1.5 var(--font-body)",
          color: "var(--accent-300)",
          textAlign: "center",
          padding: "0 14px",
        }}
      >
        {verdict(figures)}
      </div>

      {estimated && (
        <div
          style={{
            font: "400 11.5px/1.5 var(--font-body)",
            color: "var(--color-text-faint)",
            textAlign: "center",
            padding: "0 14px",
          }}
        >
          Anslag: inntekt og faste utgifter er satt manuelt til det finnes en hel kalendermåned med data.
        </div>
      )}

      <WeekCard
        weekLabel={`uke ${isoWeek(day)}`}
        remaining={figures.week_remaining}
        envelope={figures.week_envelope}
        rate={figures.week_envelope / 7}
        days={days}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          i dag
        </div>
        {todayRows.length === 0 ? (
          <div
            style={{
              font: "400 12.5px/1.5 var(--font-body)",
              color: "var(--color-text-muted)",
              padding: "8px 0",
            }}
          >
            Ingenting registrert i dag.
          </div>
        ) : (
          todayRows.map((row) => <TransactionRow key={row.id} row={row} />)
        )}
      </div>
    </div>
  );
}
