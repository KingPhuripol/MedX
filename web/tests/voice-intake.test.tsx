import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { router } from "./router-mock";

import VoiceIntake from "@/components/voice/VoiceIntake";

const MODEL_TEXT = "ควรกินยาพาราทุก 4 ชั่วโมง you should take this medicine";
const Q1 = "วันนี้มีอาการอะไรมาคะ";
const Q2 = "มีอาการนี้มานานเท่าไรแล้วคะ";
const HANDOFF = "ขอบคุณค่ะ พยาบาลจะมาดูแลต่อทันทีนะคะ";

function statuses(missing: string[]) {
  const all = ["chief_complaint", "onset_duration", "severity", "allergy_status", "current_medications", "relevant_history"];
  return all.map((field) => ({
    field,
    status: missing.includes(field) ? "MISSING" : "KNOWN",
    times_asked: 1,
    not_elicited: false,
  }));
}

function sessionState(opts: { question: string; handoff?: boolean; facts?: unknown[]; missing: string[] }) {
  return {
    session: { session_id: "s1", patient_ref: "SYN-T", status: "active", extraction_error: false, nurse_attention: !!opts.handoff },
    turns: [
      { turn_id: "a1", seq: 1, speaker: "agent", text: Q1, started_at: "2026-01-01T00:00:00Z", ended_at: "2026-01-01T00:00:00Z" },
      { turn_id: "p1", seq: 2, speaker: "patient", text: "มีไข้ค่ะ", started_at: "2026-01-01T00:00:01Z", ended_at: "2026-01-01T00:00:03Z" },
    ],
    facts: opts.facts ?? [],
    field_statuses: statuses(opts.missing),
    next_action: opts.handoff
      ? { action: "handoff", field: null, utterance_id: "handoff.nurse_attention_phrase", utterance_th: HANDOFF,
          reason: "nurse_attention_phrase", missing_fields: opts.missing }
      : { action: "ask", field: "onset_duration", utterance_id: "ask.onset_duration", utterance_th: opts.question,
          reason: null, missing_fields: [] },
  };
}

function routeFetch(getState: () => unknown) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (method === "POST" && url === "/api/voice/sessions") {
      return new Response(JSON.stringify({ session: { session_id: "s1" } }), { status: 201 });
    }
    if (method === "POST" && url.endsWith("/turns")) return new Response(JSON.stringify({ ok: true }), { status: 200 });
    return new Response(JSON.stringify(getState()), { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const FEVER_FACT = {
  fact_id: "f1",
  field: "chief_complaint",
  state: "KNOWN",
  value: "fever",
  value_text: MODEL_TEXT,
  span_turn_ids: ["p1"],
  available_at_time: "2026-01-01T00:00:03+00:00",
};

describe("VoiceIntake", () => {
  beforeEach(() => router.replace.mockReset());

  it("labels the ref, speaker and text inputs and shows the question in a status region", async () => {
    routeFetch(() => sessionState({ question: Q1, missing: ["chief_complaint"] }));
    render(<VoiceIntake />);
    const refInput = screen.getByLabelText("Synthetic patient ref");
    await userEvent.clear(refInput);
    await userEvent.type(refInput, "SYN-T{Enter}");
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(Q1);
    expect(screen.getByLabelText("Speaker")).toHaveValue("patient");
    expect(screen.getByLabelText("Turn text")).toBeInTheDocument();
    expect(within(screen.getByRole("combobox", { name: "Speaker" })).getAllByRole("option")).toHaveLength(3);
  });

  it("submits a turn with Enter, updates the question, facts and MISSING list; model text is never the question", async () => {
    let current: unknown = sessionState({ question: Q1, missing: ["chief_complaint", "onset_duration"] });
    const fetchFn = routeFetch(() => current);
    render(<VoiceIntake />);
    await userEvent.type(screen.getByLabelText("Synthetic patient ref"), "T{Enter}");
    await screen.findByRole("status");
    current = sessionState({ question: Q2, facts: [FEVER_FACT], missing: ["onset_duration"] });
    await userEvent.type(screen.getByLabelText("Turn text"), "มีไข้ค่ะ{Enter}");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(Q2));
    const post = fetchFn.mock.calls.find(([u, i]) => String(u).endsWith("/turns") && i?.method === "POST");
    const body = JSON.parse(String(post?.[1]?.body));
    expect(body).toMatchObject({ speaker: "patient", text: "มีไข้ค่ะ" });
    expect(Date.parse(body.ended_at)).toBeGreaterThanOrEqual(Date.parse(body.started_at));

    const row = screen.getByTestId("fact-row");
    expect(row).toHaveTextContent("KNOWN");
    expect(row).toHaveTextContent("fever");
    expect(within(row).getByRole("link", { name: "turn 2" })).toHaveAttribute("href", "#turn-p1");
    expect(screen.getByTestId("missing-list")).toHaveTextContent("Onset / duration");
    expect(screen.getByRole("status")).not.toHaveTextContent(MODEL_TEXT);
    expect(document.body.textContent).not.toContain(MODEL_TEXT);
  });

  it("renders the handoff banner with the missing fields", async () => {
    routeFetch(() => sessionState({ question: Q1, handoff: true, missing: ["severity", "allergy_status"] }));
    render(<VoiceIntake />);
    await userEvent.type(screen.getByLabelText("Synthetic patient ref"), "T{Enter}");
    const banner = await screen.findByTestId("handoff-banner");
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveTextContent("Attention phrase heard");
    expect(banner).toHaveTextContent("Drug allergy status");
    expect(screen.getByRole("status")).toHaveTextContent(HANDOFF);
    const missing = screen.getByTestId("missing-list");
    expect(within(missing).getAllByRole("listitem")).toHaveLength(2);
    expect(missing).not.toHaveTextContent(/no allergy/i);
  });
});
