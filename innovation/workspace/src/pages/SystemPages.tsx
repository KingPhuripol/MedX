import React from "react";
import type { Capability, Session } from "../types";
import { StatusBadge } from "../components/clinical";
import { Icon } from "../components/Icon";
import { BrandLogo } from "../components/BrandLogo";
import { Readiness } from "../components/system";

const roleLabels: Record<Session["role"], string> = { intake: "ผู้รับข้อมูล", physician: "แพทย์ผู้ตรวจ", evaluator: "ผู้ประเมินระบบ" };

export function LoginPage({ token, setToken, busy, login }: { token: string; setToken: (value: string) => void; busy: boolean; login: () => void }) {
  return <div className="login-layout"><section className="login-story"><BrandLogo /><span className="eyebrow">พื้นที่ทำงานสำหรับบุคลากร</span><h2>ข้อมูลครบขึ้น<br />ส่งต่อชัดขึ้น</h2><p>พื้นที่ทำงานที่ช่วยบุคลากรรวบรวมข้อมูล ตรวจทานหลักฐาน และเตรียมร่างส่งต่ออย่างเป็นขั้นตอน</p><ul><li><Icon name="check" /><span>บุคลากรตรวจทุกข้อมูลก่อนบันทึก</span></li><li><Icon name="check" /><span>ร่างทุกฉบับย้อนกลับถึงหลักฐานได้</span></li><li><Icon name="lock" /><span>รุ่นทดลองใช้ข้อมูลสังเคราะห์เท่านั้น</span></li></ul></section><section className="panel login-card"><span className="login-lock"><Icon name="lock" /></span><span className="eyebrow">เข้าสู่ระบบอย่างปลอดภัย</span><h2>ยินดีต้อนรับกลับ</h2><p>ใช้รหัสเข้าถึงส่วนตัวที่ผู้ดูแลจัดให้ ระบบจะไม่บันทึกรหัสในเบราว์เซอร์</p><label>รหัสเข้าถึง<input autoFocus type="password" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="current-password" placeholder="กรอกรหัสเข้าถึง" /></label><button className="button button--primary button--full" disabled={busy || !token} onClick={login}>{busy ? "กำลังตรวจสอบ…" : "เข้าสู่พื้นที่ทำงาน"}<Icon name="arrow" /></button><p className="login-help"><Icon name="lock" size={16} />เชื่อมต่อผ่าน session ที่ backend ตรวจสอบ</p></section></div>;
}

export function SettingsPage({ session, caps, logout }: { session: Session; caps: Capability | null; logout: () => void }) {
  return <div className="settings-page"><section className="settings-hero"><div><span className="eyebrow">System readiness</span><h2>สถานะความพร้อม</h2><p>แยกการตั้งค่า การเชื่อมต่อ และผลประเมิน เพื่อไม่แสดงสถานะพร้อมเกินหลักฐานจริง</p></div><StatusBadge tone="warning">ยังไม่ผ่าน clinical validation</StatusBadge></section><Readiness /><section className="panel account-card"><div className="account-identity"><span className="avatar avatar--large">{session.subject.slice(0, 1).toUpperCase()}</span><div><span className="eyebrow">บัญชีปัจจุบัน</span><h2>{session.subject}</h2><p>{roleLabels[session.role]}</p></div></div><dl><div><dt>พื้นที่ทำงาน</dt><dd>{session.workspace}</dd></div><div><dt>การสนทนา</dt><dd><StatusBadge tone={caps?.conversation ? "success" : "warning"}>{caps?.conversation ? "เปิดใช้" : "ยังไม่พร้อม"}</StatusBadge></dd></div><div><dt>การถอดเสียง</dt><dd><StatusBadge tone={caps?.speech ? "info" : "neutral"}>{caps?.speech ? "ตั้งค่าแล้ว" : "ยังไม่ตั้งค่า"}</StatusBadge></dd></div></dl><div className="account-footer"><p><Icon name="lock" size={16} />Credentials อยู่บนเซิร์ฟเวอร์และไม่แสดงในหน้านี้</p><button className="button button--secondary" onClick={logout}>ออกจากระบบ</button></div></section></div>;
}
