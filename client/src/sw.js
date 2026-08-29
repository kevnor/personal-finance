/* eslint-env serviceworker */
//
// The service worker. What it may and may not cache is decided by
// `strategyFor` in lib/swStrategy.js, which is a pure function with its own
// tests — a service worker is the worst place in a web app to find a
// mistake, because it persists across reloads and keeps serving whatever it
// decided to keep.
//
// Scope of the offline promise, from the spec: "last-loaded data is cached
// so Home shows a number with no connection, which matters in shops with
// poor signal. Writes require a connection." So reads fall back to the last
// response and writes simply fail — there is no queue. A queue means
// conflict resolution and a sync state machine, and worse, a user who
// believes an expense was recorded when it was not.

import {
  ASSET_CACHE,
  DATA_CACHE,
  PRECACHE_URLS,
  SHELL_CACHE,
  staleCaches,
  strategyFor,
} from "./lib/swStrategy.js";

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // Individually rather than addAll, which rejects the whole batch if a
      // single URL 404s — one missing icon must not leave the app with no
      // offline shell at all.
      await Promise.all(
        PRECACHE_URLS.map((url) => cache.add(url).catch(() => undefined)),
      );
      // Take over at once. One user, one device at a time: waiting for every
      // tab to close before a fix reaches them is the wrong trade here.
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(staleCaches(names).map((name) => caches.delete(name)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const strategy = strategyFor({
    method: request.method,
    url: request.url,
    mode: request.mode,
    destination: request.destination,
    origin: self.location.origin,
  });

  if (strategy === "passthrough") return;
  if (strategy === "asset") event.respondWith(cacheFirst(request));
  if (strategy === "shell") event.respondWith(shell(request));
  if (strategy === "data") event.respondWith(networkFirst(request));
});

/**
 * Content-hashed build assets. The bytes behind a given URL never change, so
 * a cached copy is not a stale copy.
 */
async function cacheFirst(request) {
  const cache = await caches.open(ASSET_CACHE);
  const hit = await cache.match(request);
  if (hit) return hit;

  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}

/**
 * Navigations. Network first so a new build is picked up immediately, with
 * the cached shell behind it so a reload works with no signal.
 */
async function shell(request) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put("/", response.clone());
    return response;
  } catch {
    return (await cache.match("/")) ?? Response.error();
  }
}

/**
 * API reads. Network first, because a figure that is merely a few seconds
 * old is still the wrong figure to prefer when the network is right there;
 * the cache is the fallback that makes the app usable in a shop.
 *
 * A 401 is cached-through deliberately as a *failure*: it is stored nowhere,
 * so a session that comes back does not have to fight a cached rejection.
 */
async function networkFirst(request) {
  const cache = await caches.open(DATA_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    const hit = await cache.match(request);
    if (hit) return hit;
    // Nothing cached and no network. Answered explicitly rather than left to
    // throw, so the client's fetch wrapper reports "no contact with the
    // server" instead of an opaque failure.
    return new Response(
      JSON.stringify({ detail: "Ingen forbindelse, og ingen lagret kopi." }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }
}
