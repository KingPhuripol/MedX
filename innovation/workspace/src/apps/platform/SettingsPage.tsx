import React from "react";
import type { Capability, Session } from "../../shared/types";
import { StatusBadge } from "../../shared/ui/StatusBadge";
import { Icon } from "../../shared/ui/Icon";
import { Readiness } from "./system";

const roleLabels: Record<Session["role"], string> = { intake: "ผู้รับข้อมูล", physician: "แพทย์ผู้ตรวจ", pharmacist: "เภสัชกร", evaluator: "ผู้ประเมินระบบ" };


export function SettingsPage({ session, caps, logout }: { session: Session; caps: Capability | null; logout: () => void }) {
  return <div className="settings-page"><section className="settings-hero"><div><span className="eyebrow">System readiness</span><h2>สถานะความพร้อม</h2><p>แยกการตั้งค่า การเชื่อมต่อ และผลประเมิน เพื่อไม่แสดงสถานะพร้อมเกินหลักฐานจริง</p></div><StatusBadge tone="warning">ยังไม่ผ่าน clinical validation</StatusBadge></section><Readiness /><section className="panel account-card"><div className="account-identity"><span className="avatar avatar--large">{session.subject.slice(0, 1).toUpperCase()}</span><div><span className="eyebrow">บัญชีปัจจุบัน</span><h2>{session.subject}</h2><p>{roleLabels[session.role]}</p></div></div><dl><div><dt>พื้นที่ทำงาน</dt><dd>{session.workspace}</dd></div><div><dt>การสนทนา</dt><dd><StatusBadge tone={caps?.conversation ? "success" : "warning"}>{caps?.conversation ? "เปิดใช้" : "ยังไม่พร้อม"}</StatusBadge></dd></div><div><dt>การถอดเสียง</dt><dd><StatusBadge tone={caps?.speech ? "info" : "neutral"}>{caps?.speech ? "ตั้งค่าแล้ว" : "ยังไม่ตั้งค่า"}</StatusBadge></dd></div></dl><div className="account-footer"><p><Icon name="lock" size={16} />Credentials อยู่บนเซิร์ฟเวอร์และไม่แสดงในหน้านี้</p><button className="button button--secondary" onClick={logout}>ออกจากระบบ</button></div></section></div>;
}
