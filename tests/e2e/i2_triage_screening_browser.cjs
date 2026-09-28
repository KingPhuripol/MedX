// Checker-owned browser probe for slice i2 (A10 web render; A15 UI). Synthetic fixtures, mock provider.
// Run: node tests/e2e/i2_triage_screening_browser.cjs <base_url> <out_dir>
const path = require("path");
const { chromium } = require(path.resolve(__dirname, "../../web/node_modules/playwright"));

const [base, outDir] = process.argv.slice(2);
const OVERCLAIM = /no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)/i;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 1600 } });
  await page.goto(`${base}/login`);
  await page.getByLabel("Username").fill("nurse1");
  await page.getByLabel("Password").fill("nurse1-dev-only");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(`${base}/nurse`);
  const result = {};
  for (const ref of ["SYN-S4-002", "SYN-S4-011", "SYN-S4-020"]) {
    await page.goto(`${base}/nurse/triage`);
    const btn = page.getByRole("button", { name: `Assess ${ref}` });
    try { await btn.waitFor({ timeout: 15000 }); } catch { result[ref] = "no assess button"; continue; }
    await btn.click();
    await page.waitForURL(/\/nurse\/triage\/[0-9a-f]{32}$/);
    await page.waitForTimeout(800);
    const text = await page.locator("main").innerText();
    await page.screenshot({ path: path.join(outDir, `triage-review-${ref}.png`), fullPage: true });
    result[ref] = {
      declared_rules_fired: /of 16 declared rules fired/.test(text),
      mentions_rule_set_version: /rf-1\.1\.0/.test(text),
      mentions_scope: /unmentioned symptom is unknown/i.test(text),
      mentions_read_at_or_age: /read_at|age_min|read at|min old|minutes ago/i.test(text),
      incomplete_banner: /INCOMPLETE/i.test(text),
      overclaim: OVERCLAIM.test(text),
    };
  }
  console.log(JSON.stringify(result, null, 1));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
