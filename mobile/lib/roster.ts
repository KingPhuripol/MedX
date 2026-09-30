/** D-V2C-1: bundled synthetic roster (no backend queue endpoint exists). Only `id` is ever sent to the backend. */

export interface Patient {
  id: string;
  sex?: string;
  age?: number;
  bed?: string;
  arrived?: string;
}

export const ROSTER: readonly Patient[] = [
  { id: "SYN-2026-0023", sex: "หญิง", age: 46, bed: "เตียง 7", arrived: "10:24" },
  { id: "SYN-2026-0017", sex: "ชาย", age: 58, bed: "เตียง 4", arrived: "10:05" },
  { id: "SYN-2026-0031", sex: "ชาย", age: 71, bed: "รถเข็น 2", arrived: "10:40" },
];

export const SYN_ID = /^SYN-[A-Za-z0-9-]{1,60}$/;

export async function loadRoster(): Promise<Patient[]> {
  return [...ROSTER];
}
