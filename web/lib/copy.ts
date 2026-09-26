/** User-facing copy shared by pages and tests. */
export const DISCLAIMER_EN =
  "Research prototype — not for clinical use. Outputs are suggestions for review and require confirmation by a clinician.";
export const DISCLAIMER_TH =
  "ต้นแบบเพื่อการวิจัย ไม่ใช้กับผู้ป่วยจริง ผลลัพธ์เป็นข้อเสนอที่ต้องให้บุคลากรยืนยัน";

export const ROLES = ["nurse", "physician", "pharmacist"] as const;
export type Role = (typeof ROLES)[number];

export const ROLE_LABELS: Record<Role, string> = {
  nurse: "Nurse",
  physician: "Physician",
  pharmacist: "Pharmacist",
};
