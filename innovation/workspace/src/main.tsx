import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/prompt/400.css";
import "@fontsource/prompt/500.css";
import "@fontsource/prompt/600.css";
import "@fontsource/prompt/700.css";
import "./tokens.css";
import "./style.css";
import { ApiError, apiCall, createIdempotencyKey, hasPendingRequest, jobError, retryPendingRequest, sendApi, setCsrfToken } from "./api";
import { FactEditor, FactView, Proposals, Review, StatusBadge } from "./components/clinical";
import { History, Readiness, Research } from "./components/system";
import { type Capability, type Case, type Draft, type Fact, type Job, type Run, type Session, handoffLabels, humanizeClinicalText } from "./types";

type Page = "cases" | "research" | "settings";
type VoiceState = "idle" | "recording" | "transcribing";

function parseRoute(): { page: Page; encounter?: string; draft?: string } {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "experiments") return { page: "research" };
  if (parts[0] === "settings") return { page: "settings" };
  if (parts[0] === "drafts" && parts[1]) return { page: "cases", draft: parts[1] };
  return { page: "cases", encounter: parts[0] === "cases" ? parts[1] : undefined };
}
function routeFor(page: Page, encounter?: string) {
  if (page === "research") return "#/experiments";
  if (page === "settings") return "#/settings";
  return encounter ? `#/cases/${encodeURIComponent(encounter)}` : "#/cases";
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
  const work = useCallback(async (action: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await action(); } catch (reason) {
      if (reason instanceof ApiError && ["AUTHENTICATION_REQUIRED", "CSRF_REQUIRED"].includes(reason.code)) {
        setCsrfToken(""); setSession(null); setCaps(null); setCurrent(null);
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
  }, []);
  const initialize = useCallback(async () => {
    const activeSession = await apiCall<Session>("/session"); setCsrfToken(activeSession.csrf); setSession(activeSession);
    setCaps(await apiCall<Capability>("/capabilities")); await loadList();
    const route = parseRoute(); const allowedPage = activeSession.role === "evaluator" && route.page === "cases" ? "research" : route.page;
    setPage(allowedPage); if (allowedPage !== route.page) location.hash = routeFor(allowedPage);
    if (route.encounter && activeSession.role !== "evaluator") await load(decodeURIComponent(route.encounter));
    if (route.draft && activeSession.role !== "evaluator") { const draft = await apiCall<Draft & { encounter_id: string }>(`/drafts/${route.draft}`); await load(draft.encounter_id); }
    const savedJob = sessionStorage.getItem("frontdoor-job");
    if (savedJob) { try { setJob(await apiCall<Job>(`/jobs/${savedJob}`)); } catch { sessionStorage.removeItem("frontdoor-job"); } }
  }, [load, loadList]);

  useEffect(() => { work(initialize); }, []);
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
      const target = session.role === "evaluator" && route.page === "cases" ? "research" : route.page;
      setPage(target);
      if (route.encounter && session.role !== "evaluator" && route.encounter !== currentRef.current?.encounter_id) {
        work(() => load(decodeURIComponent(route.encounter!)));
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
    setEditing(null); await work(async () => { await load(id); location.hash = routeFor("cases", id); });
  };
  const newFact = (old?: Fact) => {
    const timestamp = new Date().toISOString();
    setEditing({ event_id: createIdempotencyKey(), kind: old?.kind || "CHIEF_COMPLAINT", state: old?.state || "KNOWN", value: old?.value || "", observed_at: timestamp, available_at_time: timestamp, supersedes_event_id: old?.event_id || null, source: "STAFF_CONFIRMED" });
  };
  const startRun = async (intent: "conversation" | "draft") => {
    if (!current) return;
    await work(async () => {
      const created = await apiCall<Job>(`/encounters/${current.encounter_id}/jobs`, "POST", { expected_revision: current.case_revision, idempotency_key: createIdempotencyKey(), text: message || "เตรียมร่างส่งต่อ", decision_time: new Date().toISOString(), intent, design_id: intent === "draft" ? "fixed" : "single" });
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
        work(async () => { const body = new FormData(); body.append("file", new Blob(chunks, { type: activeRecorder.mimeType }), "recording.webm"); const response = await fetch("/v2/speech/transcriptions", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": session?.csrf || "" }, body }); if (!response.ok) throw Error("ถอดเสียงไม่สำเร็จ ข้อความเดิมยังอยู่และพิมพ์ต่อได้"); const output = await response.json(); setMessage([messageRef.current, output.text].filter(Boolean).join("\n")); }).finally(() => setVoiceState("idle"));
      };
      activeRecorder.start(); setVoiceState("recording"); const timer = window.setTimeout(() => { if (activeRecorder.state === "recording") activeRecorder.stop(); }, 60000); activeRecorder.addEventListener("stop", () => window.clearTimeout(timer), { once: true });
    } catch { stream?.getTracks().forEach((track) => track.stop()); setVoiceState("idle"); setError("เปิดไมโครโฟนไม่ได้ กรุณาตรวจสิทธิ์หรือพิมพ์ข้อความ"); }
  };
  const speak = async (text: string, runId: string) => {
    if (caps?.synthesis) {
      await work(async () => { audioRef.current?.pause(); const response = await fetch(`/v2/runs/${runId}/speech`, { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": session?.csrf || "" } }); if (!response.ok) throw Error("อ่านเสียงไม่สำเร็จ ใช้ข้อความต่อได้"); const url = URL.createObjectURL(await response.blob()); const audio = new Audio(url); audioRef.current = audio; audio.onended = () => URL.revokeObjectURL(url); audio.onerror = () => { URL.revokeObjectURL(url); setError("เล่นเสียงไม่ได้ ใช้ข้อความต่อได้"); }; await audio.play(); }); return;
    }
    const voice = window.speechSynthesis?.getVoices().find((item) => item.localService && item.lang.startsWith("th")); if (!voice) { setError("ยังไม่มีเสียงภาษาไทยในเครื่อง ใช้ข้อความต่อได้"); return; }
    speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(text); utterance.voice = voice; speechSynthesis.speak(utterance);
  };

  const visibleNav: { id: Page; label: string; description: string }[] = session?.role === "evaluator"
    ? [{ id: "research", label: "การทดลอง Agent", description: "เปรียบเทียบและตรวจผล" }, { id: "settings", label: "สถานะระบบ", description: "ตรวจความพร้อม" }]
    : [{ id: "cases", label: "เคสและการรับข้อมูล", description: "สนทนาและตรวจร่าง" }, ...(session?.role === "physician" ? [{ id: "research" as Page, label: "การทดลอง Agent", description: "เปรียบเทียบและตรวจผล" }] : []), { id: "settings", label: "สถานะระบบ", description: "ตรวจความพร้อม" }];
  const pageTitle = page === "cases" ? "รับข้อมูลให้ครบ ส่งต่ออย่างชัดเจน" : page === "research" ? "การทดลอง Agent Design" : "สถานะและความพร้อม";
  const pageDescription = page === "cases" ? "พื้นที่ทำงานสำหรับรับข้อมูล ตรวจทาน และเตรียมร่างส่งต่อ" : page === "research" ? "เปรียบเทียบ workflow และตรวจผลการทดลองที่ทำซ้ำได้" : "ตรวจบัญชี ความสามารถ และหลักฐานความพร้อมของระบบ";
  const navIcons: Record<Page, string> = { cases: "▦", research: "◇", settings: "⚙" };

  return <div className="app-shell">
    <a className="skip-link" href="#main">ข้ามไปเนื้อหา</a>
    <button ref={menuButtonRef} className="mobile-menu button button--secondary" aria-expanded={menuOpen} aria-controls="primary-navigation" onClick={() => setMenuOpen(!menuOpen)}>เมนู</button>
    {menuOpen ? <button className="nav-backdrop" aria-label="ปิดเมนู" onClick={() => { setMenuOpen(false); menuButtonRef.current?.focus(); }} /> : null}
    <aside className={`navigation ${menuOpen ? "navigation--open" : ""}`} aria-label="เมนูหลัก">
      <div className="brand"><span className="brand-mark" aria-hidden="true">FD</span><div><strong>Clinical Front Door</strong><span>JARVIS workspace</span></div></div>
      <div className="pilot-label"><StatusBadge tone="info">ข้อมูลสังเคราะห์เท่านั้น</StatusBadge><p>พื้นที่ทดลองภายใต้การดูแล</p></div>
      <nav id="primary-navigation">{visibleNav.map((item) => <button key={item.id} className={`nav-item ${page === item.id ? "nav-item--active" : ""}`} aria-current={page === item.id ? "page" : undefined} onClick={() => navigate(item.id)}><span className="nav-item__icon" aria-hidden="true">{navIcons[item.id]}</span><span className="nav-item__copy"><span>{item.label}</span><small>{item.description}</small></span></button>)}</nav>
      <div className="navigation__footer">{session ? <><span className="avatar" aria-hidden="true">{session.subject.slice(0, 1).toUpperCase()}</span><div><strong>{session.subject}</strong><span>{roleLabels[session.role]}</span></div></> : <span>ระบบต้นแบบ</span>}</div>
    </aside>
    <div className="app-body">
      <header className="topbar"><div><span className="eyebrow">Clinical workspace · synthetic_intake_v1</span><h1>{pageTitle}</h1><p className="topbar__subtitle">{pageDescription}</p></div><StatusBadge tone={caps?.provider === "mock-v2" ? "warning" : "info"}>{caps?.provider === "mock-v2" ? "Offline · Mock provider" : "รอผลประเมินโมเดลจริง"}</StatusBadge></header>
      <div className="synthetic-banner" role="note"><span aria-hidden="true">i</span><strong>ใช้ข้อมูลสังเคราะห์เท่านั้น</strong><p>ห้ามกรอกชื่อ เลขบัตรประชาชน หมายเลขโรงพยาบาล หรือข้อมูลที่ระบุตัวผู้ป่วยจริง</p></div>
      <main id="main" tabIndex={-1}>
        <div className="global-status" aria-live="polite">
          {job && ["queued", "running"].includes(job.status) ? <div className="inline-message inline-message--info"><div><strong>{job.status === "queued" ? "งานอยู่ในคิว" : "ผู้ช่วยกำลังทำงาน"}</strong><span>เคส {job.encounter_id}</span></div><button className="button button--text" onClick={() => work(async () => setJob(await apiCall<Job>(`/jobs/${job.job_id}/cancel`, "POST")))}>ยกเลิกงาน</button></div> : null}
          {busy ? <div className="inline-message inline-message--info" role="status"><span className="spinner" aria-hidden="true" />กำลังดำเนินการ กรุณารอสักครู่</div> : null}
          {error ? <div role="alert" className="inline-message inline-message--danger"><div><strong>ดำเนินการไม่สำเร็จ</strong><span>{error}</span></div>{hasPendingRequest() ? <button className="button button--secondary" onClick={() => work(async () => { await retryPendingRequest(); if (currentRef.current) await load(currentRef.current.encounter_id); })}>ตรวจคำขอเดิม</button> : null}</div> : null}
        </div>
        {!session ? <Login token={token} setToken={setToken} busy={busy} login={() => work(async () => { await apiCall("/session", "POST", { token }); setToken(""); await initialize(); })} />
          : page === "settings" ? <Settings session={session} caps={caps} logout={() => work(async () => { await apiCall("/session", "DELETE"); setCsrfToken(""); setSession(null); setCurrent(null); setRuns([]); setDrafts([]); setFacts([]); })} />
          : page === "research" ? <Research />
          : <CasesPage cases={cases} current={current} facts={facts} runs={runs} drafts={drafts} session={session} caps={caps} query={query} setQuery={setQuery} caseStatus={caseStatus} setCaseStatus={setCaseStatus} nextOffset={nextOffset} newCaseOpen={newCase} setNewCaseOpen={setNewCase} caseId={caseId} setCaseId={setCaseId} age={age} setAge={setAge} editing={editing} setEditing={setEditing} message={message} setMessage={setMessage} busy={busy} job={job} voiceState={voiceState} loadList={() => work(() => loadList())} moreCases={() => nextOffset !== null && work(() => loadList(nextOffset, true))} createCase={() => work(async () => { await sendApi("/encounters", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf, "Idempotency-Key": createIdempotencyKey() }, body: JSON.stringify({ encounter_id: caseId, age }) }); setNewCase(false); await loadList(); await load(caseId); location.hash = routeFor("cases", caseId); })} changeCase={changeCase} refresh={() => current && work(() => load(current.encounter_id))} startRun={startRun} record={record} speak={speak} stopAudio={() => { window.speechSynthesis?.cancel(); audioRef.current?.pause(); }} newFact={newFact} saveFact={() => current && editing && work(async () => { await apiCall(`/encounters/${current.encounter_id}/events`, "POST", { expected_revision: current.case_revision, idempotency_key: createIdempotencyKey(), fact: editing }); setEditing(null); await load(current.encounter_id); await loadList(); })} act={act} trackDirty={trackDirty} />}
      </main>
      <footer>ต้นแบบสำหรับข้อมูลสังเคราะห์ · ไม่มีการส่งต่อหรือดำเนินการรักษาภายนอกระบบ</footer>
    </div>
  </div>;
}

function Login({ token, setToken, busy, login }: { token: string; setToken: (value: string) => void; busy: boolean; login: () => void }) {
  return <section className="panel login-card"><span className="eyebrow">เข้าสู่ระบบอย่างปลอดภัย</span><h2>เข้าสู่พื้นที่ทำงาน</h2><p>ใช้รหัสเข้าถึงส่วนตัวที่ผู้ดูแลจัดให้ ระบบจะไม่บันทึกรหัสในเบราว์เซอร์</p><label>รหัสเข้าถึง<input autoFocus type="password" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="current-password" /></label><button className="button button--primary" disabled={busy || !token} onClick={login}>เข้าสู่ระบบ</button></section>;
}
function Settings({ session, caps, logout }: { session: Session; caps: Capability | null; logout: () => void }) {
  return <div className="settings-grid"><section className="panel"><div className="section-heading"><div><span className="eyebrow">Provider readiness</span><h2>ความสามารถที่เปิดใช้</h2></div><StatusBadge tone="warning">ยังไม่ผ่าน clinical validation</StatusBadge></div><Readiness /></section><aside className="panel account-card"><span className="eyebrow">บัญชีปัจจุบัน</span><h2>{session.subject}</h2><dl><dt>บทบาท</dt><dd>{roleLabels[session.role]}</dd><dt>พื้นที่</dt><dd>{session.workspace}</dd><dt>สนทนา</dt><dd>{caps?.conversation ? "เปิดใช้ตาม provider" : "ยังไม่พร้อม"}</dd><dt>ถอดเสียง</dt><dd>{caps?.speech ? "ตั้งค่าแล้ว · รอตรวจผล" : "ยังไม่ตั้งค่า"}</dd></dl><p className="supporting-text">Credentials ตั้งค่าบนเซิร์ฟเวอร์และไม่แสดงในหน้านี้</p><button className="button button--secondary" onClick={logout}>ออกจากระบบ</button></aside></div>;
}

type CasesPageProps = {
  cases: Case[]; current: Case | null; facts: Fact[]; runs: Run[]; drafts: Draft[]; session: Session; caps: Capability | null;
  query: string; setQuery: (value: string) => void; caseStatus: string; setCaseStatus: (value: string) => void; nextOffset: number | null;
  newCaseOpen: boolean; setNewCaseOpen: (value: boolean) => void; caseId: string; setCaseId: (value: string) => void; age: number; setAge: (value: number) => void;
  editing: Fact | null; setEditing: (fact: Fact | null) => void; message: string; setMessage: (value: string) => void; busy: boolean; job: Job | null; voiceState: VoiceState;
  loadList: () => void; moreCases: () => void; createCase: () => void; changeCase: (id: string) => void; refresh: () => void;
  startRun: (intent: "conversation" | "draft") => void; record: () => void; speak: (text: string, runId: string) => void; stopAudio: () => void;
  newFact: (fact?: Fact) => void; saveFact: () => void; act: (path: string, body: unknown) => Promise<void>; trackDirty: (id: string, value: boolean) => void;
};

function CasesPage(props: CasesPageProps) {
  const activeJob = !!props.job && ["queued", "running"].includes(props.job.status);
  const latestDraft = props.drafts.slice().reverse()[0];
  const olderDrafts = props.drafts.length > 1 ? props.drafts.slice(0, -1).reverse() : [];
  const pendingProposals = props.runs.reduce((total, run) => total + (run.case_revision === props.current?.case_revision ? run.proposals.filter((proposal) => proposal.proposal_id).length : 0), 0);
  const milestones = [
    { label: "รับข้อมูล", done: props.runs.length > 0 },
    { label: "ยืนยันข้อมูล", done: props.facts.length > 0 },
    { label: "เตรียมร่าง", done: !!latestDraft },
    { label: "แพทย์ยืนยัน", done: !!latestDraft?.effective },
  ];
  const activeMilestone = milestones.findIndex((item) => !item.done);

  return <>
    <div className="case-toolbar">
      <form className="search-form" role="search" onSubmit={(event) => { event.preventDefault(); props.loadList(); }}>
        <label className="sr-only" htmlFor="case-search">ค้นหารหัสเคส</label>
        <div className="search-field"><span aria-hidden="true">⌕</span><input id="case-search" type="search" placeholder="ค้นหารหัสเคสจำลอง" value={props.query} onChange={(event) => props.setQuery(event.target.value)} /></div>
        <label className="sr-only" htmlFor="case-status">สถานะร่าง</label>
        <select id="case-status" value={props.caseStatus} onChange={(event) => props.setCaseStatus(event.target.value)}><option value="">ทุกสถานะ</option>{Object.entries(handoffLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        <button className="button button--secondary">ค้นหา</button>
      </form>
      <button className="button button--primary button--create" onClick={() => props.setNewCaseOpen(!props.newCaseOpen)}><span aria-hidden="true">＋</span>เริ่มเคสจำลอง</button>
    </div>

    {props.newCaseOpen ? <form className="panel create-case" onSubmit={(event) => { event.preventDefault(); props.createCase(); }}>
      <div className="section-heading"><div><span className="eyebrow">ข้อมูลสังเคราะห์</span><h2>เริ่มเคสจำลองใหม่</h2><p className="supporting-text">ใช้รหัสที่จำง่ายและไม่เกี่ยวข้องกับข้อมูลผู้ป่วยจริง</p></div><button type="button" className="button button--text" onClick={() => props.setNewCaseOpen(false)}>ปิด</button></div>
      <div className="form-grid"><label>รหัสเคส<input required pattern="[A-Za-z0-9_-]+" value={props.caseId} onChange={(event) => props.setCaseId(event.target.value)} placeholder="เช่น demo-001" /></label><label>อายุผู้ป่วยสมมติ<input required type="number" min="18" max="120" value={props.age} onChange={(event) => props.setAge(Number(event.target.value))} /></label></div>
      <label className="check-control"><input required type="checkbox" /><span>ยืนยันว่าเคสนี้ไม่มีข้อมูลที่ระบุตัวผู้ป่วยจริง</span></label>
      <button className="button button--primary" disabled={props.busy}>สร้างและเปิดเคส</button>
    </form> : null}

    <div className="case-layout">
      <aside className="case-list" aria-label="รายการเคส">
        <div className="case-list__heading"><div><span className="eyebrow">คิวงานวันนี้</span><h2>เคสในพื้นที่</h2></div><StatusBadge tone="neutral">{props.cases.length}</StatusBadge></div>
        {!props.cases.length ? <div className="empty-state empty-state--compact"><h3>ยังไม่มีเคส</h3><p>เริ่มเคสจำลองเพื่อทดลองรับข้อมูล</p></div> : <div className="case-list__items">{props.cases.map((item) => <button className={`case-item ${props.current?.encounter_id === item.encounter_id ? "case-item--selected" : ""}`} key={item.encounter_id} onClick={() => props.changeCase(item.encounter_id)}>
          <div className="case-item__top"><span className="case-avatar" aria-hidden="true">{item.encounter_id.slice(0, 1).toUpperCase()}</span><span className="case-item__identity"><strong>{item.encounter_id}</strong><small>อายุ {item.age} ปี · รุ่น {item.case_revision}</small></span>{item.attention?.needs_attention ? <span className="attention-dot" aria-label="มีงานที่ต้องตรวจ" /> : null}</div>
          <div className="case-item__status"><StatusBadge tone={item.handoff_status === "CONFIRMED" ? "success" : item.handoff_status === "STALE" ? "warning" : "neutral"}>{handoffLabels[item.handoff_status || "NO_DRAFT"] || "ยังไม่มีร่าง"}</StatusBadge>{item.attention?.pending_proposal_count ? <small>{item.attention.pending_proposal_count} ข้อเสนอรอตรวจ</small> : null}</div>
        </button>)}</div>}
        {props.nextOffset !== null ? <button className="button button--text button--full" onClick={props.moreCases}>โหลดเคสเพิ่ม</button> : null}
      </aside>

      {!props.current ? <section className="empty-state empty-state--hero"><span className="empty-state__mark" aria-hidden="true">✦</span><span className="eyebrow">พื้นที่รับเคสพร้อมใช้งาน</span><h2>เลือกเคสเพื่อเริ่มทำงาน</h2><p>ผู้ช่วยจะช่วยเก็บข้อมูลอย่างเป็นขั้นตอน โดยทุกข้อมูลและร่างส่งต่อต้องผ่านการตรวจจากบุคลากร</p><ol><li><span>1</span><div><strong>รับข้อมูล</strong><small>สนทนาและระบุอาการสำคัญ</small></div></li><li><span>2</span><div><strong>ตรวจทาน</strong><small>ยืนยันเฉพาะข้อมูลที่ถูกต้อง</small></div></li><li><span>3</span><div><strong>ส่งให้แพทย์</strong><small>สร้างร่างและตรวจหลักฐาน</small></div></li></ol></section> : <div className="case-content">
        <section className="case-overview" aria-labelledby="case-title">
          <div className="case-overview__identity"><span className="case-overview__avatar" aria-hidden="true">{props.current.encounter_id.slice(0, 1).toUpperCase()}</span><div><span className="eyebrow">เคสสังเคราะห์</span><h2 id="case-title">{props.current.encounter_id}</h2><p>ผู้ป่วยสมมติอายุ {props.current.age} ปี · ข้อมูลรุ่น {props.current.case_revision}</p></div></div>
          <div className="case-overview__metrics"><div><strong>{props.facts.length}</strong><span>ข้อมูลยืนยัน</span></div><div><strong>{pendingProposals}</strong><span>ข้อเสนอรอตรวจ</span></div><div><strong>{latestDraft ? `ฉบับ ${latestDraft.draft_revision}` : "—"}</strong><span>ร่างล่าสุด</span></div></div>
          <button className="button button--secondary button--refresh" onClick={props.refresh}><span aria-hidden="true">↻</span>โหลดข้อมูลล่าสุด</button>
        </section>

        <ol className="workflow-steps" aria-label="ความคืบหน้าของเคส">{milestones.map((item, index) => {
          const state = item.done ? "complete" : index === activeMilestone ? "active" : "upcoming";
          return <li key={item.label} className={`workflow-step workflow-step--${state}`} aria-current={state === "active" ? "step" : undefined}><span className="workflow-step__number" aria-hidden="true">{item.done ? "✓" : index + 1}</span><span>{item.label}</span></li>;
        })}</ol>

        <div className="clinical-grid">
          <div className="primary-column">
            <section className="panel conversation-panel">
              <div className="assistant-heading"><span className="assistant-mark" aria-hidden="true">J</span><div><span className="eyebrow">JARVIS assistant</span><h2>สนทนาและรวบรวมข้อมูล</h2><p className="supporting-text">ผู้ช่วยจะเสนอข้อมูลให้ตรวจ และจะไม่บันทึกอัตโนมัติ</p></div><StatusBadge tone={props.caps?.provider === "mock-v2" ? "warning" : "info"}>{props.caps?.provider === "mock-v2" ? "โหมดออฟไลน์" : "รอตรวจโมเดลจริง"}</StatusBadge></div>
              <div className="conversation" aria-label="ประวัติการสนทนา">{!props.runs.length ? <div className="empty-state empty-state--conversation"><span aria-hidden="true">✦</span><h3>เริ่มจากอาการสำคัญ</h3><p>ลองพิมพ์ “ผู้ป่วยไอมา 2 วัน มีไข้ต่ำ” หรือถามผู้ช่วยว่าควรถามอะไรต่อ</p></div> : props.runs.map((run) => <article className="turn" key={run.run_id}>
                <div className="message-row message-row--user"><div className="message message--user"><span>คุณ</span><p>{run.user_text}</p></div><span className="message-avatar message-avatar--user" aria-hidden="true">{props.session.subject.slice(0, 1).toUpperCase()}</span></div>
                <div className="message-row"><span className="message-avatar" aria-hidden="true">J</span><div className="message message--assistant"><div><span className="eyebrow">ผู้ช่วย JARVIS</span><StatusBadge tone={run.status === "COMPLETED" ? "success" : "warning"}>{run.status === "COMPLETED" ? "ตอบแล้ว" : "ต้องตรวจสอบ"}</StatusBadge></div><p>{humanizeClinicalText(run.response)}</p>{run.status === "COMPLETED" ? <button className="button button--text button--speak" onClick={() => props.speak(humanizeClinicalText(run.response), run.run_id)}><span aria-hidden="true">◖</span>อ่านคำตอบ</button> : null}</div></div>
                <Proposals run={run} onDirty={(value) => props.trackDirty(run.run_id, value)} revision={props.current!.case_revision} act={props.act} />
              </article>)}</div>
              {!props.message ? <div className="quick-prompts" aria-label="ข้อความแนะนำ"><span>ลองถามผู้ช่วย</span><button type="button" onClick={() => props.setMessage("จากข้อมูลที่มี ควรถามอะไรต่อเพื่อให้รับเคสครบถ้วน?")}>ควรถามอะไรต่อ</button><button type="button" onClick={() => props.setMessage("ช่วยสรุปข้อมูลที่ยืนยันแล้วของเคสนี้แบบสั้น")}>สรุปข้อมูลที่มี</button><button type="button" onClick={() => props.setMessage("ช่วยตรวจว่าข้อมูลสำคัญส่วนใดยังขาดอยู่")}>ตรวจข้อมูลที่ขาด</button></div> : null}
              <div className="composer"><label className="sr-only" htmlFor="assistant-message">ข้อความถึงผู้ช่วย</label><textarea id="assistant-message" aria-label="ข้อความถึงผู้ช่วย" placeholder="พิมพ์ข้อมูล อาการ หรือคำถามที่ต้องการให้ผู้ช่วยช่วยต่อ…" value={props.message} onChange={(event) => props.setMessage(event.target.value)} /><div className="composer__footer"><div className="composer__tools"><button className={`button button--icon ${props.voiceState === "recording" ? "button--recording" : ""}`} aria-label={props.voiceState === "recording" ? "หยุดและถอดเสียง" : props.voiceState === "transcribing" ? "กำลังถอดเสียง" : "กดพูด"} title="กดพูด" disabled={!props.caps?.speech || (props.busy && props.voiceState === "idle")} onClick={props.record}>{props.voiceState === "recording" ? "■" : props.voiceState === "transcribing" ? "…" : "◉"}</button><span>{props.caps?.speech ? (props.voiceState === "recording" ? "กำลังบันทึกเสียง" : props.voiceState === "transcribing" ? "กำลังถอดเสียง" : "พิมพ์หรือกดพูด") : "พิมพ์ข้อความได้ทันที"}</span></div><button className="button button--primary button--send" aria-label="ส่งข้อความ" disabled={props.busy || !props.message.trim() || activeJob} onClick={() => props.startRun("conversation")}>ส่งให้ผู้ช่วย <span aria-hidden="true">→</span></button></div></div>
              {!props.caps?.speech ? <p className="voice-fallback">ยังไม่ตั้งค่าถอดเสียง การสนทนาด้วยข้อความใช้งานได้ครบทุกขั้นตอน</p> : null}
              <button className="button button--text stop-audio" onClick={props.stopAudio}>หยุดอ่านเสียง</button>
            </section>

            {latestDraft ? <section className="draft-workspace"><div className="content-divider"><div><span className="eyebrow">ร่างล่าสุด</span><h2>ตรวจร่างก่อนส่งต่อ</h2></div><p>ตรวจเนื้อหาและหลักฐานของฉบับล่าสุดในที่เดียว</p></div><Review key={latestDraft.draft_id} draft={latestDraft} revision={props.current.case_revision} canReview={props.session.role === "physician"} act={props.act} onDirty={(value) => props.trackDirty(latestDraft.draft_id, value)} />{olderDrafts.length ? <details className="older-drafts"><summary>ดูร่างก่อนหน้า {olderDrafts.length} รายการ</summary><div>{olderDrafts.map((draft) => <article key={draft.draft_id}><strong>ร่างฉบับที่ {draft.draft_revision}</strong><span>{draft.effective ? "ยืนยันแล้ว" : "เก็บเป็นประวัติ"}</span></article>)}</div></details> : null}</section> : null}
          </div>

          <aside className="case-sidebar">
            <section className="panel facts-panel"><div className="section-heading"><div><span className="eyebrow">ข้อมูลเคส</span><h2>ข้อมูลที่ยืนยันแล้ว</h2></div><StatusBadge tone="success">{props.facts.length} รายการ</StatusBadge></div>{!props.facts.length ? <div className="empty-state empty-state--compact"><h3>รอข้อมูลแรก</h3><p>ข้อเสนอจากผู้ช่วยจะปรากฏให้ตรวจในบทสนทนา</p></div> : <div className="fact-list">{props.facts.map((fact) => <FactView key={fact.event_id} fact={fact} onEdit={props.newFact} />)}</div>}<button className="button button--secondary button--full" onClick={() => props.newFact()}><span aria-hidden="true">＋</span>เพิ่มข้อมูลด้วยตัวเอง</button>{props.editing ? <form className="edit-surface" onSubmit={(event) => { event.preventDefault(); props.saveFact(); }}><h3>{props.editing.supersedes_event_id ? "แก้ไขข้อมูลเดิม" : "เพิ่มข้อมูล"}</h3><FactEditor key={props.editing.event_id} fact={props.editing} onChange={props.setEditing} /><div className="button-group"><button className="button button--primary" disabled={props.busy}>ตรวจแล้ว บันทึกข้อมูล</button><button type="button" className="button button--text" onClick={() => props.setEditing(null)}>ยกเลิก</button></div></form> : null}</section>
            <section className="panel next-action"><div className="next-action__icon" aria-hidden="true">→</div><span className="eyebrow">ขั้นตอนถัดไป</span><h2>{latestDraft ? "ร่างพร้อมให้ตรวจ" : "เตรียมสรุปส่งต่อ"}</h2><p>{latestDraft ? "เปิดร่างล่าสุดด้านล่างบทสนทนาเพื่อตรวจเนื้อหาและหลักฐาน" : "ระบบจะใช้เฉพาะข้อมูลที่ยืนยันแล้วและสร้างร่างให้แพทย์ตรวจอีกครั้ง"}</p><button className="button button--primary button--full" disabled={props.busy || activeJob} onClick={() => props.startRun("draft")}>{latestDraft ? "สร้างร่างจากข้อมูลล่าสุด" : "เตรียมร่างส่งต่อ"}</button></section>
            <History key={`${props.current.encounter_id}:${props.current.case_revision}`} encounter={props.current.encounter_id} />
          </aside>
        </div>
      </div>}
    </div>
  </>;
}
export { Review, Proposals, FactEditor };
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
