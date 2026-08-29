import { beforeEach, describe, expect, it } from "vitest";
import { rememberSignedIn, wasSignedIn } from "../lib/session.js";

beforeEach(() => localStorage.clear());

describe("the local signed-in note", () => {
  it("starts empty", () => {
    expect(wasSignedIn()).toBe(false);
  });

  it("remembers and forgets", () => {
    rememberSignedIn(true);
    expect(wasSignedIn()).toBe(true);
    rememberSignedIn(false);
    expect(wasSignedIn()).toBe(false);
  });

  it("survives storage being unavailable rather than throwing", () => {
    // Private mode and blocked site data throw on access rather than
    // returning null. The app must work without the offline fallback.
    const original = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new Error("blocked");
      },
      configurable: true,
    });
    expect(() => rememberSignedIn(true)).not.toThrow();
    expect(wasSignedIn()).toBe(false);
    Object.defineProperty(window, "localStorage", original);
  });
});
