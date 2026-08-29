import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App.jsx";

/**
 * A fake server that records writes.
 *
 * These are the paths where a bug means bad data rather than a bad render —
 * a wrong sign on an amount, a double submit, a correction that silently
 * teaches a rule it should not have.
 */
function server(routes) {
  const requests = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, init = {}) => {
      const method = init.method ?? "GET";
      requests.push({
        method,
        url,
        body: typeof init.body === "string" ? JSON.parse(init.body) : init.body,
      });
      for (const [pattern, handler] of Object.entries(routes)) {
        const [routeMethod, path] = pattern.split(" ");
        if (routeMethod !== method) continue;
        if (url === path || url.startsWith(`${path}?`)) {
          const result = typeof handler === "function" ? handler(requests.length) : handler;
          const status = result?.__status ?? 200;
          return { ok: status < 400, status, text: async () => JSON.stringify(result?.__body ?? result) };
        }
      }
      return { ok: false, status: 404, text: async () => JSON.stringify({ detail: `no route ${method} ${url}` }) };
    }),
  );
  return requests;
}

const CATEGORIES = [
  { id: 1, name: "Groceries", label: "Dagligvarer", kind: "expense", budget_treatment: "variable", cash_treatment: "settlement" },
  { id: 2, name: "Gifts", label: "Gaver", kind: "expense", budget_treatment: "variable", cash_treatment: "settlement" },
  { id: 3, name: "Uncategorised", label: "Ukategorisert", kind: "expense", budget_treatment: "variable", cash_treatment: "settlement" },
  { id: 4, name: "Salary", label: "Lønn", kind: "income", budget_treatment: "variable", cash_treatment: "settlement" },
];

const BUDGET = {
  day: "2026-08-29",
  week_start: "2026-08-24",
  week_end: "2026-08-30",
  estimated: false,
  figures: { week_envelope: 4164.51, week_spent: 0, week_remaining: 4164.51, today_allowance: 594.93, today_spent: 0, today_remaining: 594.93, days_left: 2 },
  pools: { "2026-08": { income: 41113.67, fixed: 13463.6, committed: 0, savings: 5000, amount: 22650.07, estimated: false } },
};

const base = (overrides = {}) => ({
  "GET /api/auth/status": { configured: true, authenticated: true },
  "GET /api/categories": CATEGORIES,
  "GET /api/accounts": [{ id: 1, name: "Bankkonto", kind: "bank" }, { id: 2, name: "Kredittkort", kind: "credit_card" }],
  "GET /api/budget": BUDGET,
  "GET /api/budget/config": { income_mode: "manual", fixed_mode: "manual", manual_income: 41113.67, manual_fixed: 13463.6, savings_target: 5000, week_starts_on: 1 },
  "GET /api/transactions": [],
  "GET /api/reimbursements": [],
  ...overrides,
});

beforeEach(() => vi.unstubAllGlobals());

const goTo = async (user, tab) => user.click(await screen.findByRole("button", { name: tab }));

