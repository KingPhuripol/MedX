import React, { useEffect, useState } from "react";
import { apiCall, createIdempotencyKey } from "../api";
import type { Fact, ReadinessReport } from "../types";
import { FactView, StatusBadge } from "./clinical";

export function History({ encounter }: { encounter: string }) {
  const [items, setItems] = useState<{ fact: Fact }[]>([]);
  const [cursor, setCursor] = useState<number | null>(0);
  const [error, setError] = useState("");
  const more = async () => {
    try {
      const page = await apiCall<{ items: { fact: Fact }[]; next_cursor: number | null }>(`/encounters/${encounter}/history?after=${cursor ?? 0}`);
      setItems((old) => [...old, ...page.items]);
      setCursor(page.next_cursor);
    } catch { setError("อ่านประวัติไม่ได้ กรุณาลองอีกครั้ง"); }
  };
  return <details className="panel history"><summary>ประวัติข้อมูลทั้งหมด</summary>{items.map((event) => <FactView key={event.fact.event_id} fact={event.fact} />)}{cursor !== null ? <button className="button button--text" onClick={more}>โหลดประวัติเพิ่ม</button> : null}{error ? <p className="field-error" role="alert">{error}</p> : null}</details>;
}

function ReadinessCell({ item }: { item: ReadinessReport["reasoning"] }) {
  const passed = item.connectivity === "PASSED" && item.smoke === "PASSED";
  return <>
    <td><StatusBadge tone={item.configured ? "info" : "neutral"}>{item.configured ? "ตั้งค่าแล้ว" : "ยังไม่ตั้งค่า"}</StatusBadge></td>
    <td><StatusBadge tone={item.connectivity === "PASSED" ? "success" : "warning"}>{item.connectivity === "PASSED" ? "ผ่าน" : "ยังไม่ยืนยัน"}</StatusBadge></td>
    <td><StatusBadge tone={item.smoke === "PASSED" ? "success" : "warning"}>{item.smoke === "PASSED" ? "ผ่าน" : "ยังไม่ยืนยัน"}</StatusBadge></td>
    <td><StatusBadge tone={item.evaluation === "PASSED" && passed ? "success" : "warning"}>{item.evaluation === "PASSED" && passed ? "ผ่าน" : "รอประเมิน"}</StatusBadge></td>
  </>;
}

export function Readiness() {
  const [data, setData] = useState<ReadinessReport | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => { apiCall<ReadinessReport>("/readiness").then(setData).catch(() => setError(true)); }, []);
  if (error) return <div className="empty-state empty-state--compact" role="alert"><h3>อ่านสถานะระบบไม่ได้</h3><p>เปิดหน้านี้ใหม่เพื่อลองเชื่อมต่ออีกครั้ง</p></div>;
  if (!data) return <div className="skeleton-stack" role="status" aria-label="กำลังตรวจสถานะ"><span /><span /><span /></div>;
  const rows: [keyof ReadinessReport, string][] = [["reasoning", "สนทนาและสรุป"], ["transcription", "ถอดเสียง"], ["synthesis", "อ่านออกเสียง"]];
  return <div className="table-scroll"><table><caption className="sr-only">สถานะความพร้อมของผู้ให้บริการแต่ละความสามารถ</caption><thead><tr><th scope="col">ความสามารถ</th><th scope="col">การตั้งค่า</th><th scope="col">เชื่อมต่อ</th><th scope="col">Smoke test</th><th scope="col">ประเมินคุณภาพ</th></tr></thead><tbody>{rows.map(([id, label]) => <tr key={id}><th scope="row">{label}</th><ReadinessCell item={data[id] as ReadinessReport["reasoning"]} /></tr>)}</tbody></table><p className="supporting-text">ผลเชื่อมต่อเป็นหลักฐานตามวันที่ตรวจ ยังไม่ใช่การรับรองทางคลินิก</p></div>;
}

type Experiment = { id: string; action: string; status: string; created_at: string; error?: string };

