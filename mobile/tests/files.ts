/** Source-tree helpers for the static checks (node_modules, .next and build output excluded). */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

export const ROOT = resolve(__dirname, "..");
const SKIP = new Set(["node_modules", ".next", "test-results", "playwright-report"]);

export function walk(dir: string, exts: string[]): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p, exts));
    else if (exts.some((e) => name.endsWith(e))) out.push(p);
  }
  return out;
}

export const rel = (p: string) => relative(ROOT, p);
export const read = (p: string) => readFileSync(resolve(ROOT, p), "utf8");

/** Every string leaf of a copy object; functions are skipped (checked with explicit arguments). */
export function leaves(o: unknown, path = ""): [string, string][] {
  if (typeof o === "string") return [[path, o]];
  if (Array.isArray(o)) return o.flatMap((v, i) => leaves(v, `${path}[${i}]`));
  if (o && typeof o === "object") return Object.entries(o).flatMap(([k, v]) => leaves(v, path ? `${path}.${k}` : k));
  return [];
}
