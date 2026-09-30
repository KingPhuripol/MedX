/** Review screen (§2.4, T10, V2C-C15): decisions, 6/6 gate, submit outcomes, never a fake success. */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Review } from "@/components/Review";
import { COPY, PROPOSED_V2C } from "@/lib/copy";
import type { Scribe } from "@/lib/voice";

import { reviewSession } from "./fixtures/scenario";
import { installApi } from "./helpers";

const R = COPY.review;
const item = (field: string) => document.querySelector(`.review-list > li[data-field="${field}"]`) as HTMLElement;

function setup(opts: { scribe?: Scribe; review?: number | "network"; finish?: number; ack?: number | null } = {}) {
  const api = installApi({
    on: {
      [`/api/voice/sessions/${reviewSession().session.session_id}/finish`]: () => ({ status: opts.finish ?? 200, body: {} }),
      [`/api/voice/sessions/${reviewSession().session.session_id}/review`]: () =>
        opts.review === "network" ? "network" : { status: opts.review ?? 404, body: {} },
    },
  });
  const props = {
    onContinue: vi.fn(),
    onSubmitted: vi.fn(),
    onAuthLost: vi.fn(),
  };
  render(
    <Review
      patient={{ id: "SYN-2026-0023" }}
      scribe={opts.scribe ?? (reviewSession() as unknown as Scribe)}
      durationMs={372_000}
      redFlag={opts.ack ? { quote: "เจ็บหน้าอก", atMs: opts.ack } : null}
      ackAtMs={opts.ack ?? null}
      consentAtMs={Date.parse("2026-09-30T10:28:00+07:00")}
      {...props}
    />,
  );
  return { api, ...props };
}

const submitBtn = () => screen.getByRole("button", { name: new RegExp(`${R.submit}|${R.retrySubmit}|${R.submitting}`) });
const confirm = (f: string) => fireEvent.click(within(item(f)).getByRole("button", { name: R.confirm }));

function decideAll() {
  confirm("chief_complaint");
  confirm("onset_duration");
  fireEvent.click(within(item("severity")).getByRole("button", { name: R.edit }));
  fireEvent.change(screen.getByLabelText(R.editLabel), { target: { value: "8 จาก 10" } });
  fireEvent.click(screen.getByRole("button", { name: R.saveEdit }));
  fireEvent.click(within(item("allergy_status")).getByRole("button", { name: R.reject }));
  fireEvent.click(within(item("allergy_status")).getByRole("radio", { name: R.rejectReasons[0] }));
  fireEvent.click(within(item("allergy_status")).getByRole("button", { name: R.rejectSave }));
  confirm("current_medications");
  confirm("relevant_history");
}

describe("review decisions", () => {
  it("shows the meta line, the source quote and the 0/6 gate", () => {
    setup();
    expect(screen.getByText(R.meta("SYN-2026-0023", 6, 12))).toBeInTheDocument();
    expect(within(item("severity")).getByText(/น่าจะเจ็ดค่ะ/)).toBeInTheDocument();
    expect(submitBtn()).toBeDisabled();
    expect(screen.getByText(R.progress(0))).toBeInTheDocument();
  });

  it("confirm collapses the row with ยืนยันแล้ว and เปลี่ยน reopens it", () => {
    setup();
    confirm("chief_complaint");
    expect(within(item("chief_complaint")).getByText(R.tag.confirmed)).toBeInTheDocument();
    fireEvent.click(within(item("chief_complaint")).getByRole("button", { name: `${R.change}อาการสำคัญ` }));
    expect(within(item("chief_complaint")).getByRole("button", { name: R.confirm })).toBeInTheDocument();
  });

  it("edit shows ระบบได้ยินว่า: <original>", () => {
    setup();
    fireEvent.click(within(item("severity")).getByRole("button", { name: R.edit }));
    fireEvent.change(screen.getByLabelText(R.editLabel), { target: { value: "8 จาก 10" } });
    fireEvent.click(screen.getByRole("button", { name: R.saveEdit }));
    expect(within(item("severity")).getByText("8 จาก 10")).toBeInTheDocument();
    expect(within(item("severity")).getByText(R.heard("7 จาก 10"))).toBeInTheDocument();
    expect(within(item("severity")).getByText(R.tag.edited)).toBeInTheDocument();
  });

  it("reject needs a reason before it can be saved", () => {
    setup();
    fireEvent.click(within(item("severity")).getByRole("button", { name: R.reject }));
    expect(within(item("severity")).getByRole("button", { name: R.rejectSave })).toBeDisabled();
    fireEvent.click(within(item("severity")).getByRole("radio", { name: R.rejectReasons[1] }));
    fireEvent.click(within(item("severity")).getByRole("button", { name: R.rejectSave }));
    expect(within(item("severity")).getByText(R.tag.rejected)).toBeInTheDocument();
    expect(within(item("severity")).getByText(R.rejectedNote)).toBeInTheDocument();
  });

  it("missing rows offer เพิ่มข้อมูล and ระบุว่าไม่ทราบ", () => {
    const s = reviewSession() as unknown as Scribe;
    s.field_statuses = s.field_statuses.map((f) => (f.field === "relevant_history" ? { ...f, status: "MISSING" } : f));
    setup({ scribe: s });
    const row = item("relevant_history");
    expect(within(row).getByText(R.tag.missing)).toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: R.markUnknown }));
    expect(within(item("relevant_history")).getByText(COPY.rec.valueUnknown)).toBeInTheDocument();
    fireEvent.click(within(item("relevant_history")).getByRole("button", { name: /เปลี่ยน/ }));
    fireEvent.click(within(item("relevant_history")).getByRole("button", { name: R.add }));
    fireEvent.change(screen.getByLabelText(R.editLabel), { target: { value: "เบาหวาน" } });
    fireEvent.click(screen.getByRole("button", { name: R.saveEdit }));
    expect(within(item("relevant_history")).getByText("เบาหวาน")).toBeInTheDocument();
  });

  it("submit is enabled only at 6/6", () => {
    setup();
    confirm("chief_complaint");
    confirm("onset_duration");
    confirm("severity");
    confirm("allergy_status");
    confirm("current_medications");
    expect(submitBtn()).toBeDisabled();
    confirm("relevant_history");
    expect(submitBtn()).toBeEnabled();
    expect(screen.getByText(R.done)).toBeInTheDocument();
  });
});