export function Research() {
  const [items, setItems] = useState<Experiment[]>([]);
  const [report, setReport] = useState<any>(null);
  const [selected, setSelected] = useState<Experiment | null>(null);
  const [design, setDesign] = useState("");
  const [error, setError] = useState("");
  const refresh = async () => { try { setItems(await apiCall<Experiment[]>("/experiments")); } catch (reason) { setError(reason instanceof Error ? reason.message : "อ่านผลไม่ได้"); } };
  useEffect(() => { refresh(); const timer = window.setInterval(refresh, 2000); return () => window.clearInterval(timer); }, []);
  const start = async (action: string, parentId?: string) => {
    try {
      setError("");
      await apiCall("/experiments", "POST", { action, parent_id: parentId, design: action === "freeze" ? design : null, idempotency_key: createIdempotencyKey() });
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "เริ่มงานไม่ได้"); }
  };
  const busy = items.some((item) => ["queued", "running"].includes(item.status));
  const choices = report?.baselines ? [...report.baselines, ...report.search.validation, ...report.random.validation] : [];
  const statusLabel: Record<string, string> = { queued: "อยู่ในคิว", running: "กำลังทำงาน", completed: "เสร็จแล้ว", failed: "ไม่สำเร็จ" };
  return <section className="panel research-panel">
    <div className="section-heading"><div><span className="eyebrow">พื้นที่ผู้ประเมิน</span><h2>การทดลอง Agent Design</h2></div><StatusBadge tone="info">Mock · ผลด้านซอฟต์แวร์</StatusBadge></div>
    <p>พัฒนา → ตรวจ validation → เลือกและตรึงแบบ → เปิด held-out โดยแยกข้อมูลทดลองจากฐานข้อมูลเคส</p>
    <button className="button button--primary" disabled={busy} onClick={() => start("search")}>เริ่มค้นหาและเปรียบเทียบ baseline</button>
    {error ? <div className="inline-message inline-message--danger" role="alert">{error}</div> : null}
    <div className="experiment-list">{!items.length ? <div className="empty-state empty-state--compact"><h3>ยังไม่มีการทดลอง</h3><p>เริ่มการค้นหาเพื่อสร้างผลเปรียบเทียบชุดแรก</p></div> : items.map((item) => <article className="experiment-item" key={item.id}><div><strong>{item.action}</strong><p className="supporting-text">{item.created_at}</p></div><StatusBadge tone={item.status === "completed" ? "success" : item.status === "failed" ? "danger" : "info"}>{statusLabel[item.status] || "กำลังตรวจ"}</StatusBadge>{item.error ? <p className="field-error">{item.error}</p> : null}{item.status === "completed" ? <button className="button button--text" onClick={async () => { try { setReport(await apiCall(`/experiments/${item.id}/report`)); setSelected(item); setDesign(""); } catch { setError("อ่านผลไม่ได้"); } }}>เปิดผลการทดลอง</button> : null}</article>)}</div>
    {report && selected ? <section className="report-surface"><h3>ผลที่เลือก: {selected.action}</h3>{choices.length ? <><div className="table-scroll"><table><thead><tr><th scope="col">แบบ</th><th scope="col">สำเร็จใน validation</th><th scope="col">Runs</th><th scope="col">Invalid</th></tr></thead><tbody>{choices.map((choice: any, index: number) => <tr key={index}><td>{choice.design.design_id}</td><td>{((choice.summary.success_rate || 0) * 100).toFixed(1)}%</td><td>{choice.summary.runs}</td><td>{choice.summary.invalid_runs}</td></tr>)}</tbody></table></div><label>เลือกแบบจากหลักฐาน validation<select value={design} onChange={(event) => setDesign(event.target.value)}><option value="">เลือกแบบก่อนตรึง</option>{choices.map((choice: any, index: number) => <option key={index} value={choice.design.design_id}>{choice.design.design_id}</option>)}</select></label><button className="button button--primary" disabled={busy || !design} onClick={() => start("freeze", selected.id)}>ตรึงแบบที่เลือก</button></> : null}{selected.action === "freeze" ? <button className="button button--primary" disabled={busy} onClick={() => start("heldout", selected.id)}>ประเมิน held-out จากแบบที่ตรึงแล้ว</button> : null}<details><summary>ดูการตั้งค่าและผลสำหรับตรวจย้อนกลับ</summary><pre>{JSON.stringify(report, null, 2)}</pre></details></section> : null}
    <div className="inline-message inline-message--info">ผล mock ใช้ตรวจพฤติกรรมซอฟต์แวร์ ยังไม่ใช่หลักฐานคุณภาพโมเดลหรือความถูกต้องทางคลินิก</div>
  </section>;
}
