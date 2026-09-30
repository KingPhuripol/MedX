/** Registers the four flows that visit all 11 C2 states, so a11y/touch/motion specs check the same screens. */
import { expect, test } from "@playwright/test";

import { completeFlow, loginState, mainFlow, redFlagFlow, type Visit } from "./flows";

export function stateTests(visit: Visit) {
  test("login", async ({ page }) => loginState(page, visit));
  test("start, idle, recording, paused, reconnecting, error", async ({ page }) => {
    expect((await mainFlow(page, visit)).foreign).toEqual([]);
  });
  test("redflag", async ({ page }) => {
    expect((await redFlagFlow(page, visit)).foreign).toEqual([]);
  });
  test("complete, review, review-ready", async ({ page }) => {
    expect((await completeFlow(page, visit)).foreign).toEqual([]);
  });
}
