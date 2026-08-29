import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App.jsx";

// A fake server: routes are matched in insertion order, and anything not
// listed 404s loudly rather than silently returning undefined.
function server(routes) {
  const calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, init = {}) => {
      const method = init.method ?? "GET";
      calls.push(`${method} ${url}`);
      for (const [pattern, handler] of Object.entries(routes)) {
        const [routeMethod, path] = pattern.split(" ");
        if (routeMethod !== method) continue;
        if (url === path || url.startsWith(`${path}?`)) {
          const result = typeof handler === "function" ? handler(init) : handler;
          const status = result.__status ?? 200;
          return {
            ok: status < 400,
            status,
            text: async () => JSON.stringify(result.__body ?? result),
          };
        }
      }
      return { ok: false, status: 404, text: async () => JSON.stringify({ detail: `no route ${method} ${url}` }) };
    }),
  );
  return calls;
}

const BUDGET = {
  day: "2026-08-29",
  week_start: "2026-08-24",
  week_end: "2026-08-30",
  estimated: false,
  figures: {
    week_envelope: 4164.51,
    week_spent: 1986,
    week_remaining: 2178.51,
    today_allowance: 594.93,
    today_spent: 268.9,
    today_remaining: 326.03,
    days_left: 2,
  },
  pools: {
    "2026-08": { income: 41113.67, fixed: 13463.6, committed: 0, savings: 5000, amount: 22650.07, estimated: false },
  },
};

const CATEGORIES = [
  { id: 1, name: "Groceries", label: "Dagligvarer", kind: "expense", budget_treatment: "variable", cash_treatment: "settlement" },
  { id: 2, name: "Uncategorised", label: "Ukategorisert", kind: "expense", budget_treatment: "variable", cash_treatment: "settlement" },
];
const ACCOUNTS = [{ id: 1, name: "Bankkonto", kind: "bank" }];

const TX = {
  id: 7,
  date: "2026-08-29",
  account: "Bankkonto",
  description: "Rema Lorenveien, Oslo",
  amount: -268.9,
  category: "Groceries",
  category_kind: "expense",
  treatment: "variable",
  counterparty: null,
  note: null,
  needs_review: false,
  is_transfer: false,
  is_derived: false,
  origin: "import",
};

const signedInRoutes = (overrides = {}) => ({
  "GET /api/auth/status": { configured: true, authenticated: true },
  "GET /api/categories": CATEGORIES,
  "GET /api/accounts": ACCOUNTS,
  "GET /api/budget": BUDGET,
  "GET /api/budget/config": { income_mode: "manual", fixed_mode: "manual", manual_income: 41113.67, manual_fixed: 13463.6, savings_target: 5000, week_starts_on: 1 },
  "GET /api/transactions": [TX],
  "GET /api/reimbursements": [],
  ...overrides,
});

beforeEach(() => vi.unstubAllGlobals());

describe("the auth gate", () => {
  it("shows first-run setup when no passcode is configured", async () => {
    server({ "GET /api/auth/status": { configured: false, authenticated: false } });
    render(<App />);
    expect(await screen.findByRole("button", { name: "Sett kode" })).toBeInTheDocument();
    expect(screen.getByLabelText("Gjenta koden")).toBeInTheDocument();
  });

  it("shows login when a passcode exists but there is no session", async () => {
    server({ "GET /api/auth/status": { configured: true, authenticated: false } });
    render(<App />);
    expect(await screen.findByRole("button", { name: "Logg inn" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Gjenta koden")).not.toBeInTheDocument();
  });

  it("refuses a first-run passcode that does not match its confirmation", async () => {
    // The server never sees the confirmation, and a typo in a passcode set
    // for the first time locks the user out of their own data.
    server({ "GET /api/auth/status": { configured: false, authenticated: false } });
    render(<App />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Kode"), "hunter2!");
    await user.type(screen.getByLabelText("Gjenta koden"), "hunter3!");
    await user.click(screen.getByRole("button", { name: "Sett kode" }));
    expect(await screen.findByText("Kodene er ikke like.")).toBeInTheDocument();
  });

  it("surfaces a rejected passcode instead of failing silently", async () => {
    server({
      "GET /api/auth/status": { configured: true, authenticated: false },
      "POST /api/auth/login": { __status: 401, __body: { detail: "incorrect passcode" } },
    });
    render(<App />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Kode"), "wrong");
    await user.click(screen.getByRole("button", { name: "Logg inn" }));
    expect(await screen.findByText("incorrect passcode")).toBeInTheDocument();
  });

  it("goes to the app once signed in", async () => {
    server(signedInRoutes());
    render(<App />);
    expect(await screen.findByText("igjen i dag")).toBeInTheDocument();
  });

  it("returns to the login screen when a session expires mid-use", async () => {
    // Otherwise the user sees an error banner they can do nothing about.
    server(
      signedInRoutes({ "GET /api/budget": { __status: 401, __body: { detail: "not signed in" } } }),
    );
    render(<App />);
    expect(await screen.findByRole("button", { name: "Logg inn" })).toBeInTheDocument();
  });

  it("reports a dead server rather than rendering an empty app", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/kontakt/i);
  });
});

describe("Home", () => {
  it("shows the server's figures rather than computing its own", async () => {
    server(signedInRoutes());
    render(<App />);
    // today_remaining, rendered without decimals.
    expect(await screen.findByText("326")).toBeInTheDocument();
    expect(screen.getByText(/av 595 kr · brukt 269 kr/)).toBeInTheDocument();
  });

  it("says how the week is going, from the numbers", async () => {
    server(signedInRoutes());
    render(<App />);
    expect(await screen.findByText(/2 179 kr igjen av uken/)).toBeInTheDocument();
  });

  it("says so plainly when the week is overspent", async () => {
    // The mock copy said "Du ligger godt an" whatever the numbers were,
    // which is the one thing a budget app must not do.
    server(
      signedInRoutes({
        "GET /api/budget": {
          ...BUDGET,
          figures: { ...BUDGET.figures, week_remaining: -420.5, today_remaining: -100 },
        },
      }),
    );
    render(<App />);
    expect(await screen.findByText(/421 kr over rammen/)).toBeInTheDocument();
  });

  it("renders today's rows with their Norwegian category label", async () => {
    server(signedInRoutes());
    render(<App />);
    expect(await screen.findByText("Rema Lorenveien, Oslo")).toBeInTheDocument();
    expect(screen.getByText("Dagligvarer")).toBeInTheDocument();
  });

  it("says nothing was registered today rather than showing a bare heading", async () => {
    server(signedInRoutes({ "GET /api/transactions": [] }));
    render(<App />);
    expect(await screen.findByText("Ingenting registrert i dag.")).toBeInTheDocument();
  });

  it("shows the attention banner when rows need review", async () => {
    server(
      signedInRoutes({
        "GET /api/transactions": (init) => [{ ...TX, needs_review: true }],
      }),
    );
    render(<App />);
    expect(await screen.findByText(/trenger gjennomgang/)).toBeInTheDocument();
  });

  it("marks the figures as an estimate during cold start", async () => {
    server(signedInRoutes({ "GET /api/budget": { ...BUDGET, estimated: true } }));
    render(<App />);
    expect(await screen.findByText(/Anslag:/)).toBeInTheDocument();
  });
});
