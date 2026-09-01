import { describe, expect, it } from "vitest";
import { addDays, daysBetween, isoWeek, isoWeekday, weekdayLabel } from "../lib/dates.js";

describe("addDays", () => {
  it("crosses a month boundary", () => {
    expect(addDays("2026-06-30", 1)).toBe("2026-07-01");
  });

  it("goes backwards", () => {
    expect(addDays("2026-07-01", -1)).toBe("2026-06-30");
  });

  it("crosses a year boundary", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("handles a leap day", () => {
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29");
  });
});

describe("daysBetween", () => {
  it("is inclusive at both ends, so a week is seven days", () => {
    expect(daysBetween("2026-08-24", "2026-08-30")).toHaveLength(7);
  });

  it("returns the single day when both ends match", () => {
    expect(daysBetween("2026-08-24", "2026-08-24")).toEqual(["2026-08-24"]);
  });
});

describe("isoWeek", () => {
  it("matches the ISO week the Norwegian 'uke N' refers to", () => {
    expect(isoWeek("2026-08-24")).toBe(35);
    expect(isoWeek("2026-08-30")).toBe(35); // Sunday still closes week 35
    expect(isoWeek("2026-08-31")).toBe(36);
  });

  it("puts 1 January in the week that owns it, not always week 1", () => {
    // 2027-01-01 is a Friday, so it belongs to week 53 of 2026.
    expect(isoWeek("2027-01-01")).toBe(53);
  });
});

describe("weekdayLabel", () => {
  it("is a short Norwegian weekday without the abbreviation dot", () => {
    expect(weekdayLabel("2026-08-24")).toBe("man");
    expect(weekdayLabel("2026-08-30")).toBe("søn");
  });
});

describe("isoWeekday", () => {
  it("is 1 on Monday and 7 on Sunday, not 0", () => {
    expect(isoWeekday("2026-08-24")).toBe(1);
    expect(isoWeekday("2026-08-27")).toBe(4);
    expect(isoWeekday("2026-08-30")).toBe(7);
  });
});
