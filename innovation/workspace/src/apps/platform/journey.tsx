import React, { useEffect, useState } from "react";
import { apiCall, createIdempotencyKey } from "../../shared/api";
import type { Workspace } from "../../shared/useWorkspace";
import type { Fact, FactValue } from "../../shared/types";
import { journeyLabels } from "../../shared/types";
import { StatusBadge } from "../../shared/ui/StatusBadge";

type Finding = { code: string; severity: "major" | "moderate" | "info"; message: string; order_event_id: string | null; evidence_ids: string[]; source: "rule" | "agent" };
type Check = { status: string; formulary_version: string; orders: Fact[]; dispenses: Fact[]; findings: Finding[]; limitations: string[];
  agent?: { status: string; summary: string | null; model: string; provider: string; error_code?: string; trace: { tool: string; status: string; elapsed_ms: number }[] } };
type CaseDetail = { encounter_id: string; case_revision: number; events: { fact: Fact }[] };

const statusLabels: Record<string, [string, "success" | "warning" | "danger" | "info"]> = {
  VALID: ["ไม่พบประเด็นจากกฎตรวจ", "success"], NEEDS_PHARMACIST_REVIEW: ["ต้องให้เภสัชกรตรวจ", "danger"],
  INSUFFICIENT_INFORMATION: ["ข้อมูลไม่พอ", "warning"], NO_ORDERS: ["ไม่มีคำสั่งยา", "info"],
};
const outcomeLabels: Record<string, string> = { DISPENSED: "จ่ายยาแล้ว", HELD: "พักไว้", CONTACT_PRESCRIBER: "ติดต่อแพทย์" };

/** Journey facts are physician/pharmacist actions; the server enforces who may write each kind. */
export async function postFact(encounterId: string, revision: number, kind: string, value: FactValue) {
  const at = new Date().toISOString();
  await apiCall(`/encounters/${encodeURIComponent(encounterId)}/events`, "POST", { expected_revision: revision, idempotency_key: createIdempotencyKey(),
    fact: { event_id: crypto.randomUUID(), kind, value, observed_at: at, available_at_time: at, source: "STAFF_CONFIRMED" } });
}

const loadCase = (id: string) => apiCall<CaseDetail>(`/encounters/${encodeURIComponent(id)}`);
const orderText = (fact: Fact) => { const v = fact.value as Record<string, string | number>; return [v.drug, v.dose, v.route, v.frequency, v.days ? `${v.days} วัน` : ""].filter(Boolean).join(" · "); };

/** Physician: write medication orders and return precautions after confirming the draft. */
export function OrdersPanel({ ws, encounterId }: { ws: Workspace; encounterId: string }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [order, setOrder] = useState({ drug: "", dose: "", frequency: "", days: "" });
  const [precaution, setPrecaution] = useState("");
  const refresh = async () => setDetail(await loadCase(encounterId));
  useEffect(() => { ws.work(refresh); }, [encounterId, ws.current?.case_revision]);
  if (!detail) return null;
  const facts = detail.events.map(e => e.fact);
  const submit = (kind: string, value: FactValue, reset: () => void) => ws.work(async () => { await postFact(encounterId, detail.case_revision, kind, value); reset(); await refresh(); await ws.loadList(); });
  return <section className="panel journey-panel">
    <h2>คำสั่งยาและคำแนะนำก่อนกลับบ้าน</h2>
    <p>แพทย์เป็นผู้สั่งยา ระบบไม่สั่งยาเอง · เภสัชกรจะตรวจก่อนจ่าย</p>
    <ul>{facts.filter(f => f.kind === "MEDICATION_ORDER").map(f => <li key={f.event_id}>💊 {orderText(f)}</li>)}
      {facts.filter(f => f.kind === "RETURN_PRECAUTION").map(f => <li key={f.event_id}>⚠️ กลับมาทันทีถ้า: {String(f.value)}</li>)}</ul>
    <form className="journey-form" onSubmit={e => { e.preventDefault(); submit("MEDICATION_ORDER", { drug: order.drug, dose: order.dose || null, frequency: order.frequency || null, days: order.days ? Number(order.days) : null }, () => setOrder({ drug: "", dose: "", frequency: "", days: "" })); }}>
      <label>ชื่อยา<input required value={order.drug} onChange={e => setOrder({ ...order, drug: e.target.value })} placeholder="เช่น paracetamol" /></label>
      <label>ขนาด<input value={order.dose} onChange={e => setOrder({ ...order, dose: e.target.value })} placeholder="500 mg" /></label>
      <label>ความถี่<input value={order.frequency} onChange={e => setOrder({ ...order, frequency: e.target.value })} placeholder="ทุก 6 ชม." /></label>
      <label>จำนวนวัน<input type="number" min={1} max={365} value={order.days} onChange={e => setOrder({ ...order, days: e.target.value })} /></label>
      <button className="button">เพิ่มคำสั่งยา</button>
    </form>
    <form className="journey-form" onSubmit={e => { e.preventDefault(); submit("RETURN_PRECAUTION", precaution.trim(), () => setPrecaution("")); }}>
      <label>อาการที่ต้องกลับมา รพ. (Red flag)<input required value={precaution} onChange={e => setPrecaution(e.target.value)} placeholder="เช่น ไข้สูงเกิน 3 วัน หายใจเหนื่อย" /></label>
      <button className="button button--secondary">เพิ่มคำแนะนำ</button>
    </form>
    <a href={`#/passport/${encodeURIComponent(encounterId)}`}>เปิด Med Passport</a>
  </section>;
}

