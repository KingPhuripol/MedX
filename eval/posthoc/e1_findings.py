"""E1 post-hoc findings (slice e1r): disclosure computed from the frozen, stored e1 outputs.

Post-hoc: computed after the frozen run from stored predictions; not part of the predeclared evaluation. No
metric, verdict, manifest, adapter or ledger line is changed, and nothing is re-run (0 new ledger lines).

Inputs (read only):
- stored outputs ``eval/results/e1/{dev,test}/{system_outputs.jsonl, voice/predictions.jsonl,
  triage/predictions.jsonl, */results.json}``; each predictions/results file must match its sha256 pin in
  ``eval/ledger/runs.jsonl`` and each system_outputs.jsonl must equal its git blob at the run commit, or the
  generator refuses and writes nothing;
- gold in ``data/synthetic/v1/gold/`` (the dataset tree must re-hash to the frozen ``dataset_tree_sha256``);
- ``eval/ledger/{runs,frozen}.jsonl`` and the frozen manifests, for the version/code bindings (C3);
- product code and rule files at the run commit via ``git show`` (citations only; nothing is imported).

Outputs: ``eval/results/e1/POSTHOC_FINDINGS.json`` and a ``.md`` rendered only from that JSON. ``--check``
regenerates both in memory and fails unless they are byte-identical to the committed files.

Stdlib + ``eval.exact`` only. Research prototype - not for clinical use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval.exact import clopper_pearson

HEADER = ("Post-hoc findings - computed after the frozen run from stored predictions; "
          "not part of the predeclared evaluation")
LABEL = "System Evaluation on synthetic data - not clinical performance"
PROTOTYPE = "Research prototype - not for clinical use"
REPO = Path(__file__).resolve().parents[2]
OUT_JSON = "POSTHOC_FINDINGS.json"
OUT_MD = "POSTHOC_FINDINGS.md"

FREEZE_COMMIT = "e5fcd78"
RUN_COMMITS = ("0a9f94e", "8943cd1")
CODE_COMMIT = "8943cd1"  # the test-run commit; product code is identical at the freeze (checked in C3)
SPLITS = ("dev", "test")
EVAL_IDS = {
    ("voice", "dev"): "e1-voice-dev-v1",
    ("triage", "dev"): "e1-triage-dev-v1",
    ("voice", "test"): "e1-voice-test-v1",
    ("triage", "test"): "e1-triage-test-v1",
}
TEXT_RULES_S4 = ("RF-CHEST", "RF-STROKE", "RF-THUNDER", "RF-ANAPH")
VOICE_FIELDS = ("chief_complaint", "onset_duration", "allergy_status")
MOCK_RULES = "backend/app/voice/mock_rules.py"
SERVICE = "backend/app/voice/service.py"
POLICY = "backend/app/voice/policy.py"
RULES_JSON = "backend/app/triage/rules/redflag_rules_v1.json"
VOICE_UI = "web/components/voice/VoiceIntake.tsx"
TRACE_CASE = ("dev", "SYNE-0196")

# Observed by an instrumented replay of dev SYNE-0196 through the unchanged S3 service (in-memory SQLite,
# nothing written under eval/results or eval/ledger). tests/e1r/test_syne0196_replay.py re-runs the replay and
# fails unless it observes exactly this. Test-split cases are analysed from stored outputs only.
REPLAY_TEST = "tests/e1r/test_syne0196_replay.py::test_replay_constant_recomputed"
INSTRUMENTED_REPLAY_SYNE0196 = {
    "verified_by": "tests/e1r/test_syne0196_replay.py",
    "provenance": ("INSTRUMENTED_REPLAY_SYNE0196 is a hand-transcribed constant in eval/posthoc/e1_findings.py; "
                   f"it is recomputed from the dev-only replay and asserted equal by {REPLAY_TEST}."),
    "agent_turns": [
        {"after_turn_index": None, "utterance_id": "ask.chief_complaint", "field": "chief_complaint"},
        {"after_turn_index": 0, "utterance_id": "reask.chief_complaint", "field": "chief_complaint"},
        {"after_turn_index": 1, "utterance_id": "handoff.nurse_attention_phrase", "field": None},
    ],
    "last_asked_field_at_patient_turns": {"1": "chief_complaint", "3": "chief_complaint", "5": "chief_complaint",
                                          "7": "chief_complaint", "9": "chief_complaint",
                                          "11": "chief_complaint"},
    "chief_complaint_facts": [
        {"turn_index": 1, "state": "KNOWN", "value": "fatigue", "value_text": "อ่อนแรง", "superseded": True},
        {"turn_index": 9, "state": "KNOWN", "value": "joint_pain", "value_text": "ปวดข้อ", "superseded": False},
    ],
    "turn_1_contains_gold_cc_text": True,
    "final_facts_equal_stored": True,
}


class PosthocError(RuntimeError):
    """Refusal: an input does not match its pin, or a stored value disagrees with another stored value."""


@dataclass(frozen=True)
class Paths:
    repo: Path = REPO
    results: Path = REPO / "eval" / "results" / "e1"
    data: Path = REPO / "data" / "synthetic" / "v1"
    ledger: Path = REPO / "eval" / "ledger"
    manifests: Path = REPO / "eval" / "manifests" / "e1"
    adapters: Path = REPO / "eval" / "adapters"
    mapping: Path = REPO / "eval" / "adapters" / "mappings" / "e1_mapping_v1.json"


# ---------------------------------------------------------------- helpers


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _jsonl(p: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if r.returncode != 0:
        raise PosthocError(f"git {' '.join(args)} failed: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout.decode("utf-8")


def _git_blob(repo: Path, commit: str, path: str) -> bytes:
    r = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True, check=False)
    if r.returncode != 0:
        raise PosthocError(f"git show {commit}:{path} failed")
    return r.stdout


def _cite(repo: Path, path: str, needle: str, commit: str = CODE_COMMIT) -> dict[str, Any]:
    lines = _git_blob(repo, commit, path).decode("utf-8").split("\n")
    for i, line in enumerate(lines, 1):
        if needle in line:
            return {"file": path, "line": i, "commit": commit, "code": line.strip()}
    raise PosthocError(f"citation not found at {commit}: {path}: {needle!r}")


def _cp(x: int, n: int) -> list[float]:
    lo, hi = clopper_pearson(x, n)
    return [round(lo, 4), round(hi, 4)]


def _yn(v: bool) -> str:
    return "yes" if v else "no"


def _frac(x: int, n: int) -> str:
    return f"{x}/{n}"


def _norm(v: Any) -> str | None:
    if v is None:
        return None
    s = " ".join(str(v).split()).casefold()
    return s or None


def _canonical_sha(obj: Any) -> str:
    return _sha(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False).encode("utf-8"))


def _table(title: str, columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    return {"title": title, "label": LABEL, "columns": columns, "rows": rows}


# ---------------------------------------------------------------- inputs


def load_inputs(p: Paths) -> dict[str, Any]:
    """Read and verify every input. Raises PosthocError (nothing written) on any pin mismatch."""
    runs = _jsonl(p.ledger / "runs.jsonl")
    frozen = _jsonl(p.ledger / "frozen.jsonl")
    run_by_id: dict[str, dict[str, Any]] = {}
    for e in runs:
        if e.get("kind") == "run":
            if e["evaluation_id"] in run_by_id:
                raise PosthocError(f"more than one run entry for {e['evaluation_id']}")
            run_by_id[e["evaluation_id"]] = e
    freeze_by_id = {e["evaluation_id"]: e for e in frozen if e.get("kind") == "freeze"}
    pins = []
    preds: dict[tuple[str, str], list[dict[str, Any]]] = {}
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for (comp, split), eid in EVAL_IDS.items():
        e = run_by_id.get(eid)
        if e is None or not e.get("frozen"):
            raise PosthocError(f"no frozen run entry for {eid} in runs.jsonl")
        for name, key in (("predictions.jsonl", "predictions_sha256"), ("results.json", "results_sha256")):
            rel = f"{split}/{comp}/{name}"
            b = (p.results / rel).read_bytes()
            if _sha(b) != e[key]:
                raise PosthocError(f"hash pin mismatch: eval/results/e1/{rel} != runs.jsonl {eid} {key}")
            pins.append([f"eval/results/e1/{rel}", _sha(b), f"runs.jsonl {eid} {key}", "match"])
        preds[(comp, split)] = _jsonl(p.results / split / comp / "predictions.jsonl")
        results[(comp, split)] = json.loads((p.results / split / comp / "results.json").read_text("utf-8"))
        if results[(comp, split)]["evaluation_id"] != eid or not results[(comp, split)]["frozen"]:
            raise PosthocError(f"results.json for {eid} is not the frozen result")
    system: dict[str, dict[str, dict[str, Any]]] = {}
    for split in SPLITS:
        rel = f"eval/results/e1/{split}/system_outputs.jsonl"
        b = (p.results / split / "system_outputs.jsonl").read_bytes()
        if _sha(b) != _sha(_git_blob(p.repo, CODE_COMMIT, rel)):
            raise PosthocError(f"{rel} differs from its git blob at {CODE_COMMIT}")
        pins.append([rel, _sha(b), f"git blob at {CODE_COMMIT} (not pinned in runs.jsonl)", "match"])
        system[split] = {r["case_id"]: r for r in map(json.loads, b.decode("utf-8").splitlines()) if r}
    manifests = {}
    for eid in EVAL_IDS.values():
        m = json.loads((p.manifests / f"{eid}.json").read_text("utf-8"))
        if _canonical_sha(m) != freeze_by_id[eid]["sha256"] or _canonical_sha(m) != run_by_id[eid]["manifest_sha256"]:
            raise PosthocError(f"manifest {eid} does not match its freeze entry")
        manifests[eid] = m
    hashes = {json.dumps(_manifest_hashes(m), sort_keys=True) for m in manifests.values()}
    if len(hashes) != 1:
        raise PosthocError("the 4 e1 manifests carry different hash bindings")
    bindings = _manifest_hashes(next(iter(manifests.values())))
    gold, tree = load_gold(p.data, bindings["dataset_tree_sha256"])
    split_sha = _sha((p.data / "splits.json").read_bytes())
    if split_sha != bindings["split_sha256"]:
        raise PosthocError("splits.json differs from the frozen split_sha256")
    doc = {"runs": runs, "frozen": frozen, "run_by_id": run_by_id, "freeze_by_id": freeze_by_id, "pins": pins,
           "preds": preds, "results": results, "system": system, "manifests": manifests, "bindings": bindings,
           "gold": gold, "tree": tree, "split_sha": split_sha}
    _cross_check(doc)
    return doc


def _manifest_hashes(m: dict[str, Any]) -> dict[str, Any]:
    c = m["$comment"]
    return json.loads(c[c.rindex("e1-hashes ") + len("e1-hashes "):])


def load_gold(data: Path, frozen_tree: str) -> tuple[dict[str, dict[str, Any]], str]:
    """Gold per split/case; the dataset tree must re-hash to the frozen dataset_tree_sha256."""
    man = json.loads((data / "manifest.json").read_text("utf-8"))
    files = {}
    for rel, listed in man["files"].items():
        h = _sha((data / rel).read_bytes())
        if h != listed:
            raise PosthocError(f"dataset file hash mismatch: {rel}")
        files[rel] = h
    text = "".join(f"{k}\t{v}\n" for k, v in files.items())
    text += (f"model_inputs_glob\t{man.get('model_inputs_glob')}\n"
             f"audit_only_globs\t{json.dumps(man.get('audit_only_globs'))}\n")
    tree = _sha(text.encode())
    if tree != frozen_tree:
        raise PosthocError(f"dataset tree {tree} != frozen {frozen_tree}")
    gold: dict[str, dict[str, Any]] = {}
    for split in SPLITS:
        gold[split] = {}
        for rel in sorted(k for k in files if k.startswith(f"gold/{split}/") and k.endswith(".json")):
            g = json.loads((data / rel).read_text("utf-8"))
            gold[split][g["case_id"]] = g
    return gold, tree


def _cross_check(d: dict[str, Any]) -> None:
    """system_outputs.jsonl must agree with the hash-pinned predictions on every field used here."""
    for split in SPLITS:
        so = d["system"][split]
        if set(so) != set(d["gold"][split]):
            raise PosthocError(f"{split}: system_outputs cases differ from gold cases")
        for r in d["preds"][("voice", split)]:
            if r["task"] == "voice_intake":
                facts = so[r["case_id"]]["voice"].get("facts", {})
                for f in VOICE_FIELDS:
                    if (facts[f]["state"] if f in facts else "MISSING") != r["s3_states"][f]:
                        raise PosthocError(f"{split} {r['case_id']}: S3 {f} state disagrees with predictions")
        for r in d["preds"][("triage", split)]:
            dp = _dp(so[r["case_id"]], r["dp"])
            if "fired_s4" in r and list(r["fired_s4"]) != list(dp["alerts"]):
                raise PosthocError(f"{split} {r['decision_point_id']}: alerts disagree with predictions")
            if "dept_status" in r and (r["dept_status"] != dp["department"]["status"]
                                       or r["system_top3_s4"] != dp["department"]["top3"]):
                raise PosthocError(f"{split} {r['decision_point_id']}: department disagrees with predictions")


def _dp(rec: dict[str, Any], dp: str) -> dict[str, Any]:
    return next(x for x in rec["decision_points"] if x["dp"] == dp)


def _gdp(g: dict[str, Any], dp: str) -> dict[str, Any]:
    return next(x for x in g["decision_times"] if x["decision_point"] == dp)


def _row(d: dict[str, Any], comp: str, split: str, metric_id: str) -> dict[str, Any]:
    return next(r for r in d["results"][(comp, split)]["rows"] if r["metric_id"] == metric_id)


def _verdict(row: dict[str, Any]) -> str | None:
    if not row["thresholds"]:
        return None
    return "PASS" if all(t["status"] == "met" for t in row["thresholds"]) else "FAIL"


def _binary_xn(d: dict[str, Any], comp: str, split: str, task: str, point: float) -> tuple[int, int]:
    rows = [r for r in d["preds"][(comp, split)] if r["task"] == task]
    x, n = sum(1 for r in rows if r["y_pred"] == r["y_true"]), len(rows)
    if n == 0 or abs(x / n - point) > 1e-12:
        raise PosthocError(f"{split} {task}: recomputed {x}/{n} != frozen point {point}")
    return x, n


def _field_counts(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> tuple[int, int, int]:
    tp = fp = fn = 0
    for r in rows:
        for f in fields:
            g, e = _norm(r["gold_fields"].get(f)), _norm(r["extracted_fields"].get(f))
            hit = g is not None and e is not None and g == e
            tp += hit
            fp += e is not None and not hit
            fn += g is not None and not hit
    return tp, fp, fn


# ---------------------------------------------------------------- sections


def section_cc(d: dict[str, Any], repo: Path) -> dict[str, Any]:
    excluded, precision = [], {}
    for split in SPLITS:
        vi = {r["case_id"]: r for r in d["preds"][("voice", split)] if r["task"] == "voice_intake"}
        known_all = correct = 0
        for cid in sorted(vi):
            r = vi[cid]
            cc = d["system"][split][cid]["voice"].get("facts", {}).get("chief_complaint")
            if not cc or cc["state"] != "KNOWN":
                continue
            known_all += 1
            if r["cc_excluded_unmappable"]:
                gcc = _gdp(d["gold"][split][cid], "T1")["required_fields"]["chief_complaint"]
                if gcc["code"] != r["gold_cc_code"]:
                    raise PosthocError(f"{split} {cid}: gold CC code disagrees with predictions")
                excluded.append({"split": split, "case_id": cid, "patient_id": r["patient_id"],
                                 "s3_chief_complaint": cc["value"], "value_text": cc["value_text"],
                                 "span_turn_indexes": cc["span_turn_indexes"], "span_text": cc["span_text"],
                                 "gold_cc_code": gcc["code"], "gold_cc_th_text": gcc["th_text"]})
            elif r["cc_acceptable"] and cc["value"] in r["cc_acceptable"]:
                correct += 1
        cc_rows = [r for r in d["preds"][("voice", split)] if r["task"] == "voice_cc"]
        tp, fp, _ = _field_counts(cc_rows, ("chief_complaint",))
        frozen = _row(d, "voice", split, "voice_cc_precision")
        if tp != correct or abs(tp / (tp + fp) - frozen["point"]) > 1e-12:
            raise PosthocError(f"{split}: frozen voice_cc_precision is not {tp}/{tp + fp}")
        precision[split] = {"frozen_voice_cc_precision": {"x": tp, "n": tp + fp, "point": frozen["point"]},
                            "all_known_cc_precision": {"x": correct, "n": known_all,
                                                       "point": round(correct / known_all, 4),
                                                       "clopper_pearson_95": _cp(correct, known_all)},
                            "n_cases": len(vi), "n_patients": len({r["patient_id"] for r in vi.values()})}
    trace = trace_syne0196(d, repo)
    rows_x = [[e["split"], e["case_id"], e["s3_chief_complaint"], e["value_text"],
               ", ".join(map(str, e["span_turn_indexes"])), e["gold_cc_code"], e["gold_cc_th_text"]]
              for e in excluded]
    rows_p = [[s, _frac(**{k: precision[s]["frozen_voice_cc_precision"][k] for k in ("x", "n")}),
               f"{precision[s]['frozen_voice_cc_precision']['point']:.4f}",
               _frac(precision[s]["all_known_cc_precision"]["x"], precision[s]["all_known_cc_precision"]["n"]),
               f"{precision[s]['all_known_cc_precision']['point']:.4f}",
               "[{:.4f}, {:.4f}]".format(*precision[s]["all_known_cc_precision"]["clopper_pearson_95"]),
               f"{precision[s]['n_cases']} / {precision[s]['n_patients']}"] for s in SPLITS]
    t = trace
    rows_t = [[k, v] for k, v in trace["evidence_rows"]]
    notes = [
        "The frozen voice_cc_precision excludes cases whose gold chief complaint is UNMAPPABLE to the S3 "
        f"vocabulary. S3 still asserted a KNOWN chief complaint in {len(excluded)} such cases (dev+test); each "
        "assertion is wrong by "
        "definition (the mapping forbids e.g. RF-FAST -> fatigue), so the frozen 1.0 hides them.",
        "All-assertion CC precision = correct KNOWN CC assertions / all KNOWN CC assertions over every case of "
        "the split. Clopper-Pearson 95% (eval.exact) assumes independent cases; cases of one patient are not "
        "independent. It is shown beside the frozen value and never replaces it.",
        f"SYNE-0196 classification: {t['classification']}. {t['classification_rationale']}",
        t["replay_statement"],
    ]
    return {
        "id": "C-E1-1",
        "heading": "C-E1-1: CC assertions hidden by exclusion; the SYNE-0196 trace",
        "data": {"excluded_known_cc_assertions": excluded, "cc_precision": precision, "syne0196_trace": trace},
        "notes": notes,
        "tables": [
            _table("KNOWN CC assertions excluded from frozen scoring (gold CC UNMAPPABLE)",
                   ["Split", "Case", "S3 CC", "Value text", "Span turn", "Gold CC code", "Gold CC text"], rows_x),
            _table("CC precision: frozen (scored population) vs all KNOWN assertions",
                   ["Split", "Frozen x/n", "Frozen point", "All-KNOWN x/n", "All-KNOWN point",
                    "All-KNOWN CP 95%", "Cases / patients"], rows_p),
            _table("SYNE-0196 (dev) trace from stored outputs and gold", ["Item", "Value"], rows_t),
            _table("SYNE-0196 code citations (file:line at the run commit)", ["Citation", "Code"],
                   [[f"{c['file']}:{c['line']} @ {c['commit']} ({c['role']})", c["code"]]
                    for c in trace["code_citations"]]),
        ],
    }


def trace_syne0196(d: dict[str, Any], repo: Path) -> dict[str, Any]:
    split, cid = TRACE_CASE
    rec, g = d["system"][split][cid], d["gold"][split][cid]
    v = rec["voice"]
    cc, allergy = v["facts"]["chief_complaint"], v["facts"]["allergy_status"]
    gcc = _gdp(g, "T1")["required_fields"]["chief_complaint"]
    dps = []
    for dpn in ("T1", "T2"):
        dp, gd = _dp(rec, dpn), _gdp(g, dpn)
        dps.append({"dp": dpn, "T": dp["T"], "cc_symptom": dp["input_info"]["cc_symptom"],
                    "department_status": dp["department"]["status"], "top3": dp["department"]["top3"],
                    "alerts": dp["alerts"], "rf_stroke_not_evaluable": "RF-STROKE" in dp["not_evaluable"],
                    "fact_kinds": sorted({f["kind"] for f in dp["facts"]}),
                    "gold_red_flags": sorted({f["rule_id"] for f in gd["red_flags"]}),
                    "gold_target_department": gd["target_department"],
                    "gold_expected_action": gd["expected_action"]})
    cites = [
        dict(_cite(repo, MOCK_RULES, "def _chief_complaint("), role="CC rule"),
        dict(_cite(repo, MOCK_RULES, 'if asked not in (None, "chief_complaint"):'), role="CC gate"),
        dict(_cite(repo, SERVICE, "last_asked = next("), role="last_asked from agent turns only"),
        dict(_cite(repo, SERVICE, 'return handoff("nurse_attention_phrase"'), role="handoff on attention"),
        dict(_cite(repo, POLICY, 'action="handoff", field=None'), role="handoff turn has no field"),
        dict(_cite(repo, SERVICE, 'if action.action == "handoff" and last_agent is not None'),
             role="no further agent turn after handoff"),
        dict(_cite(repo, SERVICE, "def latest_by_field("), role="latest fact per field wins"),
        dict(_cite(repo, MOCK_RULES, '("fatigue", ('), role="fatigue pattern includes the turn-1 word"),
        dict(_cite(repo, MOCK_RULES, '("joint_pain", ('), role="joint_pain pattern matches the allergy answer"),
        dict(_cite(repo, POLICY, '"ปากเบี้ยว"'), role="nurse-attention phrase"),
        dict(_cite(repo, POLICY, "def nurse_attention_hit("), role="deterministic nurse-attention check"),
        dict(_cite(repo, SERVICE, "    if attention:"), role="_decide: attention leads to handoff"),
        dict(_cite(repo, SERVICE, 'if session["status"] != "active":'),
             role="add_turn refuses only sessions that are not active"),
        dict(_cite(repo, SERVICE, '.values(status="finished")'), role="only finish() sets finished"),
        dict(_cite(repo, VOICE_UI, "{!finished && ("), role="web turn form rendered until finish"),
    ]
    at = {c["role"]: f"{Path(c['file']).name}:{c['line']}" for c in cites}
    dec = sorted(c["line"] for c in cites if c["role"] in ("_decide: attention leads to handoff",
                                                            "handoff on attention"))
    if dec[1] != dec[0] + 1:
        raise PosthocError("the _decide attention branch is not two consecutive lines at the run commit")
    at_decide = f"{Path(SERVICE).name}:{dec[0]}-{dec[1]}"
    stored = [
        f"chief_complaint KNOWN {cc['value']} (value_text {cc['value_text']}), span_turn_indexes "
        f"{cc['span_turn_indexes']}, span_text {cc['span_text']}",
        f"allergy_status KNOWN {allergy['value']} from the same span_turn_indexes {allergy['span_turn_indexes']}"
        " (turn 9 is the answer to the drug-reaction question)",
        f"handoff_reason {v['handoff_reason']}; missing_fields {v['missing_fields']}",
        f"S4 input cc_symptom {dps[0]['cc_symptom']} at T1 and {dps[1]['cc_symptom']} at T2; "
        f"no S4 fact kind carries the S3 handoff (T1 fact kinds: {', '.join(dps[0]['fact_kinds'])})",
    ]
    ok = (cc["value"] == "joint_pain" and cc["span_turn_indexes"] == [9] and allergy["span_turn_indexes"] == [9]
          and v["handoff_reason"] == "nurse_attention_phrase" and all(not x["alerts"] for x in dps)
          and all(x["gold_expected_action"] == "escalate" for x in dps))
    if not ok:
        raise PosthocError("SYNE-0196 stored evidence differs from the traced chain; the note would be wrong")
    rep = INSTRUMENTED_REPLAY_SYNE0196
    evidence_rows = [
        ["Turn 1 (gold CC text; replay-checked)",
         f"{gcc['th_text']} ({gcc['code']}; sudden facial droop and one-sided arm weakness)"],
        ["S3 chief_complaint (stored)", f"KNOWN {cc['value']} from turn {cc['span_turn_indexes'][0]}: "
                                        f"{cc['span_text']}"],
        ["S3 allergy_status (stored)", f"KNOWN {allergy['value']} from turn {allergy['span_turn_indexes'][0]}"],
        ["S3 handoff_reason (stored)", v["handoff_reason"]],
        ["Instrumented replay: CC facts",
         "; ".join(f"turn {f['turn_index']} {f['value']} ({f['value_text']})"
                   + (" superseded" if f["superseded"] else " final") for f in rep["chief_complaint_facts"])],
        ["Instrumented replay: agent turns",
         "; ".join(f"{a['utterance_id']} (field {a['field'] or 'none'})" for a in rep["agent_turns"])],
        ["Instrumented replay: final facts equal stored output", _yn(rep["final_facts_equal_stored"])],
        ["Instrumented replay: turn 1 contains the gold CC text", _yn(rep["turn_1_contains_gold_cc_text"])],
        ["Instrumented replay: last_asked at patient turns",
         "; ".join(f"turn {k} {v}" for k, v in rep["last_asked_field_at_patient_turns"].items())],
        ["Instrumented replay: provenance", rep["provenance"]],
    ]
    for x in dps:
        evidence_rows.append([f"S4 at {x['dp']} (stored)",
                              f"cc_symptom {x['cc_symptom']}; department {x['department_status']} top3 "
                              f"[{', '.join(x['top3'])}]; alerts {len(x['alerts'])}; RF-STROKE not_evaluable "
                              f"{_yn(x['rf_stroke_not_evaluable'])}"])
        evidence_rows.append([f"Gold at {x['dp']}", f"red flags {', '.join(x['gold_red_flags'])}; target "
                                                    f"{x['gold_target_department']}; expected "
                                                    f"{x['gold_expected_action']}"])
    return {
        "split": split, "case_id": cid, "patient_id": rec["patient_ref"],
        "stored_file": f"eval/results/e1/{split}/system_outputs.jsonl",
        "gold_chief_complaint": gcc, "voice": {"chief_complaint": cc, "allergy_status": allergy,
                                               "handoff_reason": v["handoff_reason"],
                                               "missing_fields": v["missing_fields"]},
        "decision_points": dps,
        "stored_evidence": stored,
        "instrumented_replay": rep,
        "code_citations": cites,
        "classification": "S3_DEFECT",
        "classification_rationale": (
            "The chain occurs in live use of this exact case, not only in the replay. "
            "(1) S3's own policy hands off right after source turn 1: turn 1 contains ปากเบี้ยว, a listed "
            f"nurse-attention phrase ({at['nurse-attention phrase']}); the check is deterministic "
            f"({at['deterministic nurse-attention check']}); and _decide hands off whenever attention is set "
            f"({at_decide}). So in live use S3 never asks a field other than chief_complaint in this case. "
            f"(2) The handoff turn carries no field ({at['handoff turn has no field']}), and "
            f"{at['last_asked from agent turns only']} takes last_asked from the latest agent turn with a non-null "
            "field, so last_asked stays chief_complaint at every patient turn 1..11 (replay "
            "last_asked_field_at_patient_turns) and the CC gate "
            f"({at['CC gate']}) admits every later patient turn as a chief-complaint answer. "
            "(3) The session stays active after the handoff: add_turn refuses only sessions that are not active "
            f"({at['add_turn refuses only sessions that are not active']}), only finish() sets finished "
            f"({at['only finish() sets finished']}), and the web turn form (speaker patient / relative / nurse) is "
            f"rendered until finish ({at['web turn form rendered until finish']}). "
            "The defect has three parts: (a) the no-field handoff turn leaves last_asked at chief_complaint (above); "
            "(b) a later KNOWN CC silently supersedes an earlier KNOWN CC (latest fact per field wins) with no "
            "conflict flag; (c) one-sided arm weakness is coerced to the fatigue code because S3 has no "
            "focal-deficit code. The only replay-specific differences are that the nurse turns are pre-recorded "
            "text and that there is no ASR or audio; neither changes the S3 code path. The case stays an open HIGH "
            "defect (DEF-E1R-001), not fixed."),
        "replay_statement": (
            f"Dev-only instrumented replay through the unchanged S3 service, in memory ({rep['verified_by']}); "
            "turn numbers are source-transcript turn indexes (the stored span turn index), not replay seq "
            f"numbers. S3's own policy emitted {len(rep['agent_turns'])} agent turns: "
            + ", ".join(a["utterance_id"] for a in rep["agent_turns"]) + ". "
            + " ".join(f"Turn {f['turn_index']} yielded a {f['state']} chief complaint {f['value']} (from "
                       f"{f['value_text']})" + (f"; it was superseded by {n['value']} from turn {n['turn_index']}."
                                                if f["superseded"] else "; it is final.")
                       for f, n in zip(rep["chief_complaint_facts"], rep["chief_complaint_facts"][1:] + [None]))
            + " Turn 9 is the patient's answer to the drug-reaction (allergy) question asked in a nurse turn "
            "after the handoff. The final replay facts equal the "
            f"stored output: {_yn(rep['final_facts_equal_stored'])}. The stored output keeps only the final fact per "
            "field, so only the turn-9 span is visible there. The turn-1 value would also have been wrong for "
            "scoring: the gold CC is UNMAPPABLE to S3. Provenance: " + rep["provenance"]),
        "evidence_rows": evidence_rows,
    }


def _requires_symptom(c: dict[str, Any]) -> bool:
    """True when the condition cannot be true unless some symptom leaf is true."""
    if "symptom" in c:
        return True
    if "any" in c:
        return all(_requires_symptom(x) for x in c["any"])
    if "all" in c:
        return any(_requires_symptom(x) for x in c["all"])
    if "at_least" in c:
        return sum(_requires_symptom(x) for x in c["of"]) > len(c["of"]) - c["at_least"]
    return False


def _symptoms(c: dict[str, Any]) -> list[str]:
    if "symptom" in c:
        return [c["symptom"]]
    return [s for k in ("any", "all", "of") for x in c.get(k, []) for s in _symptoms(x)]


def section_text_rf(d: dict[str, Any], repo: Path) -> dict[str, Any]:
    quoted = {}
    for split in SPLITS:
        row = _row(d, "triage", split, "rf_text_t1_recall")
        x, n = _binary_xn(d, "triage", split, "rf_text_t1_recall", row["point"])
        quoted[split] = {"x": x, "n": n, "point": row["point"], "clopper_pearson_95": _cp(x, n)}
    rules = json.loads(_git_blob(repo, CODE_COMMIT, RULES_JSON).decode("utf-8"))
    by_id = {r["id"]: r for r in rules["rules"]}
    t1 = [(s, cid, _dp(rec, "T1")) for s in SPLITS for cid, rec in sorted(d["system"][s].items())]
    t1_symptom_kinds = sorted({f["kind"] for _, _, dp in t1 for f in dp["facts"] if f["kind"].startswith("symptom.")})
    per_rule = []
    for rid in TEXT_RULES_S4:
        kinds = [f"symptom.{s}" for s in _symptoms(by_id[rid]["condition"])]
        counts = {s: sum(1 for sp, _, dp in t1 if sp == s and any(f["kind"] in kinds for f in dp["facts"]))
                  for s in SPLITS}
        req = _requires_symptom(by_id[rid]["condition"])
        total = sum(counts.values())
        per_rule.append({"rule": rid, "required_fact_kinds": kinds, "requires_one_of_these": req,
                         "citation": _cite(repo, RULES_JSON, f'"id": "{rid}"'),
                         "t1_dps_with_fact": counts, "t1_dps_with_fact_total": total, "t1_dps_total": len(t1),
                         "by_construction": req and total == 0})
    all_bc = all(r["by_construction"] for r in per_rule)
    silent = silent_escalations(d)
    rows_q = [[s, _frac(quoted[s]["x"], quoted[s]["n"]), f"{quoted[s]['point']:.4f}",
               "[{:.4f}, {:.4f}]".format(*quoted[s]["clopper_pearson_95"])] for s in SPLITS]
    rows_r = [[r["rule"], ", ".join(r["required_fact_kinds"]),
               f"{r['citation']['file']}:{r['citation']['line']} @ {r['citation']['commit']}",
               str(r["t1_dps_with_fact"]["dev"]), str(r["t1_dps_with_fact"]["test"]),
               f"{r['t1_dps_with_fact_total']}/{r['t1_dps_total']}",
               "yes" if r["by_construction"] else "no"] for r in per_rule]
    rows_s = [[e["split"], e["case_id"], e["dp"], ", ".join(e["gold_rules"]) or "-", e["gold_target_department"],
               "[" + ", ".join(e["system_top3"]) + "]", str(e["n_alerts"])] for e in silent]
    n_sil = {s: sum(1 for e in silent if e["split"] == s) for s in SPLITS}
    misses = rf_case_recall_misses(d)
    frozen_misses = {}
    for s in SPLITS:
        x, n = _binary_xn(d, "triage", s, "rf_case_recall", _row(d, "triage", s, "rf_case_recall")["point"])
        frozen_misses[s] = n - x
    check_miss_consistency(misses, frozen_misses, silent, not_evaluable_rf_overlap(d))
    mc = rf_case_recall_miss_counts(misses)
    rows_m = [[e["split"], e["case_id"], e["dp"], e["gold_target_department"], e["gold_expected_action"],
               ", ".join(e["gold_rules"]), e["system_outcome"], e["department_reason"],
               "[" + ", ".join(e["system_top3"]) + "]", str(e["n_alerts"]), _yn(e["escalation_required"]),
               ", ".join(e["also_listed_in"])] for e in misses]
    miss_note = (
        "All rf_case_recall misses (gold red-flag-positive decision points with 0 alerts), one row per frozen "
        "rf_case_recall row with y_true true and y_pred false: "
        + "; ".join(f"{s} {mc[s]['total']} (= frozen n - x {frozen_misses[s]}): {mc[s]['suggested']} with a "
                    f"department suggestion, {mc[s]['abstained']} abstained ({mc[s]['abstained_gold_not_evaluable']}"
                    f" of them gold NOT_EVALUABLE), {mc[s]['with_any_alert']} with any alert, "
                    f"{mc[s]['escalation_required_true']} with escalation_required yes" for s in SPLITS)
        + ". The suggested rows are exactly the silent escalations; the gold-NOT_EVALUABLE rows are exactly the "
        "missed C5 overlap (checked; the generator refuses otherwise). A nurse sees 'abstained', not 'urgent': "
        "each abstention here is a red-flag miss, not a safe abstention.")
    bc = ("The zero is by construction: each of the 4 text rules needs at least one of its symptom fact kinds "
          "(three-valued logic: a missing symptom leaves the rule not_evaluable, never fired), and 0 T1 decision "
          "points (dev+test) carry any of them, because S3 records no onset, acuity or exposure and the e1 "
          "mapping gives S4 no acuity-qualified symptom." if all_bc else
          "NOT by construction for every rule: at least one rule has a T1 decision point with a required fact "
          "kind present; see the table.")
    notes = [
        f"Frozen rf_text_t1_recall (quoted, no threshold): dev {_frac(quoted['dev']['x'], quoted['dev']['n'])}, "
        f"test {_frac(quoted['test']['x'], quoted['test']['n'])}.",
        bc,
        f"Symptom fact kinds present at T1 in stored S4 inputs (dev+test): {', '.join(t1_symptom_kinds)}.",
        "Follow-up recommendation (I2): add onset/acuity/exposure capture and a symptom extractor to S3 "
        "(DEF-E1R-002) and an aggregate-NEWS rule to S4 (DEF-E1R-003), then re-evaluate under new, separately "
        "frozen manifests (v2) with disclosure that the v1 test split was already consumed.",
        "Silent escalations: rule = gold expected_action escalate AND system department status suggested AND 0 "
        f"alerts. Dev {n_sil['dev']}, test {n_sil['test']} decision points. A nurse could read these as "
        "routine: a department suggestion with no alert.",
        miss_note,
        fast_abstention_sentence(misses),
    ]
    return {
        "id": "C-E1-2",
        "heading": "C-E1-2: text red flags; silent escalations; all red-flag misses",
        "data": {"rf_text_t1_recall_frozen": quoted, "text_rules": per_rule, "all_by_construction": all_bc,
                 "t1_symptom_fact_kinds": t1_symptom_kinds, "silent_escalations": silent,
                 "silent_escalation_counts": n_sil, "rf_case_recall_misses": misses,
                 "rf_case_recall_miss_counts": mc, "rf_case_recall_frozen_n_minus_x": frozen_misses,
                 "follow_up": {"defects": ["DEF-E1R-002", "DEF-E1R-003"]}},
        "notes": notes,
        "tables": [
            _table("Frozen rf_text_t1_recall (quoted from results.json)",
                   ["Split", "x/n", "Point", "CP 95%"], rows_q),
            _table("S4 text rules: required fact kinds and T1 decision points carrying them",
                   ["S4 rule", "Symptom fact kinds in the rule condition", "Rule citation", "Dev T1 DPs", "Test T1 DPs",
                    "Total", "By construction"], rows_r),
            _table("Silent escalations (gold escalate, department suggested, 0 alerts)",
                   ["Split", "Case", "DP", "Gold rules", "Gold target", "System top3", "Alerts"], rows_s),
            _table("All rf_case_recall misses (gold red-flag-positive, 0 alerts)",
                   ["Split", "Case", "DP", "Gold department", "Gold expected action", "Gold rules", "System outcome",
                    "Dept reason", "System top3", "Alerts", "escalation_required", "Also listed in"], rows_m),
        ],
    }


def _key(e: dict[str, Any]) -> tuple[str, str, str]:
    return e["split"], e["case_id"], e["dp"]


def rf_case_recall_misses(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Every frozen rf_case_recall row with y_true and not y_pred, joined with the stored S4 output and gold."""
    silent = {_key(e) for e in silent_escalations(d)}
    c5 = {_key(e) for e in not_evaluable_rf_overlap(d)}
    out = []
    for split in SPLITS:
        rows = [r for r in d["preds"][("triage", split)] if r["task"] == "rf_case_recall" and r["y_true"]
                and not r["y_pred"]]
        for r in sorted(rows, key=lambda r: (r["case_id"], r["dp"])):
            dp = _dp(d["system"][split][r["case_id"]], r["dp"])
            gd = _gdp(d["gold"][split][r["case_id"]], r["dp"])
            rules = sorted({f["rule_id"] for f in gd["red_flags"]})
            if rules != sorted(r["gold_rules"]) or not rules:
                raise PosthocError(f"{split} {r['decision_point_id']}: gold rules disagree with predictions")
            status = dp["department"]["status"]
            if status not in ("suggested", "abstained"):
                raise PosthocError(f"{split} {r['decision_point_id']}: unexpected department status {status}")
            e = {"split": split, "case_id": r["case_id"], "dp": r["dp"],
                 "gold_target_department": gd["target_department"], "gold_expected_action": gd["expected_action"],
                 "gold_rules": rules, "system_outcome": status, "department_reason": dp["department"]["reason"],
                 "system_top3": dp["department"]["top3"], "n_alerts": len(dp["alerts"]),
                 "escalation_required": bool(dp["escalation_required"])}
            e["also_listed_in"] = [n for n, keys in (("silent escalations", silent), ("C5 overlap", c5))
                                   if _key(e) in keys] or ["none"]
            out.append(e)
    return out


