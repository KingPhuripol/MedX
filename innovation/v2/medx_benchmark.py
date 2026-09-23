"""Predeclared synthetic workflow comparison; no training or clinical claims.

Run with --provider mock (default). External runs require --max-cases and use the
existing configured reservation budget. Existing artifacts are never overwritten.
"""
import argparse
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from time import monotonic
from innovation.v2.models import CaseRevision, ClinicalFact, DesignSpec
from innovation.v2.runtime import DESIGNS, Runtime
from innovation.v2.providers import MockProvider
from innovation.v2.evaluation import provider_from_environment
from innovation.v2.graph import replay
from innovation.v2.store import digest

T = datetime(2026, 9, 22, tzinfo=timezone.utc)
DESIGN_ORDER = ("fixed_path", "static_dag", "random", "adaptive", "ablation_no_check", "ablation_no_verify")


def cases():
    """Assign patient splits before creating two decision snapshots per patient."""
    patients = [(f"synthetic-medx-{i:02d}", "development" if i < 12 else "validation" if i < 16 else "test") for i in range(20)]
    result = []
    for i, (patient, split) in enumerate(patients):
        world = []
        for kind in ("CHIEF_COMPLAINT", "HISTORY", "MEDICATION", "ALLERGY", "VITAL"):
            state = "KNOWN"
            if kind == "HISTORY" and i % 4 == 1: state = "UNKNOWN"
            if kind == "MEDICATION" and i % 4 == 2: state = "REFUSED"
            if kind == "ALLERGY" and i % 4 == 3: state = "NOT_AVAILABLE"
            world.append(ClinicalFact(event_id=f"{patient}-{kind}", kind=kind, state=state,
                value=("ข้อมูลสังเคราะห์ " + kind) if state == "KNOWN" else None,
                observed_at=T, available_at_time=T))
        if i % 5 == 0:
            world[-1].conflicts_with_event_ids = [world[0].event_id]
        for kind in ("REPORT", "LABEL"):
            world.append(ClinicalFact(event_id=f"{patient}-{kind}", kind=kind, value="future synthetic report or label",
                observed_at=T + timedelta(hours=1), available_at_time=T + timedelta(hours=1)))
        for hour in (0, 1):
            decision = T + timedelta(hours=hour)
            facts = [f for f in world if f.available_at_time <= decision and f.kind != "LABEL"]
            payload = dict(encounter_id=patient, case_revision=len(world), decision_time=decision.isoformat(),
                timepoint="T1" if hour else "T0", evidence=[f.model_dump(mode="json") for f in facts])
            result.append((patient, split, CaseRevision(**payload, checksum=digest(payload))))
    return result


def designs():
    return {
        "fixed_path": DesignSpec(design_id="fixed_path", nodes=["draft"]),
        "static_dag": DESIGNS["static_dag"], "random": DESIGNS["random"], "adaptive": DESIGNS["adaptive"],
        "ablation_no_check": DesignSpec(design_id="ablation_no_check", nodes=["intake", "draft", "verify"]),
        "ablation_no_verify": DesignSpec(design_id="ablation_no_verify", nodes=["intake", "check", "draft"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=["mock", "external"], default="mock")
    parser.add_argument("--max-cases", type=int)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError("Refusing to overwrite evidence")
    if args.provider == "external" and (not args.max_cases or args.max_cases < 1): raise ValueError("External run requires positive --max-cases")
    samples = cases()
    if args.max_cases: samples = samples[:args.max_cases]
    provider = provider_from_environment() if args.provider == "external" else MockProvider()
    runtime = Runtime(provider, timeout_seconds=60)
    rows = []
    try:
        for patient, split, snapshot in samples:
            for label, design in designs().items():
                start = monotonic()
                run, content = runtime.execute(snapshot, "เตรียมร่างจากหลักฐานสังเคราะห์ที่ยืนยันแล้ว", design)
                artifact = run.provenance.get("execution")
                exact = replay(artifact)["result"]["content"] == (content.model_dump(mode="json") if content else None) if artifact else False
                floor = run.provenance.get("safety_screen", {}).get("urgency_floor", "INSUFFICIENT_INFORMATION")
                severity = {"INSUFFICIENT_INFORMATION":0,"ROUTINE_REVIEW":1,"URGENT_REVIEW":2,"IMMEDIATE_REVIEW":3}
                checks = {
                    "completed": run.status == "COMPLETED", "recorded_replay_exact": exact,
                    "temporal_and_label_boundary": all(f.available_at_time <= snapshot.decision_time and f.kind != "LABEL" for f in snapshot.evidence),
                    "content_refs_valid": content is not None and set(content.evidence_ids) <= {f.event_id for f in snapshot.evidence},
                    "urgency_floor_preserved": content is not None and severity[content.urgency.level] >= severity[floor],
                    "bounded_calls": len(run.trace) <= 8,
                }
                rows.append({"patient_id": patient, "split": split, "timepoint": snapshot.timepoint, "design": label,
                    "checks": checks, "passed": all(checks.values()), "latency_ms": (monotonic()-start)*1000,
                    "tool_calls": len(run.trace), "model_calls": sum(t.tool == "create_draft" for t in run.trace),
                    "token_usage": run.provenance.get("token_usage"), "reserved_cost_usd": run.provenance.get("reserved_cost_usd",0),
                    "output_checksum": digest(content.model_dump(mode="json")) if content else None,
                    "graph_operators": [n["operator"] for n in artifact["graph"]["nodes"]] if artifact else [],
                    "run": run.model_dump(mode="json")})
        summaries = {}
        for label in DESIGN_ORDER:
            group = [r for r in rows if r["design"] == label]
            summaries[label] = {"runs":len(group), "passed":sum(r["passed"] for r in group),
                "mean_tool_calls":sum(r["tool_calls"] for r in group)/len(group),
                "mean_latency_ms":sum(r["latency_ms"] for r in group)/len(group),
                "graph_variants":len({tuple(r["graph_operators"]) for r in group}),
                "failures":{key:sum(not r["checks"][key] for r in group) for key in group[0]["checks"]}}
        report = {"schema_version":"medx-workflow-evaluation-1.0", "recorded_at":datetime.now(timezone.utc).isoformat(),
            "revision":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
            "source_hash":digest({str(p):p.read_text() for root in (Path('innovation/v2'),Path('innovation/gateway')) for p in sorted(root.rglob('*.py'))}),
            "manifest":"experiments/manifests/exp_0002_medx_workflow.json", "provider":provider.name, "model":provider.model_version,
            "patient_splits":{split:sorted({p for p,s,_ in samples if s==split}) for split in ("development","validation","test")},
            "dataset_checksum":digest([s.model_dump(mode="json") for _,_,s in samples]),
            "clinical_validation":"NOT_REVIEWED", "training":False,
            "limitations":["Synthetic engineering cases, not clinical ground truth", "Workflow DAG only, not internal model architecture",
                "Same model and per-case caps; actual tools/tokens differ and are reported", "Mock output similarity cannot establish medical benefit",
                "No design selected or tuned using held-out outcomes", "Ablations remove optional steps, never mandatory gateway safety"],
            "summary":summaries, "runs":rows}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x') as f: json.dump(report,f,ensure_ascii=False,indent=2)
        print(json.dumps({"output":str(args.output),"summary":summaries},ensure_ascii=False))
        return 0 if all(r["passed"] for r in rows) else 1
    finally:
        if hasattr(provider,"budget"): provider.budget.close()

if __name__ == "__main__": raise SystemExit(main())
