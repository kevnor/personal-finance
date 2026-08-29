// Turning an API transaction into what the row components already expect.
//
// One place, because every screen renders the same row and each would
// otherwise decide for itself what "outside the envelope" means. The server
// already answers that: `treatment` is COALESCE(budget_override,
// category.budget_treatment), so anything but `variable` is outside.

const DOT_COLOURS = [
  "var(--accent-400)",
  "var(--accent-500)",
  "var(--accent-600)",
  "var(--accent-700)",
  "var(--accent-800)",
];

// Deterministic, so a category keeps its colour between screens and across
// reloads. Random or index-based colours make two lists of the same data
// look like different data.
export function dotFor(category) {
  const key = category ?? "";
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  return DOT_COLOURS[hash % DOT_COLOURS.length];
}

/** True when a row does not count against the weekly envelope. */
export const isOutsideEnvelope = (tx) => tx.treatment !== "variable" || tx.is_transfer;

/** The name to show: the counterparty when there is one, else the description. */
export function displayName(tx) {
  const name = tx.counterparty?.trim() || tx.description.trim();
  return name.length > 42 ? `${name.slice(0, 41)}…` : name;
}

export function toRow(tx, labelFor = (n) => n) {
  const incoming = tx.amount >= 0;
  return {
    id: tx.id,
    name: displayName(tx),
    category: labelFor(tx.category),
    amount: Math.abs(tx.amount),
    sign: incoming ? "+" : "−",
    amountColor: incoming ? "var(--accent-300)" : "var(--color-text)",
    dot: dotFor(tx.category),
    outside: isOutsideEnvelope(tx),
    flagged: tx.needs_review,
  };
}

/**
 * Spending counted against the envelope, as a positive number.
 *
 * Mirrors the server's `_variable_spent`: expense categories on `variable`
 * treatment, netted, transfers excluded. The client recomputes it only to
 * break totals down per day and per category — the authoritative figures
 * come from /api/budget, and these must agree with them.
 */
export const variableSpend = (rows) =>
  rows
    .filter((tx) => !isOutsideEnvelope(tx) && tx.category_kind === "expense")
    .reduce((total, tx) => total - tx.amount, 0);

/** Group rows by date, newest day first, each day's rows in server order. */
export function groupByDay(rows) {
  const days = new Map();
  for (const tx of rows) {
    if (!days.has(tx.date)) days.set(tx.date, []);
    days.get(tx.date).push(tx);
  }
  return [...days.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([date, items]) => ({ date, rows: items, total: variableSpend(items) }));
}