def rf_case_recall_miss_counts(misses: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out = {}
    for split in SPLITS:
        m = [e for e in misses if e["split"] == split]
        ab = [e for e in m if e["system_outcome"] == "abstained"]
        out[split] = {"total": len(m), "suggested": sum(e["system_outcome"] == "suggested" for e in m),
                      "abstained": len(ab),
                      "abstained_gold_not_evaluable": sum(e["gold_target_department"] == "NOT_EVALUABLE" for e in ab),
                      "with_any_alert": sum(e["n_alerts"] > 0 for e in m),
                      "escalation_required_true": sum(e["escalation_required"] for e in m)}
    return out


def check_miss_consistency(misses: list[dict[str, Any]], frozen_misses: dict[str, int],
                           silent: list[dict[str, Any]], overlap: list[dict[str, Any]]) -> None:
    """Refuse unless the miss rows equal n - x of the frozen rf_case_recall row, the suggested rows equal the
    silent-escalation set and the gold-NOT_EVALUABLE rows equal the missed subset of the C5 overlap."""
    counts = rf_case_recall_miss_counts(misses)
    for split in SPLITS:
        if counts[split]["total"] != frozen_misses[split]:
            raise PosthocError(f"{split}: {counts[split]['total']} rf_case_recall misses listed, frozen n - x is "
                               f"{frozen_misses[split]}")
    if {_key(e) for e in misses if e["system_outcome"] == "suggested"} != {_key(e) for e in silent}:
        raise PosthocError("suggested red-flag misses differ from the silent-escalation set")
    if {_key(e) for e in misses if e["gold_target_department"] == "NOT_EVALUABLE"} != {
            _key(e) for e in overlap if e["missed_in_rf_case_recall"]}:
        raise PosthocError("gold-NOT_EVALUABLE red-flag misses differ from the missed subset of the C5 overlap")


def fast_abstention_sentence(misses: list[dict[str, Any]]) -> str:
    fast = [e for e in misses if e["system_outcome"] == "abstained" and "RF-FAST" in e["gold_rules"]]
    if not fast or any(e["gold_target_department"] != "12" for e in fast):
        raise PosthocError("FAST-positive abstentions missing or not gold department 12")
    groups: dict[tuple[str, str], list[str]] = {}
    for e in fast:
        groups.setdefault((e["split"], e["case_id"]), []).append(e["dp"])
    names = ", ".join(f"{s} {c} {'/'.join(dps)}" for (s, c), dps in groups.items())
    return (f"The FAST-positive abstentions ({names}) are misses by the C5 rule: their gold department is 12, so "
            "they are scored in the red-flag metrics, and an abstention with no alert is not a detection.")


def silent_escalations(d: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for split in SPLITS:
        for cid, rec in sorted(d["system"][split].items()):
            for dp in rec["decision_points"]:
                gd = _gdp(d["gold"][split][cid], dp["dp"])
                if gd["expected_action"] == "escalate" and dp["department"]["status"] == "suggested" \
                        and not dp["alerts"]:
                    out.append({"split": split, "case_id": cid, "dp": dp["dp"],
                                "gold_rules": sorted({f["rule_id"] for f in gd["red_flags"]}),
                                "gold_target_department": gd["target_department"],
                                "system_top3": dp["department"]["top3"], "n_alerts": len(dp["alerts"])})
    return out


def section_f1(d: dict[str, Any]) -> dict[str, Any]:
    fields = {"voice_cc": ("voice_cc", ("chief_complaint",)), "voice_dur": ("voice_intake", ("onset_duration",)),
              "voice_allergy": ("voice_intake", ("allergy_status",)), "voice_micro": ("voice_intake", VOICE_FIELDS)}
    degenerate, coverage = [], {}
    for split in SPLITS:
        for prefix, (task, fs) in fields.items():
            row = _row(d, "voice", split, f"{prefix}_f1")
            rows = [r for r in d["preds"][("voice", split)] if r["task"] == task]
            tp, fp, fn = _field_counts(rows, fs)
            if abs(2 * tp / (2 * tp + fp + fn) - row["point"]) > 1e-12:
                raise PosthocError(f"{split} {prefix}_f1: recomputed F1 differs from the frozen point")
            reasons = [r for r, hit in (("ci_low == ci_high", row["ci_low"] == row["ci_high"]),
                                        ("x == n", fp == 0 and fn == 0)) if hit]
            if reasons:
                degenerate.append({"split": split, "metric_id": row["metric_id"], "point": row["point"],
                                   "ci": [row["ci_low"], row["ci_high"]], "reasons": reasons,
                                   "tp": tp, "fp": fp, "fn": fn,
                                   "precision": {"x": tp, "n": tp + fp, "clopper_pearson_95": _cp(tp, tp + fp)},
                                   "recall": {"x": tp, "n": tp + fn, "clopper_pearson_95": _cp(tp, tp + fn)},
                                   "n_cases": len(rows)})
        vi = [r for r in d["preds"][("voice", split)] if r["task"] == "voice_intake"]
        n_cc = sum(1 for r in d["preds"][("voice", split)] if r["task"] == "voice_cc")
        n_excl = sum(1 for r in vi if r["cc_excluded_unmappable"])
        if n_cc + n_excl != len(vi):
            raise PosthocError(f"{split}: CC population does not account for every case")
        f1 = _row(d, "voice", split, "voice_cc_f1")
        coverage[split] = {"voice_cc_f1": f1["point"], "verdict": _verdict(f1), "scored": n_cc,
                           "total": len(vi), "excluded_unmappable": n_excl}
    rows_d = [[e["split"], e["metric_id"], f"{e['point']:.4f}", "[{:.4f}, {:.4f}]".format(*e["ci"]),
               "; ".join(e["reasons"]), f"{e['tp']}/{e['fp']}/{e['fn']}",
               f"{_frac(e['precision']['x'], e['precision']['n'])} "
               "[{:.4f}, {:.4f}]".format(*e["precision"]["clopper_pearson_95"]),
               f"{_frac(e['recall']['x'], e['recall']['n'])} "
               "[{:.4f}, {:.4f}]".format(*e["recall"]["clopper_pearson_95"])] for e in degenerate]
    rows_c = [[s, f"{coverage[s]['voice_cc_f1']:.4f}", coverage[s]["verdict"],
               _frac(coverage[s]["scored"], coverage[s]["total"]), str(coverage[s]["excluded_unmappable"])]
              for s in SPLITS]
    return {
        "id": "C-E1-3",
        "heading": "C-E1-3: degenerate F1; CC coverage",
        "data": {"degenerate_f1_rows": degenerate, "cc_coverage": coverage},
        "notes": [
            "A frozen F1 row is listed when its bootstrap interval has zero width (ci_low == ci_high) or it has "
            "no errors at all (x == n, i.e. fp = fn = 0). Such an interval carries no uncertainty information; "
            "the precision and recall Clopper-Pearson bounds (eval.exact, independent cases assumed) are shown "
            "beside it. The frozen values and verdicts are unchanged.",
            "The voice_cc_f1 verdict is computed on the scored CC population only; the cases with an UNMAPPABLE "
            "gold chief complaint are excluded (counted), so the verdict covers part of each split.",
        ],
        "tables": [
            _table("Degenerate frozen F1 rows with P and R Clopper-Pearson bounds",
                   ["Split", "Metric", "Point", "Bootstrap CI", "Why listed", "tp/fp/fn", "Precision x/n CP 95%",
                    "Recall x/n CP 95%"], rows_d),
            _table("voice_cc_f1 verdict beside CC scored coverage",
                   ["Split", "voice_cc_f1", "Verdict", "Scored/total cases", "Excluded (UNMAPPABLE)"], rows_c),
        ],
    }


def section_voice_scope(repo: Path) -> dict[str, Any]:
    c = _cite(repo, MOCK_RULES, "EXTRACTOR_VERSION = ")
    m = re.search(r'EXTRACTOR_VERSION = "([^"]+)"', c["code"])
    if not m:
        raise PosthocError("extractor version not found")
    ver = m.group(1)
    rows = [
        ["Input", "T1 IntakeTranscript text, replayed turn by turn (text transcript, not speech)"],
        ["Extractor", f"S3 mock rules {ver} ({c['file']}:{c['line']} @ {c['commit']})"],
        ["ASR / audio", "none: no speech recognition and no audio in e1"],
        ["Table 3.2 response latency", "not measured"],
        ["Table 3.2 total time", "not measured"],
        ["Table 3.2 form-filling comparator", "not measured"],
    ]
    return {
        "id": "C2",
        "heading": "C2: what the Voice rows measure",
        "data": {"extractor_version": ver, "extractor_citation": c, "asr": False, "audio": False,
                 "not_measured": ["response latency", "total time", "form-filling comparator"]},
        "notes": [f"The e1 Voice Agent rows measure a text-transcript replay through the S3 mock rules {ver}. "
                  "There is no ASR and no audio. The latency and total-time metrics of Table 3.2 are not "
                  "measured. The rows are key-field extraction on synthetic text only."],
        "tables": [_table("Scope of the e1 Voice Agent rows", ["Aspect", "e1 status"], rows)],
    }


def _adapters_sha256(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def section_bindings(d: dict[str, Any], p: Paths) -> dict[str, Any]:
    repo, b = p.repo, d["bindings"]
    rows: list[list[Any]] = []
    for eid in EVAL_IDS.values():
        rows.append([f"manifest_sha256 {eid}", d["freeze_by_id"][eid]["sha256"],
                     _canonical_sha(d["manifests"][eid]), "match"])
    for eid in EVAL_IDS.values():
        rows.append([f"freeze entry_hash {eid}", d["freeze_by_id"][eid]["entry_hash"], "frozen.jsonl", "-"])
    for eid in EVAL_IDS.values():
        rows.append([f"run entry_hash {eid}", d["run_by_id"][eid]["entry_hash"], "runs.jsonl", "-"])
    rederived = {"adapters_sha256": _adapters_sha256(p.adapters), "mapping_sha256": _sha(p.mapping.read_bytes()),
                 "dataset_tree_sha256": d["tree"], "split_sha256": d["split_sha"]}
    for k, v in rederived.items():
        rows.append([k, b[k], v, "match" if v == b[k] else "MISMATCH"])
    if any(r[3] == "MISMATCH" for r in rows):
        raise PosthocError("a frozen hash binding no longer re-derives")
    rs = sorted({dp["ruleset_version"] for s in SPLITS for r in d["system"][s].values() for dp in r["decision_points"]})
    mv = sorted({dp["department"]["model_version"] or "null (abstained before any model call)"
                 for s in SPLITS for r in d["system"][s].values() for dp in r["decision_points"]})
    rules_ver = json.loads(_git_blob(repo, CODE_COMMIT, RULES_JSON).decode("utf-8"))["version"]
    ext = re.search(r'EXTRACTOR_VERSION = "([^"]+)"', _cite(repo, MOCK_RULES, "EXTRACTOR_VERSION = ")["code"])
    rows.append(["ruleset_version (stored S4 outputs)", ", ".join(rs), f"{RULES_JSON} @ {CODE_COMMIT}: {rules_ver}",
                 "match" if rs == [rules_ver] else "MISMATCH"])
    rows.append(["department model_version (stored S4 outputs)", ", ".join(mv), "-", "-"])
    rows.append(["S3 extractor version", ext.group(1) if ext else "?", f"{MOCK_RULES} @ {CODE_COMMIT}", "-"])
    commits = {}
    for role, c in (("freeze", FREEZE_COMMIT), ("run dev", RUN_COMMITS[0]), ("run test", RUN_COMMITS[1])):
        full = _git(repo, "rev-parse", f"{c}^{{commit}}").strip()
        subj = _git(repo, "log", "-1", "--format=%s", full).strip()
        commits[role] = {"short": c, "full": full, "subject": subj}
        rows.append([f"commit ({role})", c, f"{full} {subj}", "-"])
    trees = {}
    for path in ("backend/app/voice", "backend/app/triage"):
        at_f = _git(repo, "rev-parse", f"{FREEZE_COMMIT}:{path}").strip()
        at_r = _git(repo, "rev-parse", f"{CODE_COMMIT}:{path}").strip()
        trees[path] = {FREEZE_COMMIT: at_f, CODE_COMMIT: at_r}
        rows.append([f"git tree {path} @ {FREEZE_COMMIT}", at_f, f"@ {CODE_COMMIT}: {at_r}",
                     "match" if at_f == at_r else "MISMATCH"])
    diff = _git(repo, "diff", "--name-only", FREEZE_COMMIT, CODE_COMMIT, "--", "backend").strip()
    rows.append([f"git diff {FREEZE_COMMIT} {CODE_COMMIT} -- backend", "empty" if not diff else diff, "-", "-"])
    bound_keys = sorted(b)
    product_bound = any("backend" in k or "product" in k for k in bound_keys)
    rows.append(["product code hash-bound in manifests", "no" if not product_bound else "yes",
                 "e1-hashes keys: " + ", ".join(bound_keys), "-"])
    return {
        "id": "C3",
        "heading": "C3: version and code bindings",
        "data": {"bindings_frozen": b, "bindings_rederived": rederived, "ruleset_version": rs,
                 "department_model_version": mv, "extractor_version": ext.group(1) if ext else None,
                 "commits": commits, "git_trees": trees, "backend_diff_freeze_to_run_empty": not diff,
                 "product_code_hash_bound": product_bound, "stored_file_pins": d["pins"]},
        "notes": [
            "Product code (backend/app/voice, backend/app/triage) is not hash-bound in the e1 manifests: the "
            "e1-hashes bindings cover the dataset tree, splits, mapping and eval/adapters only. The binding to "
            f"product code is by git: the trees below are identical at the freeze ({FREEZE_COMMIT}) and the test "
            f"run ({CODE_COMMIT}), and git diff {FREEZE_COMMIT} {CODE_COMMIT} -- backend is "
            f"{'empty' if not diff else 'NOT empty'}.",
        ],
        "tables": [
            _table("Version and code bindings", ["Item", "Frozen / recorded", "Re-derived", "Check"], rows),
            _table("Stored inputs and their pins", ["File", "sha256", "Pinned by", "Check"], d["pins"]),
        ],
    }


def not_evaluable_rf_overlap(d: dict[str, Any]) -> list[dict[str, Any]]:
    """C5: decision points that are gold NOT_EVALUABLE and gold red-flag-positive."""
    overlap = []
    for split in SPLITS:
        pred = {(r["task"], r["decision_point_id"]): r for r in d["preds"][("triage", split)]}
        for cid, g in sorted(d["gold"][split].items()):
            for gd in g["decision_times"]:
                if gd["target_department"] == "NOT_EVALUABLE" and gd["red_flags"]:
                    dpid = f"{cid}/{gd['decision_point']}"
                    ab, rc = pred.get(("abst_on_not_evaluable", dpid)), pred.get(("rf_case_recall", dpid))
                    if ab is None or rc is None:
                        raise PosthocError(f"{split} {dpid}: expected abstention and red-flag rows")
                    overlap.append({"split": split, "case_id": cid, "dp": gd["decision_point"],
                                    "gold_rules": sorted({f["rule_id"] for f in gd["red_flags"]}),
                                    "gold_expected_action": gd["expected_action"],
                                    "system_department_status": ab["dept_status"],
                                    "counted_correct_abstention": ab["y_pred"] == ab["y_true"],
                                    "rf_case_recall_y_pred": bool(rc["y_pred"]), "alerts": rc["fired_s4"],
                                    "missed_in_rf_case_recall": not rc["y_pred"]})
    return overlap


def section_dept12(d: dict[str, Any]) -> dict[str, Any]:
    counts, overlap = {}, not_evaluable_rf_overlap(d)
    for split in SPLITS:
        dts = [gd for g in d["gold"][split].values() for gd in g["decision_times"]]
        counts[split] = {"dept_12_dps": sum(gd["target_department"] == "12" for gd in dts),
                         "dept_12_gold_escalate": sum(gd["target_department"] == "12"
                                                      and gd["expected_action"] == "escalate" for gd in dts)}
    rows_c = [[s, str(counts[s]["dept_12_dps"]), str(counts[s]["dept_12_gold_escalate"])] for s in SPLITS]
    n_correct = sum(1 for e in overlap if e["counted_correct_abstention"])
    missed = [f"{e['split']} {e['case_id']} {e['dp']}" for e in overlap if e["missed_in_rf_case_recall"]]
    detected = [f"{e['split']} {e['case_id']} {e['dp']} (y_pred=true; S4 fired {', '.join(e['alerts'])}; gold "
                f"{', '.join(e['gold_rules'])})" for e in overlap if not e["missed_in_rf_case_recall"]]
    rows_o = [[e["split"], e["case_id"], e["dp"], ", ".join(e["gold_rules"]), e["gold_expected_action"],
               e["system_department_status"], "yes" if e["counted_correct_abstention"] else "no",
               ", ".join(e["alerts"]) or "none", "yes" if e["missed_in_rf_case_recall"] else "no"] for e in overlap]
    return {
        "id": "C5",
        "heading": "C5: dept 12 vs NOT_EVALUABLE",
        "data": {"rules": {"12": "scored by the red-flag metrics (not a department in S4)",
                           "NOT_EVALUABLE": "abstention population only"},
                 "counts": counts, "not_evaluable_and_red_flag_positive": overlap,
                 "precedence_for_safety_reading": "escalation"},
        "notes": [
            "Mapping rules (e1_mapping_v1, frozen): gold department 12 (emergency) -> red-flag metrics, because S4 "
            "routes urgency through alerts; NOT_EVALUABLE (chief complaint missing) -> abstention metrics only.",
            f"Dept-12 decision points: dev {counts['dev']['dept_12_dps']}, test {counts['test']['dept_12_dps']}; "
            f"gold-escalate among them: dev {counts['dev']['dept_12_gold_escalate']}, test "
            f"{counts['test']['dept_12_gold_escalate']}.",
            f"The {len(overlap)} decision points below are both NOT_EVALUABLE and gold red-flag-positive. "
            f"{n_correct} of {len(overlap)} count as correct abstentions in abst_rate_not_evaluable; "
            f"{len(missed)} of them are missed in rf_case_recall ({', '.join(missed) or 'none'})"
            + (f"; {len(detected)} of them is detected: {'; '.join(detected)}" if detected else "") + ". "
            "For safety reading, escalation takes precedence: an abstention with no alert on a red-flag-positive "
            "decision point is a miss, not a success.",
        ],
        "tables": [
            _table("Gold department 12 decision points", ["Split", "Dept-12 DPs", "Gold escalate"], rows_c),
            _table("NOT_EVALUABLE and gold red-flag-positive decision points",
                   ["Split", "Case", "DP", "Gold rules", "Gold action", "System department", "Correct abstention",
                    "S4 alerts fired", "Missed in rf_case_recall"], rows_o),
        ],
    }


def defects(d: dict[str, Any], sec: dict[str, dict[str, Any]], repo: Path) -> list[dict[str, Any]]:
    tr = sec["C-E1-1"]["data"]["syne0196_trace"]
    text = sec["C-E1-2"]["data"]
    agg = {}
    for split in SPLITS:
        dps = [(cid, gd) for cid, g in sorted(d["gold"][split].items()) for gd in g["decision_times"]
               if any(f["rule_id"] == "RF-NEWS-AGG5" for f in gd["red_flags"])]
        agg[split] = {"gold_dps": len(dps), "first_case": dps[0][0] if dps else None,
                      "with_any_alert": sum(1 for cid, gd in dps
                                            if _dp(d["system"][split][cid], gd["decision_point"])["alerts"])}
    q = text["rf_text_t1_recall_frozen"]
    return [
        {"id": "DEF-E1R-001", "severity": "HIGH", "target_slice": "i2",
         "component": "S3 voice: chief-complaint attribution (backend/app/voice/service.py last_asked; "
                      "backend/app/voice/mock_rules.py _chief_complaint gate)",
         "repro": {"split": tr["split"], "case_id": tr["case_id"], "stored_file": tr["stored_file"],
                   "steps": "Replay the dev SYNE-0196 T1 IntakeTranscript through the S3 session service "
                            "(tests/e1r/test_syne0196_replay.py); read the final chief_complaint fact."},
         "observed": f"CC KNOWN {tr['voice']['chief_complaint']['value']} from turn "
                     f"{tr['voice']['chief_complaint']['span_turn_indexes'][0]} (the allergy answer) after a "
                     f"{tr['voice']['handoff_reason']} handoff, superseding the turn-1 KNOWN CC "
                     f"{tr['instrumented_replay']['chief_complaint_facts'][0]['value']} (dev replay); S4 cc_symptom {tr['decision_points'][0]['cc_symptom']}, "
                     f"top3 [{', '.join(tr['decision_points'][0]['top3'])}], 0 alerts at T1 and T2.",
         "expected": "No chief complaint taken from an answer to another question; a CC that cannot be expressed "
                     "(focal deficit) is not coerced to a code; after a nurse-attention handoff the case is "
                     "escalated, never routed to a routine department.",
         "evidence": [f"{c['file']}:{c['line']} @ {c['commit']} ({c['role']})" for c in tr["code_citations"]]
                     + [f"gold {', '.join(tr['decision_points'][0]['gold_red_flags'])}, target "
                        f"{tr['decision_points'][0]['gold_target_department']}, expected "
                        f"{tr['decision_points'][0]['gold_expected_action']}",
                        f"classification {tr['classification']} (C-E1-1)"],
         "live_use_reachable": True,
         "live_use_reachability": (
             f"In live use of this exact case ({tr['split']} {tr['case_id']}), S3 hands off right after turn 1 "
             "(nurse-attention phrase ปากเบี้ยว) and the session stays active, so a patient answer entered after "
             "the handoff (e.g. the allergy answer) reaches the CC gate with last_asked chief_complaint and can "
             "replace the turn-1 CC, as in the replay.")},
        {"id": "DEF-E1R-002", "severity": "HIGH", "target_slice": "i2",
         "component": "S3 voice extractor (no onset/acuity/exposure capture, no symptom extractor) and the S3->S4 "
                      "fact path",
         "repro": {"split": "dev", "case_id": "SYNE-0196", "stored_file": "eval/results/e1/dev/system_outputs.jsonl",
                   "steps": "Read decision_points[].facts at T1 for any gold text-red-flag case: no "
                            "symptom.sudden_*, acute_chest_pain, thunderclap_headache or allergen_exposure fact."},
         "observed": f"0 T1 decision points (dev+test) carry a fact kind required by RF-CHEST, RF-STROKE, "
                     f"RF-THUNDER or RF-ANAPH; rf_text_t1_recall dev {q['dev']['x']}/{q['dev']['n']}, test "
                     f"{q['test']['x']}/{q['test']['n']}.",
         "expected": "Text red flags stated in the interview reach S4 as the acuity-qualified facts its rules "
                     "need, so the rules are evaluable (S4-A01 recall target 1.00).",
         "evidence": [f"{r['citation']['file']}:{r['citation']['line']} @ {r['citation']['commit']} ({r['rule']})"
                      for r in text["text_rules"]] + ["C-E1-2 table: 0 T1 DPs per rule"]},
        {"id": "DEF-E1R-003", "severity": "HIGH", "target_slice": "i2",
         "component": f"S4 red-flag rules ({RULES_JSON}): no aggregate-NEWS rule",
         "repro": {"split": "dev", "case_id": agg["dev"]["first_case"],
                   "stored_file": "eval/results/e1/dev/triage/predictions.jsonl",
                   "steps": "Filter rf_rule_recall rows whose gold_rules contain RF-NEWS-AGG5: the pair is "
                            "UNMAPPABLE and scored as missed."},
         "observed": f"RF-NEWS-AGG5 gold decision points: dev {agg['dev']['gold_dps']} "
                     f"({agg['dev']['with_any_alert']} with any alert), test {agg['test']['gold_dps']} "
                     f"({agg['test']['with_any_alert']} with any alert); no S4 rule can express an aggregate "
                     "NEWS score of 5 or more.",
         "expected": "An aggregate NEWS rule in S4 so gold RF-NEWS-AGG5 decision points can be detected.",
         "evidence": ["e1_mapping_v1 red_flag_s1r: RF-NEWS-AGG5 -> UNMAPPABLE",
                      f"{RULES_JSON} @ {CODE_COMMIT}: rule ids " + ", ".join(
                          r["id"] for r in json.loads(_git_blob(repo, CODE_COMMIT, RULES_JSON))["rules"])]},
    ]


def headline(d: dict[str, Any], sec: dict[str, dict[str, Any]]) -> list[str]:
    rc = {s: _row(d, "triage", s, "rf_case_recall") for s in SPLITS}
    rr = {s: _row(d, "triage", s, "rf_rule_recall") for s in SPLITS}
    xn = {s: _binary_xn(d, "triage", s, "rf_case_recall", rc[s]["point"]) for s in SPLITS}
    d3 = {s: _row(d, "triage", s, "dept_top3") for s in SPLITS}
    cc = sec["C-E1-1"]["data"]["cc_precision"]
    mc = sec["C-E1-2"]["data"]["rf_case_recall_miss_counts"]
    q = sec["C-E1-2"]["data"]["rf_text_t1_recall_frozen"]
    return [
        f"Red-flag recall FAILS the predeclared threshold (point >= 1.00) on both splits: case-level dev "
        f"{xn['dev'][0]}/{xn['dev'][1]} ({rc['dev']['point']:.4f}, {_verdict(rc['dev'])}), test "
        f"{xn['test'][0]}/{xn['test'][1]} ({rc['test']['point']:.4f}, {_verdict(rc['test'])}); rule-level dev "
        f"{rr['dev']['point']:.4f} ({_verdict(rr['dev'])}), test {rr['test']['point']:.4f} ({_verdict(rr['test'])}).",
        f"Red-flag misses: dev {mc['dev']['total']} and test {mc['test']['total']} gold red-flag-positive decision "
        f"points got 0 alerts; of those, dev {mc['dev']['suggested']} / test {mc['test']['suggested']} got a "
        f"department suggestion and dev {mc['dev']['abstained']} / test {mc['test']['abstained']} abstained (a "
        "miss, not a safe abstention); text red flags at T1 score zero by construction (dev "
        f"{q['dev']['x']}/{q['dev']['n']}, test {q['test']['x']}/{q['test']['n']}).",
        f"The frozen CC precision of 1.0 excludes wrong assertions: over all KNOWN CC assertions it is dev "
        f"{cc['dev']['all_known_cc_precision']['x']}/{cc['dev']['all_known_cc_precision']['n']} and test "
        f"{cc['test']['all_known_cc_precision']['x']}/{cc['test']['all_known_cc_precision']['n']}; dev SYNE-0196 "
        "(stroke-sign presentation) was routed to ORTHO/MED with no alert - an S3 defect reachable in live use, "
        "open HIGH defect DEF-E1R-001.",
        f"Department top-3 FAILS its threshold (>= 0.80): dev {d3['dev']['point']:.4f}, test "
        f"{d3['test']['point']:.4f}; three HIGH defects are filed for I2 (DEF-E1R-001..003).",
        "Claim boundary: System Evaluation of a research prototype on synthetic data with text-transcript replay "
        "through mock rules; no ASR, no audio, no clinician review, not clinical performance; these post-hoc "
        "numbers never replace a frozen value or verdict.",
    ]


# ---------------------------------------------------------------- document + render


def build(p: Paths = Paths()) -> dict[str, Any]:
    d = load_inputs(p)
    secs = [section_cc(d, p.repo), section_text_rf(d, p.repo), section_f1(d), section_voice_scope(p.repo),
            section_bindings(d, p), section_dept12(d)]
    by_id = {s["id"]: s for s in secs}
    defs = defects(d, by_id, p.repo)
    heads = headline(d, by_id)
    secs.append({
        "id": "DEFECTS", "heading": "Defects filed for I2", "data": {"n_defects": len(defs)},
        "notes": ["Filed for I2; not repaired in e1r. Each defect keeps its evidence and a stored-file repro.",
                  f"DEF-E1R-001 live-use reachable: {_yn(defs[0]['live_use_reachable'])}. "
                  + defs[0]["live_use_reachability"]],
        "tables": [_table("Defects filed for I2",
                          ["ID", "Severity", "Target", "Component", "Repro", "Observed", "Expected"],
                          [[x["id"], x["severity"], x["target_slice"], x["component"],
                            f"{x['repro']['split']} {x['repro']['case_id']} ({x['repro']['stored_file']})",
                            x["observed"], x["expected"]] for x in defs])],
    })
    secs.append({"id": "HEADLINE", "heading": "Headline for the progress report", "data": {}, "notes": [],
                  "bullets": heads, "tables": []})
    return {
        "header": HEADER,
        "label": LABEL,
        "status": PROTOTYPE,
        "title": "E1 post-hoc findings (slice e1r, revised in e1r2)",
        "slice": "e1r",
        "scope": ("Disclosure only: computed after the frozen e1 run from stored, hash-pinned outputs. No metric, "
                  "verdict, manifest, adapter or ledger line is changed; nothing is re-run; the test split is "
                  "analysed from stored outputs only."),
        "evaluation_ids": list(EVAL_IDS.values()),
        "sections": secs,
        "defects": defs,
        "headline": heads,
        "spec_deviations": [],
    }


def _cell(v: Any) -> str:
    s = "-" if v is None else _yn(v) if isinstance(v, bool) else str(v)
    return s.replace("|", "\\|").replace("\n", " ")


def render_md(doc: dict[str, Any]) -> str:
    out = [doc["header"], "", f"# {doc['title']}", "", f"> **{doc['label']}**", f"> **{doc['status']}**", "",
           doc["scope"], "", f"Evaluation IDs: {', '.join(doc['evaluation_ids'])}.", ""]
    for s in doc["sections"]:
        out += [f"## {s['heading']}", ""]
        for n in s["notes"]:
            out += [n, ""]
        for b in s.get("bullets", []):
            out.append(f"- {b}")
        if s.get("bullets"):
            out.append("")
        for t in s["tables"]:
            out += [f"### {t['title']}", "", f"> **{t['label']}**", ""]
            out.append("| " + " | ".join(t["columns"]) + " |")
            out.append("|" + "---|" * len(t["columns"]))
            out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in t["rows"]]
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def render(doc: dict[str, Any]) -> tuple[str, str]:
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n", render_md(doc)


def run(p: Paths, check: bool = False) -> int:
    """Generate (or --check) the findings. 0 ok, 1 check failed, 2 refused (nothing written)."""
    try:
        js, md = render(build(p))
    except PosthocError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    targets = {p.results / OUT_JSON: js, p.results / OUT_MD: md}
    if check:
        bad = [k.name for k, v in targets.items() if not k.is_file() or k.read_bytes() != v.encode("utf-8")]
        if bad:
            print("CHECK FAILED (not byte-identical): " + ", ".join(bad), file=sys.stderr)
            return 1
        print("CHECK OK: POSTHOC_FINDINGS.json and .md are byte-identical to a fresh regeneration")
        return 0
    for k, v in targets.items():
        k.write_bytes(v.encode("utf-8"))
    print("wrote " + ", ".join(k.name for k in targets))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.posthoc.e1_findings", description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="fail unless regeneration is byte-identical")
    ap.add_argument("--data", type=Path, default=Paths().data, help="S1r dataset root (must be the frozen tree)")
    a = ap.parse_args(argv)
    return run(Paths(data=a.data), check=a.check)


if __name__ == "__main__":
    sys.exit(main())
