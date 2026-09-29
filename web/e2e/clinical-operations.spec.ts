import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { login, startDemoRun } from "./helpers";

async function assertNoOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(
    0,
  );
}

async function assertTouchTargets(page: Page) {
  const undersized = await page.locator("button, a.ui-button, .nav-link, .case-tab").evaluateAll((nodes) =>
    nodes
      .filter((node) => {
        const rect = node.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && (rect.width < 44 || rect.height < 43.5);
      })
      .map((node) => node.textContent?.trim()),
  );
  expect(undersized).toEqual([]);
}

async function assertA11y(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
}

test("login and seeded launcher preserve authentication and synthetic boundary", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText("ต้นแบบเพื่อการวิจัย ไม่ใช้กับผู้ป่วยจริง", { exact: false })).toBeVisible();
  await login(page, "nurse");
  await expect(page.getByRole("heading", { name: /คิวงานตามบทบาท|คิวรับเข้าและคัดกรอง/ })).toBeVisible();
  await startDemoRun(page);
  await expect(page.getByRole("heading", { name: "คิวรับเข้าและคัดกรอง" })).toBeVisible();
  await expect(page.getByText("SYN-2026-0017").first()).toBeVisible();
});

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
]) {
  test(`queue and case workspace are safe at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await login(page, "nurse");
    await startDemoRun(page);
    await assertNoOverflow(page);
    await assertTouchTargets(page);
    await page
      .getByRole("link", { name: /เปิดเคส/ })
      .nth(1)
      .click();
    await expect(page.getByRole("heading", { name: "ทบทวนข้อเสนอการคัดกรอง" })).toBeVisible();
    await expect(page.getByText("พบสัญญาณที่ต้องประเมินเร่งด่วน", { exact: true })).toBeVisible();
    await assertNoOverflow(page);
    await assertTouchTargets(page);
    await assertA11y(page);
  });
}

test("complete synthetic journey nurse to physician to pharmacist is append-only", async ({ page }) => {
  await login(page, "nurse");
  await startDemoRun(page);
  await page
    .getByRole("link", { name: /เปิดเคส/ })
    .nth(1)
    .click();
  await page.getByLabel(/รับทราบ red flag/).check();
  await page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ }).click();
  await expect(page.getByText("ตรวจทานโดยบุคลากรแล้ว")).toBeVisible();
  await page.getByRole("button", { name: /ส่งต่อให้แพทย์/ }).click();
  await page.getByRole("button", { name: /ออกจากระบบ/ }).click();

  await login(page, "physician");
  await page.getByRole("link", { name: /เปิดเคส/ }).click();
  await page.getByLabel(/รับทราบ red flag/).check();
  await page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ }).click();
  await page.getByRole("button", { name: /ส่งต่อให้เภสัชกร/ }).click();
  await page.getByRole("button", { name: /ออกจากระบบ/ }).click();

  await login(page, "pharmacist");
  await page.getByRole("link", { name: /เปิดเคส/ }).click();
  await expect(page.getByRole("heading", { name: "Medication reconciliation" })).toBeVisible();
  await page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ }).click();
  await expect(page.getByText("ตรวจทานแล้ว", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "กิจกรรม" }).click();
  await expect(page.getByText("ส่งต่อเคสแล้ว").first()).toBeVisible();
  await expect(page.getByText("บันทึก medication review แล้ว")).toBeVisible();
});

test("legacy role homes redirect to the canonical queue; role work pages stay in the shell", async ({ page }) => {
  await login(page, "nurse");
  for (const path of ["/nurse", "/physician", "/pharmacist"]) {
    await page.goto(path);
    await expect(page).toHaveURL("/app/queue");
  }
  // Domain work pages are not redirected into the seeded demo case (a different synthetic patient).
  for (const [path, heading] of [
    ["/nurse/triage", "Triage cases"],
    ["/nurse/intake", "Voice intake"],
  ]) {
    await page.goto(path);
    await expect(page).toHaveURL(path);
    await expect(page.getByRole("navigation").getByRole("link", { name: /คิวงาน/ })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(heading);
  }
});

test("review flow is keyboard operable and guarded by acknowledgement", async ({ page }) => {
  await login(page, "nurse");
  await startDemoRun(page);
  await page
    .getByRole("link", { name: /เปิดเคส/ })
    .nth(1)
    .focus();
  await page.keyboard.press("Enter");
  const confirm = page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ });
  await expect(confirm).toBeDisabled();
  await page.getByLabel(/รับทราบ red flag/).focus();
  await page.keyboard.press("Space");
  await expect(confirm).toBeEnabled();
  await confirm.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("ตรวจทานโดยบุคลากรแล้ว")).toBeVisible();
});

// U5 WP-A: role tool links (A-4), compact tablet/phone nav (A-2), 403/404 exits (A-5).
const TOOL_LINKS = { nurse: 2, physician: 1, pharmacist: 1 } as const;
for (const role of ["nurse", "physician", "pharmacist"] as const) {
  test(`${role} queue lists ${TOOL_LINKS[role]} role tool link(s) without a demo run`, async ({ page }) => {
    await login(page, role);
    const tools = page.getByRole("region", { name: "เครื่องมือของบทบาท" });
    await expect(tools).toBeVisible();
    await expect(tools.getByRole("link")).toHaveCount(TOOL_LINKS[role]);
    await expect(page.getByRole("link", { name: "ไปที่รอบเดโม" })).toBeVisible();
  });
}

test("tablet and phone shell: compact top bar and nav, sign-out never below the nav", async ({ page }) => {
  await login(page, "nurse");
  await startDemoRun(page);
  for (const [width, height, maxH1] of [
    [768, 1024, 260],
    [390, 844, 340],
  ]) {
    await page.setViewportSize({ width, height });
    const m = await page.evaluate(() => {
      const box = (el: Element | null) => (el ? el.getBoundingClientRect() : null);
      const links = [...document.querySelectorAll(".nav-link")];
      const logout = [...document.querySelectorAll("button")].find((b) => /ออกจากระบบ/.test(b.textContent || ""));
      return {
        nav: box(document.querySelector(".app-nav"))!.height,
        h1: box(document.querySelector("h1"))!.top + scrollY,
        lastNav: box(links[links.length - 1])!.top,
        logout: box(logout || null)!.top,
      };
    });
    expect(m.nav, `nav height at ${width}`).toBeLessThanOrEqual(128);
    expect(m.h1, `h1 top at ${width}`).toBeLessThanOrEqual(maxH1);
    expect(m.logout, "sign-out sits in the top bar row").toBeLessThanOrEqual(m.lastNav);
    await assertNoOverflow(page);
  }
});

test("403 and 404 offer a way back to the queue", async ({ page }) => {
  await login(page, "nurse");
  await page.goto("/physician/care");
  await expect(page.getByTestId("forbidden")).toBeVisible();
  await expect(page.getByRole("link", { name: "กลับไปคิวงาน" })).toBeVisible();
  await page.goto("/definitely-missing");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("404");
  await expect(page.getByRole("link", { name: "กลับไปคิวงาน" })).toBeVisible();
});

test("U6 overview is the shared case summary on first open, no tab click", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await login(page, "nurse");
  await startDemoRun(page);
  await page
    .getByRole("link", { name: /เปิดเคส/ })
    .nth(1)
    .click();
  await page.getByRole("link", { name: "ภาพรวม" }).click();
  await expect(page).toHaveURL(/\/overview/);
  await expect(page.getByTestId("case-summary")).toBeVisible();
  // 1 banner, 2 chief complaint, 3 vitals + direction, 4 allergy, 5 meds + discrepancy count, 6 labs
  await expect(page.getByText("พบสัญญาณที่ต้องประเมินเร่งด่วน", { exact: true })).toBeVisible();
  await expect(page.getByText("แน่นหน้าอกและหายใจลำบาก").first()).toBeVisible();
  await expect(page.getByTestId("vital-hr")).toContainText("112");
  await expect(page.getByTestId("vital-hr-dir")).toContainText("↑ เพิ่มขึ้น");
  await expect(page.getByTestId("vital-spo2-dir")).toContainText("↓ ลดลง");
  await expect(page.getByTestId("vital-temp_c")).toContainText("ไม่มีบันทึก");
  await expect(page.getByTestId("summary-allergy")).toContainText("เพนิซิลลิน");
  await expect(page.getByTestId("med-discrepancy-count")).toContainText("1 รายการ");
  await expect(page.getByTestId("summary-meds")).toContainText("Aspirin 81 mg");
  await expect(page.getByTestId("summary-labs")).toContainText("Troponin I");
  // the red flag stays before the summary in DOM order; items 1-4 sit inside the first 800px screen
  const bannerFirst = await page.evaluate(() => {
    const banner = document.querySelector(".safety-banner");
    const sum = document.querySelector("[data-testid=case-summary]");
    return !!banner && !!sum && !!(banner.compareDocumentPosition(sum) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(bannerFirst).toBe(true);
  for (const id of ["summary-vitals", "summary-allergy"]) {
    const box = await page.getByTestId(id).boundingBox();
    expect(box!.y + box!.height).toBeLessThanOrEqual(800);
  }
  await assertNoOverflow(page);
  await assertA11y(page);
  for (const viewport of [
    { width: 768, height: 1024 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await assertNoOverflow(page);
    await assertA11y(page);
  }
});

test("U7 queue lists all 7 cases red flags first; fixture overviews match the engine output and stay view-only", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await login(page, "nurse");
  await startDemoRun(page);
  const rows = page.getByTestId("queue-cases").locator("tbody tr");
  await expect(rows).toHaveCount(7);
  await expect(rows.first()).toContainText("SYN-2026-0017");
  const run = await page.evaluate(() => localStorage.getItem("medx.demo.run"));
  const listed = (await (await page.request.get(`/api/demo/v1/runs/${run}/queue`)).json()).cases as {
    case_id: string;
    view_only: boolean;
    safety_level: string;
  }[];
  const order = listed.map((c) => c.safety_level === "critical");
  expect(order).toEqual([...order].sort((a, b) => Number(b) - Number(a))); // every critical row first
  for (let i = 0; i < 7; i++) await expect(rows.nth(i)).toContainText(listed[i].case_id);
  for (const c of listed as unknown as { case_id: string; view_only: boolean; alert_count: number; not_evaluated_count: number }[]) {
    if (c.view_only) await expect(rows.filter({ hasText: c.case_id })).toContainText("ดูข้อมูลอย่างเดียว");
    if (c.view_only && !c.alert_count && c.not_evaluated_count)
      await expect(rows.filter({ hasText: c.case_id })).toContainText(`ยังประเมินไม่ครบ (${c.not_evaluated_count} กฎ)`);
  }

  let sawUnknownAllergy = false,
    sawMissingVital = false,
    sawNotEvaluated = false,
    sawAlert = false;
  for (const c of listed.filter((x) => x.view_only)) {
    const api = await (await page.request.get(`/api/demo/v1/runs/${run}/cases/${c.case_id}`)).json();
    const meds = await (await page.request.get(`/api/demo/v1/runs/${run}/cases/${c.case_id}/medications`)).json();
    await page.goto(`/app/cases/${c.case_id}/overview?run=${run}`);
    await expect(page.getByTestId("case-summary")).toBeVisible();
    for (const id of ["summary-vitals", "summary-complaint", "summary-allergy", "summary-meds", "summary-labs"])
      await expect(page.getByTestId(id)).toBeVisible();
    await expect(page.getByTestId("view-only-notice")).toContainText("เคสตัวอย่างสำหรับดูข้อมูล — ยังไม่เปิดให้ดำเนินการ");
    await expect(page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ|ส่งต่อ/ })).toHaveCount(0);
    await expect(page.getByRole("checkbox")).toHaveCount(0);
    const rf = api.engines.red_flag;
    await expect(page.getByTestId("engine-versions")).toContainText(rf.ruleset_version);
    await expect(page.getByTestId("engine-versions")).toContainText(api.engines.pharma.pipeline_version);
    await expect(page.getByTestId("med-discrepancy-count")).toContainText(`${meds.discrepancies.length} รายการ`);
    expect(meds.discrepancies.length).toBe(api.engines.pharma.issue_count);
    const banner = page.getByTestId("safety-banner");
    if (rf.alerts.length) {
      sawAlert = true;
      await expect(banner).toHaveAttribute("data-level", "critical");
      await expect(banner).toContainText("พบสัญญาณที่ต้องประเมินเร่งด่วน");
      await expect(page.getByTestId("engine-alerts").locator("li")).toHaveCount(rf.alerts.length);
    } else {
      await expect(banner).toHaveAttribute("data-level", "none");
      await expect(banner).not.toContainText("ปลอดภัย");
      if (rf.not_evaluated.length) {
        await expect(page.getByTestId("not-evaluated-notice")).toContainText(`ยังประเมินไม่ครบ (${rf.not_evaluated.length}`);
      }
    }
    await expect(page.getByRole("heading", { level: 1 })).toContainText("เคสตัวอย่าง");
    await expect(page.getByText("view_only")).toHaveCount(0);
    if (rf.not_evaluated.length) {
      sawNotEvaluated = true;
      await expect(page.getByTestId("engine-not-evaluated")).toContainText(rf.not_evaluated_text);
    }
    if (api.allergies === null) {
      sawUnknownAllergy = true;
      await expect(page.getByTestId("allergy-unknown")).toBeVisible();
    }
    if (api.vitals.some((v: Record<string, unknown>) => v.temp_c === null)) {
      sawMissingVital = true;
      await expect(page.getByTestId("vitals-prev-missing")).toBeVisible();
    }
    // the safety banner precedes the summary in DOM order
    const first = await page.evaluate(() => {
      const b = document.querySelector("[data-testid=safety-banner]");
      const s = document.querySelector("[data-testid=case-summary]");
      return !!b && !!s && !!(b.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING);
    });
    expect(first).toBe(true);
    await assertNoOverflow(page);
    await assertA11y(page);
    await page.goto(`/app/cases/${c.case_id}/medications?run=${run}`);
    await expect(page.getByTestId("med-discrepancy")).toHaveCount(meds.discrepancies.length);
    await expect(page.getByRole("button", { name: /ยืนยันข้อเสนอแนะ/ })).toHaveCount(0);
  }
  expect([sawAlert, sawNotEvaluated, sawUnknownAllergy, sawMissingVital]).toEqual([true, true, true, true]);
  await page.goto(`/app/cases/SYNE-0007/overview?run=${run}`); // a dev-split id is not served
  await expect(page.locator(".ui-notice[role=alert]")).toContainText("case not found");
});
