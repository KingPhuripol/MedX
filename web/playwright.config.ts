import { defineConfig, devices } from "@playwright/test";

// Ports come from the environment (slice runs use API_PORT=8105 WEB_PORT=3105); defaults unchanged.
const WEB_PORT = process.env.WEB_PORT || "3000";
const API_PORT = process.env.API_PORT || "8000";
const baseURL = process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${WEB_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } }],
  webServer: {
    command: `make -C .. dev API_PORT=${API_PORT} WEB_PORT=${WEB_PORT}`,
    url: `${baseURL}/login`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
