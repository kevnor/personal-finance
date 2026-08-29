import { describe, expect, it, vi } from "vitest";
import { registerServiceWorker } from "../lib/registerSW.js";

const serviceWorker = () => ({ register: vi.fn().mockResolvedValue({ scope: "/" }) });

describe("service worker registration", () => {
  it("registers at the root scope in a secure production context", async () => {
    const sw = serviceWorker();
    await registerServiceWorker({ serviceWorker: sw, isSecureContext: true, isProduction: true });
    expect(sw.register).toHaveBeenCalledWith("/sw.js", { scope: "/" });
  });

  it("does not register over plain http", async () => {
    // Service workers only register in a secure context. Served as
    // http://192.168.1.x:8000 there is no worker and no install prompt —
    // which is why `tailscale serve` is part of the design, not a nicety.
    const sw = serviceWorker();
    await registerServiceWorker({ serviceWorker: sw, isSecureContext: false, isProduction: true });
    expect(sw.register).not.toHaveBeenCalled();
  });

  it("does not register in development", async () => {
    // Vite serves modules unbundled; the worker would cache a shell the dev
    // server is about to change under it.
    const sw = serviceWorker();
    await registerServiceWorker({ serviceWorker: sw, isSecureContext: true, isProduction: false });
    expect(sw.register).not.toHaveBeenCalled();
  });

  it("is a no-op where the browser has no service worker support", async () => {
    await expect(
      registerServiceWorker({ serviceWorker: undefined, isSecureContext: true, isProduction: true }),
    ).resolves.toBeNull();
  });

  it("swallows a failed registration rather than taking the app down", async () => {
    const sw = { register: vi.fn().mockRejectedValue(new Error("nope")) };
    await expect(
      registerServiceWorker({ serviceWorker: sw, isSecureContext: true, isProduction: true }),
    ).resolves.toBeNull();
  });
});
