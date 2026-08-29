import { describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../lib/api.js";

function mockFetch(response) {
  const spy = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

const json = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  text: async () => JSON.stringify(body),
});

describe("request", () => {
  it("sends cookies, or every request after login is a 401", async () => {
    const fetch = mockFetch(json(200, { day: "2026-08-29" }));
    await api.budget.get();
    expect(fetch.mock.calls[0][1].credentials).toBe("same-origin");
  });

  it("prefixes /api so callers pass resource paths", async () => {
    const fetch = mockFetch(json(200, []));
    await api.transactions.list();
    expect(fetch.mock.calls[0][0]).toBe("/api/transactions");
  });

  it("drops undefined query parameters rather than sending 'undefined'", async () => {
    const fetch = mockFetch(json(200, []));
    await api.transactions.list({ from: "2026-08-01", to: undefined, limit: 50 });
    expect(fetch.mock.calls[0][0]).toBe("/api/transactions?from=2026-08-01&limit=50");
  });

  it("encodes a category name containing a slash or ampersand", async () => {
    const fetch = mockFetch(json(200, {}));
    await api.categories.setTreatment("Home & furniture", "exceptional");
    expect(fetch.mock.calls[0][0]).toBe("/api/categories/Home%20%26%20furniture");
  });

  it("raises ApiError with the server's detail string", async () => {
    mockFetch(json(422, { detail: "unknown category: Nope" }));
    await expect(api.transactions.create({})).rejects.toMatchObject({
      status: 422,
      detail: "unknown category: Nope",
    });
  });

  it("flattens a pydantic validation list into one readable line", async () => {
    // Otherwise a 422 renders as "[object Object]" and says nothing.
    mockFetch(
      json(422, {
        detail: [
          { loc: ["body", "amount"], msg: "amount must not be zero" },
          { loc: ["body", "date"], msg: "invalid date" },
        ],
      }),
    );
    await expect(api.transactions.create({})).rejects.toMatchObject({
      detail: "amount: amount must not be zero; date: invalid date",
    });
  });

  it("marks a 401 so the app can return to the login screen", async () => {
    mockFetch(json(401, { detail: "not signed in" }));
    const error = await api.budget.get().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.isUnauthorized).toBe(true);
  });

  it("does not mark other statuses as unauthorized", async () => {
    mockFetch(json(403, { detail: "nope" }));
    const error = await api.budget.get().catch((e) => e);
    expect(error.isUnauthorized).toBe(false);
  });

  it("turns a dead server into a readable error, not a raw TypeError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await api.budget.get().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
    expect(error.detail).toMatch(/kontakt/i);
  });

  it("survives an error body that is not JSON", async () => {
    // A proxy returning an HTML 502 page must not crash the parser.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 502, text: async () => "<html>bad gateway" }),
    );
    const error = await api.budget.get().catch((e) => e);
    expect(error.status).toBe(502);
    expect(error.detail).toContain("502");
  });

  it("returns null for an empty 204 rather than failing to parse it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 204, text: async () => "" }));
    await expect(api.auth.logout()).resolves.toBeNull();
  });

  it("sends an upload as multipart without setting Content-Type itself", async () => {
    // The browser has to set it, because it must add the multipart boundary.
    const fetch = mockFetch(json(200, { new: 1 }));
    const file = new File(["x"], "s.xlsx");
    await api.imports.preview(file, "Bankkonto");
    const [, init] = fetch.mock.calls[0];
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.body.get("account")).toBe("Bankkonto");
    expect(init.headers).toBeUndefined();
  });
});
