// Checker-owned browser journey for slice i2 at 8cde5dd (A10 web render, A09 read times, A15 UI review).
// Synthetic S4 author fixtures + S1r dev screening blocks; mock provider; against `make dev`.
// Run: node tests/e2e/i2_browser_journey.cjs <web_base> <dev_screening.json> <out_dir>
const fs = require("fs");
const path = require("path");
const { chromium } = require(path.resolve(__dirname, "../../web/node_modules/playwright"));

const [base, blocksPath, outDir] = process.argv.slice(2);
const OVERCLAIM = /no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)/i;
const blocks = JSON.parse(fs.readFileSync(blocksPath, "utf8"));
const SHOTS = { "SYN-S4-002": "partial-with-alerts", "SYN-S4-017": "evaluated-with-alerts", "SYN-S4-038": "evaluated-0-alerts" };

async function login(page, user) {
  await page.goto(`${base}/login`);
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password").fill(`${user}-dev-only`);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

function check(text, status) {
  return {
    status,
    overclaim: (text.match(OVERCLAIM) || [null])[0],
    has_block: /Red-flag screening/.test(text),
    rule_set: /rf-1\.1\.0/.test(text),
    scope: /an unmentioned symptom is unknown, not absent/.test(text),
    declared_fired: /\d+ of 16 declared rules fired/.test(text),
    zero_of_16: /0 of 16 declared rules fired/.test(text),
    incomplete: /RED-FLAG SCREENING INCOMPLETE/.test(text),
    not_performed: /RED-FLAG SCREENING NOT PERFORMED/.test(text),
    read_at: /read at .* age \d+ min of a 60 min window/.test(text),
  };
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1600 } });
  const page = await ctx.newPage();
  await login(page, "nurse1");
  const res = { live: {}, mocked: {}, review: {}, roles: {} };

  // 1) live: every S4 fixture assessed through the UI
  await page.goto(`${base}/nurse/triage`);
  await page.getByRole("button", { name: "Assess SYN-S4-001" }).waitFor({ timeout: 30000 });
  const buttons = await page.getByRole("button", { name: /^Assess SYN-S4-\d+$/ }).evaluateAll((els) =>
    els.map((e) => e.getAttribute("aria-label") || e.textContent));
  const caseRefs = buttons.map((b) => b.match(/SYN-S4-\d+/)[0]);
  res.n_assess_buttons = caseRefs.length;
  let reviewId = null;
  for (const ref of caseRefs) {
    await page.goto(`${base}/nurse/triage`);
    await page.getByRole("button", { name: `Assess ${ref}` }).click();
    await page.waitForURL(/\/nurse\/triage\/[0-9a-f]{32}$/, { timeout: 30000 });
    const sec = page.getByTestId("screening-section");
    await sec.waitFor({ timeout: 15000 });
    const status = await sec.getAttribute("data-status");
    const text = await page.locator("main").innerText();
    res.live[ref] = check(text, status);
    if (SHOTS[ref]) await page.screenshot({ path: path.join(outDir, `i2-live-${ref}-${SHOTS[ref]}.png`), fullPage: true });
    if (ref === "SYN-S4-002") reviewId = page.url().split("/").pop();
  }

  // 2) UI review journey on SYN-S4-002 (3 alerts): buttons blocked until acknowledged; confirm; checkpoint confirmed
  res.review.assessment_id = reviewId;
  await page.goto(`${base}/nurse/triage/${reviewId}`);
  try { await page.getByTestId("screening-section").waitFor({ timeout: 20000 }); }
  catch (e) { console.error("REVIEW PAGE:", page.url(), (await page.locator("body").innerText()).slice(0, 800)); throw e; }
  const confirmBtn = page.getByRole("button", { name: "Confirm department" });
  res.review.disabled_before_ack = await confirmBtn.isDisabled();
  for (const cb of await page.locator('input[type="checkbox"][id^="ack-"]').all()) await cb.check();
  res.review.disabled_after_ack = await confirmBtn.isDisabled();
  await confirmBtn.click();
  await page.getByTestId("review-result").waitFor({ timeout: 15000 });
  res.review.result_text = await page.getByTestId("review-result").innerText();
  const view = await page.request.get(`${base}/api/triage/assessments/${reviewId}`);
  const vj = await view.json();
  res.review.graph_checkpoint_status = vj.graph_checkpoint_status;
  res.review.review_status = vj.review_status;
  await page.screenshot({ path: path.join(outDir, "i2-live-SYN-S4-002-after-confirm.png"), fullPage: true });

  // 3) the real page rendering every S1r dev screening block (+ unavailable), by substituting the screening field
  const baseAssessment = vj;
  for (const [dp, block] of Object.entries(blocks)) {
    await page.route(`**/api/triage/assessments/${reviewId}`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify({ ...baseAssessment, screening: block, review_status: "pending", review: null,
          confirmed_department: null }) }));
    await page.goto(`${base}/nurse/triage/${reviewId}`);
    const sec = page.getByTestId("screening-section");
    await sec.waitFor({ timeout: 15000 });
    const text = await page.locator("main").innerText();
    res.mocked[dp] = check(text, await sec.getAttribute("data-status"));
    if (dp === "__unavailable__") await page.screenshot({ path: path.join(outDir, "i2-mocked-unavailable.png"), fullPage: true });
    await page.unroute(`**/api/triage/assessments/${reviewId}`);
  }

  // 4) roles: a physician and a pharmacist cannot open the nurse review page
  for (const user of ["physician1", "pharmacist1"]) {
    const p2 = await (await browser.newContext()).newPage();
    await login(p2, user);
    await p2.goto(`${base}/nurse/triage/${reviewId}`);
    await p2.waitForTimeout(1500);
    const t = await p2.locator("body").innerText();
    res.roles[user] = { has_review_buttons: /Confirm department|Save edited department/.test(t), url: p2.url(),
                        excerpt: t.slice(0, 200) };
  }

  const live = Object.values(res.live), mocked = Object.values(res.mocked);
  res.summary = {
    live_n: live.length,
    live_overclaim: live.filter((x) => x.overclaim).length,
    live_block_complete: live.filter((x) => x.has_block && x.rule_set && x.scope && x.declared_fired).length,
    live_status: live.reduce((m, x) => ((m[x.status] = (m[x.status] || 0) + 1), m), {}),
    live_evaluated_zero_reads_0_of_16: Object.entries(res.live).filter(([, x]) => x.status === "evaluated" && x.zero_of_16).map(([k]) => k),
    live_partial_with_banner: live.filter((x) => x.status === "partially_evaluated" && x.incomplete).length,
    live_read_at_shown: live.filter((x) => x.read_at).length,
    mocked_n: mocked.length,
    mocked_overclaim: mocked.filter((x) => x.overclaim).length,
    mocked_partial_with_banner: mocked.filter((x) => x.status === "partially_evaluated" && x.incomplete).length,
    mocked_unavailable_not_performed: res.mocked.__unavailable__ && res.mocked.__unavailable__.not_performed,
  };
  fs.writeFileSync(path.join(outDir, "i2_browser_journey.json"), JSON.stringify(res, null, 1));
  console.log(JSON.stringify({ summary: res.summary, review: res.review, roles: res.roles }, null, 1));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
