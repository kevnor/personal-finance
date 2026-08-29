import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App.jsx";
import Login from "../pages/Login.jsx";

/**
 * The client half of Entra sign-in.
 *
 * Two things here are worth more than the rest: that a lapsed Entra session
 * renews itself without dropping the user on a login screen, and that it
 * cannot do so in a loop or immediately after somebody deliberately signed
 * out. Both are about a redirect that is hard to notice going wrong -- a loop
 * looks like a blank page, and an undone sign-out looks like nothing at all.
 */

function server(status) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) => {
      if (String(url).startsWith("/api/auth/status")) {
        return { ok: true, status: 200, text: async () => JSON.stringify(status) };
      }
      return { ok: false, status: 401, text: async () => JSON.stringify({ detail: "no" }) };
    }),
  );
}

/** Stands in for the browser's navigation, which jsdom does not perform. */
function trackNavigation() {
  const went = [];
  delete window.location;
  window.location = {
    pathname: "/",
    search: "",
    href: "http://localhost/",
    assign: (url) => went.push(url),
  };
  return went;
}

function at(pathname, search = "") {
  window.location.pathname = pathname;
  window.location.search = search;
  window.location.href = `http://localhost${pathname}${search}`;
}

const SIGNED_OUT_FEDERATED = {
  configured: true,
  authenticated: false,
  entra_available: true,
  source: null,
};

let went;

beforeEach(() => {
  localStorage.clear();
  went = trackNavigation();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// -- the login screen -------------------------------------------------------

describe("the login screen", () => {
  it("offers Microsoft only when a registration is configured", () => {
    const { rerender } = render(
      <Login configured entraAvailable={false} onSignedIn={() => {}} />,
    );
    expect(screen.queryByText(/Logg inn med Microsoft/)).toBeNull();

    rerender(<Login configured entraAvailable onSignedIn={() => {}} />);
    expect(screen.getByText(/Logg inn med Microsoft/)).toBeTruthy();
  });

  it("does not offer it during first-run setup", () => {
    /* There is no session yet and no passcode, and Entra sign-in requires
       one -- the credentials file is where the signing secret lives. */
    render(<Login configured={false} entraAvailable onSignedIn={() => {}} />);
    expect(screen.queryByText(/Logg inn med Microsoft/)).toBeNull();
  });

  it("says the passcode still works, because that is the whole point of it", () => {
    render(<Login configured entraAvailable onSignedIn={() => {}} />);
    expect(screen.getByText(/Koden over virker fortsatt/)).toBeTruthy();
  });

  it("explains why the app bounced back", () => {
    render(<Login configured entraAvailable notice="required" onSignedIn={() => {}} />);
    expect(screen.getByText(/Økten er utløpt/)).toBeTruthy();
  });

  it("ignores a notice it does not recognise rather than rendering it raw", () => {
    /* The value arrives from the query string, so it is attacker-controlled
       in the sense that anyone can put anything there. */
    render(
      <Login configured entraAvailable notice="<script>x</script>" onSignedIn={() => {}} />,
    );
    expect(screen.queryByText(/script/)).toBeNull();
  });

  it("carries where you were into the sign-in, without the notice", () => {
    at("/history", "?signin=required&month=2026-07");
    render(<Login configured entraAvailable notice="required" onSignedIn={() => {}} />);
    const href = screen.getByText(/Logg inn med Microsoft/).getAttribute("href");
    expect(href).toContain(encodeURIComponent("/history"));
    expect(href).toContain(encodeURIComponent("month=2026-07"));
    expect(href).not.toContain("signin");
  });
});

// -- silent renewal ---------------------------------------------------------

describe("a lapsed Entra session", () => {
  it("renews itself rather than showing a login screen", async () => {
    localStorage.setItem("pf.signed-in", "1");
    localStorage.setItem("pf.signed-in-via", "entra");
    at("/history");
    server(SIGNED_OUT_FEDERATED);

    render(<App />);
    await waitFor(() => expect(went).toHaveLength(1));
    expect(went[0]).toContain("silent=true");
    expect(went[0]).toContain(encodeURIComponent("/history"));
  });

  it("does not renew after an explicit sign-out", async () => {
    /* Signing out clears the note. Without that, logging out would redirect
       straight back in and look like the button did nothing. */
    localStorage.clear();
    server(SIGNED_OUT_FEDERATED);

    render(<App />);
    await waitFor(() =>
      // By role, because "Logg inn med Microsoft" also matches the text.
      expect(screen.getByRole("button", { name: "Logg inn" })).toBeTruthy(),
    );
    expect(went).toHaveLength(0);
  });

  it("does not renew twice after a refused renewal", async () => {
    /* The loop guard. Entra answering `login_required` means it cannot be
       done silently, and asking again gets the same answer forever. */
    localStorage.setItem("pf.signed-in", "1");
    localStorage.setItem("pf.signed-in-via", "entra");
    at("/", "?signin=required");
    server(SIGNED_OUT_FEDERATED);

    render(<App />);
    await waitFor(() => expect(screen.getByText(/Økten er utløpt/)).toBeTruthy());
    expect(went).toHaveLength(0);
  });

  it("does not renew a passcode session, which Entra knows nothing about", async () => {
    localStorage.setItem("pf.signed-in", "1");
    localStorage.setItem("pf.signed-in-via", "passcode");
    server(SIGNED_OUT_FEDERATED);

    render(<App />);
    await waitFor(() =>
      // By role, because "Logg inn med Microsoft" also matches the text.
      expect(screen.getByRole("button", { name: "Logg inn" })).toBeTruthy(),
    );
    expect(went).toHaveLength(0);
  });

  it("does not renew on an instance with no registration at all", async () => {
    localStorage.setItem("pf.signed-in", "1");
    localStorage.setItem("pf.signed-in-via", "entra");
    server({ ...SIGNED_OUT_FEDERATED, entra_available: false });

    render(<App />);
    await waitFor(() =>
      // By role, because "Logg inn med Microsoft" also matches the text.
      expect(screen.getByRole("button", { name: "Logg inn" })).toBeTruthy(),
    );
    expect(went).toHaveLength(0);
  });
});
