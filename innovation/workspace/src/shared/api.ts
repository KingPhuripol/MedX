type PendingRequest = { path: string; options: RequestInit };

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

const errorMessages: Record<string, string> = {
  STALE_CASE_REVISION: "ข้อมูลเคสเปลี่ยนแล้ว กรุณาโหลดข้อมูลล่าสุดและทบทวนก่อนบันทึก",
  STALE_PROPOSAL: "ข้อมูลเปลี่ยนหลังผู้ช่วยเสนอ กรุณาทบทวนและขอข้อเสนอใหม่",
  STALE_REVIEW: "ร่างถูกตรวจโดยผู้ใช้อื่นแล้ว กรุณาโหลดฉบับล่าสุด",
  STALE_DRAFT: "ข้อมูลเคสเปลี่ยนแล้ว กรุณาสร้างและตรวจร่างฉบับล่าสุด",
  DRAFT_SUPERSEDED: "มีร่างฉบับใหม่กว่าแล้ว กรุณาตรวจร่างล่าสุด",
  ENCOUNTER_EXISTS: "รหัสเคสนี้มีอยู่แล้ว กรุณาเปิดเคสเดิม",
  AUTHENTICATION_REQUIRED: "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่",
  CSRF_REQUIRED: "เซสชันเปลี่ยน กรุณาเข้าสู่ระบบใหม่",
  ROLE_FORBIDDEN: "บัญชีนี้ไม่มีสิทธิ์ทำรายการดังกล่าว",
  RUN_IN_PROGRESS: "เคสนี้มีงานกำลังทำอยู่ กรุณารอให้เสร็จก่อน",
  PAID_BUDGET_EXCEEDED: "ยังไม่ได้เปิดวงเงินสำหรับบริการภายนอก",
  JOB_FAILED: "งานไม่สำเร็จ ข้อความที่กรอกยังอยู่ กรุณาลองอีกครั้ง",
  PROCESS_INTERRUPTED: "งานหยุดเมื่อระบบเริ่มใหม่ กรุณาส่งคำขออีกครั้ง",
  INVALID_PROVIDER_OUTPUT: "ผู้ช่วยตอบกลับในรูปแบบที่ตรวจไม่ผ่าน ระบบจึงไม่สร้างร่าง กรุณากดอีกครั้ง",
  INCOMPLETE_PROVIDER_OUTPUT: "ผู้ช่วยตอบไม่ครบ ระบบจึงไม่สร้างร่าง กรุณากดอีกครั้ง",
  PROVIDER_TIMEOUT: "ผู้ช่วยตอบช้าเกินกำหนด กรุณากดอีกครั้ง",
  PROVIDER_FAILURE: "เชื่อมต่อผู้ช่วยไม่สำเร็จ กรุณากดอีกครั้ง",
};

let csrfToken = "";
let pendingRequest: PendingRequest | null = null;

export const createIdempotencyKey = () => crypto.randomUUID();
export const setCsrfToken = (value: string) => { csrfToken = value; };
export const hasPendingRequest = () => pendingRequest !== null;
export const clearPendingRequest = () => { pendingRequest = null; };

export async function apiCall<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  // Sign-in and sign-out stay open while a request is unresolved: they write no clinical data,
  // and blocking them would leave an expired session unable to authenticate to retry anything.
  if (pendingRequest && method !== "GET" && !path.startsWith("/session")) {
    throw Error("มีคำขอที่ยังไม่ทราบผล กรุณาตรวจคำขอเดิมก่อน");
  }
  const options: RequestInit = {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  };
  return sendApi<T>(path, options);
}

export async function sendApi<T>(path: string, options: RequestInit): Promise<T> {
  let response: Response;
  let data: any;
  try {
    response = await fetch("/v2" + path, {
      ...options,
      credentials: "same-origin",
      signal: AbortSignal.timeout(30000),
    });
    data = await response.json();
  } catch {
    if (options.method !== "GET" && !path.startsWith("/session")) pendingRequest = { path, options };
    throw Error("เครือข่ายขัดข้อง ข้อความที่กรอกยังอยู่ กรุณาตรวจคำขอเดิม");
  }
  if (!response.ok) {
    if (response.status >= 500 && options.method !== "GET") pendingRequest = { path, options };
    else pendingRequest = null;
    const code = typeof data?.error === "string" ? data.error : data?.error?.code;
    const detail = data?.details?.current_revision
      ? ` ข้อมูลปัจจุบันเป็นรุ่น ${data.details.current_revision}`
      : "";
    throw new ApiError(code || "UNKNOWN_ERROR", (errorMessages[code] || "บันทึกไม่ได้ กรุณาตรวจข้อมูลที่กรอก") + detail, response.status);
  }
  pendingRequest = null;
  return data as T;
}

export async function retryPendingRequest<T>(): Promise<T> {
  if (!pendingRequest) throw Error("ไม่มีคำขอที่ต้องตรวจซ้ำ");
  const request = pendingRequest;
  return sendApi<T>(request.path, request.options);
}

export function jobError(code?: string | null): string {
  return errorMessages[code || ""] || "งานไม่สำเร็จ ข้อความที่กรอกยังอยู่";
}

// Speech is not a clinical write, so it never latches a pending request for replay.
export async function transcribeAudio(audio: Blob): Promise<string> {
  const body = new FormData(); body.append("file", audio, "recording.webm");
  const response = await fetch("/v2/speech/transcriptions", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrfToken }, body });
  if (!response.ok) throw Error("ถอดเสียงไม่สำเร็จ ข้อความเดิมยังอยู่และพิมพ์ต่อได้");
  return (await response.json()).text;
}

export async function synthesizeSpeech(runId: string): Promise<Blob> {
  const response = await fetch(`/v2/runs/${runId}/speech`, { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrfToken } });
  if (!response.ok) throw Error("อ่านเสียงไม่สำเร็จ ใช้ข้อความต่อได้");
  return response.blob();
}
