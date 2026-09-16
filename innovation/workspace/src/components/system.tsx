import React, { useEffect, useState } from "react";
import { apiCall, createIdempotencyKey } from "../api";
import type { Fact, ReadinessReport } from "../types";
import { FactView, StatusBadge } from "./clinical";
import { Icon, type IconName } from "./Icon";

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

export function Readiness() {
  const [data, setData] = useState<ReadinessReport | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => { apiCall<ReadinessReport>("/readiness").then(setData).catch(() => setError(true)); }, []);
  if (error) return <div className="empty-state empty-state--compact" role="alert"><h3>อ่านสถานะระบบไม่ได้</h3><p>เปิดหน้านี้ใหม่เพื่อลองเชื่อมต่ออีกครั้ง</p></div>;
  if (!data) return <div className="skeleton-stack" role="status" aria-label="กำลังตรวจสถานะ"><span /><span /><span /></div>;
  const rows: [keyof ReadinessReport, string, IconName][] = [["reasoning", "สนทนาและสรุป", "spark"], ["transcription", "ถอดเสียง", "mic"], ["synthesis", "อ่านออกเสียง", "volume"]];
  return <div><div className="readiness-grid" aria-label="สถานะความพร้อมของผู้ให้บริการ">{rows.map(([id, label, icon]) => { const item = data[id] as ReadinessReport["reasoning"]; const passed = item.connectivity === "PASSED" && item.smoke === "PASSED"; return <article className="readiness-card" key={id}><div className="readiness-card__heading"><span className="readiness-card__icon"><Icon name={icon} /></span><div><h3>{label}</h3><p>{item.configured ? "มีการตั้งค่าบนเซิร์ฟเวอร์" : "ยังไม่มีการตั้งค่า"}</p></div></div><div className="readiness-checks"><div className="readiness-check"><span>การตั้งค่า</span><StatusBadge tone={item.configured ? "info" : "neutral"}>{item.configured ? "ตั้งค่าแล้ว" : "ยังไม่ตั้งค่า"}</StatusBadge></div><div className="readiness-check"><span>การเชื่อมต่อ</span><StatusBadge tone={item.connectivity === "PASSED" ? "success" : "warning"}>{item.connectivity === "PASSED" ? "ผ่าน" : "ยังไม่ยืนยัน"}</StatusBadge></div><div className="readiness-check"><span>Smoke test</span><StatusBadge tone={item.smoke === "PASSED" ? "success" : "warning"}>{item.smoke === "PASSED" ? "ผ่าน" : "ยังไม่ยืนยัน"}</StatusBadge></div><div className="readiness-check"><span>ประเมินคุณภาพ</span><StatusBadge tone={item.evaluation === "PASSED" && passed ? "success" : "warning"}>{item.evaluation === "PASSED" && passed ? "ผ่าน" : "รอประเมิน"}</StatusBadge></div></div></article>; })}</div><p className="supporting-text readiness-note">ผลเชื่อมต่อเป็นหลักฐานตามวันที่ตรวจ ยังไม่ใช่การรับรองทางคลินิก</p></div>;
}

type Experiment = { id: string; action: string; status: string; created_at: string; error?: string };

const experimentActionLabels: Record<string, string> = {
  search: "ค้นหาแบบ agent",
  validation: "ตรวจ validation",
  freeze: "ตรึงแบบที่เลือก",
  heldout: "ประเมินชุด held-out",
};

