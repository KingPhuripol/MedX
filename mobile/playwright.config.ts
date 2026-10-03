import { defineConfig } from "@playwright/test";

/** Browser tests run against the production build (next build && next start) with every /api call mocked. */
const PORT = Number(process.env.MOBILE_E2E_PORT ?? 3112);

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    locale: "th-TH",
    timezoneId: "Asia/Bangkok",
    deviceScaleFactor: 2,
    serviceWorkers: "block",
  },
  projects: [
    { name: "390x844", use: { viewport: { width: 390, height: 844 } } },
    { name: "360x800", use: { viewport: { width: 360, height: 800 } } },
  ],
  webServer: {
    command: `npx next build && npx next start -H 127.0.0.1 -p ${PORT}`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: true,
    timeout: 240_000,
    env: { BACKEND_URL: "http://127.0.0.1:9" },
  },
});
