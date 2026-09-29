// @vitest-environment node
/** Global U1-U3 hospital-blue design-contract checks. Pure file/CSS analysis. */
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const WEB=fileURLToPath(new URL("../",import.meta.url));
const THEME=readFileSync(join(WEB,"app","theme.css"),"utf8");
const SKIP=new Set(["node_modules",".next","test-results","playwright-report"]);
function walk(dir:string):string[]{return readdirSync(dir).flatMap(name=>{if(SKIP.has(name))return [];const full=join(dir,name);return statSync(full).isDirectory()?walk(full):[full]})}
const rel=(p:string)=>relative(WEB,p).split(sep).join("/");
const sources=walk(WEB).filter(p=>/\.(css|ts|tsx|mjs)$/.test(p));
function tokens(css:string){const root=css.match(/:root\s*{([^}]*)}/);if(!root)throw new Error("missing root");return Object.fromEntries([...root[1].matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)].map(m=>[m[1],m[2].trim()]))}
const T=tokens(THEME);
function hex(name:string){let v=T[name];for(let i=0;i<5&&v?.startsWith("var(");i++)v=T[v.slice(6,-1)];if(!/^#[0-9a-f]{6}$/i.test(v||""))throw new Error(`bad token ${name}`);return v}
function lum(v:string){const c=[1,3,5].map(i=>parseInt(v.slice(i,i+2),16)/255).map(x=>x<=.03928?x/12.92:((x+.055)/1.055)**2.4);return .2126*c[0]+.7152*c[1]+.0722*c[2]}
function contrast(a:string,b:string){const values=[lum(hex(a)),lum(hex(b))].sort((x,y)=>y-x);return(values[0]+.05)/(values[1]+.05)}

describe("MedX hospital-blue theme",()=>{
 it("locks the UI-SPEC palette",()=>{
  expect(T.background.toUpperCase()).toBe("#F5F8FB");expect(T.card.toUpperCase()).toBe("#FFFFFF");expect(T.nav.toUpperCase()).toBe("#E7F0F7");expect(T.primary.toUpperCase()).toBe("#0B5CAD");expect(T.critical.toUpperCase()).toBe("#B42318");expect(T.warning.toUpperCase()).toBe("#B54708");expect(T.success.toUpperCase()).toBe("#067647");expect(T.type).toBe('"SCBXBeta2",system-ui,sans-serif');
 });
 it("keeps core text and controls at AA contrast",()=>{
  expect(contrast("foreground","background")).toBeGreaterThanOrEqual(4.5);expect(contrast("card","primary")).toBeGreaterThanOrEqual(4.5);expect(contrast("critical-fg","critical-bg")).toBeGreaterThanOrEqual(4.5);expect(contrast("warning-fg","warning-bg")).toBeGreaterThanOrEqual(4.5);
 });
 it("defines colours only in theme.css",()=>{
  const files=sources.filter(p=>rel(p)!=="app/theme.css"&&!rel(p).startsWith("tests/")&&!rel(p).startsWith("e2e/")&&rel(p)!=="package-lock.json");
  const violations=files.flatMap(p=>{const text=readFileSync(p,"utf8");return /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i.test(text)?[rel(p)]:[]});expect(violations).toEqual([]);
 });
 it("self-hosts only contract font weights 400 and 700",()=>{
  const faces=[...THEME.matchAll(/@font-face\s*{([^}]*)}/g)].map(m=>m[1]);expect(faces).toHaveLength(2);expect(faces.map(f=>f.match(/font-weight:(\d+)/)?.[1]).sort()).toEqual(["400","700"]);
  const hashes:Record<string,string>={"SCBXBeta2-Regular.otf":"1ee2d72857c69bd276a30b14f594396cea00c1680fcd2c9a3a3de1b1b61ff76b","SCBXBeta2-Bold.otf":"6a4d02311aa39d5e7ff8a873b3352e2cc2b293229dfe4b5eeea14d9bc2d5bc12"};for(const[name,sha]of Object.entries(hashes))expect(createHash("sha256").update(readFileSync(join(WEB,"public","fonts",name))).digest("hex")).toBe(sha);
 });
 it("initializes official New York shadcn configuration",()=>{const config=JSON.parse(readFileSync(join(WEB,"components.json"),"utf8"));expect(config.style).toBe("new-york");expect(config.rsc).toBe(true);expect(config.tailwind.cssVariables).toBe(true);expect(config.iconLibrary).toBe("lucide")});
});
