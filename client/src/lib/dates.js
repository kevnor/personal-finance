// Date helpers. The server decides what "today" is (in its configured
// timezone) and hands it back on /api/budget, so nothing here invents one —
// a browser in another timezone must not disagree with the server about
// which week a purchase falls in.

export const iso = (date) => date.toISOString().slice(0, 10);

export function addDays(isoDate, days) {
  const date = new Date(`${isoDate}T00:00:00`);
  date.setDate(date.getDate() + days);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function daysBetween(fromIso, toIso) {
  const out = [];
  for (let day = fromIso; day <= toIso; day = addDays(day, 1)) out.push(day);
  return out;
}

const NB = "nb-NO";

export const longDate = (isoDate) =>
  new Date(`${isoDate}T00:00:00`).toLocaleDateString(NB, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

export const shortDate = (isoDate) =>
  new Date(`${isoDate}T00:00:00`).toLocaleDateString(NB, { day: "numeric", month: "long" });

export const weekdayLabel = (isoDate) =>
  new Date(`${isoDate}T00:00:00`).toLocaleDateString(NB, { weekday: "short" }).replace(".", "");

/** 1 (Monday) through 7 (Sunday) — the "dag 4 av 7" position within the week. */
export function isoWeekday(isoDate) {
  const day = new Date(`${isoDate}T00:00:00`).getDay();
  return day === 0 ? 7 : day;
}

/** ISO week number, which is what the Norwegian "uke 35" refers to. */
export function isoWeek(isoDate) {
  const date = new Date(`${isoDate}T00:00:00Z`);
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
}
