// What the service worker should do with a given request.
//
// Kept as a pure function in its own module so it can be tested directly.
// The decision here is the whole of the offline behaviour, and a service
// worker is the worst place in a web app to discover a mistake: it persists
// across reloads and keeps serving whatever it decided to keep.

export const CACHE_VERSION = "v1";
export const SHELL_CACHE = `husholdning-shell-${CACHE_VERSION}`;
export const ASSET_CACHE = `husholdning-assets-${CACHE_VERSION}`;
export const DATA_CACHE = `husholdning-data-${CACHE_VERSION}`;

export const CURRENT_CACHES = [SHELL_CACHE, ASSET_CACHE, DATA_CACHE];

/** Stable paths worth having before the first offline load. */
export const PRECACHE_URLS = [
  "/",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
  "/icon-maskable-512.png",
];

/**
 * Decide how to serve a request.
 *
 * Returns one of:
 *  - `passthrough`   — go to the network and do not touch the cache.
 *  - `shell`         — an app-shell navigation: network first, fall back to
 *                      the cached index so a reload works with no signal.
 *  - `asset`         — a build asset: cache first. Vite content-hashes these,
 *                      so a given URL's bytes never change and serving a
 *                      cached copy forever is correct, not a staleness risk.
 *  - `data`          — an API read: network first, fall back to the last
 *                      response. This is what makes Home show a number in a
 *                      shop with no signal, which the spec asks for.
 *
 * `origin` is the app's own origin, passed in rather than read from a global
 * so this stays a pure function.
 */
export function strategyFor({ method, url, mode, destination, origin }) {
  const target = new URL(url, origin);

  // Another origin entirely — the webfont CDN. Not ours to cache, and
  // caching an opaque cross-origin response would bloat storage for nothing.
  if (target.origin !== origin) return "passthrough";

  const { pathname } = target;

  // Writes never touch the cache, and are never queued. The spec is explicit:
  // "Writes require a connection." A queue means conflict resolution and a
  // sync state machine, and — worse — a user who believes an expense was
  // recorded when it was not.
  if (method !== "GET") return "passthrough";

  if (pathname.startsWith("/api/")) {
    // Authentication state must never be served stale: a cached
    // `authenticated: true` would show the app to someone whose session the
    // server has already stopped accepting.
    if (pathname.startsWith("/api/auth/")) return "passthrough";
    return "data";
  }

  if (pathname.startsWith("/assets/")) return "asset";

  // Navigations, including a deep link the SPA routes itself.
  if (mode === "navigate" || destination === "document") return "shell";

  // The icons and the manifest.
  if (PRECACHE_URLS.includes(pathname)) return "asset";

  return "passthrough";
}

/** Caches from an older version of the worker, safe to delete on activate. */
export const staleCaches = (names) =>
  names.filter((name) => name.startsWith("husholdning-") && !CURRENT_CACHES.includes(name));
