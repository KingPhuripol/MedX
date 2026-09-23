import React from "react";
import type { Workspace } from "../../shared/useWorkspace";
import { FactView, Review, AgentTrace } from "../../shared/clinical";
import { handoffLabels, journeyLabels } from "../../shared/types";
import { StatusBadge } from "../../shared/ui/StatusBadge";
import { History } from "./system";
export function CasesPage({ ws, changeCase }: { ws: Workspace; changeCase: (id: string) => void }) {
  const latest = ws.drafts.at(-1);
  const queue = ws.cases.filter(c => c.handoff_status && c.handoff_status !== "NO_DRAFT");
  return <>
    <form className="case-toolbar" role="search" onSubmit={e => { e.preventDefault(); ws.work(() => ws.loadList()); }}><label>ค้นหารหัสเคส<input type="search" value={ws.query} onChange={e => ws.setQuery(e.target.value)} /></label><label>สถานะร่าง<select value={ws.caseStatus} onChange={e => ws.setCaseStatus(e.target.value)}><option value="">ทุกสถานะที่ส่งตรวจ</option>{Object.entries(handoffLabels).filter(([key]) => key !== "NO_DRAFT").map(([key,value]) => <option key={key} value={key}>{value}</option>)}</select></label><button className="button button--secondary">ค้นหา</button></form>
    <section className="medx-review-queue"><h2>คิวตรวจทบทวน</h2><div className="table-scroll"><table><caption>ร่างจาก MedX Intake · ข้อมูลสังเคราะห์</caption><thead><tr><th scope="col">เคส</th><th scope="col">อายุ</th><th scope="col">รุ่นข้อมูล</th><th scope="col">สถานะ</th><th scope="col">ขั้นตอน</th><th scope="col">เปิดตรวจ</th></tr></thead><tbody>{queue.map(c => <tr key={c.encounter_id} aria-selected={c.encounter_id === ws.current?.encounter_id}><th scope="row">{c.encounter_id}</th><td>{c.age}</td><td>{c.case_revision}</td><td>{handoffLabels[c.handoff_status!] || c.handoff_status}</td><td>{c.journey_stage ? <StatusBadge tone={c.journey_stage === "READY_HOME" ? "success" : c.journey_stage === "PHARMACY_HOLD" ? "warning" : "info"}>{journeyLabels[c.journey_stage] || c.journey_stage}</StatusBadge> : null}</td><td><button className="button button--text" onClick={() => changeCase(c.encounter_id)}>ตรวจเคส {c.encounter_id}</button></td></tr>)}</tbody></table></div>{!queue.length ? <p>ยังไม่มีร่างในรายการนี้ เตรียมร่างส่งตรวจจาก MedX Intake</p> : null}{ws.nextOffset !== null ? <button className="button button--text" onClick={() => ws.work(() => ws.loadList(ws.nextOffset!, true))}>โหลดเคสเพิ่ม</button> : null}</section>
    {ws.current ? <>
      <section className="medx-casebar"><div><h2>{ws.current.encounter_id}</h2><p>ข้อมูลรุ่น {ws.current.case_revision} · ผู้ป่วยสมมติ {ws.current.age} ปี</p></div><button className="button button--secondary" onClick={() => ws.work(async () => { await ws.load(ws.current!.encounter_id); await ws.loadList(); })}>โหลดข้อมูลล่าสุด</button><a href={`/nurse#/voice/${encodeURIComponent(ws.current.encounter_id)}/facts`}>แก้ข้อมูลต้นทางใน Intake</a></section>
      {latest ? <Review key={latest.draft_id} draft={latest} revision={ws.current.case_revision} canReview={ws.session?.role === "physician"} act={ws.act} onDirty={value => ws.trackDirty(latest.draft_id, value)} /> : <p>เคสนี้ยังไม่มีร่าง กรุณาเตรียมร่างใน MedX Intake</p>}
      <details className="panel"><summary>ข้อเท็จจริงต้นทางปัจจุบัน ({ws.facts.length})</summary>{ws.facts.map(f => <FactView key={f.event_id} fact={f} />)}</details>
      <History key={`${ws.current.encounter_id}:${ws.current.case_revision}:${latest?.review_sequence}`} encounter={ws.current.encounter_id} />
      <details className="panel"><summary>กราฟและ trace สำหรับตรวจสอบ</summary>{ws.runs.map(run => <section key={run.run_id}><AgentTrace run={run} /><a href={`/v2/runs/${run.run_id}/graph`} target="_blank" rel="noreferrer">เปิดกราฟที่บันทึก</a></section>)}</details>
    </> : <section className="empty-state"><h2>เลือกเคสจากคิวเพื่อทบทวน</h2><p>ตรวจข้อเสนอเทียบหลักฐาน ก่อนบันทึกการตัดสินใจของคุณ</p></section>}
  </>;
}
