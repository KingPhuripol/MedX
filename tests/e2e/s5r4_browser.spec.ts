import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import * as fs from "fs";

// e2e-tester s5r4 checker (6b2a67a, s5r3 rev 3). Servers must already be up on 3105/8105.
// Run from web/: npx playwright test -c ../tests/e2e/playwright.config.ts s5r4_browser
const pw = (u: string) => process.env[`SEED_${u.toUpperCase()}_PASSWORD`] || `${u}-dev-only`;
const PROV = "synthetic: e2e-tester s5r4 browser run (no real patient data)";
const OUT = process.env.S5R4_OUT || "../artifacts/factory/s5r4";
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
  const run = await post(page, `s5r4-${key}-${Date.now()}`, lists);
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
const M = "Metformin 500 mg 1 tab bid";
const PER = "not verifiable (an amount per day, per weight or per other unit, not per dose)";
// A10: I1, SL1, DT1, D1, QF1 in a two-source snapshot: 1 missing dose, 0 dose mismatch, reason label shown.
const A10: [string, string, string, string][] = [
  ["I1", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง​ชั่วโมงก่อนอาหาร", W, "not verifiable"],
  ["SL1", "Metformin 1000 mg／day", M, PER],
  ["DT1", "Metformin 1000 mg./day", M, PER],
  ["D1", "เมทฟอร์มิน 1000 มก. แบ่งวันละ 2 ครั้ง", M, PER],
  ["QF1", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่งชัวโมงก่อนอาหาร", W, "not verifiable"],
];
for (const [id, home, order, label] of A10) {
  test(`A10 ${id}: unverifiable dose is visible (1 missing-dose, 0 dose mismatch, no axe serious/critical)`, async ({ page }) => {
    await login(page, "pharmacist1");
    const f = await observe(page, `A10_${id}`, { home_list: [home], new_order: [order] });
    await expect(page.locator("main")).toContainText(label);
    const api = f.issues_api as [string, string | null][];
    expect(api.filter(([t, fld]) => t === "missing_field" && fld === "dose").length).toBe(1);
    expect(f.missing_field_articles).toBe(api.filter(([t]) => t === "missing_field").length);
    expect(f.dose_mismatch_articles).toBe(0);
    expect(f.axe).toEqual([]);
  });
}

// Checker findings (observed, not asserted): what the pharmacist sees when the true order differs.
const OBS: [string, string, string][] = [
  ["HT1_tone_order_half", "วาร์ฟาริน 3 มก. 1 เม็ดคร่ึง วันละ 1 ครั้ง", W],
  ["HT_control_half", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง วันละ 1 ครั้ง", W],
  ["DD1_double_sara_e_divided", "เมทฟอร์มิน 1000 มก. เเบ่งวันละ 2 ครั้ง", "Metformin 1000 mg bid"],
  ["PD1_perday", "Metformin 1000 mg perday", "Metformin 1000 mg bid"],
  ["D10_total_before_strength", "Metformin total 1000 mg bid", M],
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
