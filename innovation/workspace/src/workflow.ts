import type { Draft, Fact, Run } from "./types";

export type ClinicalWorkspaceStep = "intake" | "facts" | "draft";

export const clinicalSteps: { id: ClinicalWorkspaceStep; label: string; description: string }[] = [
  { id: "intake", label: "รับข้อมูล", description: "สนทนาและรวบรวมอาการ" },
  { id: "facts", label: "ตรวจข้อมูล", description: "ตรวจข้อเสนอและความขัดแย้ง" },
  { id: "draft", label: "ตรวจร่าง", description: "ตรวจหลักฐานและยืนยัน" },
];

export function pendingProposalCount(runs: Run[], revision: number): number {
  return runs.reduce(
    (total, run) => total + (run.case_revision === revision ? run.proposals.filter((proposal) => proposal.proposal_id).length : 0),
    0,
  );
}

export function deriveRecommendedStep(facts: Fact[], runs: Run[], drafts: Draft[], revision: number): ClinicalWorkspaceStep {
  if (pendingProposalCount(runs, revision) > 0) return "facts";
  const latest = drafts.at(-1);
  if (latest && (!latest.effective || latest.case_revision !== revision || ["STALE", "SUPERSEDED"].includes(latest.status))) return "draft";
  if (!facts.length || !runs.length) return "intake";
  return latest?.effective ? "intake" : "draft";
}

export function stepState(step: ClinicalWorkspaceStep, facts: Fact[], runs: Run[], drafts: Draft[], revision: number): "complete" | "attention" | "current" | "upcoming" {
  const latest = drafts.at(-1);
  if (step === "intake") return runs.length ? "complete" : "current";
  if (step === "facts") {
    if (pendingProposalCount(runs, revision) > 0 || facts.some((fact) => fact.conflicts_with_event_ids?.length)) return "attention";
    return facts.length ? "complete" : runs.length ? "current" : "upcoming";
  }
  if (latest?.effective && latest.case_revision === revision) return "complete";
  if (latest) return "attention";
  return facts.length ? "current" : "upcoming";
}
