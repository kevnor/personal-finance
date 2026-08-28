// Placeholder data mirroring the design's own numbers (docs/superpowers/specs/2026-08-22-personal-finance-app-design.md
// worked example) until server/lib exists for this to read from the real API.

export const WEEK_ENVELOPE = 4164.51;
export const DAILY_RATE = 594.93;
export const SPENT_BEFORE_TODAY = 1986.0;
export const SPENT_TODAY = 268.9;
export const TODAY_ALLOWANCE = (WEEK_ENVELOPE - SPENT_BEFORE_TODAY) / 4;
export const SPENT_THIS_WEEK = 2254.9;

export const WEEK_DAYS = [
  { label: "man", amount: 452.8 },
  { label: "tir", amount: 1108.2 },
  { label: "ons", amount: 425.0 },
  { label: "tor", amount: 268.9, isToday: true },
  { label: "fre", amount: 0 },
  { label: "lør", amount: 0 },
  { label: "søn", amount: 0 },
];

export const TODAY_ROWS = [
  { name: "REMA 1000 HASLE", category: "Dagligvarer", amount: 189.9, dot: "var(--accent-400)" },
  { name: "PROUD MARY", category: "Kafé & bakeri", amount: 79.0, dot: "var(--accent-300)" },
];

export const HISTORY_GROUPS = [
  {
    day: "torsdag 27. august",
    total: 268.9,
    rows: [
      { name: "REMA 1000 HASLE", category: "Dagligvarer", amount: 189.9, dot: "var(--accent-400)" },
      { name: "PROUD MARY", category: "Kafé & bakeri", amount: 79.0, dot: "var(--accent-300)" },
    ],
  },
  {
    day: "onsdag 26. august",
    total: 1665.5,
    rows: [
      { name: "VY APP", category: "Kollektivtransport", amount: 425.0, dot: "var(--accent-600)" },
      {
        name: "FJORDKRAFT AS",
        category: "Strøm",
        amount: 1240.5,
        dot: "var(--accent-700)",
        outside: true,
      },
    ],
  },
  {
    day: "tirsdag 25. august",
    total: 1108.2,
    rows: [
      { name: "MENY STORO", category: "Dagligvarer", amount: 689.2, dot: "var(--accent-400)" },
      { name: "DOMINOS PIZZA", category: "Restaurant & takeaway", amount: 225.0, dot: "var(--accent-400)" },
      { name: "BOLT.EU", category: "Taxi & ride-hailing", amount: 149.0, dot: "var(--accent-600)" },
      { name: "NARVESEN", category: "Kiosk", amount: 45.0, dot: "var(--accent-300)" },
    ],
  },
  {
    day: "mandag 24. august",
    total: 452.8,
    rows: [
      { name: "CIRCLE K LADESTASJON", category: "Drivstoff & lading", amount: 352.8, dot: "var(--accent-600)" },
      { name: "KIWI HASLE TORG", category: "Dagligvarer", amount: 100.0, dot: "var(--accent-400)" },
      {
        name: "VIPPS*SINDRE",
        category: "Vipps P2P — uten memo",
        amount: 240.0,
        dot: "var(--accent-700)",
        flagged: true,
      },
      {
        name: "GIRO NORDVEST AS",
        category: "Utleggsrefusjon",
        amount: 835.8,
        dot: "var(--accent-800)",
        sign: "+",
        amountColor: "var(--accent-300)",
      },
    ],
  },
];

export const WEEK_TOTALS = [
  { label: "u31", amount: 3120.4 },
  { label: "u32", amount: 4401.58 },
  { label: "u33", amount: 2874.1 },
  { label: "u34", amount: 4358.67 },
  { label: "u35", amount: 2254.9, isCurrent: true },
];

export const TOP_CATEGORIES = [
  { name: "Dagligvarer", value: 4238.6, pct: 100 },
  { name: "Restaurant & takeaway", value: 1892.0, pct: 45 },
  { name: "Drivstoff & lading", value: 1408.3, pct: 33 },
  { name: "Kafé & bakeri", value: 986.5, pct: 23 },
  { name: "Kollektivtransport", value: 842.0, pct: 20 },
  { name: "Klær & sko", value: 613.0, pct: 14 },
];

export const POOL_ROWS = [
  { label: "Inntekt (lønn)", value: 41113.67, sign: "" },
  { label: "Faste utgifter", value: -13463.6, sign: "" },
  { label: "Bundne overføringer", value: -4207.26, sign: "" },
  { label: "Sparemål", value: -5000, sign: "" },
  { label: "Pott · 31 dager", value: 18442.81, highlight: true },
];

export const MERCHANTS = {
  "REMA 1000": { category: "Dagligvarer", rule: "rema" },
  "Proud Mary": { category: "Kafé & bakeri", rule: "proud mary" },
  "VY App": { category: "Kollektivtransport", rule: "vy app" },
  "Bolt.eu": { category: "Taxi", rule: "bolt.eu" },
};

export const CATEGORY_OPTIONS = [
  "Dagligvarer",
  "Restaurant & takeaway",
  "Kafé & bakeri",
  "Kollektivtransport",
  "Drivstoff & lading",
  "Klær & sko",
  "Gaver",
  "Underholdning",
  "Personlig pleie",
  "Helse",
  "Bolig",
  "Vipps P2P - unspecified",
  "Uncategorised",
];

// The two unidentified merchants and the confirmed-guess giro from the spec's
// open questions (2026-08-22-personal-finance-app-design.md), plus a couple
// of unmatched Vipps transfers — a representative slice of the real 29-row
// flagged queue, not the whole thing.
export const REVIEW_QUEUE = [
  {
    id: "r1",
    name: "Ecom Capital AS",
    memo: "Visa  100121  Ecom Capital AS",
    date: "2026-08-21",
    amount: 349.0,
    suggested: "Uncategorised",
  },
  {
    id: "r2",
    name: "MAULUND A/S",
    memo: "Varekjøp Maulund A/S",
    date: "2026-08-19",
    amount: 612.0,
    suggested: "Uncategorised",
  },
  {
    id: "r3",
    name: "Ingvild Kvamme Berg",
    memo: "Overføring  90200000000 Ingvild Kvamme Berg Tpp: Vipps",
    date: "2026-08-18",
    amount: 150.0,
    suggested: "Vipps P2P - unspecified",
  },
  {
    id: "r4",
    name: "Vetle Nyhus Dahl",
    memo: "Overføring  9230000000 Vetle Nyhus Dahl Tpp: Vipps",
    date: "2026-08-15",
    amount: 300.0,
    suggested: "Vipps P2P - unspecified",
  },
  {
    id: "r5",
    name: "VIPPS*SINDRE",
    memo: "Vipps P2P — uten memo",
    date: "2026-08-24",
    amount: 240.0,
    suggested: "Vipps P2P - unspecified",
  },
  {
    id: "r6",
    name: "Giro Nordvest Teknikk AS",
    memo: "+835,80 Giro fra Nordvest Teknikk AS — kan være samme ordning som lånet",
    date: "2026-07-24",
    amount: 835.8,
    suggested: "Utleggsrefusjon",
  },
];

export const REIMBURSEMENTS = [
  {
    id: "o1",
    name: "Hjemmekontor — iPhone",
    expectedFrom: "Arbeidsgiver",
    amount: 13990,
    date: "2026-08-12",
  },
];
