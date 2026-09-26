import React, { useEffect, useState } from "react";
import { Shell, mount } from "../../shared/Shell";
import { apiCall, createIdempotencyKey } from "../../shared/api";
import { useWorkspace } from "../../shared/useWorkspace";
import { FactEditor, ScreenFindings } from "../../shared/clinical";
import { SideSheet } from "../../shared/SideSheet";
import { pendingProposalCount } from "../../shared/workflow";
import { type Fact, type SafetyScreen } from "../../shared/types";
import { IntakeStep, FactsStep } from "./IntakeStages";

const route = () => {
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  return { id: parts[1] ? decodeURIComponent(parts[1]) : undefined, step: parts[2] === "facts" ? "facts" as const : "intake" as const };
};
function NurseApp() {
  const ws = useWorkspace();
  const [step, setStep] = useState<"intake" | "facts">(route().step);
  const [creating, setCreating] = useState(false);
  const [caseId, setCaseId] = useState("");
  const [age, setAge] = useState(40);
  const [careContext, setCareContext] = useState("ED_FIRST_CONTACT_ADULT_NON_TRAUMA_NON_OBSTETRIC");
  const [screen, setScreen] = useState<SafetyScreen | null>(null);
  const initialize = async () => {
    const session = await ws.bootstrap();
    if (session.role !== "evaluator" && session.role !== "pharmacist") { const id = route().id; if (id) await ws.load(id); }
  };
  useEffect(() => { ws.work(initialize, true); }, []);
  useEffect(() => {
    const changed = () => { const next = route(); setStep(next.step); if (next.id && next.id !== ws.currentRef.current?.encounter_id) ws.work(async () => { await ws.load(next.id!); }); };
    window.addEventListener("hashchange", changed); return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    let cancelled = false; setScreen(null);
    if (ws.current) apiCall<SafetyScreen>(`/encounters/${encodeURIComponent(ws.current.encounter_id)}/screen`).then(value => { if (!cancelled) setScreen(value); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [ws.current?.encounter_id, ws.current?.case_revision]);
  const navigate = (next: "intake" | "facts", id = ws.current?.encounter_id) => {
    if (ws.unsaved && !window.confirm("มีข้อมูลที่ยังไม่บันทึก ต้องการเปลี่ยนหน้าหรือไม่?")) return;
    ws.setEditing(null); setStep(next); location.hash = id ? `#/voice/${encodeURIComponent(id)}/${next}` : "#/voice";
  };
  const create = () => ws.work(async () => {
    await apiCall("/encounters", "POST", { encounter_id: caseId, age, care_context: careContext }, { "Idempotency-Key": createIdempotencyKey() });
    setCreating(false); await ws.loadList(); await ws.load(caseId); navigate("intake", caseId);
  });
  const newFact = (old?: Fact) => {
    const timestamp = new Date().toISOString();
    ws.setEditing({ event_id: createIdempotencyKey(), kind: old?.kind || "CHIEF_COMPLAINT", state: old?.state || "KNOWN", value: old?.value || "", observed_at: timestamp, available_at_time: timestamp, supersedes_event_id: old?.event_id || null, source: "STAFF_CONFIRMED" });
  };
  const save = () => ws.current && ws.editing && ws.work(async () => {
    await apiCall(`/encounters/${ws.current!.encounter_id}/events`, "POST", { expected_revision: ws.current!.case_revision, idempotency_key: createIdempotencyKey(), fact: ws.editing });
    ws.setEditing(null); await ws.load(ws.current!.encounter_id); await ws.loadList();
  });
  const pending = ws.current ? pendingProposalCount(ws.runs, ws.current.case_revision) : 0;
  const latest = ws.drafts.at(-1);
  const ready = latest && latest.case_revision === ws.current?.case_revision;
  const active = !!ws.job && ["queued", "running"].includes(ws.job.status);
  return <Shell product="nurse" identity={{ name: "MedX Intake", tagline: "รับข้อมูลและซักประวัติ" }}
    nav={[{ id: "intake", label: "รับข้อมูล", description: "สนทนาและตรวจ transcript", icon: "mic" }, { id: "facts", label: "ยืนยันข้อมูล", description: "ตรวจข้อมูลก่อนส่ง", icon: "check" }]} page={step} onNavigate={navigate}
    switchLink={{ href: "/platform", label: "MedX Clinical Review", icon: "cases" }} title="รับข้อมูลและซักประวัติ" description="รวบรวม ตรวจยืนยัน และเตรียมข้อมูลให้ผู้ตรวจทบทวน" ws={ws} onSignedIn={initialize}>
    {ws.session?.role === "evaluator" ? <p>บัญชีผู้ประเมินใช้งานที่ <a href="/platform#/experiments">MedX Clinical Review</a></p> : ws.session?.role === "pharmacist" ? <p>บัญชีเภสัชกรใช้งานที่ <a href="/platform">MedX Clinical Review</a></p> : ws.session ? <>
      <section className="medx-casebar" aria-label="เลือกเคสรับข้อมูล"><label>เคสสังเคราะห์<select value={ws.current?.encounter_id || ""} onChange={e => navigate("intake", e.target.value)}><option value="" disabled>เลือกเคส</option>{ws.cases.map(c => <option key={c.encounter_id} value={c.encounter_id}>{c.encounter_id} · {c.age} ปี</option>)}</select></label><button className="button button--secondary" onClick={() => setCreating(!creating)}>เริ่มเคสจำลอง</button>{ws.nextOffset !== null ? <button className="button button--text" onClick={() => ws.work(() => ws.loadList(ws.nextOffset!, true))}>โหลดเคสเพิ่ม</button> : null}{ws.current ? <span>ข้อมูลรุ่น {ws.current.case_revision} · {ws.facts.length} รายการยืนยันแล้ว</span> : null}</section>
      {creating ? <form className="panel create-case" onSubmit={e => { e.preventDefault(); create(); }}><h2>เริ่มเคสจำลองใหม่</h2><div className="form-grid"><label>รหัสเคส<input required pattern="[A-Za-z0-9_\-]+" value={caseId} onChange={e => setCaseId(e.target.value)} /></label><label>อายุผู้ป่วยสมมติ<input required type="number" min="18" max="120" value={age} onChange={e => setAge(Number(e.target.value))} /></label><label>จุดบริการ<select value={careContext} onChange={e => setCareContext(e.target.value)}><option value="ED_FIRST_CONTACT_ADULT_NON_TRAUMA_NON_OBSTETRIC">ED คัดกรองแรกรับ</option><option value="OPD_ADULT_GENERAL">OPD ผู้ใหญ่ทั่วไป</option></select></label></div><label className="check-control"><input required type="checkbox" />ยืนยันว่าเคสนี้ไม่มีข้อมูลที่ระบุตัวผู้ป่วยจริง</label><button className="button button--primary" disabled={ws.busy}>สร้างและเปิดเคส</button></form> : null}
      {!ws.current ? <section className="empty-state"><h2>เริ่มต้นด้วยข้อมูลที่บุคลากรตรวจแล้ว</h2><p>สร้างหรือเลือกเคส เพื่อซักประวัติและยืนยันข้อมูลก่อนส่งให้ผู้ตรวจทบทวน</p></section> : <>
        {screen ? <ScreenFindings screen={screen} /> : null}
        {step === "intake" ? <IntakeStep props={{ ...ws, session: ws.session, changeStep: navigate, newFact }} pending={pending} /> : <FactsStep props={{ ...ws, session: ws.session, changeStep: navigate, newFact }} />}
        <section className="medx-handoff" aria-label="ส่งร่างให้ผู้ตรวจ"><div><strong>{ready ? "ร่างพร้อมอยู่ในคิวตรวจแล้ว" : "เตรียมร่างจากข้อมูลที่ยืนยัน"}</strong><p>{pending ? "มีข้อเสนอรอตรวจ โปรดยืนยันก่อนเตรียมร่าง" : "การสร้างร่างยังไม่ใช่การอนุมัติหรือส่งต่อผู้ป่วยจริง"}</p></div><button className="button button--primary" disabled={ws.busy || active || !ws.facts.length || pending > 0 || ws.dirty || !!ws.editing} onClick={() => ws.startRun("draft", "เตรียมร่างจากข้อมูลที่ยืนยันแล้ว")}>เตรียมร่างส่งตรวจ</button>{ready ? <a className="button button--secondary" href={`/platform#/cases/${encodeURIComponent(ws.current.encounter_id)}/draft`}>เปิดร่างใน Clinical Review</a> : null}</section>
      </>}
      {ws.editing ? <SideSheet title={ws.editing.supersedes_event_id ? "แก้ไขข้อมูลเดิม" : "เพิ่มข้อมูล"} description="ตรวจสถานะ ค่า และเวลาของหลักฐาน" onClose={() => ws.setEditing(null)}><form onSubmit={e => { e.preventDefault(); save(); }}><FactEditor key={ws.editing.event_id} fact={ws.editing} onChange={ws.setEditing} /><button className="button button--primary" disabled={ws.busy}>ตรวจแล้ว บันทึกข้อมูล</button></form></SideSheet> : null}
    </> : null}
  </Shell>;
}
mount(NurseApp);
