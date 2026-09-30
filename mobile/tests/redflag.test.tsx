/** V2C-C5: the red flag cannot be missed, cannot be downgraded, and blocks finish until acknowledged. */
import { act, fireEvent, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { COPY, PROPOSED_V2C } from "@/lib/copy";

import { fact, QUESTIONS, turnResponse } from "./fixtures/scenario";
import { renderRecording, tick } from "./helpers";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-30T10:06:34+07:00"));
});

const FLAG = "แน่นหน้าอก หายใจไม่ค่อยออก เหงื่อออก";

async function flagged() {
  const r = await renderRecording();
  fireEvent.click(screen.getByTestId("rec-button"));
  await tick();
  r.api.turns.push(
    turnResponse({ turnId: "vt_1", text: "เจ็บแน่นหน้าอกค่ะ", facts: [fact("chief_complaint", "chest_pain", "เจ็บแน่นหน้าอก", "vt_1")], known: { chief_complaint: "KNOWN" } }),
    turnResponse({ turnId: "vt_2", text: FLAG, known: { chief_complaint: "KNOWN" }, nurseAttention: true }),
  );
  act(() => r.b.rtc.say("i1", "เจ็บแน่นหน้าอกค่ะ"));
  await tick();
  act(() => r.b.rtc.say("i2", FLAG));
  await tick();
  return r;
}

describe("red flag (C5)", () => {
  it("shows role=alert with the triangle icon and heading, and focuses the heading", async () => {
    await flagged();
    const alert = screen.getByRole("alert");
    expect(alert.querySelector('svg[data-icon="triangle-alert"]')).not.toBeNull();
    const h = within(alert).getByRole("heading", { name: COPY.rec.redFlag.heading });
    expect(document.activeElement).toBe(h);
    expect(within(alert).getByTestId("red-flag-quote")).toHaveTextContent(FLAG);
  });

  it("hides every transcript line (final and partial) outside the quoted words, and suppresses the slot and question", async () => {
    const r = await flagged();
    act(() => r.b.rtc.emit({ type: "conversation.item.input_audio_transcription.delta", item_id: "i3", delta: "ส่วนที่กำลังพูด" }));
    await tick();
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("เจ็บแน่นหน้าอกค่ะ");
    expect(text).not.toContain("ส่วนที่กำลังพูด");
    expect(text.split(FLAG).length - 1).toBe(1);
    expect(screen.queryByTestId("slot")).toBeNull();
    expect(screen.queryByTestId("transcript")).toBeNull();
    for (const q of Object.values(QUESTIONS)) expect(text).not.toContain(q);
  });

  it("recording continues unchanged and says ยังบันทึกอยู่; pause still works", async () => {
    await flagged();
    expect(screen.getByTestId("rec-button")).toHaveAttribute("data-state", "listening");
    expect(screen.getByRole("alert")).toHaveTextContent(COPY.rec.redFlag.stillRecording);
    fireEvent.click(screen.getByTestId("rec-button"));
    await tick();
    expect(screen.getByTestId("rec-button")).toHaveAttribute("data-state", "paused");
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("จบการบันทึก does not finish: focuses the alert and shows the block copy", async () => {
    const r = await flagged();
    (document.activeElement as HTMLElement).blur();
    fireEvent.click(screen.getByRole("button", { name: COPY.rec.finish }));
    await tick(6000);
    expect(r.onFinished).not.toHaveBeenCalled();
    expect(screen.getByText(COPY.rec.finishBlocked)).toBeInTheDocument();
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: COPY.rec.redFlag.heading }));
    expect(screen.getByTestId("rec-button")).toHaveAttribute("data-state", "listening");
  });

  it("after รับทราบ: the acknowledged strip stays, hidden lines return, the slot stays paused for questions", async () => {
    const r = await flagged();
    act(() => r.b.rtc.say("i3", "เริ่มเป็นตอนเช้า"));
    await tick();
    expect(document.body.textContent).not.toContain("เริ่มเป็นตอนเช้า");
    fireEvent.click(screen.getByRole("button", { name: COPY.rec.redFlag.ack }));
    await tick();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByTestId("ack-strip")).toHaveTextContent(COPY.rec.ackStrip("10:06"));
    const transcript = screen.getByTestId("transcript");
    expect(transcript).toHaveTextContent("เริ่มเป็นตอนเช้า");
    expect(transcript).toHaveTextContent(FLAG);
    expect(transcript.querySelector(".line--flag")).toHaveTextContent(FLAG);
    expect(screen.getByTestId("slot")).toHaveTextContent(PROPOSED_V2C.slotAfterAck.head);
    for (const q of Object.values(QUESTIONS)) expect(document.body.textContent).not.toContain(q); // server sent prompt_nurse; still suppressed
    expect(document.querySelector('[data-status="asking"]')).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: COPY.rec.finish }));
    await tick(6000);
    expect(r.onFinished).toHaveBeenCalled();
  });

  it("is never downgraded by a later response without nurse_attention", async () => {
    const r = await flagged();
    r.api.turns.push(turnResponse({ turnId: "vt_3", text: "x", known: { chief_complaint: "KNOWN" } }));
    act(() => r.b.rtc.say("i3", "ดีขึ้นแล้วค่ะ"));
    await tick();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(r.rec.getSnapshot().scribe.session.nurse_attention).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: COPY.rec.redFlag.ack }));
    await tick();
    r.api.turns.push(turnResponse({ turnId: "vt_4", text: "y", known: { chief_complaint: "KNOWN" } }));
    act(() => r.b.rtc.say("i4", "ไม่เป็นไรแล้ว"));
    await tick();
    expect(screen.getByTestId("ack-strip")).toBeInTheDocument();
  });

  it("the nurse-attention handoff alone also raises the alert", async () => {
    const r = await renderRecording();
    fireEvent.click(screen.getByTestId("rec-button"));
    await tick();
    const resp = turnResponse({ turnId: "vt_1", text: "x", known: {} }) as Record<string, unknown> & { next_action: object };
    resp.next_action = { ...resp.next_action, kind: "handoff", reason: "nurse_attention_phrase", suggested_question_th: null, suggested_question_id: null, field: null };
    r.api.turns.push(resp);
    act(() => r.b.rtc.say("i1", "หมดสติไปเมื่อเช้า"));
    await tick();
    expect(screen.getByRole("alert")).toHaveTextContent("หมดสติไปเมื่อเช้า");
  });

  it("the alert carries no animation or transition (static CSS; computed style is checked in Playwright)", () => {
    const css = readFileSync(resolve(__dirname, "../app/mobile.css"), "utf8");
    const blocks = [...css.matchAll(/([^{}]*\.(?:alarm|flag-strip)[^{}]*)\{([^}]*)\}/g)];
    expect(blocks.length).toBeGreaterThan(0);
    for (const [, , body] of blocks) {
      for (const [, prop, value] of body.matchAll(/(animation|transition)[\w-]*\s*:\s*([^;]+)/g)) expect([prop, value.trim()]).toEqual([prop, "none"]);
    }
  });
});
