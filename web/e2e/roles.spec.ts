import { expect, test } from "@playwright/test";

import { login, ROLE_PAGES, ROLES } from "./helpers";

for (const role of ROLES) {
  test(`${role} logs in to the work queue, opens own pages, and is 403 on other roles' pages and APIs`, async ({
    page,
  }) => {
    await login(page, role);
    await expect(page).toHaveURL("/app/queue");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    for (const path of ROLE_PAGES[role]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.getByTestId("forbidden")).toHaveCount(0);
    }

    for (const other of ROLES.filter((r) => r !== role)) {
      for (const path of ROLE_PAGES[other]) {
        await page.goto(path);
        await expect(page.getByTestId("forbidden"), path).toBeVisible();
        await expect(page.getByRole("heading", { level: 1 })).toContainText("403");
      }
      const api = await page.request.get(`/api/home/${other}`);
      expect(api.status(), `/api/home/${other}`).toBe(403);
    }
  });
}

for (const path of ["/app/queue", ...Object.values(ROLE_PAGES).flat()]) {
  test(`unauthenticated visit to ${path} redirects to /login`, async ({ page }) => {
    await page.goto(path);
    await expect(page).toHaveURL("/login");
  });
}

test("bad credentials show an error and stay on /login", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("ชื่อผู้ใช้สังเคราะห์").fill("nurse1");
  await page.getByLabel("รหัสผ่าน").fill("wrong-password");
  await page.getByRole("button", { name: "เข้าสู่ระบบเดโม" }).click();
  await expect(page.locator("#login-error")).toHaveText("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง");
  await expect(page.locator("#login-error")).toHaveAttribute("role", "alert");
  await expect(page).toHaveURL("/login");
});
