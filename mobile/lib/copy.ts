/**
 * Every UI string of the mobile scribe (slice v2c SPEC §5, byte-exact).
 * Notices are {head, body}: the spec's "↵" separates them and is never rendered.
 * Strings the approved §5 does not contain live under PROPOSED_V2C (D-V2C-2) for owner confirmation.
 */

export interface Notice {
  head: string;
  body: string;
}

export const FIELD_LABELS: Record<string, string> = {
  chief_complaint: "อาการสำคัญ",
  onset_duration: "ระยะเวลาที่เป็น",
  severity: "ความรุนแรง",
  allergy_status: "ประวัติแพ้ยา",
  current_medications: "ยาที่ใช้อยู่",
  relevant_history: "โรคประจำตัว",
};

export const COPY = {
  limit: "ข้อมูลสังเคราะห์ · ต้นแบบเพื่อการวิจัย",

  login: {
    heading: "บันทึกซักประวัติข้างเตียง",
    purpose: "สำหรับพยาบาล อัดเสียงบทสนทนากับผู้ป่วย แล้วตรวจทานข้อมูลก่อนส่งเข้าเคส",
    username: "ชื่อผู้ใช้สังเคราะห์",
    password: "รหัสผ่าน",
    showPassword: "แสดงรหัสผ่าน",
    hidePassword: "ซ่อนรหัสผ่าน",
    cta: "เข้าสู่ระบบเดโม",
    loading: "กำลังเข้าสู่ระบบ…",
    unauthorized: "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง",
    failed: "เข้าสู่ระบบไม่สำเร็จ โปรดลองอีกครั้ง",
    network: "บริการเข้าสู่ระบบไม่พร้อมใช้งาน โปรดลองอีกครั้ง",
    wrongRole: "บัญชีนี้ไม่ใช่บัญชีพยาบาล แอปนี้ใช้ได้เฉพาะพยาบาล",
  },

  start: {
    account: (user: string) => `ออกจากระบบ (${user})`,
    title: "เลือกผู้ป่วย",
    subtitle: "ผู้ป่วยสังเคราะห์ที่รอซักประวัติ",
    searchLabel: "ค้นหาหรือพิมพ์รหัสผู้ป่วยสังเคราะห์",
    searchPlaceholder: "ค้นหาหรือพิมพ์รหัส SYN-",
    sexAge: (sex: string, age: number) => `${sex} ${age} ปี`,
    arrived: (time: string) => `มาถึง ${time} น.`,
    loading: "กำลังโหลดรายชื่อผู้ป่วย…",
    empty: { head: "ยังไม่มีผู้ป่วยที่รอซักประวัติ", body: "พิมพ์รหัส SYN- เพื่อเปิดผู้ป่วยสังเคราะห์รายอื่น" } as Notice,
    noMatch: (input: string): Notice => ({ head: `ไม่พบรหัส “${input}”`, body: "ตรวจรหัสอีกครั้ง" }),
    nonSynthetic: "ใช้ได้เฉพาะผู้ป่วยสังเคราะห์ (รหัสขึ้นต้นด้วย SYN-)",
    loadError: "โหลดรายชื่อผู้ป่วยไม่สำเร็จ",
    reload: "ลองโหลดอีกครั้ง",
    explainHeading: "ก่อนเริ่มบันทึก",
    explainLines: [
      "ครั้งแรกที่กดเริ่มบันทึก เบราว์เซอร์จะขอใช้ไมโครโฟน ให้เลือก “อนุญาต”",
      "แอปฟังเฉพาะตอนกำลังบันทึก และไม่พูดกับผู้ป่วย คุณเป็นคนถามเอง",
    ],
    consent: "แจ้งผู้ป่วยแล้วว่าจะบันทึกเสียงบทสนทนา",
    cta: "เปิดหน้าบันทึก",
    disabledHint: "เลือกผู้ป่วยและยืนยันว่าแจ้งผู้ป่วยแล้ว",
  },

  rec: {
    factsHeading: "ข้อมูลที่ได้",
    factsCount: (n: number) => `${n} จาก 6 หัวข้อ`,
    valueMissing: "ยังไม่มี",
    valueAsking: "กำลังถาม",
    valueUnknown: "ผู้ป่วยไม่ทราบ",
    valueRefused: "ผู้ป่วยไม่ตอบ",
    valueNotElicited: "ยังไม่มี (ถามครบ 2 ครั้งแล้ว)",
    glyphCaptured: "ได้ข้อมูลแล้ว",
    glyphAsking: "กำลังถาม",
    glyphMissing: "ยังไม่มีข้อมูล",
    noteListening: (field: string) => `เพื่อเก็บ “${field}” · ใช้คำพูดของคุณเองได้`,
    noteIdle: "คำถามแรกที่แนะนำ · ใช้คำพูดของคุณเองได้",
    notePaused: "หยุดชั่วคราวอยู่ · กดบันทึกต่อเมื่อพร้อม",
    noteReconnecting: "รอให้เชื่อมต่อได้ก่อนถามต่อ",
    noteError: "บันทึกหยุดอยู่ · ลองอีกครั้งหรือจบเพื่อตรวจทาน",
    complete: { head: "ได้ข้อมูลครบ 6 หัวข้อแล้ว", body: "จบการบันทึกเพื่อตรวจทานได้เลย หรือคุยต่อถ้ามีข้อมูลเพิ่ม" } as Notice,
    transcriptEmpty: "กดเริ่มบันทึก แล้วคุยกับผู้ป่วยตามปกติ ข้อความที่ได้ยินจะขึ้นที่นี่",
    transcriptOpen: "เปิดบทสนทนาทั้งหมด",
    transcriptTitle: "บทสนทนาทั้งหมด",
    paused: { head: "หยุดบันทึกชั่วคราว", body: "เสียงช่วงนี้ไม่ถูกบันทึก ข้อมูลเดิมยังอยู่ครบ" } as Notice,
    systemPause: { head: "บันทึกหยุดเพราะออกจากแอป", body: "กดบันทึกต่อเมื่อกลับมาคุยกับผู้ป่วย" } as Notice,
    reconnecting: (n: number): Notice => ({
      head: `กำลังเชื่อมต่อใหม่ (ครั้งที่ ${n} จาก 3)`,
      body: "ข้อความก่อนหน้ายังอยู่ครบ เสียงช่วงนี้อาจไม่ถูกถอดข้อความ",
    }),
    error: (n: number): Notice => ({
      head: "บันทึกเสียงต่อไม่ได้",
      body: `ลองเชื่อมต่อ 3 ครั้งไม่สำเร็จ ข้อมูล ${n} หัวข้อที่ได้ยังอยู่ครบ`,
    }),
    permissionDenied: {
      head: "ไม่ได้รับสิทธิ์ใช้ไมโครโฟน",
      body: "เปิดสิทธิ์ไมโครโฟนให้เว็บนี้ในการตั้งค่าเบราว์เซอร์ แล้วกดขอสิทธิ์อีกครั้ง",
    } as Notice,
    noMic: { head: "ไม่พบไมโครโฟน", body: "ตรวจว่าไม่มีแอปอื่นใช้ไมโครโฟนอยู่ แล้วลองอีกครั้ง" } as Notice,
    extractionUnavailable: {
      head: "ระบบสกัดข้อมูลไม่ได้ชั่วคราว",
      body: "บทสนทนายังถูกบันทึก ตรวจและกรอกข้อมูลเองในหน้าตรวจทาน",
    } as Notice,
    status: {
      idle: "พร้อมบันทึก",
      requesting_permission: "กำลังขอใช้ไมโครโฟน",
      connecting: "กำลังเชื่อมต่อ",
      listening: "กำลังฟัง",
      paused: "หยุดชั่วคราว",
      reconnecting: "ขาดสัญญาณ",
      error: "หยุดบันทึก",
      permission_denied: "ไม่มีสิทธิ์ไมโครโฟน",
      finishing: "กำลังจบการบันทึก",
    },
    button: {
      start: "เริ่มบันทึก",
      pause: "หยุดชั่วคราว",
      resume: "บันทึกต่อ",
      connecting: "กำลังเชื่อมต่อ",
      retry: "ลองอีกครั้ง",
      askAgain: "ขอสิทธิ์อีกครั้ง",
      requesting: "กำลังขอสิทธิ์",
    },
    ariaPause: "หยุดบันทึกชั่วคราว",
    ariaRetry: "ลองเชื่อมต่ออีกครั้ง",
    /** From the approved comp 03c (aria-label of the disabled button while reconnecting). */
    ariaReconnecting: "กำลังเชื่อมต่อใหม่",
    finish: "จบการบันทึก",
    leave: {
      head: "ออกจากหน้าบันทึกหรือไม่",
      body: "การบันทึกจะหยุด ข้อมูลที่ได้ยังอยู่และตรวจทานต่อได้",
      confirm: "หยุดและออก",
      back: "กลับไปบันทึก",
    },
    redFlag: {
      heading: "พบสัญญาณที่ต้องประเมินเร่งด่วน",
      stillRecording: "ยังบันทึกอยู่",
      quoteLabel: "ผู้ป่วยพูดว่า",
      body: "คำถามแนะนำหยุดไว้จนกว่าจะรับทราบ ระบบไม่ได้จัดระดับความเร่งด่วน ให้ประเมินผู้ป่วยตามแนวปฏิบัติของหน่วยงาน",
      ack: "รับทราบ",
    },
    ackStrip: (time: string) => `มีสัญญาณที่ต้องประเมินเร่งด่วน · รับทราบเมื่อ ${time} น.`,
    finishBlocked: "รับทราบสัญญาณเร่งด่วนก่อนจบการบันทึก",
  },

  review: {
    back: "บันทึกต่อ",
    title: "ตรวจทานข้อมูล",
    meta: (id: string, m: number, s: number) => `${id} · บันทึก ${m} นาที ${s} วินาที`,
    instruction: "ยืนยัน แก้ไข หรือปฏิเสธทีละหัวข้อ ข้อมูลจะเข้าเคสเมื่อกดส่งเท่านั้น",
    source: (time: string) => `จากบทสนทนา ${time}`,
    confirm: "ยืนยัน",
    edit: "แก้ไข",
    reject: "ปฏิเสธ",
    change: "เปลี่ยน",
    confirmNoAllergy: "ยืนยันว่าไม่มีประวัติแพ้ยา",
    tag: {
      waiting: "รอตรวจ",
      confirmed: "ยืนยันแล้ว",
      editing: "กำลังแก้ไข",
      edited: "แก้ไขแล้ว",
      rejected: "ปฏิเสธแล้ว",
      missing: "ไม่มีข้อมูล",
    },
    editLabel: "ค่าที่ถูกต้อง",
    saveEdit: "บันทึกการแก้ไข",
    dismiss: "กลับไปตรวจสอบ",
    heard: (original: string) => `ระบบได้ยินว่า: ${original}`,
    rejectReasons: ["ได้ยินผิด", "ไม่ใช่ข้อมูลของผู้ป่วย", "อื่น ๆ"],
    rejectSave: "ปฏิเสธและบันทึกเหตุผล",
    rejectedNote: "ไม่ส่งเข้าเคส",
    missingBody: "ไม่ได้ยินข้อมูลนี้ระหว่างบันทึก",
    add: "เพิ่มข้อมูล",
    markUnknown: "ระบุว่าไม่ทราบ",
    progress: (n: number) => `ตรวจแล้ว ${n} จาก 6 หัวข้อ`,
    progressHint: "ตรวจครบแล้วจึงส่งได้",
    done: "ตรวจครบ 6 หัวข้อ",
    editedCount: (n: number) => `แก้ไข ${n} หัวข้อ`,
    submit: "ยืนยันและส่งเข้าเคส",
    submitting: "กำลังส่ง…",
    helper: "ระบบจะเสนอแผนกจากข้อมูลที่ยืนยันแล้ว และรอพยาบาลยืนยันอีกครั้งในเคส",
    submitted: (id: string): Notice => ({
      head: "ส่งเข้าเคสแล้ว",
      body: `ข้อมูลของ ${id} อยู่ในเคสแล้ว ระบบกำลังเสนอแผนกให้พยาบาลยืนยันในแอปหลัก`,
    }),
    next: "เริ่มผู้ป่วยรายถัดไป",
    submitError: { head: "ส่งเข้าเคสไม่สำเร็จ", body: "ข้อมูลที่ตรวจแล้วยังอยู่ในเครื่องนี้" } as Notice,
    retrySubmit: "ลองส่งอีกครั้ง",
    stale: "ข้อมูลนี้มีเวอร์ชันใหม่กว่า",
    conflict: "มีผู้ใช้อื่นกำลังดำเนินการกับเคสนี้",
  },
} as const;

