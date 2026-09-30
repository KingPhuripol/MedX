/** Review decisions and submit (SPEC §2.4, §11 T10). The case write itself belongs to slice v2d. */
import { call, post, type Reply } from "./api";

export type DecisionAction = "confirm" | "edit" | "reject" | "add" | "unknown";

export interface Decision {
  field: string;
  action: DecisionAction;
  /** The value the nurse accepted or typed (null for reject). */
  value: string | null;
  /** What the system heard for this row (null when the field was missing). */
  original: string | null;
  reason?: string;
}

export interface ReviewPayload {
  session_id: string;
  patient_ref: string;
  decisions: Decision[];
  consent_acknowledged_at: string;
  red_flag_acknowledged_at: string | null;
}

export type SubmitOutcome = "submitted" | "not_connected" | "error" | "auth";

/** One fetch; the endpoint and body are provisional. */
export function submitReview(sessionId: string, payload: ReviewPayload): Promise<Reply<unknown>> {
  // TODO(v2d): endpoint and body owned by slice v2d
  return post(`/api/voice/sessions/${sessionId}/review`, payload);
}

/** T10: finish exactly once per submit (409 = already finished = done), then submitReview. Only a 2xx is success. */
export async function submitFlow(
  sessionId: string,
  payload: ReviewPayload,
): Promise<{ outcome: SubmitOutcome; finished: boolean }> {
  const f = await call(`/api/voice/sessions/${sessionId}/finish`, { method: "POST" });
  if (f.status === 401) return { outcome: "auth", finished: false };
  if (!(f.status >= 200 && f.status < 300) && f.status !== 409) return { outcome: "error", finished: false };
  const r = await submitReview(sessionId, payload);
  if (r.status === 401) return { outcome: "auth", finished: true };
  if (r.status >= 200 && r.status < 300) return { outcome: "submitted", finished: true };
  if (r.status === 404 || r.status === 405 || r.status === 501) return { outcome: "not_connected", finished: true };
  return { outcome: "error", finished: true };
}
