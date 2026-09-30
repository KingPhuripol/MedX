/** Static guards: standalone project (C12), no vendor SDK or secrets (C10), never-speak (C8), claim boundary (C14). */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { BANNED_WORDS, COPY, PROPOSED_V2C } from "@/lib/copy";

import { leaves, read, rel, ROOT, walk } from "./files";

const SRC = walk(ROOT, [".ts", ".tsx", ".mjs", ".css", ".js", ".json", ".webmanifest"]).filter((f) => !rel(f).startsWith("tests/") && !rel(f).startsWith("e2e/") && rel(f) !== "package-lock.json");
const UI = SRC.filter((f) => /^(app|components|lib|public)\//.test(rel(f)));
const grep = (files: string[], re: RegExp) => files.flatMap((f) => (re.test(readFileSync(f, "utf8")) ? [rel(f)] : []));

describe("standalone project (C12)", () => {
  it("has no imports or path aliases into ../web", () => {
    const all = walk(ROOT, [".ts", ".tsx", ".mjs"]);
    expect(grep(all, /from\s+["'][^"']*\.\.\/web/)).toEqual([]);
    expect(grep(all, /import\(["'][^"']*\.\.\/web/)).toEqual([]);
    const paths = JSON.parse(read("tsconfig.json")).compilerOptions.paths ?? {};
    expect(JSON.stringify(paths)).not.toContain("web");
  });

  it("uses only SCBXBeta2 via theme.css: no next/font, no Google Fonts, no other font-family", () => {
    expect(grep(SRC, /next\/font|fonts\.googleapis|fonts\.gstatic/)).toEqual([]);
    const families = SRC.filter((f) => rel(f) !== "app/theme.css").flatMap((f) =>
      [...readFileSync(f, "utf8").matchAll(/font-family\s*:\s*([^;]+)/g)].map((m) => `${rel(f)}: ${m[1].trim()}`),
    );
    expect(families).toEqual(["app/mobile.css: var(--type)"]);
    expect(grep(SRC, /fontFamily/)).toEqual([]);
  });

  it("names no other brand in UI files (only the synced SCBXBeta2 font face)", () => {
    const hits = UI.filter((f) => rel(f) !== "app/theme.css").flatMap((f) =>
      [...readFileSync(f, "utf8").matchAll(/scbx(?!beta2)/gi)].map(() => rel(f)),
    );
    expect(hits).toEqual([]);
  });
});

describe("no vendor SDK or secrets (C10 static part)", () => {
  it("package.json and the lockfile carry no livekit, openai or other speech/LLM SDK", () => {
    const pkg = read("package.json") + read("package-lock.json");
    for (const bad of ["livekit", "openai", "@anthropic-ai", "@google/generative-ai", "deepgram", "assemblyai", "microsoft-cognitiveservices-speech"]) {
      expect(pkg.toLowerCase()).not.toContain(bad);
    }
  });

  it("has no vendor host or name in app, components, lib or public", () => {
    expect(grep(UI.filter((f) => !f.endsWith(".otf") && !f.endsWith(".png")), /api\.openai\.com|openai/i)).toEqual([]);
  });

  it("has no key-shaped strings or env reads of server secrets", () => {
    expect(grep(SRC.filter((f) => rel(f) !== "scripts/scan-bundle.mjs"), /\bsk-[A-Za-z0-9_-]{10,}|OPENAI_API_KEY|VOICE_ACCESS_CODE/)).toEqual([]);
    const envs = [...UI, `${ROOT}/next.config.mjs`].flatMap((f) => [...readFileSync(f, "utf8").matchAll(/process\.env\.(\w+)/g)].map((m) => m[1]));
    expect(new Set(envs)).toEqual(new Set(["NEXT_PUBLIC_PUBLIC_DEMO", "BACKEND_URL"]));
  });
});

describe("privacy and never-speak (C8, C16 static parts)", () => {
  it("has 0 MediaRecorder references anywhere in mobile/", () => {
    const word = ["Media", "Recorder"].join("");
    expect(grep(walk(ROOT, [".ts", ".tsx", ".mjs", ".js"]).filter((f) => !f.endsWith("static.test.ts")), new RegExp(word))).toEqual([]);
  });

  it("speaking client events appear only in the deny-list/tests, never in product code", () => {
    expect(grep(UI, /response\.create|conversation\.item\.create|session\.update/)).toEqual([]);
  });

  it("creates no <audio>/<video> element and uses no browser storage API in product code", () => {
    expect(grep(UI, /createElement\(["'](audio|video)|<audio|<video/)).toEqual([]);
    expect(grep(UI, /localStorage|sessionStorage|indexedDB|caches\.|document\.cookie/)).toEqual([]);
  });

  it("does not log transcript text (no console calls in product code)", () => {
    expect(grep(UI.filter((f) => !f.endsWith("sw.js")), /console\./)).toEqual([]);
  });
});

describe("claim boundary (C14 static part)", () => {
  const strings = [...leaves(COPY), ...leaves(PROPOSED_V2C)].map(([, v]) => v);
  const components = walk(`${ROOT}/components`, [".tsx"]).map((f) => readFileSync(f, "utf8"));
  const literals = components.flatMap((src) => [
    ...[...src.matchAll(/>([^<>{}]*[฀-๿A-Za-z][^<>{}]*)</g)].map((m) => m[1]),
    ...[...src.matchAll(/aria-label="([^"]+)"/g)].map((m) => m[1]),
  ]);

  it.each(BANNED_WORDS.map((w) => [w]))("no UI string contains %s", (w) => {
    const re = /^[A-Za-z-]+$/.test(w) ? new RegExp(`\\b${w}\\b`) : new RegExp(w);
    expect([...strings, ...literals].filter((s) => re.test(s))).toEqual([]);
  });

  it("no em dash in UI strings", () => {
    expect(strings.filter((s) => s.includes("—"))).toEqual([]);
  });
});