/** D-V2C-2: strings not in the approved §5, kept together for the reviewer and owner. */
export const PROPOSED_V2C = {
  accessCodeLabel: "รหัสเข้าใช้บันทึกเสียง",
  accessCodeInvalid: { head: "รหัสเข้าใช้ไม่ถูกต้อง", body: "ตรวจรหัสแล้วลองอีกครั้ง" } as Notice,
  voiceUnavailable: { head: "ระบบบันทึกเสียงยังไม่พร้อมใช้งาน", body: "ข้อมูลที่ได้ยังอยู่ครบ จบเพื่อตรวจทานได้" } as Notice,
  sessionEnded: { head: "การบันทึกนี้ปิดไปแล้ว", body: "จบเพื่อตรวจทาน หรือเริ่มผู้ป่วยใหม่" } as Notice,
  failedSegments: (n: number) => `ถอดข้อความไม่ได้ ${n} ช่วง`,
  slotAfterAck: { head: "คำถามแนะนำหยุดไว้ในการบันทึกนี้", body: "ให้ประเมินผู้ป่วยตามแนวปฏิบัติของหน่วยงาน" } as Notice,
  notConnected: {
    head: "ยังส่งเข้าเคสไม่ได้",
    body: "ส่วนเชื่อมต่อกับเคสยังไม่พร้อมในต้นแบบนี้ ข้อมูลที่ตรวจแล้วยังอยู่ในหน้านี้",
  } as Notice,
  /** Builder additions (not in the D-V2C-2 list): */
  startFailed: "เปิดหน้าบันทึกไม่สำเร็จ โปรดลองอีกครั้ง",
  allergyNone: "ไม่มีประวัติแพ้ยา",
  allergyUnclear: "ข้อมูลแพ้ยายังไม่ชัด ตรวจในหน้าตรวจทาน",
  noQuestion: "ยังไม่มีคำถามแนะนำ",
  closeSheet: "ปิด",
} as const;

/** Words that must never appear in UI strings (claim boundary, §5 global rules). */
export const BANNED_WORDS = ["วินิจฉัย", "อัจฉริยะ", "AI-powered", "Submit", "OK", "Cancel", "Retry"] as const;
