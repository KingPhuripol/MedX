// @vitest-environment node
/** MedX hospital-blue design contract (docs/UI-SPEC.md, slices/u4/SPEC.md). Pure file/CSS analysis, no network. */
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const WEB = fileURLToPath(new URL("../", import.meta.url));
const THEME = readFileSync(join(WEB, "app", "theme.css"), "utf8");
// Brand name assembled at runtime so this file passes its own brand-name scan.
const BRAND = "SC" + "BX";
const SKIP_DIRS = new Set(["node_modules", ".next", "test-results", "playwright-report"]);

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    if (SKIP_DIRS.has(name)) return [];
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}
const rel = (p: string) => relative(WEB, p).split(sep).join("/");
const ALL_FILES = walk(WEB);
const SOURCE_FILES = ALL_FILES.filter((p) => /\.(css|ts|tsx|mjs)$/.test(p));

function parseTokens(css: string): Record<string, string> {
  const root = css.match(/:root\s*{([^}]*)}/);
  if (!root) throw new Error("theme.css has no :root block");
  return Object.fromEntries([...root[1].matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
}
const TOKENS = parseTokens(THEME);

function resolveHex(name: string): string {
  let value = TOKENS[name];
  for (let i = 0; i < 5 && value?.startsWith("var("); i++) value = TOKENS[value.slice(6, -1)];
  if (!value || !/^#[0-9a-fA-F]{6}$/.test(value)) throw new Error(`token --${name} does not resolve to a hex colour`);
  return value;
}
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
function contrast(fg: string, bg: string): number {
  const [a, b] = [luminance(resolveHex(fg)), luminance(resolveHex(bg))].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

// UI-SPEC palette, written without "#" so this file passes the no-hard-coded-colour scan.
const EXPECTED_TOKENS: Record<string, string> = {
  background: "F5F8FB",
  foreground: "12212F",
  card: "FFFFFF",
  nav: "E7F0F7",
  border: "C9D6E2",
  "muted-foreground": "526577",
  primary: "0B5CAD",
  critical: "B42318",
  warning: "B54708",
  success: "067647",
};

// [use, foreground token, background token, required ratio]
const PAIRS: [string, string, string, number][] = [
  ["body text", "foreground", "background", 4.5],
  ["card text", "foreground", "card", 4.5],
  ["nav text", "foreground", "nav", 4.5],
  ["muted meta text", "muted-foreground", "background", 4.5],
  ["muted meta on card", "muted-foreground", "card", 4.5],
  ["links / active nav", "primary", "background", 4.5],
  ["active nav on card", "primary", "card", 4.5],
  ["primary button label", "card", "primary", 4.5],
  ["primary button hover", "card", "primary-hover", 4.5],
  ["danger button label", "card", "critical", 4.5],
  ["red-flag heading", "critical", "critical-bg", 4.5],
  ["red-flag / error text", "critical-fg", "critical-bg", 4.5],
  ["disclaimer text", "warning-fg", "warning-bg", 4.5],
  ["warning status text", "warning", "card", 4.5],
  ["success status text", "success", "card", 4.5],
  ["focus ring on background (non-text)", "primary", "background", 3],
  ["cover text on darkest stop", "card", "primary-deep", 4.5],
  ["cover text on middle stop", "card", "primary", 4.5],
  ["live: text on call surface", "call-fg", "call-bg", 4.5],
  ["live: muted text on call surface", "call-muted", "call-bg", 4.5],
  ["live: control label on control fill", "call-fg", "call-control", 4.5],
  ["live: end icon on end fill", "card", "call-end", 4.5],
  ["live: start icon on start fill", "card", "orb-mid", 4.5],
  ["live: control border (non-text)", "call-control-border", "call-bg", 3],
  ["live: end fill (non-text)", "call-end", "call-bg", 3],
  ["live: focus ring on call surface (non-text)", "call-focus", "call-bg", 3],
  ["live: focus ring on control fill (non-text)", "call-focus", "call-control", 3],
];

const NAMED_COLOURS =
  "black|white|red|green|blue|yellow|orange|purple|pink|gray|grey|silver|maroon|navy|teal|olive|lime|aqua|fuchsia|brown|gold|indigo|violet|cyan|magenta|beige|crimson|coral|salmon|tomato|khaki|ivory|lavender|tan|turquoise";
const COLOUR_PROPS =
  "color|background|background-color|background-image|border|border-(?:top|right|bottom|left)(?:-color)?|border-color|outline|outline-color|fill|stroke|box-shadow|text-shadow|caret-color|accent-color|text-decoration-color|scrollbar-color|backgroundColor|borderColor|outlineColor";
const NAMED_IN_PROP = new RegExp(
  `(?:^|[\\s{;,"'])(?:${COLOUR_PROPS})\\s*:\\s*["']?[^;}\\n]*?\\b(?:${NAMED_COLOURS})\\b`,
  "i",
);

function colourViolations(path: string, text: string): string[] {
  const out: string[] = [];
  const noVars = text.replace(/var\(--[a-z0-9-]+\)/gi, "var()");
  for (const re of [/#[0-9a-fA-F]{3,8}\b/, /rgba?\(/, /hsla?\(/]) {
    const m = text.match(re);
    if (m) out.push(`${rel(path)}: ${m[0]}`);
  }
  const named = noVars.match(NAMED_IN_PROP);
  if (named) out.push(`${rel(path)}: named colour in "${named[0].trim()}"`);
  return out;
}

describe("MedX hospital-blue theme", () => {
  it("locks the UI-SPEC palette and font token", () => {
    for (const [name, hex] of Object.entries(EXPECTED_TOKENS)) {
      expect(TOKENS[name]?.toUpperCase(), `--${name}`).toBe(`#${hex}`);
    }
    expect(TOKENS.type).toBe('"SCBXBeta2", system-ui, sans-serif');
    // The retired grey/purple palette is gone, not aliased.
    expect(Object.keys(TOKENS).filter((t) => /^(grey|purple|warn)-|^white$/.test(t))).toEqual([]);
    const layout = readFileSync(join(WEB, "app", "layout.tsx"), "utf8");
    const themeAt = layout.indexOf('import "./theme.css"');
    expect(themeAt).toBeGreaterThan(-1);
    expect(layout.indexOf('import "./globals.css"')).toBeGreaterThan(themeAt);
  });

  it("contrast pairs meet WCAG AA", () => {
    const failures = PAIRS.map(([use, fg, bg, min]) => ({ use, ratio: contrast(fg, bg), min })).filter(
      (p) => p.ratio < p.min,
    );
    expect(failures).toEqual([]);
  });

  it("the PWA manifest colours equal the call-bg token", () => {
    const manifest = JSON.parse(readFileSync(join(WEB, "public", "manifest.webmanifest"), "utf8"));
    const want = resolveHex("call-bg").toLowerCase();
    expect(String(manifest.theme_color).toLowerCase()).toBe(want);
    expect(String(manifest.background_color).toLowerCase()).toBe(want);
    expect(manifest.start_url).toBe("/live");
    expect(manifest.icons.map((i: { src: string }) => i.src).every((src: string) => !/logo/i.test(src))).toBe(true);
  });

  it("no hard-coded colours outside theme.css (all web sources, tests included)", () => {
    const scanned = SOURCE_FILES.filter((p) => {
      const r = rel(p);
      return r !== "app/theme.css" && !r.startsWith("public/fonts/") && r !== "package-lock.json";
    });
    expect(scanned.length).toBeGreaterThan(10);
    expect(scanned.flatMap((p) => colourViolations(p, readFileSync(p, "utf8")))).toEqual([]);
    // The scanner itself catches each forbidden form.
    const hash = "#";
    expect(colourViolations("x.css", `a { color: ${hash}fff; }`)).toHaveLength(1);
    expect(colourViolations("x.css", `a { color: ${"rgb"}(0, 0, 0); }`)).toHaveLength(1);
    const [named1, named2] = [
      ["r", "e", "d"],
      ["wh", "ite"],
    ].map((parts) => parts.join(""));
    expect(colourViolations("x.css", `a { border: 1px solid ${named1}; }`)).toHaveLength(1);
    expect(colourViolations("x.tsx", `style={{ color: "${named2}" }}`)).toHaveLength(1);
    expect(colourViolations("x.css", "a { color: var(--foreground); }")).toEqual([]);
  });

  it("every var(--token) used in web sources is defined in theme.css", () => {
    const used = new Set(
      SOURCE_FILES.filter(
        (p) => /\.(css|tsx|ts)$/.test(p) && !rel(p).startsWith("tests/") && !rel(p).startsWith("e2e/"),
      ).flatMap((p) => [...readFileSync(p, "utf8").matchAll(/var\(--([a-z0-9-]+)/g)].map((m) => m[1])),
    );
    expect([...used].filter((t) => !(t in TOKENS))).toEqual([]);
  });

  it("self-hosts SCBXBeta2 400 and 700 with matching sha256", () => {
    const faces = [...THEME.matchAll(/@font-face\s*{([^}]*)}/g)].map((m) => m[1]);
    expect(faces).toHaveLength(2);
    expect(faces.map((f) => f.match(/font-weight:\s*(\d+)/)?.[1]).sort()).toEqual(["400", "700"]);
    for (const face of faces) {
      expect(face).toMatch(/font-family:\s*"SCBXBeta2"/);
      expect(face).toMatch(/font-display:\s*swap/);
      expect(face).toMatch(/src:\s*url\("\/fonts\/SCBXBeta2-(Regular|Bold)\.otf"\)/);
    }
    const hashes: Record<string, string> = {
      "SCBXBeta2-Regular.otf": "1ee2d72857c69bd276a30b14f594396cea00c1680fcd2c9a3a3de1b1b61ff76b",
      "SCBXBeta2-Bold.otf": "6a4d02311aa39d5e7ff8a873b3352e2cc2b293229dfe4b5eeea14d9bc2d5bc12",
    };
    for (const [name, sha] of Object.entries(hashes)) {
      expect(
        createHash("sha256")
          .update(readFileSync(join(WEB, "public", "fonts", name)))
          .digest("hex"),
        name,
      ).toBe(sha);
    }
  });

  it("no remote font URLs or CSS imports", () => {
    const hits: string[] = [];
    for (const p of SOURCE_FILES) {
      const text = readFileSync(p, "utf8");
      if (/next\/font\/google|fonts\.googleapis|fonts\.gstatic/.test(text)) hits.push(rel(p));
      if (p.endsWith(".css") && /url\(\s*["']?(https?:)?\/\//.test(text)) hits.push(`${rel(p)}: remote url()`);
      if (p.endsWith(".css") && /@import/.test(text)) hits.push(`${rel(p)}: @import`);
    }
    expect(hits).toEqual([]);
  });

  it(`no ${BRAND} logo files or references`, () => {
    const logoHashes = new Set([
      "a1312461aa1a28923dc1efea7060b2c16d81d17d8c80e46f7b15b0b1fb5803cb", // logo-black.png
      "dfee5ad8885947df01587ff56bb5da1bfa091e1939655dc595ce46c22919b1d0", // logo-white.png
    ]);
    const files = ALL_FILES.filter((p) => rel(p) !== "package-lock.json");
    expect(files.filter((p) => /logo/i.test(rel(p)))).toEqual([]);
    const byHash = files.filter((p) => logoHashes.has(createHash("sha256").update(readFileSync(p)).digest("hex")));
    expect(byHash).toEqual([]);
    // The brand name may appear only inside the font family/filename SCBXBeta2.
    const needle = new RegExp("sc" + "bx(?!beta2)", "i");
    const refs = files
      .filter((p) => !rel(p).startsWith("public/fonts/"))
      .filter((p) => needle.test(readFileSync(p, "utf8")) || needle.test(rel(p)))
      .map(rel);
    expect(refs).toEqual([]);
  });

  it("titles use the MedX template and the wordmark is the MedX text mark", () => {
    const layout = readFileSync(join(WEB, "app", "layout.tsx"), "utf8");
    expect(layout).toContain('const SITE_TITLE = "MedX — AI Clinical Front Door (research prototype)"');
    expect(layout).toContain("template: `%s · ${SITE_TITLE}`");
    expect(layout).toContain("default: SITE_TITLE");
    const stale = SOURCE_FILES.filter((p) => rel(p).startsWith("app/"))
      .flatMap((p) =>
        readFileSync(p, "utf8")
          .split("\n")
          .map((line) => [rel(p), line] as const),
      )
      .filter(([, line]) => line.includes("Clinical Front Door (research prototype)") && !line.includes("MedX"));
    expect(stale).toEqual([]);
    const wordmark = readFileSync(join(WEB, "components", "Wordmark.tsx"), "utf8");
    expect(wordmark).toContain('aria-label="MedX"');
    expect(wordmark).not.toMatch(/<img|<svg|\.png|\.svg/);
  });

  it("keeps the official New York shadcn configuration", () => {
    const config = JSON.parse(readFileSync(join(WEB, "components.json"), "utf8"));
    expect(config.style).toBe("new-york");
    expect(config.rsc).toBe(true);
    expect(config.tailwind.cssVariables).toBe(true);
    expect(config.iconLibrary).toBe("lucide");
  });
});
