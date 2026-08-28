export default function RingProgress({ fraction, size = 252, radius = 104, strokeWidth = 16, children }) {
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(1, Math.max(0, fraction));
  const dash = `${(circumference * clamped).toFixed(1)} ${circumference.toFixed(1)}`;
  const center = size / 2;

  return (
    <div style={{ display: "grid", placeItems: "center", position: "relative" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block", transform: "rotate(-90deg)" }}>
        <circle cx={center} cy={center} r={radius} fill="none" stroke="var(--color-surface)" strokeWidth={strokeWidth} />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="var(--accent-500)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={dash}
          opacity="0.28"
          style={{ filter: "blur(6px)" }}
        />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="var(--accent-500)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={dash}
        />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        {children}
      </div>
    </div>
  );
}
