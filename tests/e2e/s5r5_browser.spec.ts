import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import * as fs from "fs";

// e2e-tester s5r5 checker (7382c7c, s5r4 spec rev 5 + s5r5 closing rule). Servers must already be up on 3105/8105.
// Run from web/: npx playwright test -c ../tests/e2e/playwright.config.ts s5r5_browser
const pw = (u: string) => process.env[`SEED_${u.toUpperCase()}_PASSWORD`] || `${u}-dev-only`;
const PROV = "synthetic: e2e-tester s5r5 browser run (no real patient data)";
const OUT = process.env.S5R5_OUT || "../artifacts/factory/s5r5/browser";
const findings: Record<string, unknown> = {};

async function login(page: Page, user: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password").fill(pw(user));
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

const AT: Record<string, string> = { home_list: "2026-06-01T09:00:00+07:00", new_order: "2026-07-01T09:40:00+07:00" };

async function post(page: Page, ref: string, lists: Record<string, string[]>) {
  const snapshot = {
    patient_ref: ref, as_of: "2026-07-01T10:00:00+07:00", data_class: "synthetic",
    sources: Object.entries(lists).map(([t, entries]) => ({
      source_type: t, evidence_ref: `${ref}/${t}/1`, available_at_time: AT[t], provenance: PROV, version: "1",
      entries: entries.map((text) => ({ text })),
    })),
    allergies: [],
  };
  const resp = await page.request.post("/api/pharma/reconcile", { data: { snapshot, mode: "rules_only" } });
  expect(resp.status()).toBe(200);
  return resp.json();
}

async function openRun(page: Page, runId: string) {
  await page.goto(`/pharmacist/reconcile?run=${encodeURIComponent(runId)}`);
  await expect(page.getByRole("status")).toContainText(/Saved run loaded/);
}

async function observe(page: Page, key: string, lists: Record<string, string[]>) {
  const run = await post(page, `s5r5-${key}-${Date.now()}`, lists);
  await openRun(page, run.run_id);
  const body = await page.locator("main").innerText();
  const axe = (await new AxeBuilder({ page }).analyze()).violations
    .filter((x) => ["serious", "critical"].includes(x.impact ?? "")).map((x) => x.id);
  const f = {
    run_id: run.run_id,
    lists,
    issues_api: run.issues.map((i: { type: string; field?: string }) => [i.type, i.field ?? null]),
    missing_field_articles: await page.locator("ol.issue-list > li > article[data-type='missing_field']").count(),
    dose_mismatch_articles: await page.locator("ol.issue-list > li > article[data-type='dose_mismatch']").count(),
    summary: await page.getByTestId("unchecked-summary").innerText(),
    dose_lines: body.split("\n").filter((l) => /Dose per administration|mg x|mg ×/.test(l)),
    axe,
  };
  findings[key] = f;
  await page.screenshot({ path: `${OUT}/browser_${key}.png`, fullPage: true });
  return f;
}


test.afterAll(() => {
  fs.writeFileSync(`${OUT}/browser_findings.json`, JSON.stringify(findings, null, 1));
});

const M = "Metformin 1000 mg bid";
// New rev-5-round findings (observed, not asserted) and their P4-word controls.
const OBS: [string, string, string][] = [
  ["BE-1_en_every_morning_bid", "Metformin 1000 mg every morning bid", M],
  ["BE-5_th_thukchao_wanla2", "เมทฟอร์มิน 1000 มก. ทุกเช้า วันละ 2 ครั้ง", M],
  ["BE-8_th_thukchao_1x2", "เมทฟอร์มิน 1000 มก. ทุกเช้า 1x2", M],
  ["NR-3_name_region_thukwan", "เมทฟอร์มิน ทุกวัน 1000 มก. วันละ 2 ครั้ง", M],
  ["CTRL_en_daily_in_the_morning_bid", "Metformin 1000 mg daily in the morning bid", M],
  ["CTRL_th_thukwan_chao_wanla2", "เมทฟอร์มิน 1000 มก. ทุกวัน ตอนเช้า วันละ 2 ครั้ง", M],
];
for (const [key, home, order] of OBS) {
  test(`observed: ${key}`, async ({ page }) => {
    await login(page, "pharmacist1");
    const f = await observe(page, key, { home_list: [home], new_order: [order] });
    expect(f.axe).toEqual([]);
  });
}

test("nurse gets the 403 page on /pharmacist/reconcile", async ({ page }) => {
  await login(page, "nurse1");
  await page.goto("/pharmacist/reconcile");
  await expect(page.locator("main")).toContainText(/403|not allowed|permission/i);
});
