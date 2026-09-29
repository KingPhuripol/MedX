/** Exact Thai copy for MedX Live (slices/v1/SPEC.md section 2.4 and 2.5). */
import type { RealtimeConfig } from "@/lib/realtime";

export type LiveState =
  | "loading"
  | "disabled"
  | "idle"
  | "connecting"
  | "listening"
  | "processing"
  | "speaking"
  | "error"
  | "ended";

export const STATUS_TH: Record<LiveState, string> = {
  loading: "กำลังตรวจสอบโหมดเสียง…",
  disabled: "โหมดเสียงยังไม่เปิดใช้งาน — ใช้การพิมพ์แทนได้",
  idle: "พร้อมเริ่มสนทนา",
  connecting: "กำลังเชื่อมต่อ…",
  listening: "กำลังฟัง…",
  processing: "กำลังบันทึก…",
  speaking: "MedX กำลังพูด…",
  error: "การเชื่อมต่อขัดข้อง",
  ended: "จบการสนทนาแล้ว",
};

export const MUTED_STATUS_TH = "ปิดไมค์อยู่ — แตะปุ่มไมค์เพื่อเปิด";
export const NEAR_END_STATUS_TH = "ใกล้หมดเวลา";
export const IDLE_SUBLINE_TH = "พยาบาลถือเครื่องไว้ใกล้ผู้ป่วย แล้วกดเริ่มเมื่อพร้อม";

export const DISABLED_REASON_TH: Record<string, string> = {
  voice_disabled: "ผู้ดูแลระบบยังไม่เปิดโหมดเสียง",
  not_configured: "ยังไม่ได้ตั้งค่าบริการเสียง",
  access_code_not_configured: "ยังไม่ได้ตั้งรหัสเข้าใช้โหมดเสียงสำหรับเดโมสาธารณะ",
};
export const CONFIG_UNAVAILABLE_TH = "ไม่สามารถตรวจสอบสถานะโหมดเสียงได้";

export const ERROR_TH = {
  mic: "ไม่ได้รับสิทธิ์ใช้ไมโครโฟน — อนุญาตในการตั้งค่าเบราว์เซอร์ หรือพิมพ์แทน",
  insecure: "ต้องเปิดผ่าน HTTPS จึงจะใช้ไมโครโฟนได้",
  codeInvalid: "รหัสเข้าใช้ไม่ถูกต้อง",
  codeMissing: "กรุณากรอกรหัสเข้าใช้โหมดเสียง",
  rateLimited: "เริ่มสนทนาบ่อยเกินไป ลองใหม่ในอีกสักครู่",
  connect: "เชื่อมต่อบริการเสียงไม่สำเร็จ",
  finish: "บันทึกสรุปไม่สำเร็จ — กดลองใหม่เพื่อจบการสนทนาอีกครั้ง",
} as const;

export const HINT_TH = {
  notHeard: "ไม่ได้ยินชัดเจน กรุณาพูดอีกครั้ง",
  audioFailed: "เสียงขัดข้อง — โปรดอ่านคำถามบนจอให้ผู้ป่วยฟัง",
  turnFailed: "บันทึกประโยคไม่สำเร็จ — กรุณาพูดหรือพิมพ์อีกครั้ง",
} as const;

export const ALERT_TH = {
  nurseAttention: "พบสัญญาณอันตราย: มีคำพูดที่ต้องให้พยาบาลประเมินทันที",
  allergyConflict:
    "ข้อมูลแพ้ยาขัดแย้ง: คำตอบภายหลังไม่ตรงกับประวัติแพ้ยาที่บันทึกไว้ ระบบคงประวัติเดิมไว้ — พยาบาลโปรดยืนยันกับผู้ป่วย",
  extraction: "ระบบสกัดข้อมูลไม่สำเร็จ — พยาบาลบันทึกต่อเอง",
} as const;

export function vendorBannerTh(label: string): string {
  return `เสียงถูกส่งไปยัง ${label} — ใช้กับบทสังเคราะห์เท่านั้น`;
}

export function fmtClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export type DisabledReason = NonNullable<RealtimeConfig["reason"]>;
