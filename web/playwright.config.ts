import { defineConfig, devices } from "@playwright/test";

// Ports are configurable so parallel slices can run side by side (defaults stay 3000/8000).
const WEB_PORT = process.env.WEB_PORT || "3000";
const API_PORT = process.env.API_PORT || "8000";
const BASE_URL = process.env.BASE_URL || `http://127.0.0.1:${WEB_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: BASE_URL, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } }],
  webServer: {
    command: `DEMO_MODE=1 make -C .. dev WEB_PORT=${WEB_PORT} API_PORT=${API_PORT}`,
    url: `${BASE_URL}/login`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
