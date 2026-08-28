import { useState } from "react";
import RingProgress from "../components/RingProgress.jsx";
import WeekCard from "../components/WeekCard.jsx";
import AttentionBanner from "../components/AttentionBanner.jsx";
import TransactionRow from "../components/TransactionRow.jsx";
import { nok } from "../lib/format.js";
import {
  WEEK_ENVELOPE,
  DAILY_RATE,
  SPENT_TODAY,
  TODAY_ALLOWANCE,
  SPENT_THIS_WEEK,
  WEEK_DAYS,
  TODAY_ROWS,
} from "../lib/mockData.js";

function greeting() {
  const hour = new Date().getHours();
  if (hour < 10) return "God morgen";
  if (hour < 17) return "God ettermiddag";
  return "God kveld";
}

export default function Home({ extraRows, reviewCount, owed, onReviewClick, onOwedClick }) {
  const [bannerVisible, setBannerVisible] = useState(true);
  const todayLeft = TODAY_ALLOWANCE - SPENT_TODAY;
  const fraction = SPENT_TODAY / TODAY_ALLOWANCE;
  const weekRemaining = WEEK_ENVELOPE - SPENT_THIS_WEEK;
  const rows = [...extraRows, ...TODAY_ROWS];

  const today = new Date().toLocaleDateString("nb-NO", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <div style={{ font: "500 22px/1.15 var(--font-heading)", letterSpacing: "-.015em" }}>{greeting()}</div>
          <div style={{ font: "400 12.5px/1.4 var(--font-body)", color: "var(--color-text-muted)", marginTop: 3 }}>
            {today} · uke 35
          </div>
        </div>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 9999,
            background: "var(--accent-900)",
            border: "1px solid rgba(145,132,217,.45)",
            display: "grid",
            placeItems: "center",
            font: "500 12px var(--font-heading)",
            color: "var(--accent-300)",
          }}
        >
          K
        </div>
      </div>

      {bannerVisible && (
        <AttentionBanner
          reviewCount={reviewCount}
          owed={owed}
          onDismiss={() => setBannerVisible(false)}
          onReviewClick={onReviewClick}
          onOwedClick={onOwedClick}
        />
      )}

      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, padding: "6px 0 2px" }}>
        <RingProgress fraction={fraction} size={252} radius={104} strokeWidth={16}>
          <div className="eyebrow">igjen i dag</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginTop: 6 }}>
            <span className="tabular" style={{ font: "500 52px/1 var(--font-heading)", letterSpacing: "-.03em" }}>
              {nok(todayLeft, 0)}
            </span>
            <span style={{ font: "400 17px/1 var(--font-body)", color: "var(--color-text-muted)" }}>kr</span>
          </div>
          <div style={{ font: "400 12px/1.4 var(--font-body)", color: "var(--color-text-muted)", marginTop: 9 }}>
            av {nok(TODAY_ALLOWANCE, 0)} kr · brukt {nok(SPENT_TODAY, 0)} kr
          </div>
        </RingProgress>
      </div>

      <div style={{ font: "400 13.5px/1.5 var(--font-body)", color: "var(--accent-300)", textAlign: "center", padding: "0 14px" }}>
        Du ligger godt an — {nok(weekRemaining, 0)} kr igjen av uken, og to rolige dager foran deg.
      </div>

      <WeekCard weekLabel="uke 35" remaining={weekRemaining} envelope={WEEK_ENVELOPE} rate={DAILY_RATE} days={WEEK_DAYS} />

      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          i dag
        </div>
        {rows.map((row, i) => (
          <TransactionRow key={`${row.name}-${i}`} row={row} />
        ))}
      </div>
    </div>
  );
}
