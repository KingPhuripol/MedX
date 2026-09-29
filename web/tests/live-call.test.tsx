import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const router = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() };
let query = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => query,
  usePathname: () => "/app/queue",
}));

import AppShell from "@/components/clinical/AppShell";
import WorkQueue from "@/components/clinical/WorkQueue";
import { FactSheet } from "@/components/live/FactSheet";
import LiveCall from "@/components/live/LiveCall";
import type { SessionState } from "@/lib/voice";

const Q1 = "วันนี้มีอาการอะไรมาคะ";
const Q_ONSET = "มีอาการนี้มานานเท่าไรแล้วคะ";
const Q_SEV = "ถ้าให้คะแนนความรุนแรง 0 ถึง 10 ตอนนี้ประมาณเท่าไรคะ";
const HANDOFF = "ขอบคุณค่ะ พยาบาลจะมาดูแลต่อทันทีนะคะ";
const FIELDS = ["chief_complaint", "onset_duration", "severity", "allergy_status", "current_medications", "relevant_history"];

const CONFIG = {
  enabled: true, reason: null, access_code_required: false, max_session_seconds: 300,
  vendor_label: "TestVendor", model: "m", transcribe_model: "transcribe-test",
};
const MINT = {
  client_secret: "ek_TEST", expires_at: 4102444800, connect_url: "https://rt.example.test/calls", data_channel: "oai-events",
  model: "m", transcribe_model: "transcribe-test", vendor_label: "TestVendor", max_session_seconds: 300, instructions_version: "v",
};

// ---------------------------------------------------------------- fake realtime peer connection
let channel: { onmessage: ((m: { data: string }) => void) | null; sent: { type: string; response?: { input: { content: { text: string }[] }[] } }[] };
let track: { enabled: boolean; stop: () => void };
class FakePC {
  connectionState = "new";
  ontrack: unknown = null;
  onconnectionstatechange: unknown = null;
  addTrack() {}
  createDataChannel() {
    channel = { onmessage: null, sent: [] };
    return { readyState: "open", get onmessage() { return channel.onmessage; }, set onmessage(v: typeof channel.onmessage) { channel.onmessage = v; },
      send: (d: string) => channel.sent.push(JSON.parse(d)), close: () => {} };
  }
  async createOffer() { return { type: "offer", sdp: "offer" }; }
  async setLocalDescription() {}
  async setRemoteDescription() {}
  close() {}
}
const emit = (evt: object) => act(async () => channel.onmessage?.({ data: JSON.stringify(evt) }));

// ---------------------------------------------------------------- fake backend
interface Server {
  turns: { turn_id: string; seq: number; speaker: string; text: string; started_at: string; ended_at: string }[];
  facts: object[];
  nurse_attention: boolean;
  allergy_conflict: boolean;
  extraction_error: boolean;
  action: { action: string; field: string | null; utterance_id: string; utterance_th: string; reason: string | null; missing_fields: string[] };
  posted: Record<string, unknown>[];
  status: string;
  script: string[];
}
let server: Server;
let mint: { status: number; body: unknown };
let config: { status: number; body: unknown };
let finishBody: unknown;

const ask = (uid: string, text: string, field: string | null) => ({ action: "ask", field, utterance_id: uid, utterance_th: text, reason: null, missing_fields: [] });
function statuses() {
  const known = new Set(server.facts.map((f) => (f as { field: string }).field));
  return FIELDS.map((field) => ({ field, status: known.has(field) ? "KNOWN" : "MISSING", times_asked: 1, not_elicited: false }));
}
function sessionPayload() {
  return {
    session_id: "s1", patient_ref: "SYN-T1", status: server.status, extraction_error: server.extraction_error,
    nurse_attention: server.nurse_attention, allergy_conflict: server.allergy_conflict,
  };
}
function state() {
  return { session: sessionPayload(), turns: server.turns, facts: server.facts, field_statuses: statuses(), next_action: server.action };
}
const fact = (field: string, value: string, text: string, turn: number, at: string) => ({
  fact_id: `f-${field}`, field, state: "KNOWN", value, value_text: text, span_turn_ids: [`t${turn}`], available_at_time: at,
});

