/// <reference types="vite/client" />
import { expect, it } from "vitest";

// DEC-0017: the nurse and platform apps share only src/shared and never import each other.
const sources = import.meta.glob(["./apps/**/*.{ts,tsx}", "./shared/**/*.{ts,tsx}"], { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const importsOf = (source: string) => [...source.matchAll(/from\s+"([^"]+)"/g)].map((match) => match[1]);
const offenders = (prefix: string, forbidden: RegExp) => Object.entries(sources)
  .filter(([file, source]) => file.startsWith(prefix) && importsOf(source).some((path) => forbidden.test(path)))
  .map(([file]) => file);

it("finds the app sources", () => {
  expect(Object.keys(sources).some((file) => file.startsWith("./apps/nurse/"))).toBe(true);
  expect(Object.keys(sources).some((file) => file.startsWith("./apps/platform/"))).toBe(true);
});
it("nurse never imports platform", () => expect(offenders("./apps/nurse/", /platform\//)).toEqual([]));
it("platform never imports nurse", () => expect(offenders("./apps/platform/", /nurse\//)).toEqual([]));
it("shared never imports an app", () => expect(offenders("./shared/", /apps\//)).toEqual([]));
