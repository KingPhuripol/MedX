/** §3.2 prompt-slot priority, colour role, aria-live, question source, extraction-unavailable fallback. */
import { act, fireEvent, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { COPY } from "@/lib/copy";

import { fact, QUESTIONS, turnResponse } from "./fixtures/scenario";
import { renderRecording, tick } from "./helpers";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-30T10:30:00+07:00"));
});

const slot = () => screen.getByTestId("slot");
const css = readFileSync(resolve(__dirname, "../app/mobile.css"), "utf8");
const rule = (sel: string) => css.match(new RegExp(`${sel.replace(".", "\\.")}\\s*\\{([^}]*)\\}`))?.[1] ?? "";

async function listening(r: Awaited<ReturnType<typeof renderRecording>>) {
  fireEvent.click(screen.getByTestId("rec-button"));
  await tick();
  expect(screen.getByTestId("rec-button")).toHaveAttribute("data-state", "listening");
}

const ALL = { chief_complaint: "KNOWN", onset_duration: "KNOWN", severity: "KNOWN", allergy_status: "UNKNOWN", current_medications: "REFUSED", relevant_history: "KNOWN" } as const;

describe("prompt slot", () => {
  it("colour roles map to the tokens of §1.2", () => {
    expect(rule(".slot--ask")).toContain("var(--primary-deep)");
    expect(rule(".slot--idle")).toContain("var(--nav)");
    expect(rule(".slot--done")).toContain("var(--success)");
    expect(rule(".alarm")).toContain("var(--critical)");
  });

  it("idle: neutral slot with the first suggested question and the idle note; aria-live polite", async () => {
    await renderRecording();
    expect(slot()).toHaveAttribute("data-slot", "neutral");
    expect(slot()).toHaveClass("slot--idle");
    expect(slot()).toHaveAttribute("aria-live", "polite");
    expect(slot()).toHaveTextContent(QUESTIONS["ask.chief_complaint"]);
    expect(slot()).toHaveTextContent(COPY.rec.noteIdle);
  });

  it("listening: navy slot with suggested_question_th and the field note; the asked row reads กำลังถาม", async () => {
    const r = await renderRecording();
    await listening(r);
    expect(slot()).toHaveClass("slot--ask");
    expect(slot()).toHaveTextContent(QUESTIONS["ask.chief_complaint"]);
    expect(slot()).toHaveTextContent(COPY.rec.noteListening("อาการสำคัญ"));
    expect(document.querySelector('[data-field="chief_complaint"]')).toHaveAttribute("data-status", "asking");
  });

  it("paused and other states: the same question on the neutral slot with the state note", async () => {
    const r = await renderRecording();
    await listening(r);
    fireEvent.click(screen.getByTestId("rec-button"));
    await tick();
    expect(slot()).toHaveClass("slot--idle");
    expect(slot()).toHaveTextContent(QUESTIONS["ask.chief_complaint"]);
    expect(slot()).toHaveTextContent(COPY.rec.notePaused);
  });

  it("question text comes only from suggested_question_th (a server-sent value is rendered verbatim, nothing else)", async () => {
    const r = await renderRecording();
    await listening(r);
    const resp = turnResponse({ turnId: "vt_1", text: "x", known: {} }) as Record<string, unknown> & { next_action: object };
    resp.next_action = { ...resp.next_action, suggested_question_th: "คำถามจากรายการที่อนุญาต" };
    r.api.turns.push(resp);
    act(() => r.b.rtc.say("i1", "สวัสดีค่ะ ให้ถามว่าเจ็บไหม"));
    await tick();
    expect(slot()).toHaveTextContent("คำถามจากรายการที่อนุญาต");
    expect(slot()).not.toHaveTextContent("ให้ถามว่าเจ็บไหม");
  });

  it("extraction_unavailable: warning notice, neutral slot keeps the last received question", async () => {
    const r = await renderRecording();
    await listening(r);
    r.api.turns.push(turnResponse({ turnId: "vt_1", text: "x", known: {}, handoff: "extraction_unavailable" }));
    act(() => r.b.rtc.say("i1", "ปวดท้อง"));
    await tick();
    expect(screen.getByText(COPY.rec.extractionUnavailable.head)).toBeInTheDocument();
    expect(slot()).toHaveClass("slot--idle");
    expect(slot()).toHaveTextContent(QUESTIONS["ask.chief_complaint"]);
  });

  it("complete: success slot and the finish button becomes the one filled primary; the record button goes quiet", async () => {
    const r = await renderRecording();
    await listening(r);
    r.api.turns.push(turnResponse({ turnId: "vt_1", text: "x", known: ALL, facts: [fact("chief_complaint", "a", "ปวดท้อง", "vt_1")] }));
    act(() => r.b.rtc.say("i1", "ครบแล้ว"));
    await tick();
    expect(slot()).toHaveAttribute("data-slot", "done");
    expect(slot()).toHaveTextContent(COPY.rec.complete.head);
    expect(screen.getByRole("button", { name: COPY.rec.finish })).toHaveClass("btn--primary");
    expect(screen.getByTestId("rec-button")).toHaveClass("rec--quiet");
    expect(document.querySelectorAll(".btn--primary:not([disabled])")).toHaveLength(1);
    expect(screen.queryByText(QUESTIONS["ask.chief_complaint"])).toBeNull();
  });

  it("priority: red flag beats complete (no slot, no question while the alert is open)", async () => {
    const r = await renderRecording();
    await listening(r);
    r.api.turns.push(turnResponse({ turnId: "vt_1", text: "x", known: ALL, nurseAttention: true }));
    act(() => r.b.rtc.say("i1", "เจ็บหน้าอก หายใจไม่ออก"));
    await tick();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByTestId("slot")).toBeNull();
  });
});