function installBackend() {
  server = {
    turns: [{ turn_id: "t1", seq: 1, speaker: "agent", text: Q1, started_at: "2026-01-01T00:00:00Z", ended_at: "2026-01-01T00:00:00Z" }],
    facts: [], nurse_attention: false, allergy_conflict: false, extraction_error: false, action: ask("ask.chief_complaint", Q1, "chief_complaint"),
    posted: [], status: "active", script: [],
  };
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
    if (url === "/api/voice/realtime/config") return json(config.status, config.body);
    if (url === "/api/voice/realtime/session") return json(mint.status, mint.body);
    if (url === MINT.connect_url) return new Response("answer", { status: 201 });
    if (method === "POST" && url === "/api/voice/sessions") return json(201, { session: sessionPayload() });
    if (method === "GET" && url === "/api/voice/sessions/s1") return json(200, state());
    if (method === "POST" && url === "/api/voice/sessions/s1/turns") {
      const body = JSON.parse(String(init?.body));
      server.posted.push(body);
      const n = server.turns.length;
      server.turns.push({ turn_id: `t${n + 1}`, seq: n + 1, speaker: body.speaker, text: body.text, started_at: body.started_at, ended_at: body.ended_at });
      const at = body.ended_at as string;
      if (body.text.includes("เจ็บหน้าอก")) {
        server.facts.push(fact("chief_complaint", "chest_pain", "เจ็บหน้าอก", n + 1, at), fact("onset_duration", "PT2H", "สองชั่วโมง", n + 1, at));
        server.action = ask("ask.severity", Q_SEV, "severity");
      } else if (body.text.includes("หมดสติ")) {
        server.nurse_attention = true;
        server.action = { action: "handoff", field: null, utterance_id: "handoff.nurse_attention_phrase", utterance_th: HANDOFF, reason: "nurse_attention_phrase", missing_fields: [] };
      } else server.action = ask("ask.onset_duration", Q_ONSET, "onset_duration");
      server.turns.push({ turn_id: `t${n + 2}`, seq: n + 2, speaker: "agent", text: server.action.utterance_th, started_at: at, ended_at: at });
      return json(200, {
        turn: { ended_at: body.ended_at }, next_action: server.action, field_statuses: statuses(), session: sessionPayload(),
        nurse_attention: server.nurse_attention,
      });
    }
    if (method === "POST" && url === "/api/voice/sessions/s1/finish") {
      server.status = "finished";
      return json(200, finishBody);
    }
    return json(404, {});
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const FINISH = { handoff_reason: "finished_by_nurse", missing_fields: ["severity", "current_medications"], evidence: [{}, {}], facts: [], field_statuses: [] };

beforeEach(() => {
  vi.clearAllMocks();
  query = new URLSearchParams();
  config = { status: 200, body: CONFIG };
  mint = { status: 200, body: MINT };
  finishBody = FINISH;
  track = { enabled: true, stop: vi.fn() };
  vi.stubGlobal("RTCPeerConnection", FakePC);
  vi.stubGlobal("MediaStream", class {});
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getAudioTracks: () => [track], getTracks: () => [track] })) },
  });
  installBackend();
});

const status = () => screen.getByTestId("live-status");
const root = () => screen.getByTestId("live-root");

async function openIdle() {
  render(<LiveCall />);
  await waitFor(() => expect(root()).toHaveAttribute("data-state", "idle"));
}
async function startCall() {
  await openIdle();
  await userEvent.click(screen.getByTestId("live-start"));
  await waitFor(() => expect(channel).toBeDefined());
  await waitFor(() => expect(channel.onmessage).not.toBeNull());
  await emit({ type: "session.created" });
  await waitFor(() => expect(root()).toHaveAttribute("data-state", "listening"));
}
const speakDone = async () => {
  await emit({ type: "output_audio_buffer.started" });
  await emit({ type: "output_audio_buffer.stopped" });
  await waitFor(() => expect(root()).toHaveAttribute("data-state", "listening"), { timeout: 2000 });
};
const say = async (item: string, transcript: string) => {
  await emit({ type: "input_audio_buffer.speech_started", item_id: item });
  await emit({ type: "input_audio_buffer.speech_stopped", item_id: item });
  await emit({ type: "conversation.item.input_audio_transcription.completed", item_id: item, transcript });
};
const speaks = () => channel.sent.filter((e) => e.type === "response.create").map((e) => e.response!.input[0].content[0].text);

