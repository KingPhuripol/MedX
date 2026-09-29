"use client";

import {
  AlertOctagon,
  AlertTriangle,
  CircleCheck,
  Keyboard,
  LoaderCircle,
  Mic,
  MicOff,
  PhoneOff,
  Play,
  RotateCcw,
  Volume2,
  X,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import Wordmark from "@/components/Wordmark";
import { Field } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";

import {
  ALERT_TH,
  CONFIG_UNAVAILABLE_TH,
  DISABLED_REASON_TH,
  IDLE_SUBLINE_TH,
  MUTED_STATUS_TH,
  NEAR_END_STATUS_TH,
  STATUS_TH,
  fmtClock,
  vendorBannerTh,
  type LiveState,
} from "./copy";
import { FactSheet } from "./FactSheet";
import { Orb } from "./Orb";
import { HandoffLink, Summary } from "./Summary";
import { TypeForm } from "./TypeForm";
import { useLiveCall } from "./useLiveCall";

const REF_PATTERN = /^SYN-[A-Za-z0-9-]+$/;
const CALL_STATES: LiveState[] = ["connecting", "listening", "processing", "speaking"];

function randomRef(): string {
  const bytes = new Uint8Array(3);
  if (typeof crypto !== "undefined" && crypto.getRandomValues) crypto.getRandomValues(bytes);
  else bytes.forEach((_, i) => (bytes[i] = Math.floor(Math.random() * 256)));
  return `SYN-LIVE-${[...bytes].map((b) => b.toString(16).padStart(2, "0")).join("").toUpperCase()}`;
}

function useDesktop(): boolean {
  const [desktop, setDesktop] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(min-width: 1024px)");
    setDesktop(query.matches);
    const onChange = (e: MediaQueryListEvent) => setDesktop(e.matches);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);
  return desktop;
}

function Ctl({
  testId,
  label,
  icon,
  onClick,
  size = "sm",
  tone,
  disabled,
  pressed,
  expanded,
}: {
  testId: string;
  label: string;
  icon: ReactNode;
  onClick: () => void;
  size?: "sm" | "lg";
  tone?: "end" | "start";
  disabled?: boolean;
  pressed?: boolean;
  expanded?: boolean;
}) {
  return (
    <button
      type="button"
      className={["live-ctl", size === "lg" ? "live-ctl--lg" : "", tone ? `live-ctl--${tone}` : ""].filter(Boolean).join(" ")}
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed}
      aria-expanded={expanded}
    >
      <span className="live-ctl-disc" aria-hidden="true">
        {icon}
      </span>
      <span className="live-ctl-label">{label}</span>
    </button>
  );
}

function StatusIcon({ state, muted }: { state: LiveState; muted: boolean }) {
  const size = 20;
  if (state === "connecting" || state === "processing" || state === "loading")
    return <LoaderCircle size={size} className="live-spin" aria-hidden="true" />;
  if (state === "listening") return muted ? <MicOff size={size} aria-hidden="true" /> : <Mic size={size} aria-hidden="true" />;
  if (state === "speaking") return <Volume2 size={size} aria-hidden="true" />;
  if (state === "error") return <AlertTriangle size={size} aria-hidden="true" />;
  if (state === "ended") return <CircleCheck size={size} aria-hidden="true" />;
  if (state === "disabled") return <MicOff size={size} aria-hidden="true" />;
  return <Mic size={size} aria-hidden="true" />;
}

