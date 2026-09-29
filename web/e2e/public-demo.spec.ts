import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { DISCLAIMER_EN } from "../lib/copy";
import { ROLES, type Role } from "./helpers";

// Slice d1: PUBLIC_DEMO flow against a staged Vercel bundle run locally (see docs/DEPLOY-VERCEL.md), e.g.
//   PUBLIC_DEMO_E2E=1 BASE_URL=http://127.0.0.1:3117 npx playwright test e2e/public-demo.spec.ts
// Skipped in the normal `make e2e` run, whose servers use password login.
test.skip(process.env.PUBLIC_DEMO_E2E !== "1", "needs a PUBLIC_DEMO=1 / NEXT_PUBLIC_PUBLIC_DEMO=1 server");

const LABEL: Record<Role, RegExp> = { nurse: /^Nurse · พยาบาล$/, physician: /^Physician · แพทย์$/, pharmacist: /^Pharmacist · เภสัชกร$/ };

async function pick(page: Page, role: Role) {
  await page.goto("/login");
  await page.getByRole("button", { name: LABEL[role] }).click();
  await expect(page).toHaveURL(`/${role}`);
}

test("login page is a role picker with no password field; disclaimer shown; no serious/critical axe", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(0);
  await expect(page.locator("input[type=password]")).toHaveCount(0);
  for (const role of ROLES) await expect(page.getByRole("button", { name: LABEL[role] })).toBeVisible();
  await expect(page.getByTestId("research-disclaimer")).toContainText(DISCLAIMER_EN);
  // Same bar as a11y.spec.ts: no serious/critical violations.
  const axe = await new AxeBuilder({ page }).analyze();
  expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
});

for (const role of ROLES) {
  test(`${role} one-click login lands on own home and is 403 on other roles`, async ({ page }) => {
    await pick(page, role);
    await expect(page.getByTestId("research-disclaimer")).toBeVisible();
    for (const other of ROLES.filter((r) => r !== role)) {
      await page.goto(`/${other}`);
      await expect(page.getByTestId("forbidden")).toBeVisible();
    }
  });
}

test("physician care list shows synthetic cases", async ({ page }) => {
  await pick(page, "physician");
  await page.goto("/physician/care");
  await expect(page.getByRole("button", { name: /^Assess SYNE-\d+ at T1$/ }).first()).toBeVisible();
});

test("pharmacist reconcile run works", async ({ page }) => {
  await pick(page, "pharmacist");
  await page.goto("/pharmacist/reconcile");
  await page.getByLabel("Synthetic patient").selectOption("demo-01");
  await page.getByRole("button", { name: "Run check" }).click();
  await expect(page.getByRole("status")).toContainText(/issue\(s\)/);
});

test("unknown or forged session goes back to the role picker, not a crash", async ({ page, context, baseURL }) => {
  await context.addCookies([{ name: "fd_session", value: "d1.forged.sig", url: baseURL! }]);
  await page.goto("/physician");
  await expect(page).toHaveURL("/login");
  await expect(page.getByRole("button", { name: LABEL.physician })).toBeVisible();
});
