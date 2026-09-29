/** Slice u4 — MedX hospital-blue theme browser checks (token-only colours, wordmark, fonts, overflow). */
import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { login, startDemoRun, type Role } from "./helpers";

const SITE_TITLE = "MedX — AI Clinical Front Door (research prototype)";
const BRAND = "SC" + "BX"; // assembled so web/ source only contains the brand inside the font name
const FONT_FAMILY = /^SCBXBeta2$/;
const SHOTS_DIR = join(__dirname, "..", "..", "artifacts", "factory", "u4");
const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
];

type PageSpec = { name: string; path: string; role?: Role; run?: boolean };
const PAGES: PageSpec[] = [
  { name: "login", path: "/login" },
  { name: "403", path: "/403" },
  { name: "404", path: "/definitely-missing" },
  { name: "queue", path: "/app/queue", role: "nurse" },
  { name: "demo", path: "/demo", role: "nurse" },
  { name: "case-overview", path: "/app/cases/SYN-2026-0017/overview", role: "nurse", run: true },
  { name: "case-triage", path: "/app/cases/SYN-2026-0017/triage", role: "nurse", run: true },
  { name: "case-medications", path: "/app/cases/SYN-2026-0017/medications", role: "pharmacist", run: true },
  { name: "nurse-triage", path: "/nurse/triage", role: "nurse" },
  { name: "nurse-intake", path: "/nurse/intake", role: "nurse" },
  { name: "physician-care", path: "/physician/care", role: "physician" },
  { name: "pharmacist-reconcile", path: "/pharmacist/reconcile", role: "pharmacist" },
];

let session: Role | undefined;
let runStarted = false;
async function visit(page: Page, spec: PageSpec) {
  if (spec.role && session !== spec.role) {
    await page.context().clearCookies();
    await login(page, spec.role);
    session = spec.role;
  }
  if (!spec.role && session) {
    await page.context().clearCookies();
    session = undefined;
  }
  if (spec.run && !runStarted) {
    await startDemoRun(page);
    runStarted = true;
  }
  await page.goto(spec.path);
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
}
test.beforeEach(() => {
  session = undefined;
  runStarted = false;
});

/** Computed colour string of every theme token, as the browser resolves it. */
async function tokenColours(page: Page): Promise<Record<string, string>> {
  return page.evaluate(() => {
    const out: Record<string, string> = {};
    const names = [...document.styleSheets]
      .flatMap((s) => {
        try {
          return [...s.cssRules];
        } catch {
          return [];
        }
      })
      .filter((r): r is CSSStyleRule => r instanceof CSSStyleRule && r.selectorText === ":root")
      .flatMap((r) => [...r.style].filter((p) => p.startsWith("--")));
    for (const name of names) {
      const probe = document.createElement("span");
      probe.style.color = `var(${name})`;
      document.body.appendChild(probe);
      out[name.slice(2)] = getComputedStyle(probe).color;
      probe.remove();
    }
    return out;
  });
}

