import { describe, expect, it } from "vitest";
import { displayName, dotFor, groupByDay, isOutsideEnvelope, toRow, variableSpend } from "../lib/rows.js";

const tx = (overrides = {}) => ({
  id: 1,
  date: "2026-08-29",
  account: "Bankkonto",
  description: "Rema Lorenveien, Oslo",
  amount: -189.9,
  category: "Groceries",
  category_kind: "expense",
  treatment: "variable",
  counterparty: null,
  note: null,
  needs_review: false,
  is_transfer: false,
  is_derived: false,
  origin: "import",
  ...overrides,
});

describe("isOutsideEnvelope", () => {
  it("counts a variable expense as inside", () => {
    expect(isOutsideEnvelope(tx())).toBe(false);
  });

  it.each(["fixed", "exceptional", "reimbursable", "ignore"])(
    "counts %s treatment as outside",
    (treatment) => {
      expect(isOutsideEnvelope(tx({ treatment }))).toBe(true);
    },
  );

  it("counts a transfer as outside even on variable treatment", () => {
    // Card settlements carry `variable` but must never reduce the envelope:
    // the card's own purchase lines already carry that spending.
    expect(isOutsideEnvelope(tx({ treatment: "variable", is_transfer: true }))).toBe(true);
  });
});

describe("variableSpend", () => {
  it("is positive-going for outgoings", () => {
    expect(variableSpend([tx({ amount: -100 })])).toBe(100);
  });

  it("nets an incoming row against its category", () => {
    // The Jysk chair reimbursed by a friend cancels the purchase.
    expect(variableSpend([tx({ amount: -1800 }), tx({ id: 2, amount: 1800 })])).toBe(0);
  });

  it("ignores income, so payday does not read as negative spending", () => {
    const salary = tx({ amount: 41113.67, category: "Salary", category_kind: "income" });
    expect(variableSpend([tx({ amount: -100 }), salary])).toBe(100);
  });

  it("ignores rows outside the envelope", () => {
    expect(variableSpend([tx({ amount: -5000, treatment: "fixed" })])).toBe(0);
  });
});

describe("toRow", () => {
  it("shows an outgoing as a minus and an incoming as a plus", () => {
    expect(toRow(tx({ amount: -50 }))).toMatchObject({ sign: "−", amount: 50 });
    expect(toRow(tx({ amount: 50 }))).toMatchObject({ sign: "+", amount: 50 });
  });

  it("translates the category through the label lookup", () => {
    const row = toRow(tx(), (name) => (name === "Groceries" ? "Dagligvarer" : name));
    expect(row.category).toBe("Dagligvarer");
  });

  it("flags a row that needs review", () => {
    expect(toRow(tx({ needs_review: true })).flagged).toBe(true);
  });
});

describe("displayName", () => {
  it("prefers the counterparty when there is one", () => {
    expect(displayName(tx({ counterparty: "Aslak Fjellheim" }))).toBe("Aslak Fjellheim");
  });

  it("falls back to the description", () => {
    expect(displayName(tx({ counterparty: "   " }))).toBe("Rema Lorenveien, Oslo");
  });

  it("truncates a long statement description rather than breaking the layout", () => {
    const long = "Overføring 4790000001 Somebody With A Very Long Name Indeed Tpp: Vipps";
    expect(displayName(tx({ description: long })).length).toBeLessThanOrEqual(42);
  });
});

describe("dotFor", () => {
  it("gives a category the same colour every time", () => {
    // Random or index-based colours make two views of the same data look
    // like different data.
    expect(dotFor("Groceries")).toBe(dotFor("Groceries"));
  });
});

describe("groupByDay", () => {
  it("groups by date, newest first", () => {
    const groups = groupByDay([
      tx({ id: 1, date: "2026-08-27" }),
      tx({ id: 2, date: "2026-08-29" }),
      tx({ id: 3, date: "2026-08-29" }),
    ]);
    expect(groups.map((g) => g.date)).toEqual(["2026-08-29", "2026-08-27"]);
    expect(groups[0].rows).toHaveLength(2);
  });

  it("totals only what counts against the envelope", () => {
    const groups = groupByDay([
      tx({ amount: -100 }),
      tx({ id: 2, amount: -900, treatment: "fixed" }),
    ]);
    expect(groups[0].total).toBe(100);
  });
});