/** Pharmacist: rule check + Pharma Agent note, then the pharmacist records the dispense decision. */
export function PharmacyPage({ ws, selected }: { ws: Workspace; selected?: string }) {
  const [check, setCheck] = useState<Check | null>(null);
  const [revision, setRevision] = useState(0);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const queue = ws.cases.filter(c => c.journey_stage === "PHARMACY" || c.journey_stage === "PHARMACY_HOLD");
  const refresh = async (id: string) => {
    const [result, detail] = await Promise.all([apiCall<Check>(`/encounters/${encodeURIComponent(id)}/pharmacy-check`), loadCase(id)]);
    setCheck(result); setRevision(detail.case_revision);
  };
  useEffect(() => { setCheck(null); if (selected) ws.work(() => refresh(selected)); }, [selected]);
  const latest = (orderId: string) => check?.dispenses.filter(d => (d.value as { order_event_id: string }).order_event_id === orderId).at(-1);
  const decide = (orderId: string, outcome: string) => ws.work(async () => {
    const reason = reasons[orderId]?.trim();
    if (outcome !== "DISPENSED" && !reason) throw Error("กรุณาระบุเหตุผลเมื่อพักยาหรือติดต่อแพทย์");
    await postFact(selected!, revision, "DISPENSE", { order_event_id: orderId, outcome, reason: reason || null });
    await refresh(selected!); await ws.loadList();
  });
  const [label, tone] = check ? statusLabels[check.status] : ["", "info" as const];
  return <>
    <section className="medx-review-queue"><h2>คิวห้องยา</h2><div className="table-scroll"><table><caption>เคสที่แพทย์ยืนยันแล้วและมีคำสั่งยา · ข้อมูลสังเคราะห์</caption>
      <thead><tr><th scope="col">เคส</th><th scope="col">อายุ</th><th scope="col">ขั้นตอน</th><th scope="col">เปิด</th></tr></thead>
      <tbody>{queue.map(c => <tr key={c.encounter_id} aria-selected={c.encounter_id === selected}><th scope="row">{c.encounter_id}</th><td>{c.age}</td>
        <td><StatusBadge tone={c.journey_stage === "PHARMACY_HOLD" ? "warning" : "info"}>{journeyLabels[c.journey_stage!]}</StatusBadge></td>
        <td><a href={`#/pharmacy/${encodeURIComponent(c.encounter_id)}`}>ตรวจยา {c.encounter_id}</a></td></tr>)}</tbody></table></div>
      {!queue.length ? <p>ยังไม่มีเคสรอจ่ายยา</p> : null}</section>
    {selected && check ? <section className="panel">
      <h2>{selected} · <StatusBadge tone={tone}>{label}</StatusBadge></h2>
      <button className="button" onClick={() => ws.work(async () => { setCheck(await apiCall<Check>(`/encounters/${encodeURIComponent(selected)}/pharmacy-review`, "POST")); })}>ให้ Pharma Agent ช่วยตรวจ</button>
      {check.agent ? <div className="agent-note"><h3>ความเห็น Pharma Agent ({check.agent.model})</h3>
        {check.agent.status === "COMPLETED" ? <p>{check.agent.summary}</p> : <p>Agent ทำงานไม่สำเร็จ ({check.agent.error_code}) · แสดงผลจากกฎตรวจเท่านั้น</p>}
        <details><summary>trace ({check.agent.trace.length} tool calls)</summary><ol>{check.agent.trace.map((t, i) => <li key={i}>{t.tool} · {t.status} · {Math.round(t.elapsed_ms)} ms</li>)}</ol></details></div> : null}
      <h3>ประเด็นที่พบ ({check.findings.length})</h3>
      <ul className="findings">{check.findings.map((f, i) => <li key={i}><StatusBadge tone={f.severity === "major" ? "danger" : f.severity === "moderate" ? "warning" : "info"}>{f.severity}</StatusBadge> {f.message} {f.source === "agent" ? <em>(agent)</em> : null}</li>)}</ul>
      <h3>คำสั่งยา</h3>
      {check.orders.map(o => { const done = latest(o.event_id); return <article key={o.event_id} className="order-card">
        <p><strong>💊 {orderText(o)}</strong> {done ? <StatusBadge tone={(done.value as { outcome: string }).outcome === "DISPENSED" ? "success" : "warning"}>{outcomeLabels[(done.value as { outcome: string }).outcome]}</StatusBadge> : null}</p>
        {(done?.value as { outcome?: string } | undefined)?.outcome === "DISPENSED" ? null : <>
          <label>เหตุผล (จำเป็นเมื่อพักยา/ติดต่อแพทย์)<input value={reasons[o.event_id] || ""} onChange={e => setReasons({ ...reasons, [o.event_id]: e.target.value })} /></label>
          <div className="actions"><button className="button" onClick={() => decide(o.event_id, "DISPENSED")}>จ่ายยา</button>
            <button className="button button--secondary" onClick={() => decide(o.event_id, "HELD")}>พักไว้</button>
            <button className="button button--secondary" onClick={() => decide(o.event_id, "CONTACT_PRESCRIBER")}>ติดต่อแพทย์</button></div></>}
      </article>; })}
      <ul className="limitations">{check.limitations.map(l => <li key={l}>{l}</li>)}</ul>
      <a href={`#/passport/${encodeURIComponent(selected)}`}>เปิด Med Passport</a>
    </section> : <section className="empty-state"><h2>เลือกเคสจากคิวห้องยา</h2><p>ตรวจคำสั่งยาเทียบประวัติแพ้ยาและยาที่ใช้อยู่ ก่อนตัดสินใจจ่ายยา</p></section>}
  </>;
}

