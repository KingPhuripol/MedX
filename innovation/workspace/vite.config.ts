import { defineConfig } from "vitest/config";

// Two apps, two bundles: nurse.html and platform.html share only src/shared.
export default defineConfig({
  base: "/workspace-assets/",
  build: { outDir: "dist", assetsDir: "assets", rollupOptions: { input: { nurse: "nurse.html", platform: "platform.html" } } },
  test: { exclude: ["e2e/**", "node_modules/**", "dist/**"] },
});