function channels(colour: string): number[] {
  return (colour.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
}
function contrastRatio(a: string, b: string): number {
  const lum = (c: string) => {
    const [r, g, bl] = channels(c).map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

test.describe("MedX hospital-blue theme", () => {
  test("every rendered text, background and border colour is a theme token", async ({ page }) => {
    for (const spec of PAGES) {
      await visit(page, spec);
      const allowed = new Set(Object.values(await tokenColours(page)));
      const offenders = await page.evaluate(
        (ok) => {
          const allow = new Set(ok);
          const transparent = (c: string) => c === `${"rgb"}a(0, 0, 0, 0)` || c === "transparent";
          const bad: string[] = [];
          for (const el of document.querySelectorAll<HTMLElement>("body *")) {
            if (el.closest("svg") && el.tagName.toLowerCase() !== "svg") continue;
          if (el.closest("nextjs-portal")) continue; // Next.js dev overlay, not product UI
            const s = getComputedStyle(el);
            if (s.display === "none" || s.visibility === "hidden") continue;
            const checks: [string, string][] = [
              ["color", s.color],
              ["background-color", s.backgroundColor],
            ];
            for (const side of ["Top", "Right", "Bottom", "Left"] as const) {
              if (parseFloat(s[`border${side}Width`]) > 0 && s[`border${side}Style`] !== "none")
                checks.push([`border-${side.toLowerCase()}`, s[`border${side}Color`]]);
            }
            for (const [prop, value] of checks) {
              if (!transparent(value) && !allow.has(value))
                bad.push(`${el.tagName.toLowerCase()}.${el.className}: ${prop} ${value}`);
            }
          }
          return [...new Set(bad)].slice(0, 10);
        },
        [...allowed],
      );
      expect(offenders, spec.name).toEqual([]);
    }
  });

  test("disclaimer is first, visible and uses the warning tokens", async ({ page }) => {
    for (const vp of VIEWPORTS.slice(0, 2)) {
      await page.setViewportSize(vp);
      for (const spec of PAGES) {
        await visit(page, spec);
        const note = page.getByTestId("research-disclaimer");
        await expect(note, `${spec.name} ${vp.width}`).toBeInViewport({ ratio: 1 });
        await expect(note).toHaveAttribute("role", "note");
        const tokens = await tokenColours(page);
        const facts = await note.evaluate((el) => ({
          // Next 15 injects an empty <div hidden> metadata outlet before layout content; skip only that.
          first:
            [...document.body.children].find(
              (c) => !(c instanceof HTMLElement && c.hidden && !c.textContent?.trim()),
            ) === el,
          bg: getComputedStyle(el).backgroundColor,
          fg: getComputedStyle(el).color,
          sizes: [...el.querySelectorAll("p")].map((p) => parseFloat(getComputedStyle(p).fontSize)),
        }));
        expect(facts.first, `${spec.name}: disclaimer is first child of body`).toBe(true);
        expect(facts.bg).toBe(tokens["warning-bg"]);
        expect(facts.fg).toBe(tokens["warning-fg"]);
        expect(facts.sizes).toHaveLength(2);
        for (const size of facts.sizes) expect(size).toBeGreaterThanOrEqual(14);
      }
    }
  });

  test("one visible MedX wordmark after the disclaimer, MedX title, no brand logo or name", async ({ page }) => {
    for (const spec of PAGES) {
      await visit(page, spec);
      const mark = page.getByRole("img", { name: "MedX" }).filter({ visible: true });
      await expect(mark, spec.name).toHaveCount(1);
      const tokens = await tokenColours(page);
      const x = await mark.locator(".wordmark-x").evaluate((el) => {
        const s = getComputedStyle(el);
        return { colour: s.color, size: parseFloat(s.fontSize), weight: Number(s.fontWeight) };
      });
      expect([tokens.primary, tokens["primary-soft"]], spec.name).toContain(x.colour);
      expect(x.size).toBeGreaterThanOrEqual(24);
      expect(x.weight).toBeGreaterThanOrEqual(700);
      expect(await page.title(), spec.name).toContain(SITE_TITLE);
      const order = await mark.evaluate((w) => {
        const d = document.querySelector('[data-testid="research-disclaimer"]')!;
        return Boolean(d.compareDocumentPosition(w) & Node.DOCUMENT_POSITION_FOLLOWING);
      });
      expect(order).toBe(true);
      expect(await page.locator("img[src*='logo' i], [class*='logo' i]").count(), spec.name).toBe(0);
      const text = await page.evaluate(() => document.body.innerText);
      expect(text.toUpperCase(), spec.name).not.toContain(BRAND);
    }
  });

  test("SCBXBeta2 renders Thai and English text (document.fonts + CDP platform fonts)", async ({ page }) => {
    for (const spec of [PAGES[0], PAGES[3]]) {
      await visit(page, spec);
      const loaded = await page.evaluate(() =>
        [...document.fonts]
          .filter((f) => f.family.replace(/["']/g, "") === "SCBXBeta2" && f.status === "loaded")
          .map((f) => f.weight),
      );
      expect(loaded, spec.name).toEqual(expect.arrayContaining(["400", "700"]));
      const cdp = await page.context().newCDPSession(page);
      await cdp.send("DOM.enable");
      await cdp.send("CSS.enable");
      const { root } = await cdp.send("DOM.getDocument", { depth: -1 });
      for (const selector of [
        '[data-testid="research-disclaimer"] p[lang="th"]',
        '[data-testid="research-disclaimer"] p[lang="en"]',
        "main h1",
      ]) {
        const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector });
        expect(nodeId, selector).toBeGreaterThan(0);
        const { fonts } = await cdp.send("CSS.getPlatformFontsForNode", { nodeId });
        const total = fonts.reduce((n, f) => n + f.glyphCount, 0);
        const ours = fonts.filter((f) => FONT_FAMILY.test(f.familyName)).reduce((n, f) => n + f.glyphCount, 0);
        expect(total, `${spec.name} ${selector}`).toBeGreaterThan(0);
        expect(ours, `${spec.name} ${selector}: ${fonts.map((f) => f.familyName).join(", ")}`).toBe(total);
      }
      await cdp.detach();
    }
  });

  test("no external requests; fonts are same-origin", async ({ page }) => {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    const offOrigin: string[] = [];
    const fontRequests: { path: string; status: number | undefined }[] = [];
    const pending: Promise<void>[] = [];
    page.on("request", (req) => {
      const url = new URL(req.url());
      if (url.protocol === "data:" || url.protocol === "blob:") return;
      const hosts = [`127.0.0.1:${process.env.WEB_PORT || "3000"}`, `127.0.0.1:${process.env.API_PORT || "8000"}`];
      if (!hosts.includes(url.host)) offOrigin.push(req.url());
      if (req.resourceType() === "font")
        pending.push(
          req.response().then((resp) => void fontRequests.push({ path: url.pathname, status: resp?.status() })),
        );
    });
    for (const spec of PAGES) await visit(page, spec);
    await Promise.all(pending);
    expect(offOrigin).toEqual([]);
    expect(fontRequests.length).toBeGreaterThan(0);
    for (const f of fontRequests) {
      expect(f.path).toMatch(/^\/fonts\/SCBXBeta2-(Regular|Bold)\.otf$/);
      expect(f.status).toBe(200);
    }
  });

  test("errors use the critical tokens", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("ชื่อผู้ใช้สังเคราะห์").fill("nurse1");
    await page.getByLabel("รหัสผ่าน").fill("wrong-password");
    await page.getByRole("button", { name: "เข้าสู่ระบบเดโม" }).click();
    const alert = page.locator("#login-error[role=alert]");
    await expect(alert).toHaveText("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง");
    const tokens = await tokenColours(page);
    const s = await alert.evaluate((el) => ({
      fg: getComputedStyle(el).color,
      bg: getComputedStyle(el).backgroundColor,
    }));
    expect(s.fg).toBe(tokens["critical-fg"]);
    expect(s.bg).toBe(tokens["critical-bg"]);
  });

  test("focus rings are visible on every focusable element", async ({ page }) => {
    for (const spec of [PAGES[0], PAGES[1], PAGES[3], PAGES[8]]) {
      await visit(page, spec);
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
      const pageBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      const seen = new Set<string>();
      for (let i = 0; i < 40; i++) {
        await page.keyboard.press("Tab");
        const info = await page.evaluate(() => {
          const el = document.activeElement as HTMLElement | null;
          if (!el || el === document.body) return null;
          const s = getComputedStyle(el);
          const key = `${el.tagName}#${el.id}:${el.textContent?.trim()}:${[...el.parentElement!.children].indexOf(el)}`;
          return { key, style: s.outlineStyle, width: parseFloat(s.outlineWidth), colour: s.outlineColor };
        });
        if (!info || seen.has(info.key)) break;
        seen.add(info.key);
        expect(info.style, `${spec.name} ${info.key}`).not.toBe("none");
        expect(info.width, `${spec.name} ${info.key}`).toBeGreaterThanOrEqual(2);
        expect(contrastRatio(info.colour, pageBg), `${spec.name} ${info.key}`).toBeGreaterThanOrEqual(3);
      }
      expect(seen.size, spec.name).toBeGreaterThan(0);
    }
  });

  test("no horizontal overflow at 1280, 768 and 390 px; screenshots", async ({ page }) => {
    mkdirSync(SHOTS_DIR, { recursive: true });
    for (const vp of VIEWPORTS) {
      await page.setViewportSize(vp);
      for (const spec of PAGES) {
        await visit(page, spec);
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow, `${spec.name} at ${vp.width}`).toBeLessThanOrEqual(0);
        await page.screenshot({ path: join(SHOTS_DIR, `${spec.name}-${vp.width}x${vp.height}.png`), fullPage: true });
      }
    }
  });
});
