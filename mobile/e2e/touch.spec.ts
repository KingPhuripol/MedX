/** V2C-C11 touch: every visible control ≥ 44×44, and §1.5 sizes (56/72/48/44/64) in every C2 state. */
import { expect } from "@playwright/test";

import { stateTests } from "./states";

stateTests(async (state, page) => {
  const problems = await page.evaluate((state) => {
    const out: string[] = [];
    const visible = (el: Element) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return r.width > 1 && r.height > 1 && cs.visibility !== "hidden" && cs.display !== "none" && !el.closest("dialog:not([open])");
    };
    const name = (el: Element) => (el.getAttribute("aria-label") ?? el.textContent ?? el.tagName).trim().slice(0, 30);
    const controls = document.querySelectorAll("button, a[href], input:not([type=radio]):not([type=checkbox]), textarea, label.pick, label.consent, label.chip");
    for (const el of controls) {
      if (!visible(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 44 - 0.5 || r.height < 44 - 0.5) out.push(`${state}: ${name(el)} ${r.width.toFixed(1)}x${r.height.toFixed(1)} < 44`);
    }
    const expectH = (sel: string, h: number, w?: number) => {
      for (const el of document.querySelectorAll(sel)) {
        if (!visible(el)) continue;
        const r = el.getBoundingClientRect();
        if (Math.abs(r.height - h) > 0.5 || (w !== undefined && Math.abs(r.width - w) > 0.5)) {
          out.push(`${state}: ${sel} "${name(el)}" ${r.width.toFixed(1)}x${r.height.toFixed(1)} != ${w ?? "*"}x${h}`);
        }
      }
    };
    expectH(".btn--primary:not(.finish)", 56); // primary CTA
    expectH(".alarm .btn", 56); // "รับทราบ"
    expectH(".rec", 72, 72); // record button
    expectH(".finish, .btn:not(.btn--primary):not(.btn--ghost):not(.btn--link):not(.alarm .btn):not(.acts .btn)", 48); // secondary
    expectH(".acts .btn", 44); // review actions
    expectH("label.pick", 64); // patient rows
    return out;
  }, state);
  expect(problems).toEqual([]);
});
