import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/prompt/400.css";
import "@fontsource/prompt/500.css";
import "@fontsource/prompt/600.css";
import "@fontsource/prompt/700.css";
import "./tokens.css";
import "./style.css";
import "./redesign.css";
import { ApiError, apiCall, clearPendingRequest, createIdempotencyKey, hasPendingRequest, jobError, retryPendingRequest, sendApi, setCsrfToken } from "./api";
import { StatusBadge } from "./components/clinical";
import { Research } from "./components/system";
import { Icon, type IconName } from "./components/Icon";
import { BrandLogo } from "./components/BrandLogo";
import { CasesPage } from "./pages/CasesPage";
import { VoicePage } from "./pages/VoicePage";
import { LoginPage, SettingsPage } from "./pages/SystemPages";
import { type Capability, type Case, type Draft, type Fact, type Job, type Run, type Session } from "./types";
import { deriveRecommendedStep, type ClinicalWorkspaceStep } from "./workflow";

type Page = "cases" | "research" | "settings" | "voice";
type VoiceState = "idle" | "recording" | "transcribing";
type Surface = "platform" | "nurse" | "legacy";

const surface: Surface = location.pathname === "/nurse"
  ? "nurse"
  : location.pathname === "/platform"
  ? "platform"
  : "legacy";

function parseRoute(): { page: Page; encounter?: string; draft?: string; step?: ClinicalWorkspaceStep } {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (surface === "nurse") {
    const encounter = parts[0] === "voice" ? parts[1] : parts[0] === "cases" ? parts[1] : undefined;
    return { page: "voice", encounter };
  }
  if (parts[0] === "voice") return { page: "voice", encounter: parts[1] };
  if (parts[0] === "experiments") return { page: "research" };
  if (parts[0] === "settings") return { page: "settings" };
  if (parts[0] === "drafts" && parts[1]) return { page: "cases", draft: parts[1], step: "draft" };
  const step = ["intake", "facts", "draft"].includes(parts[2]) ? parts[2] as ClinicalWorkspaceStep : undefined;
  return { page: "cases", encounter: parts[0] === "cases" ? parts[1] : undefined, step };
}
function allowedPage(role: Session["role"], requested: Page): Page {
  if (surface === "nurse") return role === "evaluator" ? "settings" : "voice";
  if (surface === "platform") return role === "evaluator" ? (requested === "settings" ? "settings" : "research") : requested === "voice" ? "cases" : requested;
  return role === "evaluator" && (requested === "cases" || requested === "voice") ? "research" : requested;
}
function routeFor(page: Page, encounter?: string, step?: ClinicalWorkspaceStep) {
  if (page === "voice") return encounter ? `#/voice/${encodeURIComponent(encounter)}` : "#/voice";
  if (page === "research") return "#/experiments";
  if (page === "settings") return "#/settings";
  return encounter ? `#/cases/${encodeURIComponent(encounter)}/${step || "intake"}` : "#/cases";
}
const roleLabels: Record<Session["role"], string> = { intake: "ผู้รับข้อมูล", physician: "แพทย์ผู้ตรวจ", evaluator: "ผู้ประเมินระบบ" };

