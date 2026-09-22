#!/usr/bin/env python3
"""Create a complete planned experiment manifest without running the experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from harness_lib import validate_file


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "experiments" / "manifests"
SCHEMA = ROOT / "schemas" / "experiment-manifest.schema.json"


def git_state() -> tuple[str, bool]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
            ).stdout.strip()
        )
        return revision, dirty
    except (OSError, subprocess.CalledProcessError):
        return "no-commit-yet", True


def next_id() -> str:
    numbers = []
    for path in MANIFEST_DIR.glob("exp_*.json"):
        match = re.match(r"exp_([0-9]{4})_", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return f"exp_{(max(numbers) + 1) if numbers else 0:04d}"


def slug_value(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise argparse.ArgumentTypeError("slug must use lowercase letters, digits, and single hyphens")
    return value


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--slug", required=True, type=slug_value)
    p.add_argument("--owner", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--decision", required=True, help="Decision this experiment will inform")
    p.add_argument("--tier", required=True, type=int, choices=range(5))
    p.add_argument("--model-name", required=True)
    p.add_argument("--model-version", required=True)
    p.add_argument("--parameter-count", required=True, type=int)
    p.add_argument("--model-license", required=True)
    p.add_argument("--initialization", required=True)
    p.add_argument("--dataset-version", required=True)
    p.add_argument("--split-version", required=True)
    p.add_argument("--split-checksum", required=True)
    p.add_argument("--preprocessing-version", required=True)
    p.add_argument("--temporal-audit-id", required=True)
    p.add_argument("--classification", default="SYNTHETIC", choices=["SYNTHETIC", "PUBLIC_LICENSED", "DEIDENTIFIED_APPROVED", "IDENTIFIABLE_OR_LINKABLE", "RESTRICTED_DERIVATIVE"])
    p.add_argument("--license-status", default="cleared", choices=["cleared", "restricted", "unresolved"])
    p.add_argument("--graph-mode", required=True, choices=["fixed", "static", "soft", "sparse", "discrete", "random", "not_applicable"])
    p.add_argument("--primary-metric", required=True, action="append")
    p.add_argument("--secondary-metric", action="append", default=[])
    p.add_argument("--baseline", action="append", default=[])
    p.add_argument("--fixed-factor", required=True, action="append")
    p.add_argument("--changed-factor", required=True, action="append")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--precision", default="bf16", choices=["fp32", "fp16", "bf16", "mixed", "not_applicable"])
    p.add_argument("--optimizer", default="AdamW")
    p.add_argument("--scheduler", default="cosine")
    p.add_argument("--max-steps", type=int, default=100)
    p.add_argument("--max-tokens", type=int, default=0)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--gradient-accumulation", type=int, default=1)
    p.add_argument("--gpu-count", type=int, default=0)
    p.add_argument("--devices", default="CPU")
    p.add_argument("--estimated-minutes", type=int, required=True)
    p.add_argument("--estimated-gpu-hours", type=float, default=0)
    p.add_argument("--estimated-cost-usd", type=float, default=0)
    p.add_argument("--estimated-storage-gb", type=float, required=True)
    p.add_argument("--approval-id", action="append", default=[])
    p.add_argument("--risk-id", action="append", default=[])
    p.add_argument("--parent-experiment-id")
    return p


def main() -> int:
    args = parser().parse_args()
    if args.gpu_count > 1 and args.tier < 3:
        raise SystemExit("multi-GPU experiments must be Tier 3 or Tier 4")
    if args.estimated_minutes > 60 and args.tier < 3:
        raise SystemExit("experiments over 60 minutes must be Tier 3 or Tier 4")
    if not re.fullmatch(r"TASK-[0-9]{4}", args.task_id):
        raise SystemExit("--task-id must match TASK-NNNN")
    if len(args.question) < 20 or len(args.hypothesis) < 20:
        raise SystemExit("question and hypothesis must each contain at least 20 characters")

    experiment_id = next_id()
    revision, dirty = git_state()
    created = datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds")
    config_source = json.dumps(vars(args), sort_keys=True, default=str).encode("utf-8")
    config_hash = hashlib.sha256(config_source).hexdigest()
    artifact_root = f"artifacts/experiments/{experiment_id}"
    manifest = {
        "schema_version": "1.0.0",
        "experiment_id": experiment_id,
        "slug": args.slug,
        "owner": args.owner,
        "task_id": args.task_id,
        "parent_experiment_id": args.parent_experiment_id,
        "research_question": args.question,
        "hypothesis": args.hypothesis,
        "decision_informed": args.decision,
        "status": "planned",
        "run_tier": args.tier,
        "created_at": created,
        "code": {"revision": revision, "dirty": dirty, "diff_artifact": f"{artifact_root}/working-tree.diff" if dirty else None, "config_hash": config_hash},
        "model": {"name": args.model_name, "version": args.model_version, "parameter_count": args.parameter_count, "initialization": args.initialization, "license": args.model_license},
        "data": {"dataset_version": args.dataset_version, "split_version": args.split_version, "split_checksum": args.split_checksum, "preprocessing_version": args.preprocessing_version, "temporal_audit_id": args.temporal_audit_id, "classification": args.classification, "license_status": args.license_status},
        "training": {"seed": args.seed, "precision": args.precision, "optimizer": args.optimizer, "scheduler": args.scheduler, "max_steps": args.max_steps, "max_tokens": args.max_tokens, "batch_size": args.batch_size, "gradient_accumulation": args.gradient_accumulation, "checkpoint_policy": "Versioned periodic checkpoints plus last-known-good; no automatic deletion"},
        "graph": {"mode": args.graph_mode, "schema_version": "1.0.0", "operator_library_version": "1.0.0", "max_nodes": 32, "max_depth": 8, "routing_objectives": ["task_quality", "budget_compliance", "non_collapse"] if args.graph_mode not in {"fixed", "not_applicable"} else []},
        "resources": {"devices": args.devices, "gpu_count": args.gpu_count, "estimated_minutes": args.estimated_minutes, "estimated_gpu_hours": args.estimated_gpu_hours, "estimated_cost_usd": args.estimated_cost_usd, "estimated_storage_gb": args.estimated_storage_gb},
        "comparisons": {"baseline_experiment_ids": args.baseline, "fixed_factors": args.fixed_factor, "changed_factors": args.changed_factor, "fairness_notes": "Match data, split, preprocessing, optimization opportunity, tokens or steps, search budget, parameters or compute; record every unavoidable difference before execution"},
        "evaluation": {"evaluator_version": "evaluation-contract-1.0.0", "primary_metrics": args.primary_metric, "secondary_metrics": args.secondary_metric, "statistics_plan": "Report patient-level denominators and uncertainty intervals; use paired comparisons and clustered resampling where applicable", "exclusion_rules": ["Exclude only predeclared unavailable ground truth; retain schema failures, abstentions, timeouts, and stopped runs in accounting"], "final_test_access": "none"},
        "stop_rules": ["Stop on temporal or patient leakage", "Stop on NaN or unrecoverable checkpoint failure", "Stop on routing collapse when the manifest remediation budget is exhausted", "Stop when the approved compute, time, cost, or storage limit is reached"],
        "artifacts": {"root": artifact_root, "logs": f"{artifact_root}/logs", "checkpoints": f"{artifact_root}/checkpoints", "predictions": f"{artifact_root}/predictions", "evaluation_record": f"{artifact_root}/evaluation-record.json", "retention": "Retain manifests, logs, metrics, checksums, failures, and required recovery checkpoints under the Training and Approval policies"},
        "approvals": {"required": args.tier >= 3, "approval_ids": args.approval_id},
        "risks": args.risk_id,
        "result": None,
    }
    path = MANIFEST_DIR / f"{experiment_id}_{args.slug}.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite existing manifest {path}")
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    errors = validate_file(path, SCHEMA)
    if errors:
        path.unlink(missing_ok=True)
        raise SystemExit("generated manifest failed validation:\n" + "\n".join(f"- {error}" for error in errors))
    print(path.relative_to(ROOT))
    if args.tier >= 3 and not args.approval_id:
        print("Planned Tier 3/4 manifest created. Execution remains blocked until an exact human approval ID is recorded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

