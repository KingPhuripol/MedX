import React, { useEffect, useRef, useState } from "react";
import { Icon } from "../components/Icon";
import { StatusBadge } from "../components/clinical";
import { type Capability, type Case, type Fact, type Job, type Run, type Session, humanizeClinicalText } from "../types";

export type VoicePageProps = {
  cases: Case[];
  current: Case | null;
  facts: Fact[];
  runs: Run[];
  session: Session;
  caps: Capability | null;
  voiceState: "idle" | "recording" | "transcribing";
  busy: boolean;
  job: Job | null;
  message: string;
  setMessage: (value: string) => void;
  record: () => void;
  speak: (text: string, runId?: string) => void;
  stopAudio: () => void;
  startRun: (intent: "conversation" | "draft") => void;
  changeCase: (id: string) => void;
  newCaseOpen: boolean;
  setNewCaseOpen: (open: boolean) => void;
  onNavigateToCockpit: () => void;
};

export function VoicePage({
  cases,
  current,
  facts,
  runs,
  session,
  caps,
  voiceState,
  busy,
  job,
  message,
  setMessage,
  record,
  speak,
  stopAudio,
  startRun,
  changeCase,
  setNewCaseOpen,
  onNavigateToCockpit,
}: VoicePageProps) {
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [showQuickInput, setShowQuickInput] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const lastProcessedRunIdRef = useRef<string | null>(runs.length ? runs[runs.length - 1].run_id : null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const activeJob = !!job && ["queued", "running"].includes(job.status);

  // Auto-scroll chat stream to bottom when runs change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [runs.length, activeJob]);

  // Auto-speak the assistant response when a new completed run arrives
  useEffect(() => {
    if (!autoSpeak || !runs.length) return;
    const latestRun = runs[runs.length - 1];
    if (
      latestRun &&
      latestRun.status === "COMPLETED" &&
      latestRun.run_id !== lastProcessedRunIdRef.current
    ) {
      lastProcessedRunIdRef.current = latestRun.run_id;
      const textToSpeak = humanizeClinicalText(latestRun.response);
      setIsSpeaking(true);
      speak(textToSpeak, latestRun.run_id);
    }
  }, [runs, autoSpeak, speak]);

  const handleOrbClick = () => {
    if (isSpeaking) {
      stopAudio();
      setIsSpeaking(false);
      return;
    }
    if (voiceState === "recording") {
      record(); // stops recording and triggers Whisper
    } else if (voiceState === "idle" && !busy && !activeJob) {
      record(); // starts recording
    }
  };

  const handleSendTypedMessage = () => {
    if (!busy && message.trim() && !activeJob) {
      startRun("conversation");
      setShowQuickInput(false);
    }
  };

  // Telemetry items: find vitals or chief complaint facts
  const vitalFacts = facts.filter((f) => f.kind === "VITAL" || f.kind === "CHIEF_COMPLAINT");
  const pendingProposalsCount = current?.attention?.pending_proposal_count || 0;
  const activeCaseId = current?.encounter_id || (cases.length > 0 ? cases[0].encounter_id : "");

  return (
    <div className="voice-mobile-container">
      {/* Mobile Top Header */}
      <header className="voice-mobile-header">
        <button
          className="button button--secondary voice-back-btn"
          onClick={onNavigateToCockpit}
          title="เปิดพื้นที่ตรวจเคส"
          aria-label="เปิดพื้นที่ตรวจเคส"
        >
          <Icon name="arrow" className="icon-flip-x" size={16} />
          <span className="voice-btn-label">พื้นที่ตรวจเคส</span>
        </button>

        <div className="voice-case-selector">
          <label htmlFor="voice-case-select" className="sr-only">เลือกเคส</label>
          <select
            id="voice-case-select"
            value={activeCaseId}
            onChange={(e) => changeCase(e.target.value)}
            className="voice-select"
          >
            {cases.map((c) => (
              <option key={c.encounter_id} value={c.encounter_id}>
                {c.encounter_id} (อายุ {c.age} ปี)
              </option>
            ))}
          </select>
          <button
            className="button button--icon button--sm voice-add-case-btn"
            onClick={() => setNewCaseOpen(true)}
            title="สร้างเคสใหม่"
            aria-label="สร้างเคสใหม่"
          >
            <Icon name="plus" size={16} />
          </button>
        </div>

        <div className="voice-agent-badge">
          <span className="voice-pulse-dot" />
          <span className="voice-agent-name">Luna AI</span>
        </div>
      </header>

      {/* Hero Visualizer: Interactive Voice Orb */}
      <section className="voice-hero-section">
        <div className="voice-orb-wrapper">
          <div
            className={`voice-orb-rings ${
              voiceState === "recording"
                ? "voice-orb-rings--recording"
                : activeJob
                ? "voice-orb-rings--thinking"
                : isSpeaking
                ? "voice-orb-rings--speaking"
                : ""
            }`}
          />
          <button
            type="button"
            className={`voice-orb-button ${
              voiceState === "recording"
                ? "voice-orb-button--recording"
                : activeJob
                ? "voice-orb-button--thinking"
                : isSpeaking
                ? "voice-orb-button--speaking"
                : ""
            }`}
            onClick={handleOrbClick}
            disabled={voiceState === "transcribing"}
            aria-label={
              voiceState === "recording"
                ? "กำลังบันทึกเสียง แตะเพื่อเสร็จสิ้น"
                : activeJob
                ? "ผู้ช่วยกำลังคิดคำตอบ"
                : isSpeaking
                ? "กำลังพูด แตะเพื่อหยุด"
                : "แตะเพื่อพูดคุยกับ Luna"
            }
          >
            {voiceState === "recording" ? (
              <Icon name="stop" size={36} />
            ) : isSpeaking ? (
              <Icon name="volume" size={36} />
            ) : activeJob ? (
              <Icon name="spark" size={36} />
            ) : (
              <Icon name="mic" size={38} />
            )}
          </button>
        </div>

        {/* State description */}
        <div className="voice-state-banner">
          <h2 className="voice-state-title">
            {voiceState === "recording"
              ? "กำลังฟังเสียงคุณ..."
              : voiceState === "transcribing"
              ? "กำลังแปลงเสียงภาษาไทย (Whisper)..."
              : activeJob
              ? "ผู้ช่วย Luna กำลังจัดระเบียบข้อมูล..."
              : isSpeaking
              ? "น้อง Luna กำลังพูดตอบกลับ..."
              : message
              ? "ตรวจ transcript ก่อนส่ง"
              : "แตะเพื่อบันทึกเสียงระหว่างซักประวัติ"}
          </h2>
          <p className="voice-state-hint">
            {voiceState === "recording"
              ? "แตะปุ่มอีกครั้งเมื่อพูดจบ ระบบจะถอดเสียงให้ตรวจ ไม่ส่งอัตโนมัติ"
              : isSpeaking
              ? "แตะปุ่มเพื่อหยุดเสียงชั่วคราว"
              : "ใช้โดยบุคลากรเท่านั้น และห้ามบันทึกข้อมูลระบุตัวผู้ป่วยจริง"}
          </p>
        </div>

        {/* Voice utility bar */}
        <div className="voice-util-bar">
          <label className="voice-toggle-label">
            <input
              type="checkbox"
              checked={autoSpeak}
              onChange={(e) => setAutoSpeak(e.target.checked)}
            />
            <span>พูดตอบกลับด้วยเสียง</span>
          </label>
          <button
            type="button"
            className="button button--text button--sm voice-quick-type-btn"
            onClick={() => setShowQuickInput(!showQuickInput)}
          >
            {showQuickInput ? "ซ่อนแป้นพิมพ์" : "💬 พิมพ์ข้อความ"}
          </button>
        </div>

        {/* Optional quick typed composer */}
        {showQuickInput || message ? (
          <div className="voice-quick-composer">
            <label className="voice-transcript-label" htmlFor="voice-reviewed-transcript">Transcript รอตรวจ</label>
            <textarea
              id="voice-reviewed-transcript"
              placeholder="ถอดเสียงหรือพิมพ์ข้อมูลที่บุคลากรจะตรวจ..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              className="voice-quick-input"
            />
            <button
              className="button button--primary button--sm"
              disabled={busy || !message.trim() || activeJob}
              onClick={handleSendTypedMessage}
            >
              ตรวจแล้ว ส่งให้ผู้ช่วย
            </button>
          </div>
        ) : null}
      </section>

      {/* Real-time Extracted Clinical Telemetry Pill */}
      {vitalFacts.length > 0 || pendingProposalsCount > 0 ? (
        <section className="voice-telemetry-banner">
          <div className="voice-telemetry-header">
            <Icon name="spark" size={16} />
            <strong>ข้อมูลที่บุคลากรยืนยันแล้ว</strong>
            {pendingProposalsCount > 0 ? (
              <StatusBadge tone="warning">
                {pendingProposalsCount} ข้อเสนอรอตรวจ
              </StatusBadge>
            ) : null}
          </div>
          <div className="voice-telemetry-pills">
            {vitalFacts.map((fact) => (
              <span key={fact.event_id} className="voice-fact-pill">
                <strong>{fact.kind}:</strong>{" "}
                {typeof fact.value === "object" ? JSON.stringify(fact.value) : String(fact.value)}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {/* Live Conversation Stream (Mobile Chat Bubbles) */}
      <section className="voice-chat-stream" aria-label="บทสนทนากับผู้ช่วย Luna">
        <h3 className="voice-stream-heading">ประวัติการสนทนาในเคสนี้</h3>
        {!runs.length ? (
          <div className="empty-state empty-state--voice">
            <Icon name="spark" size={28} />
            <p>ยังไม่มีข้อความ แตะไมค์เพื่อถอดเสียง แล้วตรวจ transcript ก่อนส่ง</p>
          </div>
        ) : (
          runs.map((run) => (
            <div key={run.run_id} className="voice-turn-bubble-group">
              {/* User Voice Message */}
              <div className="voice-bubble voice-bubble--user">
                <div className="voice-bubble__meta">
                  <span className="voice-bubble__sender">บุคลากร</span>
                  <span className="voice-bubble__tag"><Icon name="mic" size={12} /> เสียง</span>
                </div>
                <p className="voice-bubble__text">{run.user_text}</p>
              </div>

              {/* Assistant Luna Reply */}
              <div className="voice-bubble voice-bubble--assistant">
                <div className="voice-bubble__meta">
                  <span className="voice-bubble__sender">Luna · ผู้ช่วยรับข้อมูล</span>
                  {run.status === "COMPLETED" ? (
                    <button
                      className="button button--text button--sm voice-bubble__replay"
                      onClick={() => {
                        setIsSpeaking(true);
                        speak(humanizeClinicalText(run.response), run.run_id);
                      }}
                      title="ฟังเสียงตอบกลับนี้อีกครั้ง"
                    >
                      <Icon name="volume" size={14} /> ฟังอีกครั้ง
                    </button>
                  ) : (
                    <StatusBadge tone="warning">กำลังวิเคราะห์</StatusBadge>
                  )}
                </div>
                <p className="voice-bubble__text">
                  {humanizeClinicalText(run.response)}
                </p>
              </div>
            </div>
          ))
        )}

        {/* Typing indicator when job is active */}
        {activeJob ? (
          <div className="voice-bubble voice-bubble--assistant voice-bubble--loading">
            <span className="voice-typing-dots">
              <span />
              <span />
              <span />
            </span>
            <span className="voice-typing-text">Luna กำลังจัดระเบียบข้อมูลเพื่อให้บุคลากรตรวจ...</span>
          </div>
        ) : null}

        <div ref={chatEndRef} />
      </section>

      {/* Sticky Bottom Handoff Bar */}
      <footer className="voice-bottom-handoff-bar">
        <div className="voice-handoff-info">
          <small>ตรวจข้อเสนอและร่างก่อนส่งต่อ</small>
          <strong>เคส {activeCaseId || "ยังไม่เลือกเคส"}</strong>
        </div>
        <button
          type="button"
          className="button button--primary voice-handoff-button"
          onClick={onNavigateToCockpit}
        >
          <span>เปิดพื้นที่ตรวจเคส</span>
          <Icon name="arrow" size={18} />
        </button>
      </footer>
    </div>
  );
}
