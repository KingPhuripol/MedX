/** V2C-C13: axe 0 serious/critical in every C2 state; visible 2px focus ring on every control; §4 tab order. */
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

import { settle } from "./harness";
import { stateTests } from "./states";

/** Tab through the page once; for each stop, report a label and whether its focus ring is visible (≥ 2 px). */
async function traverse(page: Page) {
  // Chrome resumes Tab from the last clicked element, so walk one full cycle and order the stops by DOM position.
  const stops: { label: string; ring: boolean; detail: string; pos: number }[] = [];
  for (let i = 0; i < 80; i++) {
    await page.keyboard.press("Tab");
    const s = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const probe = document.createElement("i");
      probe.style.color = "var(--primary)";
      document.body.append(probe);
      const primary = getComputedStyle(probe).color;
      probe.style.color = "var(--card)";
      const card = getComputedStyle(probe).color;
      probe.remove();
      const input = el as HTMLInputElement;
      // Native radio/checkbox are visually replaced: the ring is drawn on the row / custom box.
      const target =
        input.type === "radio" ? el.closest(".pick") : input.type === "checkbox" ? el.closest("label")?.querySelector(".check") : el;
      const cs = getComputedStyle(target as Element);
      const onRed = !!el.closest(".alarm");
      let ring = parseFloat(cs.outlineWidth) >= 2 && cs.outlineStyle !== "none" && cs.outlineColor === (onRed ? card : primary);
      if (!ring && el.closest(".input")) {
        // Text fields: 1px primary border + 1px primary spread = 2px ring on the wrapper.
        const w = getComputedStyle(el.closest(".input") as Element);
        ring = w.borderColor === primary && w.boxShadow.includes(primary);
      }
      const label = el.getAttribute("data-testid") ?? el.getAttribute("aria-label") ?? (el.textContent ?? "").trim().slice(0, 40);
      const pos = [...document.querySelectorAll("*")].indexOf(el);
      return { label: label || `${el.tagName}[${input.type ?? ""}]`, ring, detail: `${cs.outlineWidth} ${cs.outlineStyle} ${cs.outlineColor}`, pos };
    });
    if (!s) continue; // left the document (browser chrome); the next Tab re-enters at the top
    if (stops.some((x) => x.pos === s.pos)) break;
    stops.push(s);
  }
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  return stops.sort((a, b) => a.pos - b.pos);
}

stateTests(async (state, page) => {
  await settle(page);
  const res = await new AxeBuilder({ page }).analyze();
  const bad = res.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${state}: ${v.id} @ ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(bad).toEqual([]);
  expect(await page.getAttribute("html", "lang")).toBe("th");

  const stops = await traverse(page);
  expect(stops.filter((s) => !s.ring).map((s) => `${state}: ${s.label} (${s.detail})`)).toEqual([]);

  const idx = (l: string) => stops.findIndex((s) => s.label === l);
  if (state === "recording") {
    // §4 order: … transcript → record → finish.
    expect(idx("transcript")).toBeGreaterThanOrEqual(0);
    expect(idx("transcript")).toBeLessThan(idx("rec-button"));
    expect(idx("rec-button")).toBeLessThan(idx("จบการบันทึก"));
  }
  if (state === "review-ready") {
    // §4 order: … items → submit (the submit is the last stop in the list).
    const submit = idx("ยืนยันและส่งเข้าเคส");
    expect(submit).toBeGreaterThan(0);
    expect(stops.slice(0, submit).some((s) => s.label.startsWith("เปลี่ยน"))).toBe(true);
  }
  if (state === "redflag") {
    expect(await page.evaluate(() => document.querySelector("[role=alert] h2") !== null)).toBe(true);
  }
});