describe("MedX Live call flow", () => {
  it("F4: a completed transcription becomes one asr turn and the next spoken text is exactly the server utterance", async () => {
    await startCall();
    expect(speaks()).toEqual([Q1]);
    await speakDone();
    await say("i1", "เจ็บหน้าอกมาสองชั่วโมงค่ะ.");
    await waitFor(() => expect(speaks()).toEqual([Q1, Q_SEV]));
    expect(server.posted).toHaveLength(1);
    expect(server.posted[0]).toMatchObject({ speaker: "patient", text: "เจ็บหน้าอกมาสองชั่วโมงค่ะ", source: "asr", asr_model: "transcribe-test" });
    expect(screen.getByTestId("live-question")).toHaveTextContent(Q_SEV);
    expect(channel.sent.every((e) => ["response.create", "input_audio_buffer.clear"].includes(e.type))).toBe(true);
  });

  it("F6: data-state walks idle > connecting > listening > processing > speaking > listening with the exact status text", async () => {
    await openIdle();
    expect(status()).toHaveTextContent("พร้อมเริ่มสนทนา");
    const seen: string[] = [];
    const obs = new MutationObserver(() => seen.push(`${root().getAttribute("data-state")}|${status().textContent}`));
    obs.observe(root(), { attributes: true, attributeFilter: ["data-state"], subtree: false });
    await userEvent.click(screen.getByTestId("live-start"));
    await waitFor(() => expect(channel?.onmessage).toBeTruthy());
    await emit({ type: "session.created" });
    await waitFor(() => expect(root()).toHaveAttribute("data-state", "listening"));
    expect(status()).toHaveTextContent("กำลังฟัง…");
    await emit({ type: "output_audio_buffer.started" });
    expect(root()).toHaveAttribute("data-state", "speaking");
    expect(status()).toHaveTextContent("MedX กำลังพูด…");
    await emit({ type: "output_audio_buffer.stopped" });
    await waitFor(() => expect(root()).toHaveAttribute("data-state", "listening"), { timeout: 2000 });
    await emit({ type: "input_audio_buffer.speech_started", item_id: "i1" });
    await emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "i1", transcript: "เจ็บหน้าอก" });
    await waitFor(() => expect(seen.some((s) => s.startsWith("processing|"))).toBe(true));
    expect(seen.find((s) => s.startsWith("processing|"))).toBe("processing|กำลังบันทึก…");
    expect(seen.map((s) => s.split("|")[0]).filter((s, i, a) => s !== a[i - 1])).toEqual(expect.arrayContaining(["connecting", "listening", "speaking", "processing"]));
    obs.disconnect();
    await waitFor(() => expect(speaks()).toHaveLength(2));
    await speakDone();
  });

  it("F9: the mic is off while MedX speaks (+300 ms) and a transcription that began inside that window posts nothing", async () => {
    await startCall();
    await emit({ type: "output_audio_buffer.started" });
    expect(track.enabled).toBe(false);
    await emit({ type: "input_audio_buffer.speech_started", item_id: "echo" });
    await emit({ type: "output_audio_buffer.stopped" });
    expect(track.enabled).toBe(false);
    await waitFor(() => expect(track.enabled).toBe(true), { timeout: 2000 });
    await emit({ type: "conversation.item.input_audio_transcription.completed", item_id: "echo", transcript: "เจ็บหน้าอก" });
    await new Promise((r) => setTimeout(r, 50));
    expect(server.posted).toEqual([]);
    expect(channel.sent.some((e) => e.type === "input_audio_buffer.clear")).toBe(true);
  });

  it("empty or failed transcription posts nothing and shows the hint", async () => {
    await startCall();
    await speakDone();
    await say("i1", " . ");
    expect(screen.getByTestId("live-hint")).toHaveTextContent("ไม่ได้ยินชัดเจน กรุณาพูดอีกครั้ง");
    await emit({ type: "conversation.item.input_audio_transcription.failed", item_id: "i2" });
    expect(server.posted).toEqual([]);
    await emit({ type: "response.done", response: { status: "failed" } });
    expect(screen.getByTestId("live-hint")).toHaveTextContent("เสียงขัดข้อง — โปรดอ่านคำถามบนจอให้ผู้ป่วยฟัง");
  });

  it("mute toggles the track and the status line", async () => {
    await startCall();
    await speakDone();
    const mute = screen.getByTestId("live-mute");
    await userEvent.click(mute);
    expect(mute).toHaveAttribute("aria-pressed", "true");
    expect(track.enabled).toBe(false);
    expect(status()).toHaveTextContent("ปิดไมค์อยู่ — แตะปุ่มไมค์เพื่อเปิด");
    await userEvent.click(mute);
    expect(track.enabled).toBe(true);
  });

  it("a red-flag phrase shows the critical alert, disables the mic, speaks the handoff and ends", async () => {
    await startCall();
    await speakDone();
    await say("i1", "หมดสติค่ะ");
    const alert = await screen.findByTestId("live-alert-nurse-attention");
    expect(alert).toHaveAttribute("role", "alert");
    expect(alert).toHaveTextContent("พบสัญญาณอันตราย: มีคำพูดที่ต้องให้พยาบาลประเมินทันที");
    expect(track.enabled).toBe(false);
    await waitFor(() => expect(speaks()).toEqual([Q1, HANDOFF]));
    finishBody = { ...FINISH, handoff_reason: "nurse_attention_phrase" };
    await emit({ type: "output_audio_buffer.started" });
    await emit({ type: "output_audio_buffer.stopped" });
    await waitFor(() => expect(root()).toHaveAttribute("data-state", "ended"), { timeout: 2000 });
    expect(screen.getByTestId("live-summary")).toHaveTextContent("พบคำพูดที่ต้องให้พยาบาลประเมินทันที");
    expect(track.stop).toHaveBeenCalled();
  });

  it("F10: END finishes the session and shows the Thai summary; handoff goes to /nurse/triage without a case", async () => {
    await startCall();
    await speakDone();
    await userEvent.click(screen.getByTestId("live-end"));
    await waitFor(() => expect(root()).toHaveAttribute("data-state", "ended"));
    const summary = screen.getByTestId("live-summary");
    expect(summary).toHaveTextContent("เหตุผลที่ส่งต่อ: พยาบาลจบการสนทนา");
    expect(summary).toHaveTextContent("หัวข้อที่ยังขาด: ความรุนแรง (0–10), ยาที่ใช้อยู่");
    expect(summary).toHaveTextContent("หลักฐานที่บันทึก: 2 รายการ");
    expect(within(summary).getByRole("heading", { level: 2 })).toHaveFocus();
    expect(screen.getByTestId("live-handoff")).toHaveAttribute("href", "/nurse/triage");
  });

  it("F10: with case and run the handoff opens the case triage tab; close returns to the case", async () => {
    query = new URLSearchParams("case=SYN-2026-0017&run=abc");
    await startCall();
    await userEvent.click(screen.getByTestId("live-close"));
    expect(router.push).toHaveBeenCalledWith("/app/cases/SYN-2026-0017/overview?run=abc");
  });

  it("F10: handoff link with case and run", async () => {
    query = new URLSearchParams("case=SYN-2026-0017&run=abc");
    await startCall();
    await userEvent.click(screen.getByTestId("live-end"));
    await waitFor(() => expect(root()).toHaveAttribute("data-state", "ended"));
    expect(screen.getByTestId("live-handoff")).toHaveAttribute("href", "/app/cases/SYN-2026-0017/triage?run=abc");
    expect(screen.getByTestId("live-case-chip")).toHaveTextContent("SYN-T1");
  });
});

