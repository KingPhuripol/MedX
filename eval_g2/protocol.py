"""Frozen g2 protocol: manifest ``g2-redflag-retest-0001`` (S8r schema) + sibling ``.protocol.json``.

The manifest carries the metrics and the single gating threshold; the protocol JSON carries everything the S8r schema
cannot hold (question, decision rule, definitions, disclosures, code/config pins, status). The manifest ``$comment``
binds the protocol hash (status excluded, so DRAFT -> FROZEN does not change it), the dataset, split, mapping,
rule set and code hashes; a run refuses when any differs. Research prototype - not for clinical use.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from eval.adapters import hashes
from eval.adapters.gold import split_patients
from eval_i2 import protocol as i2p
from .score import gold_tasks

ROOT = Path(__file__).resolve().parents[1]
G2_DIR = Path(__file__).resolve().parent
MANIFEST_DIR = ROOT / "eval" / "manifests"
EVALUATION_ID = "g2-redflag-retest-0001"
HASH_PREFIX = "g2-hashes "
SEED = 20260929
N_BOOT = 2000
PRIMARY = "rf_case_recall"
ITEM = "Department suggestion"  # S8r item used by e1 for the red-flag metrics
RULES_PATH = ROOT / "backend" / "app" / "triage" / "rules" / "redflag_rules_v1.json"
HELDOUT_NAME = "g2-heldout-20260929"
HELDOUT_MANIFEST_SHA256 = "572869b5f94b635fd27fe2d32cb41661b41c7f7f9c620a56bd70efdca83f6573"
BASE_REVISION = "a2544dde0a64631e6e7a3224c01015a7a13c6a47"  # factory/g2-redflag HEAD the eval branch forks from
COMMENT = ("Slice g2 manifest: held-out red-flag re-test of the Case Graph (System Evaluation on synthetic data - not "
           "clinical performance). Full protocol in the sibling .protocol.json. Hash bindings follow as canonical "
           "JSON after the prefix 'g2-hashes '. ")

DECISION_RULE = ("PASS iff rf_case_recall = 1.00 exactly (point estimate, x = n) on the held-out test split. Any miss "
                 "is FAIL. Clopper-Pearson 95% interval reported; a PASS is a point-estimate statement on a small "
                 "circular synthetic sample, not evidence of clinical safety. Secondaries are descriptive, never "
                 "gating, and cannot rescue a FAIL.")

DISCLOSURES = [
    "The v1 test split (e1) is consumed: its 9/22 = 0.41 result led to the fixes evaluated here. This held-out set "
    "(seed 20260929, test split only) is the first fresh split, and it is single-use: if the primary fails and the "
    "system is changed, a further re-test needs a new dataset.",
    "Circularity: rules, extractor lexicon, fixtures and gold share authors; the mock model is deterministic. The "
    "result measures rule/extractor coverage of the authors' own scenarios, not clinical performance.",
    "RF-NEWS-AGG5 (rf-1.2.0) is PROPOSED, pending clinical sign-off. It follows RCP NEWS2 (2017) SpO2 Scale 1, not "
    "the S1r gold (NEWS 2012).",
    "Known rule/gold disagreements kept, not fixed (slices/g2/NOTES.md): new-confusion scores 3 in the rule and 0 in "
    "gold; a null on-oxygen is missing in the rule and 0 in gold; gold scores any null parameter 0 while the rule "
    "abstains. AGG5 gold DPs can therefore be missed or over-fired for reasons of definition.",
    "Metric naming: e1 calls rf_case_recall 'case-level' but its unit is the decision point and any alert of any rule "
    "counts. That definition is mirrored for comparability with 9/22; it is weaker than rule-matched recall, which "
    "is reported beside it.",
    "Id-name collision: held-out ids are SYNH-*/SYNHE-*, the same names as the archived s6r-heldout dataset "
    "(different seed and content). Nothing here reads that dataset.",
    "The e1 mapping v1 is frozen and pinned to rf-1.1.0; the AGG5 row comes from eval_i2.score.AGG5_OVERLAY.",
    "Clopper-Pearson assumes independent units; DPs of one patient/case are not independent, so a patient-level "
    "bootstrap (n_boot=2000) is reported beside it. Small n: intervals are wide.",
    "The manifest's task_patient_lists come from gold red-flag membership (labels only, no system output), as in e1 "
    "and i2; the held-out system outputs were not produced in phase 1.",
]

DEFINITIONS = {
    "rf_case_recall": "PRIMARY. Mirrors e1 eval/adapters/protocol.py rf_case_recall: gold-positive DPs (>=1 gold red "
                      "flag) where the Case Graph fired >=1 alert of any rule. Unit: decision point.",
    "rf_rulematched_dp": "Same population; caught iff an alert of a rule mapped to a gold rule of that DP fired.",
    "rf_rule_<RULE>": "Per S1r rule: gold (DP, rule) pairs where a mapped S4 rule fired (e1 mapping v1 + AGG5 overlay).",
    "rf_case_agg": "Unit case: cases with a gold-positive DP; caught iff any such DP has any alert.",
    "rf_case_agg_rulematched": "Unit case: caught iff any gold-positive DP has a rule-matched alert.",
    "rf_fpr": "Gold-negative DPs with >=1 alert of any rule (false-positive rate).",
    "rf_surfaced": "Gold-positive DPs where an alert fired or a gold rule was not_evaluated (input gap surfaced). "
                   "Silent escalation failure = 1 - surfaced: the screen evaluated, raised nothing, said nothing.",
}


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_gold(dataset: Path, split: str) -> dict[str, dict[str, Any]]:
    """Local loader (glob ``*.json``): the e1 loader globs SYNE-*, which misses the SYNHE-* held-out ids."""
    out = {}
    for p in sorted((Path(dataset) / "gold" / split).glob("*.json")):
        g = json.loads(p.read_text(encoding="utf-8"))
        if g["case_id"] != p.stem or g["split"] != split:
            raise ValueError(f"{p}: case_id/split mismatch")
        out[p.stem] = g
    return out


def g2_code_sha256() -> str:
    h = hashlib.sha256()
    for p in sorted(G2_DIR.rglob("*.py")):
        if "__pycache__" in p.parts or "tests" in p.relative_to(G2_DIR).parts:
            continue
        h.update(p.relative_to(G2_DIR).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def rule_set() -> dict[str, str]:
    return {"version": json.loads(RULES_PATH.read_text(encoding="utf-8"))["version"],
            "file": RULES_PATH.relative_to(ROOT).as_posix(), "sha256": sha256_file(RULES_PATH)}


def protocol_sha256(p: dict[str, Any]) -> str:
    body = {k: v for k, v in p.items() if k != "status"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def declared_hashes(dataset: Path) -> dict[str, Any]:
    """Hashes that need no system run and no gold: manifest.json, splits.json and code."""
    dm = json.loads((Path(dataset) / "manifest.json").read_text(encoding="utf-8"))
    return {
        "dataset_manifest_sha256": sha256_file(Path(dataset) / "manifest.json"),
        "dataset_tree_sha256_declared": dm["tree_sha256"],
        "split_sha256": hashes.split_sha256(dataset),
        "mapping_sha256": hashes.mapping_sha256(),
        "rule_set": rule_set(),
        "system_sha256": i2p.system_sha256(),
        "i2_adapters_sha256": i2p.adapters_sha256(),
        "g2_code_sha256": g2_code_sha256(),
    }


def tree_mismatch(dataset: Path) -> list[str]:
    """Full re-hash of the dataset tree at run time (integrity errors; empty = intact)."""
    tree, errors = hashes.dataset_tree_sha256(dataset)
    dm = json.loads((Path(dataset) / "manifest.json").read_text(encoding="utf-8"))
    return errors + ([] if tree == dm["tree_sha256"] else ["tree differs from manifest.json"])


def metrics(tasks: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    def m(mid: str, task: str, estimand: str, primary: bool = False) -> dict[str, Any]:
        return {"id": mid, "item": ITEM, "task": task, "name": "accuracy", "params": {"estimand": estimand},
                "primary": primary}
    spec = [m(PRIMARY, PRIMARY, DEFINITIONS[PRIMARY], True),
            m("rf_rulematched_dp", "rf_rulematched_dp", DEFINITIONS["rf_rulematched_dp"]),
            m("rf_case_agg", "rf_case_agg", DEFINITIONS["rf_case_agg"]),
            m("rf_case_agg_rulematched", "rf_case_agg_rulematched", DEFINITIONS["rf_case_agg_rulematched"])]
    spec += [m(t, t, f"per-rule recall of {t.removeprefix('rf_rule_')}: " + DEFINITIONS["rf_rule_<RULE>"])
             for t in sorted(x for x in tasks if x.startswith("rf_rule_RF-"))]
    spec += [m("rf_fpr", "rf_fpr", DEFINITIONS["rf_fpr"]), m("rf_surfaced", "rf_surfaced", DEFINITIONS["rf_surfaced"])]
    spec = [x for x in spec if x["task"] in tasks]
    return spec, [{"metric": PRIMARY, "op": ">=", "value": 1.0, "rule": "point"}]


def members(dataset: Path, split: str) -> list[tuple[str, str, str]]:
    gold = load_gold(dataset, split)
    return sorted((t, u, g["patient_ref"]) for g in gold.values() for t, u in gold_tasks(g))


def build_protocol(dataset: Path, split: str, status: str = "DRAFT") -> dict[str, Any]:
    members_ = members(dataset, split)
    tasks = {t for t, _, _ in members_}
    dm = json.loads((Path(dataset) / "manifest.json").read_text(encoding="utf-8"))
    return {
        "protocol_version": "1.0",
        "evaluation_id": EVALUATION_ID,
        "status": status,
        "question": "Does the Case Graph (S4 engine wired in i2, rule set rf-1.2.0 incl. RF-NEWS-AGG5) reach "
                    "case-level red-flag recall of 1.00 on a fresh held-out synthetic split, where e1 measured "
                    "9/22 = 0.41 on the (consumed) v1 test split?",
        "code": {"base_revision": BASE_REVISION, "branch": "factory/g2-redflag-eval",
                 "system_sha256": i2p.system_sha256(), "note": "system_sha256 (casegraph + triage/voice/gateway code) "
                 "and g2_code_sha256 are the binding pins; a commit adding only eval_g2 does not change the system"},
        "config": {"rule_set": rule_set(), "seed": SEED, "n_boot": N_BOOT, "arm": "case_graph (mock gateways)",
                   "mapping": "e1_mapping_v1 + eval_i2.score.AGG5_OVERLAY", "tier": 0, "provider": "mock, no network"},
        "dataset": {"name": HELDOUT_NAME if split == "test" else dataset.name, "path": str(dataset), "split": split,
                    "manifest_json_sha256": sha256_file(Path(dataset) / "manifest.json"),
                    "expected_manifest_json_sha256": HELDOUT_MANIFEST_SHA256 if split == "test" else None,
                    "tree_sha256": dm["tree_sha256"], "data_class": dm["data_class"],
                    "n_patients": len(split_patients(dataset, split)), "n_cases": dm["counts"]["cases"] if
                    "counts" in dm else None},
        "primary_metric": PRIMARY,
        "metric_definitions": DEFINITIONS,
        "secondary_metrics": ["rf_rulematched_dp", "rf_rule_<each S1r rule present>", "rf_case_agg",
                              "rf_case_agg_rulematched", "rf_fpr", "rf_surfaced (silent escalation failures)"],
        "statistics": {"interval": "Clopper-Pearson 95% (eval.exact), plus patient-level percentile bootstrap "
                                   "(S8r runner) shown beside it", "denominators": "every gold-positive DP/case is "
                       "scored; a schema failure, timeout or missing prediction is a miss, never dropped"},
        "decision_rule": DECISION_RULE,
        "exclusions": "none predeclared",
        "disclosures": DISCLOSURES,
        "task_units": {t: sum(1 for x, _, _ in members_ if x == t) for t in sorted(tasks)},
    }


def build_manifest(dataset: Path, split: str, protocol: dict[str, Any], n_boot: int = N_BOOT) -> dict[str, Any]:
    ms = members(dataset, split)
    tasks = {t for t, _, _ in ms}
    spec, thresholds = metrics(tasks)
    dm = json.loads((Path(dataset) / "manifest.json").read_text(encoding="utf-8"))
    bound = {**declared_hashes(dataset), "protocol_sha256": protocol_sha256(protocol)}
    return {
        "$comment": COMMENT + HASH_PREFIX + json.dumps(bound, sort_keys=True, separators=(",", ":")),
        "manifest_version": "1.0",
        "evaluation_id": EVALUATION_ID,
        "slice": "g2",
        "dataset": {"name": protocol["dataset"]["name"], "version": f"{protocol['dataset']['name']}"
                    f"+tree:{dm['tree_sha256']}", "data_class": dm["data_class"]},
        "split": split,
        "split_version": hashes.split_sha256(dataset),
        "split_patient_list": split_patients(dataset, split),
        "task_patient_lists": {t: sorted({p for tt, _, p in ms if tt == t}) for t in sorted(tasks)},
        "metrics": spec,
        "comparators": [],
        "thresholds": thresholds,
        "bootstrap": {"n_boot": n_boot, "seed": SEED, "ci_level": 0.95, "method": "percentile"},
        "expert_review": {"done": False, "n_reviewers": 0},
    }


def parse_hashes(m: dict[str, Any]) -> dict[str, Any]:
    c = m.get("$comment", "")
    if HASH_PREFIX not in c:
        raise ValueError(f"{m.get('evaluation_id')}: manifest has no g2 hash binding")
    return json.loads(c.rsplit(HASH_PREFIX, 1)[1])


def hash_mismatches(m: dict[str, Any], protocol: dict[str, Any], dataset: Path) -> list[str]:
    bound = parse_hashes(m)
    now = {**declared_hashes(dataset), "protocol_sha256": protocol_sha256(protocol)}
    bad = sorted(k for k in now if bound.get(k) != now[k])
    if m["split"] == "test" and now["dataset_manifest_sha256"] != HELDOUT_MANIFEST_SHA256:
        bad.append("dataset_manifest_sha256 != pinned held-out value")
    return bad + [f"tree: {e}" for e in tree_mismatch(dataset)]


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
