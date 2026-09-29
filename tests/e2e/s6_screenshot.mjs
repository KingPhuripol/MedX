// s6 checker: independent browser look at the care review page (alert case + abstained case). Run from web/.
import { chromium } from "@playwright/test";
const out = process.argv[2];
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
const base = "http://127.0.0.1:3106";
await p.goto(base + "/login");
await p.getByLabel("Username").fill("physician1");
await p.getByLabel("Password").fill("physician1-dev-only");
await p.getByRole("button", { name: "Sign in" }).click();
await p.waitForURL(base + "/physician");
const res = {};
for (const [cid, dp, tag] of [["SYNE-0007", "T2", "alert"], ["SYNE-0071", "T1", "abstained"]]) {
  await p.goto(base + "/physician/care");
  await p.getByRole("button", { name: `Assess ${cid} at ${dp}` }).click();
  await p.waitForURL(/\/physician\/care\/[0-9a-f]{32}$/);
  await p.getByRole("heading", { level: 1 }).waitFor();
  await p.screenshot({ path: `${out}/care_${tag}_${cid}_${dp}.png`, fullPage: true });
  const txt = await p.locator("main").innerText();
  res[tag] = { url: p.url(), first600: txt.slice(0, 600),
    confirmDisabled: (await p.getByRole("button", { name: "Confirm suggestion" }).count())
      ? await p.getByRole("button", { name: "Confirm suggestion" }).isDisabled() : "absent" };
}
console.log(JSON.stringify(res, null, 1));
await b.close();
