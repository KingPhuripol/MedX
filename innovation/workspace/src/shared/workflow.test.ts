import { describe, expect, it } from "vitest";
import { deriveRecommendedStep, stepState } from "./workflow";

const revision = 3;
const fact = { event_id: "f1", kind: "HISTORY", state: "KNOWN", value: "ไอ", observed_at: "2026-09-12T00:00:00Z", available_at_time: "2026-09-12T00:00:00Z", supersedes_event_id: null, source: "STAFF_CONFIRMED" } as any;

describe("focused clinical workflow", () => {
  it("starts intake before facts or a draft exist", () => {
    expect(deriveRecommendedStep([], [], [], revision)).toBe("intake");
  });

  it("routes pending assistant proposals to facts review", () => {
    const run = { run_id: "r1", case_revision: revision, status: "COMPLETED", response: "", user_text: "อาการ", proposals: [{ proposal_id: "p1", fact, requires_confirmation: true }] } as any;
    expect(deriveRecommendedStep([], [run], [], revision)).toBe("facts");
  });

  it("routes reviewed facts to draft preparation", () => {
    const run = { run_id: "r1", case_revision: revision, status: "COMPLETED", response: "", user_text: "อาการ", proposals: [] } as any;
    expect(deriveRecommendedStep([fact], [run], [], revision)).toBe("draft");
  });

  it("marks a draft stale when the case revision changes", () => {
    const draft = { draft_id: "d1", draft_revision: 1, case_revision: 2, status: "PENDING_REVIEW", effective: true } as any;
    expect(stepState("draft", [fact], [], [draft], revision)).toBe("attention");
  });
});