describe("MedX Live safe failures", () => {
  it("F7: red flag, allergy conflict and extraction alerts render from the session payload", async () => {
    server.nurse_attention = true;
    server.allergy_conflict = true;
    server.extraction_error = true;
    query = new URLSearchParams("session=s1");
    await openIdle();
    const red = await screen.findByTestId("live-alert-nurse-attention");
    const allergy = screen.getByTestId("live-alert-allergy-conflict");
    for (const el of [red, allergy]) expect(el).toHaveAttribute("role", "alert");
    expect(allergy).toHaveTextContent(
      "ข้อมูลแพ้ยาขัดแย้ง: คำตอบภายหลังไม่ตรงกับประวัติแพ้ยาที่บันทึกไว้ ระบบคงประวัติเดิมไว้ — พยาบาลโปรดยืนยันกับผู้ป่วย",
    );
    expect(screen.getByTestId("live-alert-extraction")).toHaveTextContent("ระบบสกัดข้อมูลไม่สำเร็จ — พยาบาลบันทึกต่อเอง");
  });

  it("F8: voice disabled shows the reason and the open text form; a typed turn posts as typed", async () => {
    config = { status: 200, body: { ...CONFIG, enabled: false, reason: "not_configured" } };
    render(<LiveCall />);
    await waitFor(() => expect(root()).toHaveAttribute("data-state", "disabled"));
    expect(status()).toHaveTextContent("โหมดเสียงยังไม่เปิดใช้งาน — ใช้การพิมพ์แทนได้");
    expect(screen.getByTestId("live-disabled")).toHaveTextContent("ยังไม่ได้ตั้งค่าบริการเสียง");
    expect(screen.queryByTestId("live-vendor-banner")).toBeNull();
    const form = await screen.findByTestId("live-type-form");
    await userEvent.type(within(form).getByLabelText("ข้อความ"), "เจ็บหน้าอกมาสองชั่วโมงค่ะ");
    await userEvent.click(within(form).getByRole("button", { name: "ส่ง" }));
    await waitFor(() => expect(server.posted).toHaveLength(1));
    expect(server.posted[0]).toMatchObject({ speaker: "patient", source: "typed" });
    expect(await screen.findAllByTestId("live-fact-row")).toHaveLength(2);
  });

  it("F8: a config failure also lands in disabled with the text fallback", async () => {
    config = { status: 503, body: { detail: "down" } };
    render(<LiveCall />);
    await waitFor(() => expect(root()).toHaveAttribute("data-state", "disabled"));
    expect(screen.getByTestId("live-disabled")).toHaveTextContent("ไม่สามารถตรวจสอบสถานะโหมดเสียงได้");
    expect(screen.getByTestId("live-type-form")).toBeInTheDocument();
  });

  it("F8: mic denied shows the Thai error with retry and the text fallback", async () => {
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("denied"));
    await openIdle();
    await userEvent.click(screen.getByTestId("live-start"));
    await waitFor(() => expect(root()).toHaveAttribute("data-state", "error"));
    expect(status()).toHaveTextContent("การเชื่อมต่อขัดข้อง");
    expect(screen.getByTestId("live-error")).toHaveTextContent("ไม่ได้รับสิทธิ์ใช้ไมโครโฟน — อนุญาตในการตั้งค่าเบราว์เซอร์ หรือพิมพ์แทน");
    expect(screen.getByTestId("live-error")).toHaveAttribute("role", "alert");
    expect(screen.getByTestId("live-retry")).toBeInTheDocument();
    expect(screen.getByTestId("live-type-toggle")).toBeInTheDocument();
  });

  it("F8: 429 and 502 map to the exact copy; a wrong access code returns to idle with a field error", async () => {
    mint = { status: 429, body: { detail: { reason: "rate_limited" } } };
    await openIdle();
    await userEvent.click(screen.getByTestId("live-start"));
    await waitFor(() => expect(screen.getByTestId("live-error")).toHaveTextContent("เริ่มสนทนาบ่อยเกินไป ลองใหม่ในอีกสักครู่"));
    mint = { status: 502, body: { detail: { reason: "upstream_error", upstream_status: 500 } } };
    await userEvent.click(screen.getByTestId("live-retry"));
    await waitFor(() => expect(screen.getByTestId("live-error")).toHaveTextContent("เชื่อมต่อบริการเสียงไม่สำเร็จ"));
    expect(track.stop).toHaveBeenCalled();
  });

  it("F8: access code is required by the config, kept out of storage, and an invalid code is reported", async () => {
    config = { status: 200, body: { ...CONFIG, access_code_required: true } };
    mint = { status: 403, body: { detail: { reason: "access_code_invalid" } } };
    await openIdle();
    const code = screen.getByTestId("live-access-code");
    expect(code).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByTestId("live-start"));
    expect(await screen.findByText("กรุณากรอกรหัสเข้าใช้โหมดเสียง")).toBeInTheDocument();
    await userEvent.type(code, "wrong");
    await userEvent.click(screen.getByTestId("live-start"));
    expect(await screen.findByText("รหัสเข้าใช้ไม่ถูกต้อง")).toBeInTheDocument();
    expect(root()).toHaveAttribute("data-state", "idle");
    expect(JSON.stringify({ ...localStorage })).not.toContain("wrong");
    expect(window.location.href).not.toContain("wrong");
  });

  it("S5: the vendor banner carries the server-provided label in every call state", async () => {
    await startCall();
    expect(screen.getByTestId("live-vendor-banner")).toHaveTextContent("เสียงถูกส่งไปยัง TestVendor — ใช้กับบทสังเคราะห์เท่านั้น");
  });
});