type Passport = { encounter_id: string; age: number; care_context: string; as_of: string; intake: Fact[];
  physician: { summary: string; reviewed_by: string; reviewed_at: string; still_current: boolean } | null;
  orders: (Fact & { dispense: Fact | null })[]; pharmacy: { status: string; findings: Finding[] };
  return_precautions: Fact[]; recorded_by: string[]; limitations: string[] };
type Assist = { status: string; patient_summary: string | null; proposed_return_precautions: string[]; model: string; error_code?: string };
const kindLabels: Record<string, string> = { CHIEF_COMPLAINT: "อาการสำคัญ", HISTORY: "ประวัติ", MEDICATION: "ยาที่ใช้อยู่", ALLERGY: "การแพ้ยา", VITAL: "สัญญาณชีพ", LAB: "ผลแล็บ", REPORT: "รายงาน" };
const factText = (f: Fact) => f.state !== "KNOWN" ? `(${f.state})` : typeof f.value === "object" && f.value && "unit" in f.value ? `${String(f.value.name)} ${String(f.value.value)} ${String(f.value.unit)}` : String(f.value);

/** Universal Med Passport: printable hand-off for the next station or the patient, plus FHIR export. */
export function PassportPage({ ws, encounterId }: { ws: Workspace; encounterId?: string }) {
  const [passport, setPassport] = useState<Passport | null>(null);
  const [assist, setAssist] = useState<Assist | null>(null);
  const id = encounterId ? encodeURIComponent(encounterId) : "";
  const refresh = async () => setPassport(await apiCall<Passport>(`/encounters/${id}/passport`));
  useEffect(() => { setPassport(null); setAssist(null); if (encounterId) ws.work(refresh); }, [encounterId]);
  if (!encounterId) return <section className="empty-state"><h2>เลือกเคสเพื่อเปิด Med Passport</h2><p>เปิดจากคิวตรวจทบทวนหรือห้องยา</p></section>;
  if (!passport) return null;
  const confirm = (text: string) => ws.work(async () => { const detail = await loadCase(encounterId); await postFact(encounterId, detail.case_revision, "RETURN_PRECAUTION", text);
    setAssist(a => a && { ...a, proposed_return_precautions: a.proposed_return_precautions.filter(p => p !== text) }); await refresh(); });
  return <article className="passport">
    <header className="passport__head"><div><span className="eyebrow">MedX · Universal Med Passport</span><h2>{passport.encounter_id}</h2>
      <p>ผู้ป่วยสมมติ อายุ {passport.age} ปี · {passport.care_context === "OPD_ADULT_GENERAL" ? "ผู้ป่วยนอก (OPD)" : "ห้องฉุกเฉิน (ED)"} · ข้อมูล ณ {new Date(passport.as_of).toLocaleString("th-TH")}</p></div>
      <div className="actions no-print"><button className="button" onClick={() => window.print()}>พิมพ์ / บันทึก PDF</button>
        <a className="button button--secondary" href={`/v2/encounters/${id}/passport/fhir`} download={`medx-passport-${passport.encounter_id}.json`}>ดาวน์โหลด FHIR</a></div></header>
    <section><h3>1 · ข้อมูลแรกรับ</h3><ul>{passport.intake.map(f => <li key={f.event_id}><strong>{kindLabels[f.kind] || f.kind}:</strong> {factText(f)}</li>)}</ul></section>
    <section><h3>2 · สรุปที่แพทย์ยืนยัน</h3>{passport.physician ? <><p className="summary-text">{passport.physician.summary}</p>
      <p className="supporting-text">ยืนยันโดย {passport.physician.reviewed_by} · {new Date(passport.physician.reviewed_at).toLocaleString("th-TH")}{passport.physician.still_current ? "" : " · มีข้อมูลใหม่หลังยืนยัน ต้องทบทวน"}</p></> : <p>ยังไม่มีสรุปที่แพทย์ยืนยัน</p>}</section>
    <section><h3>3 · ยา</h3>{passport.orders.length ? <ul>{passport.orders.map(o => <li key={o.event_id}>💊 {orderText(o)} — {o.dispense ? outcomeLabels[(o.dispense.value as { outcome: string }).outcome] : "รอห้องยา"}</li>)}</ul> : <p>ไม่มีคำสั่งยา</p>}
      <p className="supporting-text">ผลตรวจห้องยา: {statusLabels[passport.pharmacy.status]?.[0]} ({passport.pharmacy.findings.length} ประเด็น)</p></section>
    <section className="passport__redflag"><h3>4 · กลับมาโรงพยาบาลทันทีถ้ามีอาการ</h3>{passport.return_precautions.length ? <ul>{passport.return_precautions.map(f => <li key={f.event_id}>⚠️ {String(f.value)}</li>)}</ul> : <p>แพทย์ยังไม่ได้ระบุ</p>}</section>
    {ws.session?.role === "physician" ? <section className="no-print agent-note"><h3>Passport Agent</h3>
      <button className="button button--secondary" onClick={() => ws.work(async () => setAssist(await apiCall<Assist>(`/encounters/${id}/passport-assist`, "POST")))}>ให้ Agent ร่างคำอธิบายสำหรับผู้ป่วย</button>
      {assist ? assist.status === "COMPLETED" ? <><p className="summary-text">{assist.patient_summary}</p>
        {assist.proposed_return_precautions.map(p => <p key={p}>ข้อเสนอ: {p} <button className="button button--text" onClick={() => confirm(p)}>แพทย์ยืนยันเพิ่ม</button></p>)}</>
        : <p>Agent ทำงานไม่สำเร็จ ({assist.error_code})</p> : null}</section> : null}
    <footer><ul className="limitations">{passport.limitations.map(l => <li key={l}>{l}</li>)}</ul><p className="supporting-text">บันทึกโดย: {passport.recorded_by.join(", ")}</p></footer>
  </article>;
}
