/**
 * The nested day/week ring: a thin outer arc for the week's progress and a
 * thick, glowing inner arc for today's, sharing one centre.
 */
export default function DayWeekRing({ dayFraction, weekFraction, children }) {
  const size = 264;
  const center = size / 2;
  const outerRadius = 120;
  const outerWidth = 9;
  const innerRadius = 94;
  const innerWidth = 18;

  const clamp = (f) => Math.min(1, Math.max(0, f));
  const dashFor = (radius, fraction) => {
    const circumference = 2 * Math.PI * radius;
    return `${(circumference * clamp(fraction)).toFixed(1)} ${circumference.toFixed(1)}`;
  };

  return (
    <div style={{ display: "grid", placeItems: "center", position: "relative" }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ display: "block", transform: "rotate(-90deg)" }}
      >
        <circle cx={center} cy={center} r={outerRadius} fill="none" stroke="var(--color-surface)" strokeWidth={outerWidth} />
        <circle
          cx={center}
          cy={center}
          r={outerRadius}
          fill="none"
          stroke="var(--accent-700)"
          strokeWidth={outerWidth}
          strokeLinecap="round"
          strokeDasharray={dashFor(outerRadius, weekFraction)}
        />
        <circle cx={center} cy={center} r={innerRadius} fill="none" stroke="var(--color-surface)" strokeWidth={innerWidth} />
        <circle
          cx={center}
          cy={center}
          r={innerRadius}
          fill="none"
          stroke="var(--accent-500)"
          strokeWidth={innerWidth}
          strokeLinecap="round"
          strokeDasharray={dashFor(innerRadius, dayFraction)}
          opacity="0.3"
          style={{ filter: "blur(7px)" }}
        />
        <circle
          cx={center}
          cy={center}
          r={innerRadius}
          fill="none"
          stroke="var(--accent-500)"
          strokeWidth={innerWidth}
          strokeLinecap="round"
          strokeDasharray={dashFor(innerRadius, dayFraction)}
        />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        {children}
      </div>
    </div>
  );
}