describe("FactSheet", () => {
  const data: SessionState = {
    session: { session_id: "s", patient_ref: "SYN-T", status: "active", extraction_error: false, nurse_attention: false },
    turns: [
      { turn_id: "a1", seq: 1, speaker: "agent", text: Q1, started_at: "", ended_at: "" },
      { turn_id: "p2", seq: 2, speaker: "patient", text: "x", started_at: "", ended_at: "" },
    ],
    facts: [
      { fact_id: "f1", field: "chief_complaint", state: "KNOWN", value: "chest_pain", value_text: "เจ็บหน้าอก", span_turn_ids: ["p2"], available_at_time: "2026-01-01T00:00:02Z" },
    ],
    field_statuses: [
      { field: "chief_complaint", status: "KNOWN", times_asked: 1, not_elicited: false },
      { field: "severity", status: "MISSING", times_asked: 2, not_elicited: true },
      { field: "allergy_status", status: "MISSING", times_asked: 0, not_elicited: false },
    ],
    next_action: { action: "ask", field: null, utterance_id: "u", utterance_th: "q", reason: null, missing_fields: [] },
  };

  it("F5: a fact row cites its source utterance and missing fields are neutral chips", () => {
    render(<FactSheet data={data} expanded desktop={false} onToggle={() => {}} />);
    const row = screen.getByTestId("live-fact-row");
    expect(row).toHaveAttribute("data-field", "chief_complaint");
    expect(row).toHaveTextContent("อาการสำคัญ");
    expect(row).toHaveTextContent("เจ็บหน้าอก");
    expect(row).toHaveTextContent("จากประโยค #2");
    const chips = screen.getAllByTestId("live-missing-chip");
    expect(chips.map((c) => c.getAttribute("data-field"))).toEqual(["severity", "allergy_status"]);
    expect(chips[0]).toHaveTextContent("ความรุนแรง (0–10) (ถามครบ 2 ครั้งแล้ว)");
    expect(screen.getByTestId("live-sheet-toggle")).toHaveTextContent("ข้อมูลที่กรอกแล้ว 1/3");
    expect(screen.getByTestId("live-sheet-toggle")).toHaveAttribute("aria-expanded", "true");
  });

  it("collapsed peek shows no missing chips and the desktop panel drops the toggle", () => {
    const { rerender } = render(<FactSheet data={data} expanded={false} desktop={false} onToggle={() => {}} />);
    expect(screen.queryByTestId("live-missing-chip")).toBeNull();
    rerender(<FactSheet data={data} expanded={false} desktop onToggle={() => {}} />);
    expect(screen.queryByTestId("live-sheet-toggle")).toBeNull();
    expect(screen.getAllByTestId("live-missing-chip")).toHaveLength(2);
  });
});