function App() {
  const initialRoute = parseRoute();
  const [session, setSession] = useState<Session | null>(null);
  const [token, setToken] = useState("");
  const [cases, setCases] = useState<Case[]>([]);
  const [current, setCurrent] = useState<Case | null>(null);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [caps, setCaps] = useState<Capability | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState<Page>(initialRoute.page);
  const [clinicalStep, setClinicalStep] = useState<ClinicalWorkspaceStep>(initialRoute.step || "intake");
  const [query, setQuery] = useState("");
  const [newCase, setNewCase] = useState(false);
  const [caseId, setCaseId] = useState("");
  const [age, setAge] = useState(40);
  const [editing, setEditing] = useState<Fact | null>(null);
  const [dirtyEntries, setDirtyEntries] = useState<Record<string, boolean>>({});
  const [job, setJob] = useState<Job | null>(null);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [caseStatus, setCaseStatus] = useState("");
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [menuOpen, setMenuOpen] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const messageRef = useRef(message);
  const currentRef = useRef(current);
  const dirty = Object.values(dirtyEntries).some(Boolean);
  messageRef.current = message;
  currentRef.current = current;

  const trackDirty = useCallback((id: string, value: boolean) => setDirtyEntries((previous) => previous[id] === value ? previous : { ...previous, [id]: value }), []);
  const work = useCallback(async (action: () => Promise<void>, silentAuthentication = false) => {
    setBusy(true); setError("");
    try { await action(); } catch (reason) {
      if (reason instanceof ApiError && ["AUTHENTICATION_REQUIRED", "CSRF_REQUIRED"].includes(reason.code)) {
        // A latched request cannot be replayed across sign-in: its CSRF token died with the session.
        setCsrfToken(""); clearPendingRequest(); setSession(null); setCaps(null); setCurrent(null);
        if (silentAuthentication) return;
      }
      setError(reason instanceof Error ? reason.message : "เกิดข้อผิดพลาด กรุณาลองอีกครั้ง");
    }
    finally { setBusy(false); }
  }, []);
  const loadList = useCallback(async (offset = 0, append = false) => {
    const response = await apiCall<{ items: Case[]; next_offset: number | null }>(`/encounters?q=${encodeURIComponent(query)}&status=${caseStatus}&offset=${offset}`);
    setCases((previous) => append ? [...previous, ...response.items] : response.items); setNextOffset(response.next_offset);
  }, [query, caseStatus]);
  const load = useCallback(async (id: string) => {
    const [encounter, snapshot, encounterRuns, encounterDrafts] = await Promise.all([
      apiCall<Case>(`/encounters/${id}?include_history=false`), apiCall<{ evidence: Fact[] }>(`/encounters/${id}/snapshot`),
      apiCall<Run[]>(`/encounters/${id}/turns`), apiCall<Draft[]>(`/encounters/${id}/drafts`),
    ]);
    setCurrent(encounter); setFacts(snapshot.evidence); setRuns(encounterRuns); setDrafts(encounterDrafts);
    setMessage(sessionStorage.getItem(`frontdoor-message:${id}`) || "");
    return { encounter, facts: snapshot.evidence, runs: encounterRuns, drafts: encounterDrafts };
  }, []);
  const initialize = useCallback(async () => {
    const activeSession = await apiCall<Session>("/session"); setCsrfToken(activeSession.csrf); setSession(activeSession);
    setCaps(await apiCall<Capability>("/capabilities")); await loadList();
    const route = parseRoute(); const permittedPage = allowedPage(activeSession.role, route.page);
    setPage(permittedPage); if (permittedPage !== route.page) location.hash = routeFor(permittedPage);
    if (route.encounter && activeSession.role !== "evaluator") {
      const id = decodeURIComponent(route.encounter);
      const loaded = await load(id);
      const step = route.step || deriveRecommendedStep(loaded.facts, loaded.runs, loaded.drafts, loaded.encounter.case_revision);
      setClinicalStep(step);
      if (!route.step) history.replaceState(null, "", routeFor("cases", id, step));
    } else if (!route.encounter && permittedPage === "voice" && activeSession.role !== "evaluator") {
      const listResp = await apiCall<{ items: Case[] }>(`/encounters?offset=0&limit=1`);
      if (listResp.items.length) await load(listResp.items[0].encounter_id);
    }
    if (route.draft && activeSession.role !== "evaluator") { const draft = await apiCall<Draft & { encounter_id: string }>(`/drafts/${route.draft}`); await load(draft.encounter_id); setClinicalStep("draft"); history.replaceState(null, "", routeFor("cases", draft.encounter_id, "draft")); }
    const savedJob = sessionStorage.getItem("frontdoor-job");
    if (savedJob) { try { setJob(await apiCall<Job>(`/jobs/${savedJob}`)); } catch { sessionStorage.removeItem("frontdoor-job"); } }
  }, [load, loadList]);

  useEffect(() => { work(initialize, true); }, []);
  useEffect(() => {
    document.title = surface === "nurse"
      ? "Clinical Front Door · Nurse Intake"
      : surface === "platform"
      ? "Clinical Front Door · Central Platform"
      : "Clinical Front Door";
  }, []);
  useEffect(() => {
    if (!current) return; const storageKey = `frontdoor-message:${current.encounter_id}`;
    if (message) sessionStorage.setItem(storageKey, message); else sessionStorage.removeItem(storageKey);
  }, [message, current?.encounter_id]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return; let stopped = false;
    const timer = window.setInterval(async () => {
      try {
        const next = await apiCall<Job>(`/jobs/${job.job_id}`); if (stopped) return; setJob(next);
        if (!["queued", "running"].includes(next.status)) {
          sessionStorage.removeItem("frontdoor-job"); if (currentRef.current?.encounter_id === next.encounter_id) await load(next.encounter_id);
          if (next.status === "completed" && next.result?.user_text === messageRef.current) setMessage("");
          if (next.status === "failed") setError(jobError(next.error_code));
        }
      } catch { if (!stopped) setError("อ่านสถานะงานไม่ได้ ระบบจะตรวจให้อีกครั้ง"); }
    }, 1000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [job?.job_id, job?.status, load]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (message || dirty || editing || hasPendingRequest()) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [message, dirty, editing]);
  useEffect(() => {
    if (!session) return;
    const routeChanged = () => {
      const route = parseRoute();
      const target = allowedPage(session.role, route.page);
      setPage(target);
      if (route.step) setClinicalStep(route.step);
      if (route.encounter && session.role !== "evaluator" && route.encounter !== currentRef.current?.encounter_id) {
        work(async () => {
          const id = decodeURIComponent(route.encounter!);
          const loaded = await load(id);
          if (route.page === "cases") {
            const step = route.step || deriveRecommendedStep(loaded.facts, loaded.runs, loaded.drafts, loaded.encounter.case_revision);
            setClinicalStep(step);
            if (!route.step) history.replaceState(null, "", routeFor("cases", id, step));
          } else if (route.page === "voice") {
            history.replaceState(null, "", routeFor("voice", id));
          }
        });
      } else if (!route.encounter && route.page === "voice" && session.role !== "evaluator" && !currentRef.current) {
        work(async () => {
          const listResp = await apiCall<{ items: Case[] }>(`/encounters?offset=0&limit=1`);
          if (listResp.items.length) await load(listResp.items[0].encounter_id);
        });
      }
    };
    window.addEventListener("hashchange", routeChanged);
    return () => window.removeEventListener("hashchange", routeChanged);
  }, [session, load, work]);

  const act = async (path: string, body: unknown) => work(async () => { await apiCall(path, "POST", body); if (currentRef.current) await load(currentRef.current.encounter_id); await loadList(); });
  const navigate = (target: Page, encounter?: string) => {
    if ((dirty || message || editing) && target !== page && !window.confirm("มีงานที่ยังไม่บันทึก ต้องการออกจากหน้านี้หรือไม่?")) return;
    setPage(target); setMenuOpen(false); location.hash = routeFor(target, encounter); window.requestAnimationFrame(() => menuButtonRef.current?.focus());
  };
  const changeCase = async (id: string) => {
    if ((dirty || message || editing) && current?.encounter_id !== id && !window.confirm("มีข้อความหรือข้อมูลที่ยังไม่บันทึก ต้องการเปลี่ยนเคสหรือไม่?")) return;
    setEditing(null); await work(async () => { const loaded = await load(id); const step = deriveRecommendedStep(loaded.facts, loaded.runs, loaded.drafts, loaded.encounter.case_revision); setClinicalStep(step); location.hash = routeFor("cases", id, step); });
  };
  const changeClinicalStep = (step: ClinicalWorkspaceStep) => {
    if (!current) return;
    if ((dirty || editing) && step !== clinicalStep && !window.confirm("มีข้อมูลที่ยังไม่บันทึก ต้องการเปลี่ยนขั้นตอนหรือไม่?")) return;
    setClinicalStep(step); location.hash = routeFor("cases", current.encounter_id, step);
  };
  const newFact = (old?: Fact) => {
    const timestamp = new Date().toISOString();
    setEditing({ event_id: createIdempotencyKey(), kind: old?.kind || "CHIEF_COMPLAINT", state: old?.state || "KNOWN", value: old?.value || "", observed_at: timestamp, available_at_time: timestamp, supersedes_event_id: old?.event_id || null, source: "STAFF_CONFIRMED" });
  };
  const startRun = async (intent: "conversation" | "draft", customText?: string) => {
    if (!current) return;
    await work(async () => {
      const textToRun = customText !== undefined ? customText : (message || "เตรียมร่างส่งต่อ");
      const created = await apiCall<Job>(`/encounters/${current.encounter_id}/jobs`, "POST", { expected_revision: current.case_revision, idempotency_key: createIdempotencyKey(), text: textToRun, decision_time: new Date().toISOString(), intent, design_id: intent === "draft" ? "fixed" : "single" });
      setJob(created);
      if (["queued", "running"].includes(created.status)) sessionStorage.setItem("frontdoor-job", created.job_id);
      else { await load(current.encounter_id); if (created.status === "completed" && intent === "conversation" && created.result?.user_text === messageRef.current) setMessage(""); if (created.status === "failed") throw Error(jobError(created.error_code)); }
    });
  };
  const record = async () => {
    if (recorder.current?.state === "recording") { recorder.current.stop(); return; }
    let stream: MediaStream | undefined;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true }); const activeRecorder = new MediaRecorder(stream); recorder.current = activeRecorder; const chunks: BlobPart[] = [];
      activeRecorder.ondataavailable = (event) => chunks.push(event.data);
      activeRecorder.onerror = () => { stream?.getTracks().forEach((track) => track.stop()); setVoiceState("idle"); setError("บันทึกเสียงไม่ได้ กรุณาใช้ข้อความต่อ"); };
      activeRecorder.onstop = () => {
        stream?.getTracks().forEach((track) => track.stop()); setVoiceState("transcribing");
        work(async () => {
          const body = new FormData(); body.append("file", new Blob(chunks, { type: activeRecorder.mimeType }), "recording.webm");
          const response = await fetch("/v2/speech/transcriptions", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": session?.csrf || "" }, body });
          if (!response.ok) throw Error("ถอดเสียงไม่สำเร็จ ข้อความเดิมยังอยู่และพิมพ์ต่อได้");
          const output = await response.json();
          const transcribed = output.text;
          setMessage([messageRef.current, transcribed].filter(Boolean).join("\n"));
        }).finally(() => setVoiceState("idle"));
      };
      activeRecorder.start(); setVoiceState("recording"); const timer = window.setTimeout(() => { if (activeRecorder.state === "recording") activeRecorder.stop(); }, 60000); activeRecorder.addEventListener("stop", () => window.clearTimeout(timer), { once: true });
    } catch { stream?.getTracks().forEach((track) => track.stop()); setVoiceState("idle"); setError("เปิดไมโครโฟนไม่ได้ กรุณาตรวจสิทธิ์หรือพิมพ์ข้อความ"); }
  };
  const speak = async (text: string, runId?: string) => {
    if (runId && caps?.synthesis) {
      await work(async () => { audioRef.current?.pause(); const response = await fetch(`/v2/runs/${runId}/speech`, { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": session?.csrf || "" } }); if (!response.ok) throw Error("อ่านเสียงไม่สำเร็จ ใช้ข้อความต่อได้"); const url = URL.createObjectURL(await response.blob()); const audio = new Audio(url); audioRef.current = audio; audio.onended = () => URL.revokeObjectURL(url); audio.onerror = () => { URL.revokeObjectURL(url); }; try { await audio.play(); } catch { /* Autoplay restriction handled safely */ } }); return;
    }
    const voice = window.speechSynthesis?.getVoices().find((item) => item.localService && item.lang.startsWith("th")); if (!voice) { setError("ยังไม่มีเสียงภาษาไทยในเครื่อง ใช้ข้อความต่อได้"); return; }
    speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(text); utterance.voice = voice; speechSynthesis.speak(utterance);
  };

  const roleNav: { id: Page; label: string; description: string }[] = session?.role === "evaluator"
    ? [{ id: "research", label: "การทดลอง Agent", description: "เปรียบเทียบและตรวจผล" }, { id: "settings", label: "สถานะระบบ", description: "ตรวจความพร้อม" }]
    : [
        { id: "voice", label: "รับข้อมูลด้วยเสียง", description: "สำหรับบุคลากรระหว่างซักประวัติ" },
        { id: "cases", label: "พื้นที่ตรวจเคส", description: "ตรวจข้อมูลและร่างส่งต่อ" },
        ...(session?.role === "physician" ? [{ id: "research" as Page, label: "การทดลอง Agent", description: "เปรียบเทียบและตรวจผล" }] : []),
        { id: "settings", label: "สถานะระบบ", description: "ตรวจความพร้อม" }
      ];
  const visibleNav = surface === "nurse"
    ? roleNav.filter((item) => item.id === "voice" || item.id === "settings")
    : surface === "platform"
    ? roleNav.filter((item) => item.id !== "voice")
    : roleNav;
  const pageTitle = page === "voice" ? "รับข้อมูลด้วยเสียงสำหรับบุคลากร" : page === "cases" ? "รับข้อมูลให้ครบ ส่งต่ออย่างชัดเจน" : page === "research" ? "การทดลอง Agent Design" : "สถานะและความพร้อม";
  const pageDescription = page === "voice" ? "พยาบาลหรือเจ้าหน้าที่ตรวจ transcript ก่อนส่งให้ผู้ช่วยทุกครั้ง" : page === "cases" ? "พื้นที่ทำงานสำหรับรับข้อมูล ตรวจทาน และเตรียมร่างส่งต่อ" : page === "research" ? "เปรียบเทียบ workflow และตรวจผลการทดลองที่ทำซ้ำได้" : "ตรวจบัญชี ความสามารถ และหลักฐานความพร้อมของระบบ";
  const navIcons: Record<Page, IconName> = { voice: "mic", cases: "cases", research: "research", settings: "settings" };

  return <div className={`app-shell app-shell--${surface} ${session ? "app-shell--signed-in" : "app-shell--signed-out"}`}>
    <a className="skip-link" href="#main">ข้ามไปเนื้อหา</a>
    <button ref={menuButtonRef} className="mobile-menu button button--secondary" aria-expanded={menuOpen} aria-controls="primary-navigation" onClick={() => setMenuOpen(!menuOpen)}>เมนู</button>
    {menuOpen ? <button className="nav-backdrop" aria-label="ปิดเมนู" onClick={() => { setMenuOpen(false); menuButtonRef.current?.focus(); }} /> : null}
    <aside className={`navigation ${menuOpen ? "navigation--open" : ""}`} aria-label="เมนูหลัก">
      <BrandLogo />
      <div className="surface-identity"><strong>{surface === "nurse" ? "Nurse Intake" : surface === "platform" ? "Central Platform" : "JARVIS workspace"}</strong><span>{surface === "nurse" ? "สำหรับพยาบาลและเจ้าหน้าที่รับข้อมูล" : surface === "platform" ? "ตรวจเคส ตัดสินใจ และประเมินระบบ" : "พื้นที่ทำงานร่วม"}</span></div>
      <div className="pilot-label"><StatusBadge tone="info">ข้อมูลสังเคราะห์เท่านั้น</StatusBadge><p>พื้นที่ทดลองภายใต้การดูแล</p></div>
      <nav id="primary-navigation">{visibleNav.map((item) => <button key={item.id} className={`nav-item ${page === item.id ? "nav-item--active" : ""}`} aria-current={page === item.id ? "page" : undefined} onClick={() => navigate(item.id)}><span className="nav-item__icon"><Icon name={navIcons[item.id]} /></span><span className="nav-item__copy"><span>{item.label}</span><small>{item.description}</small></span></button>)}</nav>
      {surface !== "legacy" ? <a className="surface-switch" href={surface === "nurse" ? "/platform#/cases" : "/nurse#/voice"}><Icon name={surface === "nurse" ? "cases" : "mic"} /><span>{surface === "nurse" ? "เปิด Central Platform" : "เปิดเว็บ Nurse Intake"}</span></a> : null}
      <div className="navigation__footer">{session ? <><span className="avatar" aria-hidden="true">{session.subject.slice(0, 1).toUpperCase()}</span><div><strong>{session.subject}</strong><span>{roleLabels[session.role]}</span></div></> : <span>ระบบต้นแบบ</span>}</div>
    </aside>
    <div className="app-body">
      <header className="topbar"><div><span className="eyebrow">Clinical workspace · synthetic_intake_v1</span><h1>{pageTitle}</h1><p className="topbar__subtitle">{pageDescription}</p></div><StatusBadge tone={caps?.provider === "mock-v2" ? "warning" : "info"}>{caps?.provider === "mock-v2" ? "Offline · Mock provider" : "รอผลประเมินโมเดลจริง"}</StatusBadge></header>
      <div className="synthetic-banner" role="note"><span aria-hidden="true">i</span><div><strong>พื้นที่ทดลองสำหรับข้อมูลสังเคราะห์</strong><p>ต้องมีบุคลากรตรวจทุกครั้ง · ระบบไม่วินิจฉัย สั่งยา สั่งตรวจ หรือส่งต่อผู้ป่วย</p></div></div>
      <main id="main" tabIndex={-1}>
        <div className="global-status" aria-live="polite">
          {job && ["queued", "running"].includes(job.status) ? <div className="inline-message inline-message--info"><div><strong>{job.status === "queued" ? "งานอยู่ในคิว" : "ผู้ช่วยกำลังทำงาน"}</strong><span>เคส {job.encounter_id}</span></div><button className="button button--text" onClick={() => work(async () => setJob(await apiCall<Job>(`/jobs/${job.job_id}/cancel`, "POST")))}>ยกเลิกงาน</button></div> : null}
          {busy ? <div className="inline-message inline-message--info" role="status"><span className="spinner" aria-hidden="true" />กำลังดำเนินการ กรุณารอสักครู่</div> : null}
          {error ? <div role="alert" className="inline-message inline-message--danger"><div><strong>ดำเนินการไม่สำเร็จ</strong><span>{error}</span></div>{hasPendingRequest() ? <button className="button button--secondary" onClick={() => work(async () => { await retryPendingRequest(); if (currentRef.current) await load(currentRef.current.encounter_id); })}>ตรวจคำขอเดิม</button> : null}</div> : null}
        </div>
        {!session ? <LoginPage token={token} setToken={setToken} busy={busy} login={() => work(async () => { await apiCall("/session", "POST", { token }).catch((reason) => { throw reason instanceof ApiError && reason.code === "AUTHENTICATION_REQUIRED" ? Error("รหัสเข้าถึงไม่ถูกต้อง กรุณาตรวจแล้วลองอีกครั้ง") : reason; }); setToken(""); await initialize(); })} />
          : page === "settings" ? <SettingsPage session={session} caps={caps} logout={() => work(async () => { await apiCall("/session", "DELETE"); setCsrfToken(""); setSession(null); setCurrent(null); setRuns([]); setDrafts([]); setFacts([]); })} />
          : page === "research" ? <Research />
          : page === "voice" ? <VoicePage cases={cases} current={current} facts={facts} runs={runs} session={session} caps={caps} voiceState={voiceState} busy={busy} job={job} message={message} setMessage={setMessage} record={record} speak={speak} stopAudio={() => { window.speechSynthesis?.cancel(); audioRef.current?.pause(); }} startRun={startRun} changeCase={async (id) => { await changeCase(id); location.hash = routeFor("voice", id); }} newCaseOpen={newCase} setNewCaseOpen={setNewCase} onNavigateToCockpit={() => { if (surface === "nurse") location.assign(current?.encounter_id ? `/platform#/cases/${encodeURIComponent(current.encounter_id)}/intake` : "/platform#/cases"); else navigate("cases", current?.encounter_id); }} />
          : <CasesPage cases={cases} current={current} facts={facts} runs={runs} drafts={drafts} session={session} caps={caps} step={clinicalStep} changeStep={changeClinicalStep} query={query} setQuery={setQuery} caseStatus={caseStatus} setCaseStatus={setCaseStatus} nextOffset={nextOffset} newCaseOpen={newCase} setNewCaseOpen={setNewCase} caseId={caseId} setCaseId={setCaseId} age={age} setAge={setAge} editing={editing} setEditing={setEditing} message={message} setMessage={setMessage} busy={busy} job={job} voiceState={voiceState} loadList={() => work(() => loadList())} moreCases={() => nextOffset !== null && work(() => loadList(nextOffset, true))} createCase={() => work(async () => { await sendApi("/encounters", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf, "Idempotency-Key": createIdempotencyKey() }, body: JSON.stringify({ encounter_id: caseId, age }) }); setNewCase(false); await loadList(); await load(caseId); setClinicalStep("intake"); location.hash = routeFor("cases", caseId, "intake"); })} changeCase={changeCase} refresh={() => current && work(async () => { await load(current.encounter_id); })} startRun={startRun} record={record} speak={speak} stopAudio={() => { window.speechSynthesis?.cancel(); audioRef.current?.pause(); }} newFact={newFact} saveFact={() => current && editing && work(async () => { await apiCall(`/encounters/${current.encounter_id}/events`, "POST", { expected_revision: current.case_revision, idempotency_key: createIdempotencyKey(), fact: editing }); setEditing(null); await load(current.encounter_id); await loadList(); })} act={act} trackDirty={trackDirty} />}
      </main>
      {session && surface === "legacy" ? <nav className="mobile-bottom-bar" aria-label="เมนูด่วนมือถือ">
        <button className={`mobile-bottom-item ${page === "voice" ? "mobile-bottom-item--active" : ""}`} onClick={() => navigate("voice", current?.encounter_id)}>
          <Icon name="mic" size={20} /><span>รับข้อมูลเสียง</span>
        </button>
        <button className={`mobile-bottom-item ${page === "cases" ? "mobile-bottom-item--active" : ""}`} onClick={() => navigate("cases", current?.encounter_id)}>
          <Icon name="cases" size={20} /><span>ตรวจเคส</span>
        </button>
        <button className={`mobile-bottom-item ${page === "settings" ? "mobile-bottom-item--active" : ""}`} onClick={() => navigate("settings")}>
          <Icon name="settings" size={20} /><span>ระบบ</span>
        </button>
      </nav> : null}
      <footer>ต้นแบบสำหรับข้อมูลสังเคราะห์ · ไม่มีการส่งต่อหรือดำเนินการรักษาภายนอกระบบ</footer>
    </div>
  </div>;
}

export { Review, Proposals, FactEditor } from "./components/clinical";
const root = document.getElementById("root");
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="fatal-error"><section className="panel"><span className="eyebrow">ระบบหยุดอย่างปลอดภัย</span><h1>เปิดพื้นที่ทำงานใหม่</h1><p>หน้าจอพบข้อผิดพลาด ข้อมูลที่บันทึกแล้วไม่ถูกแก้ไข กรุณาโหลดหน้าใหม่ก่อนทำรายการต่อ</p><button className="button button--primary" onClick={() => location.reload()}>โหลดหน้าใหม่</button></section></main>;
    return this.props.children;
  }
}
if (root) createRoot(root).render(<ErrorBoundary><App /></ErrorBoundary>);
