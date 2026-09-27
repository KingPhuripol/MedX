import { expect, test } from "@playwright/test";

const API_PORT = process.env.API_PORT || "8000";

test("API health reports mock provider and research prototype", async ({ request }) => {
  const resp = await request.get(`http://127.0.0.1:${API_PORT}/api/health`);
  expect(resp.status()).toBe(200);
  expect(await resp.json()).toEqual({ status: "ok", default_provider: "mock", research_prototype: true });
});

test("web login page serves with the disclaimer", async ({ page }) => {
  const resp = await page.goto("/login");
  expect(resp?.status()).toBe(200);
  await expect(page.getByTestId("research-disclaimer")).toBeVisible();
});
