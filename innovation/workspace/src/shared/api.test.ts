import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, apiCall, clearPendingRequest, hasPendingRequest, retryPendingRequest, sendApi } from "./api";

// The pending-request latch is module state, so each test starts from a known one.
beforeEach(() => clearPendingRequest());
afterEach(() => { vi.unstubAllGlobals(); clearPendingRequest(); });

const ok = (body: unknown = {}) =>
  vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body });
const status = (code: number, body: unknown = { error: "STALE_CASE_REVISION" }) =>
  vi.fn().mockResolvedValue({ ok: false, status: code, json: async () => body });
const offline = () => vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

it("latches a failed mutation so the exact same command can be retried, and blocks the next one", async () => {
  vi.stubGlobal("fetch", offline());
  const body = { idempotency_key: "key-1", summary: "ข้อความที่ยังไม่ถูกบันทึก" };
  await expect(apiCall("/encounters/c1/events", "POST", body)).rejects.toThrow();
  expect(hasPendingRequest()).toBe(true);

  // A second mutation while the first is unresolved would risk a duplicate clinical write.
  await expect(apiCall("/encounters/c1/events", "POST", body)).rejects.toThrow(/คำขอเดิม/);

  // The retry must replay the original body and key, not build a new command.
  const replay = ok({ case_revision: 2 });
  vi.stubGlobal("fetch", replay);
  await expect(retryPendingRequest()).resolves.toEqual({ case_revision: 2 });
  expect(replay.mock.calls[0][0]).toBe("/v2/encounters/c1/events");
  expect(JSON.parse(replay.mock.calls[0][1].body)).toEqual(body);
  expect(hasPendingRequest()).toBe(false);
});

it("does not latch a failed GET, which is safe to repeat", async () => {
  vi.stubGlobal("fetch", offline());
  await expect(apiCall("/encounters/c1/snapshot")).rejects.toThrow();
  expect(hasPendingRequest()).toBe(false);
});

it("does not latch a failed sign-in, which would lock the user out of recovering", async () => {
  vi.stubGlobal("fetch", offline());
  await expect(apiCall("/session", "POST", { token: "t" })).rejects.toThrow();
  expect(hasPendingRequest()).toBe(false);
});

it("lets the user sign in again while a request is still unresolved", async () => {
  vi.stubGlobal("fetch", offline());
  await expect(apiCall("/encounters/c1/events", "POST", {})).rejects.toThrow();
  expect(hasPendingRequest()).toBe(true);

  vi.stubGlobal("fetch", ok({ csrf: "c" }));
  await expect(apiCall("/session", "POST", { token: "t" })).resolves.toEqual({ csrf: "c" });
});

it("latches on 5xx but clears on a rejection the server actually decided", async () => {
  vi.stubGlobal("fetch", status(503, {}));
  await expect(sendApi("/drafts/d/reviews", { method: "POST" })).rejects.toBeInstanceOf(ApiError);
  expect(hasPendingRequest()).toBe(true);

  clearPendingRequest();
  vi.stubGlobal("fetch", status(409, { error: "STALE_CASE_REVISION", details: { current_revision: 7 } }));
  const error: ApiError = await sendApi("/drafts/d/reviews", { method: "POST" })
    .then(() => { throw Error("expected a rejection"); }, (e: ApiError) => e);
  expect(error.code).toBe("STALE_CASE_REVISION");
  expect(error.message).toContain("7");
  expect(hasPendingRequest()).toBe(false);
});
