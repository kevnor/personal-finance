import { describe, expect, it } from "vitest";
import {
  CURRENT_CACHES,
  PRECACHE_URLS,
  staleCaches,
  strategyFor,
} from "../lib/swStrategy.js";

const ORIGIN = "https://finance.tailnet.ts.net";
const decide = (overrides) =>
  strategyFor({ origin: ORIGIN, method: "GET", url: `${ORIGIN}/`, ...overrides });

describe("what the service worker caches", () => {
  it("serves a navigation from the shell so a reload works with no signal", () => {
    expect(decide({ url: `${ORIGIN}/`, mode: "navigate" })).toBe("shell");
    expect(decide({ url: `${ORIGIN}/historikk`, mode: "navigate" })).toBe("shell");
    expect(decide({ url: `${ORIGIN}/x`, destination: "document" })).toBe("shell");
  });

  it("serves build assets from cache, because their URLs are content-hashed", () => {
    expect(decide({ url: `${ORIGIN}/assets/index-BCWZg14-.js` })).toBe("asset");
    expect(decide({ url: `${ORIGIN}/assets/index-zlJgZhyj.css` })).toBe("asset");
  });

  it("caches the icons and the manifest, which have stable names", () => {
    for (const path of PRECACHE_URLS.filter((p) => p !== "/")) {
      expect(decide({ url: ORIGIN + path })).toBe("asset");
    }
  });

  it("falls back to the last API read, which is the whole offline promise", () => {
    // "last-loaded data is cached so Home shows a number with no connection".
    expect(decide({ url: `${ORIGIN}/api/budget` })).toBe("data");
    expect(decide({ url: `${ORIGIN}/api/transactions?from=2026-08-01` })).toBe("data");
    expect(decide({ url: `${ORIGIN}/api/categories` })).toBe("data");
  });
});

describe("what it must never cache", () => {
  it.each(["POST", "PUT", "PATCH", "DELETE"])("passes %s straight through", (method) => {
    // "Writes require a connection." No queue: a queue means a user who
    // believes an expense was recorded when it was not.
    expect(decide({ method, url: `${ORIGIN}/api/transactions` })).toBe("passthrough");
  });

  it("never caches auth state", () => {
    // A cached `authenticated: true` would show the app to someone whose
    // session the server has already stopped accepting.
    expect(decide({ url: `${ORIGIN}/api/auth/status` })).toBe("passthrough");
    expect(decide({ method: "POST", url: `${ORIGIN}/api/auth/login` })).toBe("passthrough");
    expect(decide({ method: "POST", url: `${ORIGIN}/api/auth/logout` })).toBe("passthrough");
  });

  it("leaves other origins alone", () => {
    expect(decide({ url: "https://fonts.googleapis.com/css2?family=Inter" })).toBe("passthrough");
    expect(decide({ url: "https://fonts.gstatic.com/s/inter/x.woff2" })).toBe("passthrough");
  });

  it("does not claim a path it knows nothing about", () => {
    expect(decide({ url: `${ORIGIN}/robots.txt` })).toBe("passthrough");
  });
});

describe("cache cleanup on activate", () => {
  it("deletes this app's older caches and keeps the current ones", () => {
    const names = [
      ...CURRENT_CACHES,
      "husholdning-shell-v0",
      "husholdning-data-v0",
      "some-other-app-cache",
    ];
    expect(staleCaches(names).sort()).toEqual([
      "husholdning-data-v0",
      "husholdning-shell-v0",
    ]);
  });

  it("never deletes a cache belonging to something else on the origin", () => {
    expect(staleCaches(["workbox-precache", "other"])).toEqual([]);
  });
});
