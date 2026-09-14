import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "/workspace-assets/",
  build: { outDir: "dist", assetsDir: "assets" },
  test: { exclude: ["e2e/**", "node_modules/**", "dist/**"] },
});
