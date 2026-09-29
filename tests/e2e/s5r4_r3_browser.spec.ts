import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import * as fs from "fs";

// e2e-tester s5r4 rev-5 checker (444ca3e, spec rev 5). Servers must already be up on 3105/8105.
// Run from web/: npx playwright test -c ../tests/e2e/playwright.config.ts s5r4_browser
const pw = (u: string) => process.env[`SEED_${u.toUpperCase()}_PASSWORD`] || `${u}-dev-only`;
const PROV = "synthetic: e2e-tester s5r4 browser run (no real patient data)";
const OUT = process.env.S5R4_OUT || "../artifacts/factory/s5r4/r3_browser";
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
  const run = await post(page, `s5r4r3-${key}-${Date.now()}`, lists);
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

const W = "Warfarin 3 mg 1 tab od";
const M = "Metformin 1000 mg bid";
const PER = "not verifiable (an amount per day, per weight or per other unit, not per dose)";
const PUA = "not verifiable (an amount per day, per weight or per other unit, not per dose)";
// A10 rev-5 additions (B1, B6, B12, B16): 1 missing-dose, 0 dose mismatch, "could not be verified" shown, axe clean.
const A10: [string, string, string][] = [
  ["B1", "Metformin 1000 mg day", M],
  ["B6", "Metformin 1000 mg po daily bid", M],
  ["B12", "Metformin 1000 mg daily morning, evening", M],
  ["B16", "Metformin 1000 mg qd bid", M],
  ["B14_th", "เมทฟอร์มิน 1000 มก. ทุกวัน เช้า เย็น", M],
];
for (const [id, home, order] of A10) {
  test(`A10 ${id}: unverifiable dose is visible (1 missing-dose, 0 dose mismatch, no axe serious/critical)`, async ({ page }) => {
    await login(page, "pharmacist1");
    const f = await observe(page, `A10_${id}`, { home_list: [home], new_order: [order] });
    await expect(page.locator("main")).toContainText("could not be verified");
    const api = f.issues_api as [string, string | null][];
    expect(api.filter(([t, fld]) => t === "missing_field" && fld === "dose").length).toBe(1);
    expect(f.missing_field_articles).toBe(api.filter(([t]) => t === "missing_field").length);
    expect(f.dose_mismatch_articles).toBe(0);
    expect(f.axe).toEqual([]);
  });
}

// K16 (AB1): Perindopril now resolves and is compared; Name read shows the name.
test("K16 Perindopril 4 mg od resolves (no missing-dose)", async ({ page }) => {
  await login(page, "pharmacist1");
  const f = await observe(page, "K16_perindopril", { home_list: ["Perindopril 4 mg od"], new_order: ["Perindopril 4 mg od"] });
  expect(f.missing_field_articles).toBe(0);
  expect(f.axe).toEqual([]);
});

// Rev-5 round findings (observed, not asserted): Q5 'N x k' as the MULTI / once-daily statement.
const OBS: [string, string, string][] = [
  ["BQ5-1_en_daily_1x2", "Metformin 1000 mg daily 1x2", M],
  ["BQ5-5_th_thukwan_1x2", "เมทฟอร์มิน 1000 มก. ทุกวัน 1x2", M],
  ["BQ5-7_th_wanlakrang_1x2", "เมทฟอร์มิน 1000 มก. วันละครั้ง 1x2", M],
  ["BQ5b-2_th_1x1_chao_yen", "เมทฟอร์มิน 1000 มก. 1x1 เช้า เย็น", M],
  ["BN-1_nightly_bid", "Metformin 1000 mg nightly bid", M],
  ["CTRL_en_daily_1_tab_bid", "Metformin 1000 mg daily 1 tab bid", M],
  ["CTRL_th_thukwan_1_tab_wanla2", "เมทฟอร์มิน 1000 มก. ทุกวัน 1 เม็ด วันละ 2 ครั้ง", M],
];
for (const [key, home, order] of OBS) {
  test(`observed: ${key}`, async ({ page }) => {
    await login(page, "pharmacist1");
    await observe(page, key, { home_list: [home], new_order: [order] });
  });
}

test("nurse gets the 403 page on /pharmacist/reconcile", async ({ page }) => {
  await login(page, "nurse1");
  await page.goto("/pharmacist/reconcile");
  await expect(page.locator("main")).toContainText(/403|not allowed|permission/i);
});
