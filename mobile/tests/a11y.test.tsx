/** V2C-C13 unit parts: §4 roles and names, record aria-label per state, lang, limitation label last. */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { recButton } from "@/components/Recording";
import { Review, Submitted } from "@/components/Review";
import { Login } from "@/components/Login";
import { Start } from "@/components/Start";
import { COPY } from "@/lib/copy";
import type { RecState } from "@/lib/recorder";
import type { Scribe } from "@/lib/voice";

import { reviewSession } from "./fixtures/scenario";
import { read } from "./files";
import { installApi, renderRecording, tick } from "./helpers";

const B = COPY.rec.button;
/** §3.1 table: aria-label per record state (states without a quoted aria-label use the visible label). */
const ARIA: Record<RecState, string> = {
  idle: B.start,
  requesting_permission: B.requesting,
  connecting: B.connecting,
  listening: "หยุดบันทึกชั่วคราว",
  paused: B.resume,
  reconnecting: COPY.rec.ariaReconnecting,
  error: "ลองเชื่อมต่ออีกครั้ง",
  permission_denied: B.askAgain,
  finishing: COPY.rec.status.finishing,
};

describe("record button (§3.1)", () => {
  it.each(Object.entries(ARIA))("%s → aria-label %s", (state, aria) => {
    expect(recButton(state as RecState).aria).toBe(aria);
  });

  it.each([
    ["idle", false],
    ["requesting_permission", true],
    ["connecting", true],
    ["listening", false],
    ["paused", false],
    ["reconnecting", true],
    ["error", false],
    ["permission_denied", false],
    ["finishing", true],
  ] as const)("%s disabled=%s", (state, disabled) => {
    expect(recButton(state).disabled).toBe(disabled);
  });
});

describe("recording roles", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-30T10:30:00+07:00"));
  });

  it("status is role=status, slot is aria-live=polite, glyphs are labelled, record has its name", async () => {
    await renderRecording();
    expect(screen.getByTestId("rec-status")).toHaveAttribute("role", "status");
    expect(screen.getByTestId("slot")).toHaveAttribute("aria-live", "polite");
    expect(screen.getAllByRole("img", { name: COPY.rec.glyphMissing })).toHaveLength(6);
    expect(screen.getByRole("button", { name: B.start })).toBe(screen.getByTestId("rec-button"));
  });

  it("the transcript opener is named and opens a labelled dialog", async () => {
    const r = await renderRecording();
    fireEvent.click(screen.getByTestId("rec-button"));
    await tick();
    act(() => r.b.rtc.say("i1", "ปวดท้องค่ะ"));
    await tick();
    expect(screen.getAllByRole("img", { name: COPY.rec.glyphAsking })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: COPY.rec.transcriptOpen }));
    const dlg = screen.getByRole("dialog", { name: COPY.rec.transcriptTitle, hidden: true });
    expect(dlg).toHaveAttribute("open");
    expect(screen.getByRole("button", { name: "ปิด", hidden: true })).toBeInTheDocument();
  });

  it("transcript lines carry no speaker label", async () => {
    const r = await renderRecording();
    fireEvent.click(screen.getByTestId("rec-button"));
    await tick();
    act(() => r.b.rtc.say("i1", "ปวดท้องค่ะ"));
    await tick();
    expect(screen.getByTestId("transcript").textContent).not.toMatch(/พยาบาล|ผู้ป่วย:|nurse|patient/i);
  });

  it("the dock ends with the limitation label", async () => {
    await renderRecording();
    const all = [...document.querySelectorAll("main *")].filter((e) => e.children.length === 0 && e.textContent?.trim());
    expect(all[all.length - 1]).toHaveTextContent(COPY.limit);
  });
});

describe("other screens", () => {
  const lastText = () => {
    const all = [...document.querySelectorAll("main *")].filter((e) => e.children.length === 0 && e.textContent?.trim());
    return all[all.length - 1];
  };

  it("login: labelled fields, limitation last", () => {
    installApi();
    render(<Login onUser={vi.fn()} publicDemo={false} />);
    expect(screen.getByLabelText(COPY.login.username)).toHaveAttribute("autocomplete", "username");
    expect(lastText()).toHaveTextContent(COPY.limit);
  });

  it("start: radiogroup, real checkbox, labelled search, limitation last", async () => {
    render(<Start username="nurse1" accessCodeRequired={false} onSignOut={vi.fn()} onOpen={vi.fn()} />);
    expect(await screen.findByRole("radiogroup")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: COPY.start.consent })).toHaveProperty("type", "checkbox");
    expect(screen.getByRole("textbox", { name: COPY.start.searchLabel })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: COPY.start.account("nurse1") })).toBeInTheDocument();
    expect(lastText()).toHaveTextContent(COPY.limit);
  });

  it("review and submitted: limitation last", () => {
    installApi();
    const { unmount } = render(
      <Review patient={{ id: "SYN-1" }} scribe={reviewSession() as unknown as Scribe} durationMs={0} redFlag={null} ackAtMs={null} consentAtMs={0} onContinue={vi.fn()} onSubmitted={vi.fn()} onAuthLost={vi.fn()} />,
    );
    expect(lastText()).toHaveTextContent(COPY.limit);
    unmount();
    render(<Submitted patientId="SYN-1" onNext={vi.fn()} />);
    expect(lastText()).toHaveTextContent(COPY.limit);
  });

  it('the document is lang="th"', () => {
    expect(read("app/layout.tsx")).toMatch(/<html lang="th">/);
  });

  it("focus ring: 2px --primary with 2px offset on every control (CSS)", () => {
    const css = read("app/mobile.css");
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--primary\)[^}]*outline-offset:\s*2px/);
  });
});