describe("entry points", () => {
  function shellFetch() {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/me") return new Response(JSON.stringify({ user: { id: 1, username: "nurse1", role: "nurse" } }), { status: 200 });
        if (String(url).endsWith("/queue"))
          return new Response(
            JSON.stringify({ items: [{ task_id: "t", case_id: "SYN-2026-0017", role: "nurse", kind: "intake", label: "รับเข้า", priority: "warning", status: "open", owner: null, stage: "s", safety_state: "x", next_action: "รับเข้า", version: 1 }] }),
            { status: 200 },
          );
        return new Response("{}", { status: 200 });
      }),
    );
  }

  it("F12: nav and queue links render only when NEXT_PUBLIC_VOICE_ENABLED=1", async () => {
    localStorage.setItem("medx.demo.run", "run-1");
    shellFetch();
    vi.stubEnv("NEXT_PUBLIC_VOICE_ENABLED", "0");
    const off = render(
      <AppShell>
        <WorkQueue />
      </AppShell>,
    );
    await screen.findByText(/คิวรับเข้าและคัดกรอง/);
    expect(screen.queryByRole("link", { name: /MedX Live/ })).toBeNull();
    expect(screen.queryByTestId("live-entry-task")).toBeNull();
    off.unmount();

    vi.stubEnv("NEXT_PUBLIC_VOICE_ENABLED", "1");
    shellFetch();
    render(
      <AppShell>
        <WorkQueue />
      </AppShell>,
    );
    const task = await screen.findByTestId("live-entry-task");
    const links = screen.getAllByRole("link", { name: /MedX Live/ });
    expect(links.length).toBeGreaterThanOrEqual(2);
    expect(links.some((l) => l.getAttribute("href") === "/live")).toBe(true);
    expect(task.getAttribute("href")).toMatch(/^\/live\?case=SYN-2026-0017&run=/);
    vi.unstubAllEnvs();
  });
});
