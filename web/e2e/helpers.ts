import { expect, type Page } from "@playwright/test";

export const ROLES = ["nurse", "physician", "pharmacist"] as const;
export type Role = (typeof ROLES)[number];

// Dev-only synthetic accounts; passwords default to the values documented in .env.example.
export const PASSWORDS: Record<Role, string> = {
  nurse: process.env.SEED_NURSE1_PASSWORD || "nurse1-dev-only",
  physician: process.env.SEED_PHYSICIAN1_PASSWORD || "physician1-dev-only",
  pharmacist: process.env.SEED_PHARMACIST1_PASSWORD || "pharmacist1-dev-only",
};

export async function login(page: Page, role: Role) {
  await page.goto("/login");
  await page.getByLabel("ชื่อผู้ใช้สังเคราะห์").fill(`${role}1`);
  await page.getByLabel("รหัสผ่าน").fill(PASSWORDS[role]);
  await page.getByRole("button", { name: "เข้าสู่ระบบเดโม" }).click();
  await expect(page).toHaveURL("/app/queue");
}

export async function startDemoRun(page: Page) {
  await page.goto("/demo");
  await page.getByRole("button", { name: /เริ่มรอบเดโมใหม่/ }).click();
  await expect(page).toHaveURL("/app/queue");
  await expect(page.getByText(/รอบ [a-f0-9]{8}/)).toBeVisible();
}