const experimentStages = [
  ["search", "ค้นหา", "เปรียบเทียบ baseline และแบบที่เสนอ"],
  ["validation", "ตรวจ validation", "คัดแบบที่น่าเชื่อถือใน development"],
  ["freeze", "ตรึงแบบ", "ล็อกแบบก่อนเปิดข้อมูลทดสอบ"],
  ["heldout", "ประเมิน held-out", "วัดผลบนเคสที่ไม่ใช้ในการออกแบบ"],
] as const;

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
  const completedActions = new Set(items.filter((item) => item.status === "completed").map((item) => item.action));
  const activeStage = items.find((item) => ["queued", "running"].includes(item.status))?.action ||
    (completedActions.has("heldout") ? "heldout" : completedActions.has("freeze") ? "heldout" : completedActions.has("search") ? "validation" : "search");
  const completedCount = items.filter((item) => item.status === "completed").length;
  return <section className="panel research-panel">
    <div className="experiment-hero"><div><span className="eyebrow">พื้นที่ผู้ประเมิน</span><h2>ออกแบบ agent อย่างมีหลักฐาน</h2><p>ค้นหาแบบที่เหมาะสม ตรวจ validation แล้วตรึงก่อนเปิดชุด held-out โดยแยกข้อมูลทดลองจากฐานข้อมูลเคส</p></div><div className="experiment-hero__mark" aria-hidden="true"><Icon name="spark" /></div></div>
    <div className="experiment-stagebar" aria-label="ขั้นตอนการทดลอง">
      {experimentStages.map(([id, label, description], index) => {
        const isDone = id === "search" ? completedActions.has("search") : id === "freeze" ? completedActions.has("freeze") : id === "heldout" ? completedActions.has("heldout") : completedActions.has("search");
        const isActive = activeStage === id;
        return <div className={`experiment-stage ${isDone ? "experiment-stage--done" : ""} ${isActive ? "experiment-stage--active" : ""}`} key={id}><span className="experiment-stage__number">{isDone ? <Icon name="check" /> : index + 1}</span><div><strong>{label}</strong><small>{description}</small></div></div>;
      })}
    </div>
    <div className="experiment-summary" aria-label="สรุปการทดลอง"><article><span>การรันทั้งหมด</span><strong>{items.length}</strong></article><article><span>เสร็จแล้ว</span><strong>{completedCount}</strong></article><article><span>สถานะปัจจุบัน</span><strong>{busy ? "กำลังทำงาน" : completedActions.has("heldout") ? "มีผล held-out" : "พร้อมเริ่ม"}</strong></article></div>
    <div className="experiment-toolbar"><div><h3>เริ่มรอบการค้นหา</h3><p className="supporting-text">ระบบจะรัน baseline, fixed workflow และ random search ด้วยงบเท่ากัน</p></div><button className="button button--primary" disabled={busy} onClick={() => start("search")}><Icon name="spark" />เริ่มค้นหาและเปรียบเทียบ</button></div>
    {error ? <div className="inline-message inline-message--danger" role="alert">{error}</div> : null}
    <div className="experiment-list">{!items.length ? <div className="empty-state empty-state--compact"><span className="empty-state__mark"><Icon name="research" /></span><h3>ยังไม่มีการทดลอง</h3><p>เริ่มการค้นหาเพื่อสร้างผลเปรียบเทียบชุดแรก</p></div> : items.map((item) => <article className="experiment-item" key={item.id}><div className="experiment-item__title"><span className="metric-icon"><Icon name={item.action === "search" ? "search" : item.action === "heldout" ? "check" : "research"} /></span><div><strong>{experimentActionLabels[item.action] || "การทดลอง"}</strong><p className="supporting-text">เริ่มเมื่อ {item.created_at}</p></div></div><StatusBadge tone={item.status === "completed" ? "success" : item.status === "failed" ? "danger" : "info"}>{statusLabel[item.status] || "กำลังตรวจ"}</StatusBadge>{item.error ? <p className="field-error">{item.error}</p> : null}{item.status === "completed" ? <button className="button button--text" onClick={async () => { try { setReport(await apiCall(`/experiments/${item.id}/report`)); setSelected(item); setDesign(""); } catch { setError("อ่านผลไม่ได้"); } }}>เปิดผลการทดลอง</button> : null}</article>)}</div>
    {report && selected ? <section className="report-surface"><div className="section-heading"><div><span className="eyebrow">ผลการทดลอง</span><h3>{experimentActionLabels[selected.action] || "ผลที่เลือก"}</h3></div><StatusBadge tone="success">ตรวจสอบย้อนกลับได้</StatusBadge></div>{choices.length ? <><div className="table-scroll"><table><caption className="sr-only">เปรียบเทียบแบบ agent จาก validation</caption><thead><tr><th scope="col">แบบ</th><th scope="col">สำเร็จใน validation</th><th scope="col">Runs</th><th scope="col">Invalid</th></tr></thead><tbody>{choices.map((choice: any, index: number) => <tr key={index}><td><strong>{choice.design.design_id}</strong></td><td>{((choice.summary.success_rate || 0) * 100).toFixed(1)}%</td><td>{choice.summary.runs}</td><td>{choice.summary.invalid_runs}</td></tr>)}</tbody></table></div><label>เลือกแบบจากหลักฐาน validation<select value={design} onChange={(event) => setDesign(event.target.value)}><option value="">เลือกแบบก่อนตรึง</option>{choices.map((choice: any, index: number) => <option key={index} value={choice.design.design_id}>{choice.design.design_id}</option>)}</select></label><button className="button button--primary" disabled={busy || !design} onClick={() => start("freeze", selected.id)}><Icon name="lock" />ตรึงแบบที่เลือก</button></> : null}{selected.action === "freeze" ? <button className="button button--primary" disabled={busy} onClick={() => start("heldout", selected.id)}><Icon name="check" />ประเมิน held-out จากแบบที่ตรึงแล้ว</button> : null}<details><summary>ดูการตั้งค่าและผลสำหรับผู้ประเมิน</summary><pre>{JSON.stringify(report, null, 2)}</pre></details></section> : null}
    <div className="inline-message inline-message--info">ผล mock ใช้ตรวจพฤติกรรมซอฟต์แวร์ ยังไม่ใช่หลักฐานคุณภาพโมเดลหรือความถูกต้องทางคลินิก</div>
  </section>;
}