/** MedX Live: a phone-first Thai voice screen. Speech in/out only; the policy and facts stay server-side. */
export default function LiveCall() {
  const params = useSearchParams();
  const caseParam = params.get("case");
  const runId = params.get("run");
  const sessionParam = params.get("session");
  const caseId = caseParam && REF_PATTERN.test(caseParam) ? caseParam : null;
  const initialRef = useMemo(() => caseId ?? randomRef(), [caseId]);
  const live = useLiveCall({ caseId, runId, sessionParam, initialRef });
  const { state, data, muted, remaining, summary } = live;
  const desktop = useDesktop();
  const [sheetOpen, setSheetOpen] = useState(false);

  useEffect(() => {
    if (state === "disabled") live.setTypeOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  const inCall = CALL_STATES.includes(state);
  const session = data?.session;
  const refShown = session?.patient_ref ?? live.patientRef;
  const nearEnd = remaining !== null && remaining <= 30 && (state === "listening" || state === "processing" || state === "speaking");
  const clock = remaining ?? live.cfg?.max_session_seconds ?? null;

  let status = STATUS_TH[state];
  if (state === "listening" && muted) status = MUTED_STATUS_TH;
  else if (state === "listening" && nearEnd) status = NEAR_END_STATUS_TH;

  const lastPatient = [...(data?.turns ?? [])].reverse().find((t) => t.speaker !== "agent");
  const question = data && state !== "ended" && state !== "loading" ? data.next_action.utterance_th : null;
  const showSheet = data !== null && state !== "ended" && state !== "loading";
  const showBanner = live.vendorLabel && state !== "disabled" && state !== "loading";
  const patientTurns = (data?.turns ?? []).some((t) => t.speaker !== "agent");
  const canFinishTyped = !inCall && state !== "ended" && !live.finishing && patientTurns;
  const reasonLine = live.cfg?.reason ? DISABLED_REASON_TH[live.cfg.reason] : live.cfgFailed ? CONFIG_UNAVAILABLE_TH : null;

  let centre: ReactNode;
  if (state === "idle") centre = <Ctl testId="live-start" label="เริ่มสนทนา" size="lg" tone="start" icon={<Play size={28} />} onClick={() => void live.start()} />;
  else if (state === "error")
    centre = <Ctl testId="live-retry" label="ลองใหม่" size="lg" tone="start" icon={<RotateCcw size={28} />} onClick={live.retry} />;
  else
    centre = (
      <Ctl
        testId="live-end"
        label="จบการสนทนา"
        size="lg"
        tone="end"
        icon={<PhoneOff size={28} />}
        disabled={live.finishing || state === "loading" || (state === "disabled" && !data)}
        onClick={() => void live.endCall()}
      />
    );

  return (
    <div className="live-root" data-live-root data-testid="live-root" data-state={state}>
      <audio ref={live.audioRef} autoPlay playsInline />

      <header className="live-header">
        <h1 className="live-title">
          <Wordmark /> Live
        </h1>
        <p className="live-case-chip" data-testid="live-case-chip">
          ผู้ป่วยสังเคราะห์ · {refShown}
        </p>
        <p className="live-timer" data-testid="live-timer">
          <span className="sr-only">เวลาที่เหลือ </span>
          {clock === null ? "--:--" : nearEnd ? `เหลือ ${fmtClock(clock)}` : fmtClock(clock)}
        </p>
        <button type="button" className="live-close" data-testid="live-close" aria-label="ปิด MedX Live" onClick={live.close}>
          <X size={20} aria-hidden="true" />
        </button>
      </header>

      <div className="live-grid">
        <div className="live-main">
          <div className="live-banners">
            {showBanner && (
              <Notice tone="warning" data-testid="live-vendor-banner" icon={<AlertTriangle size={16} />}>
                <p>{vendorBannerTh(live.vendorLabel!)}</p>
              </Notice>
            )}
            {session?.nurse_attention && (
              <Notice tone="critical" role="alert" data-testid="live-alert-nurse-attention" icon={<AlertOctagon size={24} />}>
                <p>{ALERT_TH.nurseAttention}</p>
              </Notice>
            )}
            {session?.allergy_conflict && (
              <Notice tone="critical" role="alert" data-testid="live-alert-allergy-conflict" icon={<AlertOctagon size={24} />}>
                <p>{ALERT_TH.allergyConflict}</p>
              </Notice>
            )}
            {session?.extraction_error && (
              <Notice tone="warning" data-testid="live-alert-extraction" icon={<AlertTriangle size={24} />}>
                <p>{ALERT_TH.extraction}</p>
              </Notice>
            )}
          </div>

          {state === "ended" && summary ? (
            <Summary result={summary} data={data} />
          ) : (
            <>
              <div className="live-centre">
                <Orb state={state} getLevel={live.getLevel} />
                <p className="live-status" role="status" aria-live="polite" data-testid="live-status">
                  <StatusIcon state={state} muted={muted} />
                  <span>{status}</span>
                </p>
                {state === "idle" && <p className="live-subline">{IDLE_SUBLINE_TH}</p>}
                {state === "disabled" && reasonLine && (
                  <p className="live-subline" data-testid="live-disabled">
                    {reasonLine}
                  </p>
                )}
                {state === "error" && live.cause && (
                  <p className="live-error" role="alert" data-testid="live-error">
                    {live.cause}
                  </p>
                )}
              </div>

              {state === "idle" && (
                <div className="live-panel live-idle-fields">
                  <Field
                    label="รหัสผู้ป่วยสังเคราะห์"
                    htmlFor="live-ref"
                    hint="ขึ้นต้นด้วย SYN- (บทสังเคราะห์เท่านั้น)"
                    error={REF_PATTERN.test(live.patientRef.trim()) || data ? null : "ต้องขึ้นต้นด้วย SYN- และมีเฉพาะตัวอักษร ตัวเลข และ -"}
                  >
                    <input
                      id="live-ref"
                      data-testid="live-patient-ref"
                      value={data ? data.session.patient_ref : live.patientRef}
                      readOnly={data !== null}
                      onChange={(e) => live.setPatientRef(e.target.value)}
                      pattern="SYN-[A-Za-z0-9-]+"
                      aria-describedby="live-ref-hint"
                      autoComplete="off"
                    />
                  </Field>
                  {live.cfg?.access_code_required && (
                    <Field label="รหัสเข้าใช้โหมดเสียง" htmlFor="live-code" error={live.codeError}>
                      <input
                        id="live-code"
                        data-testid="live-access-code"
                        type="password"
                        autoComplete="off"
                        value={live.accessCode}
                        onChange={(e) => live.setAccessCode(e.target.value)}
                        aria-invalid={live.codeError ? true : undefined}
                      />
                    </Field>
                  )}
                </div>
              )}

              <div className="live-captions">
                {question && (
                  <p className="live-question" lang="th" data-testid="live-question">
                    {question}
                  </p>
                )}
                {lastPatient && (
                  <p className="live-last" lang="th" data-testid="live-last-utterance">
                    คุณพูดว่า: {lastPatient.text}
                  </p>
                )}
                <div aria-live="polite">
                  {live.hint && (
                    <p className="live-hint" data-testid="live-hint">
                      {live.hint}
                    </p>
                  )}
                </div>
              </div>

              {live.typeOpen && (
                <TypeForm
                  busy={live.typedBusy}
                  onSpeaker={live.setSpeaker}
                  onSubmit={live.submitTyped}
                  onFinish={canFinishTyped ? () => void live.endCall() : undefined}
                />
              )}
            </>
          )}
        </div>

        {showSheet && <FactSheet data={data} expanded={sheetOpen} desktop={desktop} onToggle={() => setSheetOpen((v) => !v)} />}

        {state === "ended" ? (
          <div className="live-controls live-controls--ended">
            <HandoffLink caseId={caseId} runId={runId} />
          </div>
        ) : (
          <div className="live-controls">
            <Ctl
              testId="live-mute"
              label={muted ? "เปิดไมค์" : "ปิดไมค์"}
              icon={muted ? <MicOff size={24} /> : <Mic size={24} />}
              pressed={muted}
              disabled={!inCall}
              onClick={live.toggleMute}
            />
            {centre}
            <Ctl
              testId="live-type-toggle"
              label="พิมพ์แทน"
              icon={<Keyboard size={24} />}
              expanded={live.typeOpen}
              onClick={() => live.setTypeOpen(!live.typeOpen)}
            />
          </div>
        )}
      </div>
    </div>
  );
}
