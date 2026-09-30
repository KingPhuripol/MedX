/** V2C-C9: one case per T7 row. Every failure has a visible state and a recovery; captured data stays. */
import { act, fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { COPY, PROPOSED_V2C } from "@/lib/copy";

import config from "./fixtures/realtime-config.json";
import mintBody from "./fixtures/realtime-session.json";
import { fact, turnResponse } from "./fixtures/scenario";
import { renderRecording, tick } from "./helpers";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-30T10:30:00+07:00"));
});

const recBtn = () => screen.getByTestId("rec-button");
const state = () => recBtn().getAttribute("data-state");
const mints = (api: { calls: { url: string }[] }) => api.calls.filter((c) => c.url === "/api/voice/realtime/session").length;
const finishBtn = () => screen.getByRole("button", { name: COPY.rec.finish });

/** Start listening and capture one fact, so every error can prove captured data is still shown. */
async function capture(r: Awaited<ReturnType<typeof renderRecording>>) {
  r.api.turns.push(
    turnResponse({ turnId: "vt_1", text: "ปวดท้องค่ะ", facts: [fact("chief_complaint", "abdominal_pain", "ปวดท้องใต้ลิ้นปี่", "vt_1")], known: { chief_complaint: "KNOWN" } }),
  );
  fireEvent.click(recBtn());
  await tick();
  expect(state()).toBe("listening");
  act(() => r.b.rtc.say("i1", "ปวดท้องค่ะ"));
  await tick();
  expect(screen.getByText("ปวดท้องใต้ลิ้นปี่")).toBeInTheDocument();
}

const stillShown = () => {
  expect(screen.getByText("ปวดท้องใต้ลิ้นปี่")).toBeInTheDocument();
  expect(screen.getByText(COPY.rec.factsCount(1))).toBeInTheDocument();
};

describe("T7 error mapping", () => {
  it.each(["NotAllowedError", "SecurityError"])("mic %s → permission_denied notice + ขอสิทธิ์อีกครั้ง", async (name) => {
    const r = await renderRecording({ gumError: name });
    fireEvent.click(recBtn());
    await tick();
    expect(state()).toBe("permission_denied");
    expect(screen.getByText(COPY.rec.permissionDenied.head)).toBeInTheDocument();
    expect(recBtn()).toHaveAccessibleName(COPY.rec.button.askAgain);
    expect(mints(r.api)).toBe(0);
    await tick(10_000);
    expect(r.b.gum).toHaveBeenCalledTimes(1); // no auto-retry
    fireEvent.click(recBtn());
    await tick();
    expect(r.b.gum).toHaveBeenCalledTimes(2);
  });

  it.each(["NotFoundError", "NotReadableError"])("mic %s → error + No microphone notice", async (name) => {
    await renderRecording({ gumError: name });
    fireEvent.click(recBtn());
    await tick();
    expect(state()).toBe("error");
    expect(screen.getByText(COPY.rec.noMic.head)).toBeInTheDocument();
    expect(recBtn()).toHaveAccessibleName(COPY.rec.ariaRetry);
  });

  it.each([
    ["config enabled:false", { ...config, enabled: false, reason: "not_configured" }, null],
    ["config ambient_supported:false", { ...config, ambient_supported: false }, null],
    ["mint 503", config, 503],
  ] as const)("%s → voice-unavailable notice, no auto-retry", async (_n, cfg, mintStatus) => {
    const r = await renderRecording({ init: { config: cfg as never } });
    if (mintStatus) r.api.mint.push({ status: mintStatus, body: { detail: { reason: "not_configured" } } });
    fireEvent.click(recBtn());
    await tick();
    expect(state()).toBe("error");
    expect(screen.getByText(PROPOSED_V2C.voiceUnavailable.head)).toBeInTheDocument();
    const n = mints(r.api);
    await tick(20_000);
    expect(mints(r.api)).toBe(n);
    expect(state()).toBe("error");
  });

  it("mint 403 access_code_invalid → access-code notice; ลองอีกครั้ง returns to start for the field", async () => {
    const r = await renderRecording();
    r.api.mint.push({ status: 403, body: { detail: { reason: "access_code_invalid" } } });
    fireEvent.click(recBtn());
    await tick();
    expect(state()).toBe("error");
    expect(screen.getByText(PROPOSED_V2C.accessCodeInvalid.head)).toBeInTheDocument();
    await tick(10_000);
    expect(mints(r.api)).toBe(1);
    fireEvent.click(recBtn());
    expect(r.onBackToStart).toHaveBeenCalledWith("access_code");
  });

  it.each([409, 404])("mint %s → session-ended notice; จบการบันทึก reaches review; captured data stays", async (status) => {
    const r = await renderRecording();
    await capture(r);
    r.api.mint.push({ status, body: { detail: "voice session is not active" } });
    act(() => r.b.rtc.drop());
    await tick(1000);
    expect(state()).toBe("error");
    expect(screen.getByText(PROPOSED_V2C.sessionEnded.head)).toBeInTheDocument();
    stillShown();
    expect(finishBtn()).toBeEnabled();
    fireEvent.click(finishBtn());
    await tick(6000);
    expect(r.onFinished).toHaveBeenCalled();
  });

  it.each([
    ["mint 502", { status: 502 }],
    ["mint 504", { status: 504 }],
    ["mint 429", { status: 429 }],
  ] as const)("%s → reconnecting (ครั้งที่ n จาก 3) then success returns to listening", async (_n, m) => {
    const r = await renderRecording();
    await capture(r);
    r.api.mint.push({ ...m, body: {} });
    act(() => r.b.rtc.drop());
    await tick();
    expect(state()).toBe("reconnecting");
    expect(screen.getByText(COPY.rec.reconnecting(1).head)).toBeInTheDocument();
    stillShown();
    await tick(1000);
    expect(screen.getByText(COPY.rec.reconnecting(2).head)).toBeInTheDocument();
    await tick(2000);
    expect(state()).toBe("listening");
  });

  it("network error, SDP non-2xx and disconnect ×3 → error with the 3-attempts copy; ลองอีกครั้ง reconnects", async () => {
    const r = await renderRecording();
    await capture(r);
    let sdpCalls = 0;
    r.api.on["/v1/realtime/calls"] = () => (++sdpCalls === 1 ? { status: 500, body: {} } : "network");
    r.api.on["/api/voice/realtime/session"] = () => (sdpCalls < 2 ? { status: 200, body: mintBody } : "network");
    act(() => r.b.rtc.drop());
    await tick();
    expect(screen.getByText(COPY.rec.reconnecting(1).head)).toBeInTheDocument();
    await tick(1000 + 2000 + 4000);
    expect(state()).toBe("error");
    const notice = screen.getByText(COPY.rec.error(1).head).closest(".notice") as HTMLElement;
    expect(within(notice).getByText(COPY.rec.error(1).body)).toBeInTheDocument();
    stillShown();
    delete r.api.on["/v1/realtime/calls"];
    delete r.api.on["/api/voice/realtime/session"];
    fireEvent.click(recBtn());
    await tick();
    expect(state()).toBe("listening");
  });
});
