"""g2 run: Case Graph (Arm A only) over one split -> red-flag rows -> S8r runner -> summary. Research prototype.

Test split: refuses unless the protocol status is FROZEN, the manifest is frozen in the ledger, every bound hash
(dataset tree, splits, rule set, mapping, system code, g2 code, protocol) matches, and no frozen output exists.
Unfrozen (dev) runs use a scratch ledger and write to ``<out>/unfrozen/<split>``: exploratory, never the result.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from app.config import Settings  # noqa: F401  (backend on sys.path; same import surface as eval_i2.arms)
from casegraph.executor import Executor
from casegraph.providers import mock_gateways
from casegraph.sources.s1r import load_split
from casegraph.store import MemoryStateStore, OutputStore
from eval.errors import RunRefused
from eval.exact import clopper_pearson
from eval.jsonio import canonical_bytes
from eval.ledger_chain import Ledger
from eval.manifest import load_manifest, manifest_sha256
from eval.runner import run as s8r_run
from eval_i2 import arms as i2arms
from eval_i2.score import gold_dp, miss_reason
from . import protocol as P
from .score import CASE_TASKS, dp_flags, gold_tasks, rows_for_case

OUT_ROOT = P.ROOT / "eval" / "results" / "g2"
BANNER = "System Evaluation on synthetic data — not clinical performance"
CIRCULARITY = ("Circularity: rules, lexicon, fixtures and gold share authors and the mock model is deterministic; "
               "this measures coverage of the authors' own scenarios.")


def run_arm_a(dataset: Path, split: str) -> list[dict[str, Any]]:
    """One record per DP: the Case Graph only (compile + execute + replay), snapshot inputs only, no gold."""
    gateways = mock_gateways()
    outputs, state = OutputStore(), MemoryStateStore()
    executor = Executor(gateways, outputs, state)
    recs = []
    for snap in load_split(Path(dataset), split):
        a = i2arms._arm_a(executor, state, outputs, gateways, snap)
        recs.append({"dp_id": snap.dp_id, "case_id": snap.case_id, "decision_point": snap.decision_point,
                     "patient_ref": snap.patient_ref, "split": split, "T": snap.T.isoformat(), i2arms.ARM_A: a})
    return recs


def score(dataset: Path, split: str, records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict]:
    gold = P.load_gold(dataset, split)
    if sorted(gold) != sorted({r["case_id"] for r in records}):
        raise ValueError(f"{split}: gold and inputs cover different cases")
    by_case: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if gold[r["case_id"]]["patient_ref"] != r["patient_ref"]:
            raise ValueError(f"{r['case_id']}: patient_ref differs between gold and inputs")
        by_case.setdefault(r["case_id"], []).append(r)
    rows = [x for cid, rs in sorted(by_case.items()) for x in rows_for_case(rs, gold[cid])]
    expected = sorted(m for g in gold.values() for m in gold_tasks(g))
    if expected != sorted((r["task"], r["decision_point_id"]) for r in rows):
        raise AssertionError(f"{split}: scored rows differ from gold-derived memberships")
    rows.sort(key=lambda r: (r["task"], r["patient_id"], r["decision_point_id"]))
    return rows, gold


def _x_n(rows: list[dict[str, Any]], task: str) -> dict[str, Any]:
    rs = [r for r in rows if r["task"] == task]
    x, n = sum(bool(r["y_pred"]) for r in rs), len(rs)
    out: dict[str, Any] = {"x": x, "n": n, "n_patients": len({r["patient_id"] for r in rs})}
    if n:
        lo, hi = clopper_pearson(x, n)
        out |= {"point": round(x / n, 6), "clopper_pearson_95": [round(lo, 6), round(hi, 6)]}
    return out


def summarize(split: str, manifest: dict[str, Any], results: dict[str, Any], records, rows, gold) -> dict[str, Any]:
    tasks = sorted({r["task"] for r in rows})
    boot = {r["metric_id"]: {"point": r["point"], "ci": [r["ci_low"], r["ci_high"]], "n_degenerate": r["n_degenerate"]}
            for r in results["rows"]}
    stats = {t: {**_x_n(rows, t), "bootstrap_patient_level": boot.get(t)} for t in tasks}
    missed, silent, fp = [], [], Counter()
    for rec in records:
        d = gold_dp(gold[rec["case_id"]], rec["decision_point"])
        f = dp_flags(rec, d)
        if d["red_flags"]:
            for r in f["rules"]:
                pair_hit = bool(set(i2s(r)) & set(f["fired"]))
                if not pair_hit:
                    missed.append({"dp_id": rec["dp_id"], "rule": r, "reason": miss_reason(r, rec, d)})
            if not f["surfaced"]:
                silent.append({"dp_id": rec["dp_id"], "gold_rules": f["rules"]})
        else:
            fp.update(f["fired"])
    primary = stats.get(P.PRIMARY, {})
    verdict = ("PASS" if primary.get("n") and primary["x"] == primary["n"] else "FAIL") if primary else "NO_DATA"
    return {
        "label": BANNER, "circularity_note": CIRCULARITY, "evaluation_id": manifest["evaluation_id"], "split": split,
        "frozen": results["frozen"], "manifest_sha256": results["manifest_sha256"],
        "n_dp": len(records), "n_patients": len({r["patient_ref"] for r in records}),
        "rule_set_versions_seen": sorted({r[i2arms.ARM_A]["red_flag"]["rule_set_version"] for r in records}),
        "screening_status": dict(sorted(Counter(r[i2arms.ARM_A]["red_flag"]["status"] for r in records).items())),
        "primary": {"metric": P.PRIMARY, "decision_rule": P.DECISION_RULE, "verdict": verdict, **primary},
        "metrics": stats,
        "missed_gold_pairs": sorted(missed, key=lambda m: (m["dp_id"], m["rule"])),
        "missed_reason_counts": dict(sorted(Counter(m["reason"] for m in missed).items())),
        "silent_escalation_failures": silent,
        "false_alerts_on_gold_negative_dps": dict(sorted(fp.items())),
        "replay": {"checked": len(records), "identical": sum(r[i2arms.ARM_A]["replay_ok"] for r in records)},
    }


def i2s(rule: str) -> list[str]:
    from eval_i2.score import s1r_targets
    return s1r_targets().get(rule) or []


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_bytes(r) + b"\n" for r in rows)


def run_split(split: str, dataset: Path, manifest_path: Path, protocol_path: Path, out_root: Path = OUT_ROOT,
              ledger_dir: Path | None = None) -> Path:
    manifest = load_manifest(manifest_path)
    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    if manifest["split"] != split:
        raise RunRefused(f"manifest split {manifest['split']!r} != requested {split!r}")
    if split == "test" and protocol["status"] != "FROZEN":
        raise RunRefused(f"protocol status is {protocol['status']!r}; the test split needs FROZEN")
    bad = P.hash_mismatches(manifest, protocol, dataset)
    if bad:
        raise RunRefused(f"{manifest['evaluation_id']}: bound hashes differ: {', '.join(bad)}")
    ledger = Ledger(ledger_dir)
    ledger.verify()
    frozen = any(e["sha256"] == manifest_sha256(manifest) for e in ledger.frozen(manifest["evaluation_id"]))
    if split == "test" and (protocol["status"] != "FROZEN" or not frozen):
        raise RunRefused("the test split needs protocol status FROZEN and the manifest frozen in the ledger "
                         "(python -m eval freeze)")
    out = Path(out_root) / (split if frozen else f"unfrozen/{split}")
    if frozen and out.exists() and any(out.iterdir()):
        raise RunRefused(f"{out} already has files; frozen results are never overwritten")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage"
        run_ledger = ledger
        if not frozen:
            run_ledger = Ledger(Path(tmp) / "scratch-ledger")
            run_ledger.init()
        records = run_arm_a(dataset, split)
        rows, gold = score(dataset, split, records)
        stage.mkdir()
        (stage / "system_outputs.jsonl").write_bytes(_jsonl(records))
        (stage / "predictions.jsonl").write_bytes(_jsonl(rows))
        results = s8r_run(manifest_path, stage / "predictions.jsonl", stage, None, run_ledger)
        s = summarize(split, manifest, results, records, rows, gold)
        (stage / "g2_summary.json").write_text(json.dumps(s, sort_keys=True, indent=1, ensure_ascii=False,
                                                          allow_nan=False) + "\n", encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(stage, out)
    return out