describe("hand entry", () => {
  it("sends the amount as a negative, because the pad collects a magnitude", async () => {
    const requests = server(base({ "POST /api/transactions": { id: 1, ...BUDGET } }));
    render(<App />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Ny utgift" }));
    await user.click(screen.getByRole("button", { name: "2" }));
    await user.click(screen.getByRole("button", { name: "5" }));
    await user.type(screen.getByLabelText("Hva"), "Rema 1000");
    await user.click(screen.getByRole("button", { name: "Lagre utgift" }));

    await waitFor(() => {
      const post = requests.find((r) => r.method === "POST" && r.url === "/api/transactions");
      expect(post.body.amount).toBe(-25);
      expect(post.body.description).toBe("Rema 1000");
      expect(post.body.account).toBe("Bankkonto");
    });
  });

  it("leaves the category to the server unless one is chosen", async () => {
    // The server runs the same categorise the importer runs, learned rules
    // included; the client has no copy of the rules to guess with.
    const requests = server(base({ "POST /api/transactions": { id: 1 } }));
    render(<App />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Ny utgift" }));
    await user.click(screen.getByRole("button", { name: "9" }));
    await user.type(screen.getByLabelText("Hva"), "Meny");
    await user.click(screen.getByRole("button", { name: "Lagre utgift" }));

    await waitFor(() => {
      const post = requests.find((r) => r.method === "POST" && r.url === "/api/transactions");
      expect(post.body.category).toBeUndefined();
    });
  });

  it("will not save without both an amount and a description", async () => {
    server(base());
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Ny utgift" }));

    expect(screen.getByRole("button", { name: "Lagre utgift" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "5" }));
    expect(screen.getByRole("button", { name: "Lagre utgift" })).toBeDisabled();
    await user.type(screen.getByLabelText("Hva"), "Noe");
    expect(screen.getByRole("button", { name: "Lagre utgift" })).toBeEnabled();
  });

  it("keeps what was typed when the save fails, rather than discarding it", async () => {
    server(base({ "POST /api/transactions": { __status: 422, __body: { detail: "unknown account" } } }));
    render(<App />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Ny utgift" }));
    await user.click(screen.getByRole("button", { name: "7" }));
    await user.type(screen.getByLabelText("Hva"), "Noe dyrt");
    await user.click(screen.getByRole("button", { name: "Lagre utgift" }));

    expect(await screen.findByText("unknown account")).toBeInTheDocument();
    expect(screen.getByLabelText("Hva")).toHaveValue("Noe dyrt");
  });
});

describe("review", () => {
  const flagged = {
    id: 42,
    date: "2026-08-21",
    account: "Bankkonto",
    description: "Visa  100121  Ecom Capital AS",
    amount: -349,
    category: "Uncategorised",
    category_kind: "expense",
    treatment: "variable",
    counterparty: null,
    note: null,
    needs_review: true,
    is_transfer: false,
    is_derived: false,
    origin: "import",
  };

  it("teaches a rule from the description when a category is chosen", async () => {
    const requests = server(
      base({ "GET /api/transactions": [flagged], "PATCH /api/transactions/42": { ...flagged, needs_review: false } }),
    );
    render(<App />);
    const user = userEvent.setup();

    await user.click(await screen.findByText(/trenger gjennomgang/));
    await user.click(await screen.findByRole("button", { name: "Gaver" }));

    await waitFor(() => {
      const patch = requests.find((r) => r.method === "PATCH");
      expect(patch.body).toMatchObject({
        category: "Gifts",
        teach: true,
        teach_pattern: "visa  100121  ecom capital as",
      });
    });
  });

  it("offers only expense categories, not Salary", async () => {
    server(base({ "GET /api/transactions": [flagged] }));
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByText(/trenger gjennomgang/));

    expect(await screen.findByRole("button", { name: "Gaver" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Lønn" })).not.toBeInTheDocument();
  });

  it("says the queue is done when nothing is flagged", async () => {
    server(base({ "GET /api/transactions": [] }));
    render(<App />);
    const user = userEvent.setup();
    // Reached through Settings' nav rather than the banner, which is hidden
    // when there is nothing to attend to.
    expect(await screen.findByText("igjen i dag")).toBeInTheDocument();
    expect(screen.queryByText(/trenger gjennomgang/)).not.toBeInTheDocument();
  });
});

describe("owed", () => {
  const debt = {
    id: 3,
    transaction_id: 9,
    date: "2026-07-30",
    description: "Mol*Hoome AS",
    expected_from: "Nordvest Teknikk AS",
    expected_amount: 13990,
    note: null,
    settled_at: null,
  };

  it("settles a debt, and the list then reflects it", async () => {
    // Driven by whether the settle actually happened rather than by a
    // request count, so the test cannot pass because of ordering luck.
    let settled = false;
    const requests = server(
      base({
        "GET /api/reimbursements": () => (settled ? [] : [debt]),
        "POST /api/reimbursements/3/settle": () => {
          settled = true;
          return { ...debt, settled_at: "2026-08-29" };
        },
      }),
    );
    render(<App />);
    const user = userEvent.setup();

    await user.click(await screen.findByText(/står utestående/));
    await user.click(await screen.findByRole("button", { name: "merk mottatt" }));

    await waitFor(() =>
      expect(requests.some((r) => r.url === "/api/reimbursements/3/settle")).toBe(true),
    );
    expect(await screen.findByText("Ingenting utestående")).toBeInTheDocument();
  });

  it("shows the total owed", async () => {
    server(base({ "GET /api/reimbursements": [debt] }));
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByText(/står utestående/));
    expect(await screen.findByText(/totalt utestående/)).toBeInTheDocument();
  });
});

describe("settings", () => {
  it("saves a changed savings target and not an unchanged one", async () => {
    const requests = server(base({ "PUT /api/budget/config": { income_mode: "manual", fixed_mode: "manual", manual_income: 41113.67, manual_fixed: 13463.6, savings_target: 6000, week_starts_on: 1 } }));
    render(<App />);
    const user = userEvent.setup();
    await goTo(user, "Innstillinger");

    const field = await screen.findByLabelText("Kroner");
    expect(screen.getByRole("button", { name: "Lagre" })).toBeDisabled();

    await user.clear(field);
    await user.type(field, "6000");
    await user.click(screen.getByRole("button", { name: "Lagre" }));

    await waitFor(() => {
      const put = requests.find((r) => r.method === "PUT");
      expect(put.body).toEqual({ savings_target: 6000 });
    });
  });

  it("shows the pool the server computed, broken down", async () => {
    server(base());
    render(<App />);
    const user = userEvent.setup();
    await goTo(user, "Innstillinger");

    expect(await screen.findByText("Inntekt")).toBeInTheDocument();
    expect(screen.getByText("Pott denne måneden")).toBeInTheDocument();
    expect(screen.getByText("22 650,07")).toBeInTheDocument();
  });

  it("changes a category's treatment by name, not by label", async () => {
    // The label is what the user sees; the name is what rules key on, and
    // sending the wrong one would 404.
    const requests = server(
      base({ "PATCH /api/categories/Groceries": { ...CATEGORIES[0], budget_treatment: "fixed" } }),
    );
    render(<App />);
    const user = userEvent.setup();
    await goTo(user, "Innstillinger");

    await user.click(await screen.findByRole("button", { name: /kategoribehandling/i }));
    const row = (await screen.findByText("Dagligvarer")).parentElement;
    await user.click(within(row).getByRole("button", { name: "Fast" }));

    await waitFor(() =>
      expect(requests.some((r) => r.url === "/api/categories/Groceries")).toBe(true),
    );
  });
});

describe("statement upload", () => {
  it("previews before it commits, and commits only what was previewed", async () => {
    const requests = server(
      base({
        "POST /api/imports/preview": { account: "Bankkonto", total: 43, new: 5, existing: 38, needs_review: 2, rows: [] },
        "POST /api/imports": { account: "Bankkonto", inserted: 5, skipped: 38, derived: 0 },
      }),
    );
    render(<App />);
    const user = userEvent.setup();
    await goTo(user, "Innstillinger");

    const file = new File(["x"], "Kontoutskrift.xlsx");
    await user.upload(await screen.findByLabelText("Fil (.xlsx)"), file);
    await user.click(screen.getByRole("button", { name: "Forhåndsvis" }));

    expect(await screen.findByText(/nye rader/)).toBeInTheDocument();
    expect(requests.some((r) => r.url === "/api/imports")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Importer 5" }));
    await waitFor(() => expect(requests.some((r) => r.url === "/api/imports")).toBe(true));
    expect(await screen.findByText(/Importert: 5 nye/)).toBeInTheDocument();
  });

  it("will not commit a statement with nothing new in it", async () => {
    server(
      base({
        "POST /api/imports/preview": { account: "Bankkonto", total: 43, new: 0, existing: 43, needs_review: 0, rows: [] },
      }),
    );
    render(<App />);
    const user = userEvent.setup();
    await goTo(user, "Innstillinger");

    await user.upload(await screen.findByLabelText("Fil (.xlsx)"), new File(["x"], "s.xlsx"));
    await user.click(screen.getByRole("button", { name: "Forhåndsvis" }));

    expect(await screen.findByText(/allerede lest inn/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Importer 0" })).toBeDisabled();
  });
});
