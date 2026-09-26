import { defineConfig, devices } from "@playwright/test";

// Ports follow the Makefile (defaults 8000/3000; slice s4 runs on API_PORT=8104 WEB_PORT=3104).
const WEB_PORT = process.env.WEB_PORT || "3000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } }],
  webServer: {
    command: "make -C .. dev",
    url: `http://127.0.0.1:${WEB_PORT}/login`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
