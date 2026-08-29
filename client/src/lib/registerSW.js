/**
 * Register the service worker, when it is possible and worth doing.
 *
 * Three guards, each for a real reason:
 *
 *  - `serviceWorker` missing: an old or restricted browser. Not an error;
 *    the app works, it just has no offline cache.
 *  - Not a secure context: service workers only register over HTTPS or on
 *    localhost. Served as `http://192.168.1.x:8000` there is no worker and
 *    no install prompt — which is exactly why the spec makes `tailscale
 *    serve` part of the design rather than a nicety.
 *  - Development: Vite serves modules unbundled and the worker would cache a
 *    shell that the dev server is about to change under it.
 *
 * Failure is swallowed on purpose. A registration that fails must not take
 * the app down with it: everything here is an enhancement to a client that
 * works without it.
 */
export function registerServiceWorker({
  serviceWorker = typeof navigator !== "undefined" ? navigator.serviceWorker : undefined,
  isSecureContext = typeof window !== "undefined" ? window.isSecureContext : false,
  isProduction = import.meta.env?.PROD ?? false,
} = {}) {
  if (!serviceWorker || !isSecureContext || !isProduction) return Promise.resolve(null);
  return serviceWorker.register("/sw.js", { scope: "/" }).catch(() => null);
}
