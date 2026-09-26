import { expect, test } from "@playwright/test";

import { login, ROLES } from "./helpers";

for (const role of ROLES) {
  test(`${role} logs in, lands on own home, and is 403 on others`, async ({ page }) => {
    await login(page, role);
    await expect(page).toHaveURL(`/${role}`);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(new RegExp(role, "i"));
    await expect(page.getByText(/features arrive in later slices/)).toBeVisible();

    for (const other of ROLES.filter((r) => r !== role)) {
      await page.goto(`/${other}`);
      await expect(page.getByTestId("forbidden")).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).toContainText("403");
    }
  });
}

for (const role of ROLES) {
  test(`unauthenticated visit to /${role} redirects to /login`, async ({ page }) => {
    await page.goto(`/${role}`);
    await expect(page).toHaveURL("/login");
  });
}

test("bad credentials show an error and stay on /login", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("nurse1");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator("#login-error")).toHaveText("Invalid username or password.");
  await expect(page.locator("#login-error")).toHaveAttribute("role", "alert");
  await expect(page).toHaveURL("/login");
});