describe("submit outcomes (C15)", () => {
  it("404 → not-yet-connected notice, never the success copy, decisions kept, บันทึกต่อ hidden after finish", async () => {
    const s = setup({ review: 404 });
    decideAll();
    fireEvent.click(submitBtn());
    await screen.findByText(PROPOSED_V2C.notConnected.head);
    expect(screen.queryByText("ส่งเข้าเคสแล้ว")).toBeNull();
    expect(s.onSubmitted).not.toHaveBeenCalled();
    expect(within(item("severity")).getByText("8 จาก 10")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: R.back })).toBeNull();
    const finishes = s.api.calls.filter((c) => c.url.endsWith("/finish"));
    expect(finishes).toHaveLength(1);
    const body = s.api.calls.find((c) => c.url.endsWith("/review"))!.body as Record<string, unknown>;
    expect(body.consent_acknowledged_at).toMatch(/\+07:00$/);
    expect((body.decisions as { action: string; original: string | null }[]).map((d) => d.action)).toEqual(["confirm", "confirm", "edit", "reject", "confirm", "confirm"]);
    expect((body.decisions as { original: string | null }[])[2].original).toBe("7 จาก 10");
  });

  it.each([500, "network"] as const)("%s → Submit error notice, decisions kept, retry label", async (review) => {
    const s = setup({ review });
    decideAll();
    fireEvent.click(submitBtn());
    await screen.findByText(R.submitError.head);
    expect(s.onSubmitted).not.toHaveBeenCalled();
    expect(submitBtn()).toHaveTextContent(R.retrySubmit);
    expect(within(item("allergy_status")).getByText(R.tag.rejected)).toBeInTheDocument();
  });

  it("2xx → onSubmitted; the red-flag acknowledgement time is in the payload", async () => {
    const ack = Date.parse("2026-09-30T10:07:00+07:00");
    const s = setup({ review: 201, ack });
    expect(screen.getByTestId("ack-strip")).toHaveTextContent("10:07");
    decideAll();
    fireEvent.click(submitBtn());
    await waitFor(() => expect(s.onSubmitted).toHaveBeenCalled());
    const body = s.api.calls.find((c) => c.url.endsWith("/review"))!.body as Record<string, unknown>;
    expect(body.red_flag_acknowledged_at).toBe("2026-09-30T10:07:00.000+07:00");
  });

  it("finish 409 counts as done and still submits", async () => {
    const s = setup({ review: 200, finish: 409 });
    decideAll();
    fireEvent.click(submitBtn());
    await waitFor(() => expect(s.onSubmitted).toHaveBeenCalled());
  });

  it("บันทึกต่อ is available before submit", () => {
    const s = setup();
    fireEvent.click(screen.getByRole("button", { name: R.back }));
    expect(s.onContinue).toHaveBeenCalled();
  });
});
