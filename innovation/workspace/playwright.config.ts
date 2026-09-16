import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8771",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], channel: "chrome", viewport: { width: 1440, height: 900 } } },
    { name: "tablet", use: { ...devices["Desktop Chrome"], channel: "chrome", viewport: { width: 768, height: 1024 }, hasTouch: true } },
  ],
  webServer: {
    command: "cd ../.. && FRONT_DOOR_DB=/tmp/frontdoor-playwright.sqlite3 ${PYTHON:-python3} -m uvicorn innovation.api.app:app --host 127.0.0.1 --port 8771",
    url: "http://127.0.0.1:8771/ready",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
