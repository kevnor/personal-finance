import { defineConfig } from "vite";

/**
 * A second build, for the service worker only.
 *
 * The worker imports its strategy from `src/lib/swStrategy.js` so that logic
 * can be unit-tested; classic (non-module) service workers cannot import, so
 * it is bundled here into one self-contained `dist/sw.js`. The alternative --
 * inlining the rules in the worker -- would mean two copies of the one
 * decision that governs what the app serves offline.
 *
 * Module workers (`type: "module"`) would remove the need for this, but
 * support is still uneven, and an app that fails to register its worker on
 * some browsers fails silently.
 *
 * `emptyOutDir: false` because the main build has already written dist/.
 */
export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: false,
    // Not minified: a service worker is the one script a person may need to
    // read in devtools to understand why the app is serving what it is.
    minify: false,
    rollupOptions: {
      input: "src/sw.js",
      output: {
        entryFileNames: "sw.js",
        format: "iife",
      },
    },
  },
});
