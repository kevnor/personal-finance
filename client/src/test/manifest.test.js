import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";

const PUBLIC = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "public");
const manifest = JSON.parse(readFileSync(join(PUBLIC, "manifest.webmanifest"), "utf8"));

/** The width and height in a PNG's IHDR chunk, which starts at byte 16. */
function pngSize(path) {
  const buffer = readFileSync(path);
  expect(buffer.subarray(0, 8)).toEqual(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

describe("the web app manifest", () => {
  it("declares what a browser needs to offer installation", () => {
    // The manifest previously had `"icons": []`, which means no install
    // prompt on Android and no home-screen app — leaving a browser tab,
    // which is not what the design calls for.
    expect(manifest.name).toBeTruthy();
    expect(manifest.start_url).toBe("/");
    expect(manifest.display).toBe("standalone");
    expect(manifest.icons.length).toBeGreaterThan(0);
  });

  it("has the 192 and 512 icons installability requires", () => {
    const sizes = manifest.icons.map((icon) => icon.sizes);
    expect(sizes).toContain("192x192");
    expect(sizes).toContain("512x512");
  });

  it("has a maskable icon, so a launcher does not crop the mark", () => {
    const maskable = manifest.icons.filter((icon) => icon.purpose?.includes("maskable"));
    expect(maskable.length).toBeGreaterThan(0);
  });

  it("points at files that exist and are the size they claim", () => {
    // A manifest naming a missing icon fails installability silently.
    for (const icon of manifest.icons) {
      const path = join(PUBLIC, icon.src.replace(/^\//, ""));
      expect(existsSync(path), `${icon.src} is missing`).toBe(true);

      const [width, height] = icon.sizes.split("x").map(Number);
      expect(pngSize(path)).toEqual({ width, height });
    }
  });

  it("matches the app's own colours, so the splash screen is not white", () => {
    expect(manifest.background_color).toBe("#161826");
    expect(manifest.theme_color).toBe("#161826");
  });
});
