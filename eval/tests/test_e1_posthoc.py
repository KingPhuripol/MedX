"""Slice e1r: post-hoc findings computed from the frozen, stored e1 outputs (no metric change, no new run).

The S1r dataset is generated into a tmp dir with ``python -m data_factory generate`` in a subprocess (no import
of data_factory under eval/). Nothing here writes under eval/results or eval/ledger. Research prototype.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from eval.posthoc import e1_findings as F

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "eval" / "results" / "e1"
FORBIDDEN = re.compile(r"diagnos|clinical efficacy demonstrated|accuracy of diagnosis|clinical efficacy",
                       re.IGNORECASE)
SECTION_HEADINGS = [
    "## C-E1-1: ", "## C-E1-2: ", "## C-E1-3: ", "## C2: ", "## C3: ", "## C5: ",
    "## Defects filed for I2", "## Headline for the progress report",
]


@pytest.fixture(scope="module")
def ds(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("s1r") / "v1"
    env = {**os.environ, "PYTHONPATH": f"{REPO}{os.pathsep}{REPO / 'backend'}"}
    subprocess.run([sys.executable, "-m", "data_factory", "generate", "--seed", "20260926", "--out", str(out)],
                   check=True, cwd=REPO, env=env, capture_output=True)
    return out


@pytest.fixture(scope="module")
def doc(ds) -> dict:
    return F.build(F.Paths(data=ds))


def _section(doc: dict, sid: str) -> dict:
    return next(s for s in doc["sections"] if s["id"] == sid)


def _results_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "results"
    shutil.copytree(RESULTS, dst)
    for name in (F.OUT_JSON, F.OUT_MD):
        (dst / name).unlink(missing_ok=True)
    return dst


# ---------------------------------------------------------------- 1. hash pins


@pytest.mark.parametrize("rel", ["dev/voice/predictions.jsonl", "test/triage/results.json",
                                 "dev/system_outputs.jsonl"])
def test_hash_pins_refuse_tampered(ds, tmp_path, capsys, rel):
    res = _results_copy(tmp_path)
    p = res / rel
    b = bytearray(p.read_bytes())
    b[len(b) // 2] ^= 0x01
    p.write_bytes(bytes(b))
    before = sorted(x.relative_to(res).as_posix() for x in res.rglob("*"))
    assert F.run(F.Paths(results=res, data=ds)) == 2
    assert "REFUSED" in capsys.readouterr().err
    assert sorted(x.relative_to(res).as_posix() for x in res.rglob("*")) == before
    assert not (res / F.OUT_JSON).exists() and not (res / F.OUT_MD).exists()
    with pytest.raises(F.PosthocError):
        F.build(F.Paths(results=res, data=ds))


def test_hash_pins_match_ledger_for_4_evaluation_ids(doc):
    pins = _section(doc, "C3")["data"]["stored_file_pins"]
    ledger_pins = [r for r in pins if r[2].startswith("runs.jsonl")]
    assert len(ledger_pins) == 8 and all(r[3] == "match" for r in pins)
    assert {r[2].split()[1] for r in ledger_pins} == set(F.EVAL_IDS.values())


def test_refuses_wrong_dataset_tree(ds, tmp_path):
    bad = tmp_path / "ds"
    shutil.copytree(ds, bad)
    g = next((bad / "gold" / "dev").glob("*.json"))
    g.write_text(g.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(F.PosthocError, match="dataset file hash mismatch"):
        F.build(F.Paths(data=bad))


def _resign(ds: Path, rel: str) -> None:
    """Re-list one file's sha256 in manifest.json, so only the E1 projection check can catch the change."""
    man = json.loads((ds / "manifest.json").read_text(encoding="utf-8"))
    man["files"][rel] = hashlib.sha256((ds / rel).read_bytes()).hexdigest()
    (ds / "manifest.json").write_text(json.dumps(man, indent=2), encoding="utf-8")


def _edit_gold(ds: Path, rel: str, fn) -> None:
    p = ds / rel
    g = json.loads(p.read_text(encoding="utf-8"))
    fn(g)
    p.write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
    _resign(ds, rel)


def _set_t1(key, value):
    return lambda g: next(d for d in g["decision_times"] if d["decision_point"] == "T1").__setitem__(key, value)


@pytest.mark.parametrize("rel,fn", [
    ("gold/dev/SYNE-0196.json", _set_t1("expected_action", "suggest")),
    ("gold/test/SYNE-0009.json", _set_t1("red_flags", [{"item_ids": [], "rule_id": "RF-TAMPERED"}])),
    ("gold/train/SYNE-0001.json", _set_t1("department_evaluable", None)),
    ("gold/dev/SYNE-0196.json", lambda g: g.__setitem__("patient_ref", "SYNP-9999")),
])
def test_projection_refuses_changed_used_gold_field(ds, tmp_path, rel, fn):
    bad = tmp_path / "ds"
    shutil.copytree(ds, bad)
    _edit_gold(bad, rel, fn)
    with pytest.raises(F.PosthocError, match="E1 data projection .* != frozen"):
        F.build(F.Paths(data=bad))


def test_projection_refuses_missing_used_gold_field(ds, tmp_path):
    bad = tmp_path / "ds"
    shutil.copytree(ds, bad)
    _edit_gold(bad, "gold/dev/SYNE-0196.json", lambda g: g["decision_times"][0].pop("required_fields"))
    with pytest.raises(F.PosthocError, match="gold field used by E1 is missing"):
        F.build(F.Paths(data=bad))


def test_projection_refuses_changed_or_added_input(ds, tmp_path):
    bad = tmp_path / "ds"
    shutil.copytree(ds, bad)
    snap = sorted((bad / "inputs" / "dev").rglob("snapshot_T1.json"))[0]
    b = bytearray(snap.read_bytes())
    b[len(b) // 2] ^= 0x01
    snap.write_bytes(bytes(b))
    _resign(bad, snap.relative_to(bad).as_posix())
    with pytest.raises(F.PosthocError, match="E1 data projection .* != frozen"):
        F.build(F.Paths(data=bad))
    extra = tmp_path / "ds2"
    shutil.copytree(ds, extra)
    (extra / "inputs" / "dev" / "stray.json").write_text("{}", encoding="utf-8")
    with pytest.raises(F.PosthocError, match="inputs/\\*\\* on disk differs"):
        F.build(F.Paths(data=extra))


def test_projection_ignores_gold_keys_e1_does_not_read(ds, tmp_path, doc):
    """Additive / unread gold keys (s6 care labels, label_version, medication_issues) leave E1 unchanged."""
    alt = tmp_path / "ds"
    shutil.copytree(ds, alt)

    def fn(g):
        g["label_version"] = "9.9.9"
        for d in g["decision_times"]:
            d["care"] = {"tampered": True}
            d["medication_issues"] = []

    _edit_gold(alt, "gold/dev/SYNE-0196.json", fn)
    assert F.render(F.build(F.Paths(data=alt))) == F.render(doc)


def test_projection_pin_recomputed_from_frozen_generator(tmp_path):
    """E1_PROJECTION_SHA256 is recomputed from the S1r v1.1.1 generator at 8943cd1 (the e1 frozen tree)."""
    src = tmp_path / "src"
    src.mkdir()
    arch = subprocess.run(["git", "-C", str(REPO), "archive", "8943cd1", "data_factory", "casegraph", "backend",
                           "schemas"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(src)], input=arch, check=True)
    out = tmp_path / "v111"
    env = {**os.environ, "PYTHONPATH": f"{src}{os.pathsep}{src / 'backend'}"}
    subprocess.run([sys.executable, "-m", "data_factory", "generate", "--seed", "20260926", "--out", str(out)],
                   check=True, cwd=src, env=env, capture_output=True)
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    frozen = F._manifest_hashes(json.loads((REPO / "eval/manifests/e1/e1-voice-dev-v1.json").read_text("utf-8")))
    assert man["generator_version"] == "1.1.1"
    assert man["tree_sha256"] == frozen["dataset_tree_sha256"] == F.E1_PROJECTION_FROZEN_TREE
    files = {rel: hashlib.sha256((out / rel).read_bytes()).hexdigest() for rel in man["files"]}
    assert files == man["files"]
    assert F.e1_data_projection(out, files)[0] == F.E1_PROJECTION_SHA256


# ---------------------------------------------------------------- 2. byte-identical regeneration


def test_check_byte_identical(ds, tmp_path, doc):
    assert F.run(F.Paths(data=ds), check=True) == 0
    js, md = F.render(doc)
    assert (js, md) == F.render(F.build(F.Paths(data=ds)))  # two runs, same bytes
    assert (RESULTS / F.OUT_JSON).read_text(encoding="utf-8") == js
    assert (RESULTS / F.OUT_MD).read_text(encoding="utf-8") == md
    res = _results_copy(tmp_path)
    (res / F.OUT_JSON).write_text(js, encoding="utf-8")
    (res / F.OUT_MD).write_text(md, encoding="utf-8")
    assert F.run(F.Paths(results=res, data=ds), check=True) == 0
    i = md.index("24/26")
    (res / F.OUT_MD).write_text(md[:i] + "25" + md[i + 2:], encoding="utf-8")
    assert F.run(F.Paths(results=res, data=ds), check=True) == 1


def test_md_rendered_from_json_only(doc):
    js, md = F.render(doc)
    assert F.render_md(json.loads(js)) == md


# ---------------------------------------------------------------- 3. C-E1-1


def test_cc_known_precision(doc):
    data = _section(doc, "C-E1-1")["data"]
    p = data["cc_precision"]
    assert (p["dev"]["all_known_cc_precision"]["x"], p["dev"]["all_known_cc_precision"]["n"]) == (24, 26)
    assert (p["test"]["all_known_cc_precision"]["x"], p["test"]["all_known_cc_precision"]["n"]) == (19, 20)
    assert p["dev"]["all_known_cc_precision"]["clopper_pearson_95"] == [0.7487, 0.9905]
    assert p["test"]["all_known_cc_precision"]["clopper_pearson_95"] == [0.7513, 0.9987]
    assert (p["dev"]["frozen_voice_cc_precision"]["x"], p["dev"]["frozen_voice_cc_precision"]["n"]) == (24, 24)
    assert (p["test"]["frozen_voice_cc_precision"]["x"], p["test"]["frozen_voice_cc_precision"]["n"]) == (19, 19)
    excl = {(e["split"], e["case_id"], e["s3_chief_complaint"]) for e in data["excluded_known_cc_assertions"]}
    assert excl == {("dev", "SYNE-0012", "fatigue"), ("dev", "SYNE-0196", "joint_pain"),
                    ("test", "SYNE-0031", "fatigue")}
    for e in data["excluded_known_cc_assertions"]:
        assert e["gold_cc_code"].startswith("CC-") and e["span_turn_indexes"]


def test_syne0196_trace(doc):
    t = _section(doc, "C-E1-1")["data"]["syne0196_trace"]
    assert len(t["stored_evidence"]) >= 2
    cited = {(c["file"], c["code"]) for c in t["code_citations"]}
    assert any(f == F.MOCK_RULES and 'asked not in (None, "chief_complaint")' in c for f, c in cited)
    assert any(f == F.SERVICE and "last_asked = next(" in c and '"agent"' in c for f, c in cited)
    assert all(c["commit"] == "8943cd1" and c["line"] > 0 for c in t["code_citations"])
    assert t["voice"]["chief_complaint"]["value"] == "joint_pain"
    assert t["voice"]["chief_complaint"]["span_turn_indexes"] == [9]
    assert t["voice"]["handoff_reason"] == "nurse_attention_phrase"
    assert "ปากเบี้ยว" in t["gold_chief_complaint"]["th_text"]
    assert "แขนอ่อนแรงข้างเดียว" in t["gold_chief_complaint"]["th_text"]
    for dp in t["decision_points"]:
        assert dp["cc_symptom"] == "joint_pain" and dp["top3"] == ["ORTHO", "MED"] and dp["alerts"] == []
        assert dp["gold_red_flags"] == ["RF-FAST"] and dp["gold_target_department"] == "12"
        assert dp["gold_expected_action"] == "escalate"
    rep = t["instrumented_replay"]
    assert [a["utterance_id"] for a in rep["agent_turns"]] == [
        "ask.chief_complaint", "reask.chief_complaint", "handoff.nurse_attention_phrase"]
    assert [(f["turn_index"], f["value"], f["value_text"], f["superseded"]) for f in rep["chief_complaint_facts"]] \
        == [(1, "fatigue", "อ่อนแรง", True), (9, "joint_pain", "ปวดข้อ", False)]
    assert rep["final_facts_equal_stored"] is True and rep["turn_1_contains_gold_cc_text"] is True
    stmt = t["replay_statement"]
    for needle in ("3 agent turns", "ask.chief_complaint, reask.chief_complaint, handoff.nurse_attention_phrase",
                   "Turn 1 yielded a KNOWN chief complaint fatigue (from อ่อนแรง)",
                   "superseded by joint_pain from turn 9", "allergy", "equal the stored output: yes"):
        assert needle in stmt, needle
    notes = " ".join(_section(doc, "C-E1-1")["notes"])
    assert stmt in notes
    js, md = F.render(doc)
    for text in (js, md):
        assert not re.search(r"yielded no|no CC|0 agent turns|no agent turns", text, re.IGNORECASE)


# ---------------------------------------------------------------- 3b. SYNE-0196 classification (e1r2)

FORBIDDEN_0196 = re.compile(r"would ask allergy_status|would not reach the CC gate|asks? allergy_status|"
                            r"REPLAY_ARTIFACT|replay artifact", re.IGNORECASE)
NEW_CITES = {  # file:line at 8943cd1 -> the code the line must hold (verified with git show)
    ("backend/app/voice/policy.py", 17): '"ปากเบี้ยว"',
    ("backend/app/voice/policy.py", 30): "def nurse_attention_hit(",
    ("backend/app/voice/policy.py", 47): 'action="handoff", field=None',
    ("backend/app/voice/service.py", 157): "if attention:",
    ("backend/app/voice/service.py", 158): 'return handoff("nurse_attention_phrase"',
    ("backend/app/voice/service.py", 378): 'if session["status"] != "active":',
    ("backend/app/voice/service.py", 401): "last_asked = next(",
    ("backend/app/voice/service.py", 548): '.values(status="finished")',
    ("web/components/voice/VoiceIntake.tsx", 199): "{!finished && (",
}


def test_syne0196_classification(doc):
    t = _section(doc, "C-E1-1")["data"]["syne0196_trace"]
    assert t["classification"] == "S3_DEFECT"
    rat = t["classification_rationale"]
    # fact 1: handoff right after source turn 1 on ปากเบี้ยว (deterministic)
    assert "hands off right after source turn 1" in rat and "ปากเบี้ยว" in rat
    assert {"policy.py:17", "policy.py:30", "service.py:157-158"} <= set(re.findall(r"\w+\.py:[\d-]+", rat))
    assert "never asks a field other than chief_complaint" in rat
    # fact 2: last_asked stays chief_complaint at every patient turn 1..11
    assert "last_asked stays chief_complaint at every patient turn 1..11" in rat
    assert {"policy.py:47", "service.py:401", "mock_rules.py:195"} <= set(re.findall(r"\w+\.py:\d+", rat))
    assert set(t["instrumented_replay"]["last_asked_field_at_patient_turns"]) == {"1", "3", "5", "7", "9", "11"}
    assert set(t["instrumented_replay"]["last_asked_field_at_patient_turns"].values()) == {"chief_complaint"}
    # fact 3: the session stays active after the handoff
    assert "The session stays active after the handoff" in rat
    assert {"service.py:378", "service.py:548", "VoiceIntake.tsx:199"} <= set(re.findall(r"\w+\.\w+:\d+", rat))
    # parts (a)-(c) and the only replay-specific differences
    for needle in ("(a) the no-field handoff turn", "(b) a later KNOWN CC silently supersedes",
                   "(c) one-sided arm weakness is coerced to the fatigue code",
                   "nurse turns are pre-recorded text", "no ASR or audio", "neither changes the S3 code path"):
        assert needle in rat, needle
    js, md = F.render(doc)
    for text in (js, md, (RESULTS / F.OUT_JSON).read_text("utf-8"), (RESULTS / F.OUT_MD).read_text("utf-8")):
        assert not FORBIDDEN_0196.search(text), FORBIDDEN_0196.search(text)
    cited = {(c["file"], c["line"]): c for c in t["code_citations"]}
    for (f, line), code in NEW_CITES.items():
        assert (f, line) in cited, (f, line)
        assert code in cited[(f, line)]["code"] and cited[(f, line)]["commit"] == "8943cd1"
        at = subprocess.run(["git", "-C", str(REPO), "show", f"8943cd1:{f}"], capture_output=True, check=True)
        assert code in at.stdout.decode("utf-8").split("\n")[line - 1], (f, line)


def test_def001_live_use(doc):
    d1 = doc["defects"][0]
    assert d1["id"] == "DEF-E1R-001" and d1["severity"] == "HIGH" and d1["target_slice"] == "i2"
    assert d1["live_use_reachable"] is True
    stmt = d1["live_use_reachability"]
    assert "SYNE-0196" in stmt and "reaches the CC gate" in stmt and "live use" in stmt
    assert "after the handoff" in stmt and "replace the turn-1 CC" in stmt
    ev = " ".join(d1["evidence"])
    assert "backend/app/voice/service.py:378 @ 8943cd1" in ev and "backend/app/voice/service.py:548 @ 8943cd1" in ev
    assert "classification S3_DEFECT (C-E1-1)" in ev
    for k in ("id", "severity", "target_slice", "component", "repro", "observed", "expected", "evidence"):
        assert d1[k]
    committed = json.loads((RESULTS / F.OUT_JSON).read_text("utf-8"))["defects"][0]
    assert committed["live_use_reachable"] is True and committed["live_use_reachability"] == stmt


# ---------------------------------------------------------------- 4. silent escalations


def test_silent_escalations(doc):
    got = {(e["split"], e["case_id"], e["dp"]) for e in _section(doc, "C-E1-2")["data"]["silent_escalations"]}
    dev = {("dev", c, dp) for c in ("SYNE-0081", "SYNE-0108", "SYNE-0127", "SYNE-0196") for dp in ("T1", "T2")}
    test = {("test", "SYNE-0039", "T2")} | {("test", c, dp) for c in ("SYNE-0101", "SYNE-0187")
                                          for dp in ("T1", "T2")}
    assert got == dev | test
    for e in _section(doc, "C-E1-2")["data"]["silent_escalations"]:
        assert e["n_alerts"] == 0 and e["system_top3"] and e["gold_target_department"]


# ---------------------------------------------------------------- 4b. all red-flag misses (e1r2)


def _dps(split: str, cases: dict[str, str]) -> set[tuple[str, str, str]]:
    return {(split, f"SYNE-{c}", dp) for c, dps in cases.items() for dp in dps.split("/")}


def test_rf_case_recall_misses(doc):
    data = _section(doc, "C-E1-2")["data"]
    rows = data["rf_case_recall_misses"]
    got = {(e["split"], e["case_id"], e["dp"]): e for e in rows}
    assert len(got) == len(rows)
    dev_sug = _dps("dev", {"0081": "T1/T2", "0108": "T1/T2", "0127": "T1/T2", "0196": "T1/T2"})
    dev_ne = _dps("dev", {"0107": "T1/T2"})
    dev_ab = _dps("dev", {"0071": "T1/T2", "0089": "T1/T2", "0119": "T1/T2", "0165": "T2", "0166": "T1/T2"})
    test_sug = _dps("test", {"0039": "T2", "0101": "T1/T2", "0187": "T1/T2"})
    test_ab = _dps("test", {"0033": "T1/T2", "0125": "T1/T2", "0131": "T1/T2", "0141": "T1/T2"})
    assert set(got) == dev_sug | dev_ne | dev_ab | test_sug | test_ab
    assert {k for k, e in got.items() if e["system_outcome"] == "suggested"} == dev_sug | test_sug
    assert {k for k, e in got.items() if e["system_outcome"] == "abstained"} == dev_ne | dev_ab | test_ab
    assert {k for k, e in got.items() if e["gold_target_department"] == "NOT_EVALUABLE"} == dev_ne
    for e in rows:
        assert e["n_alerts"] == 0 and e["escalation_required"] is False and e["gold_rules"]
        assert e["gold_expected_action"] == "escalate"
    silent = {(e["split"], e["case_id"], e["dp"]) for e in data["silent_escalations"]}
    assert {k for k, e in got.items() if "silent escalations" in e["also_listed_in"]} == silent == dev_sug | test_sug
    c5 = {(e["split"], e["case_id"], e["dp"]) for e in _section(doc, "C5")["data"][
        "not_evaluable_and_red_flag_positive"] if e["missed_in_rf_case_recall"]}
    assert {k for k, e in got.items() if "C5 overlap" in e["also_listed_in"]} == c5 == dev_ne
    zero = {"with_any_alert": 0, "escalation_required_true": 0}
    assert data["rf_case_recall_miss_counts"] == {
        "dev": {"total": 19, "suggested": 8, "abstained": 11, "abstained_gold_not_evaluable": 2, **zero},
        "test": {"total": 13, "suggested": 5, "abstained": 8, "abstained_gold_not_evaluable": 0, **zero}}
    assert data["rf_case_recall_frozen_n_minus_x"] == {"dev": 24 - 5, "test": 22 - 9}
    table = next(t for t in _section(doc, "C-E1-2")["tables"] if t["title"].startswith("All rf_case_recall misses"))
    assert len(table["rows"]) == 32 and table["columns"][6] == "System outcome"
    assert {(r[0], r[1], r[2]) for r in table["rows"]} == set(got)


def _miss(split, case, dp, outcome="abstained", dept="12"):
    return {"split": split, "case_id": case, "dp": dp, "system_outcome": outcome, "gold_target_department": dept,
            "n_alerts": 0, "escalation_required": False}


def test_miss_count_mismatch_refused():
    misses = [_miss("dev", "A", "T1", "suggested"), _miss("dev", "B", "T1", dept="NOT_EVALUABLE"),
              _miss("test", "C", "T2")]
    silent = [{"split": "dev", "case_id": "A", "dp": "T1"}]
    overlap = [{"split": "dev", "case_id": "B", "dp": "T1", "missed_in_rf_case_recall": True},
               {"split": "test", "case_id": "D", "dp": "T1", "missed_in_rf_case_recall": False}]
    F.check_miss_consistency(misses, {"dev": 2, "test": 1}, silent, overlap)  # consistent: no raise
    with pytest.raises(F.PosthocError, match="n - x"):  # a miss dropped
        F.check_miss_consistency(misses[1:], {"dev": 2, "test": 1}, silent, overlap)
    with pytest.raises(F.PosthocError, match="n - x"):
        F.check_miss_consistency(misses, {"dev": 3, "test": 1}, silent, overlap)
    with pytest.raises(F.PosthocError, match="silent-escalation"):
        F.check_miss_consistency(misses, {"dev": 2, "test": 1}, silent + [{"split": "test", "case_id": "C",
                                                                          "dp": "T2"}], overlap)
    with pytest.raises(F.PosthocError, match="C5 overlap"):
        F.check_miss_consistency(misses, {"dev": 2, "test": 1}, silent,
                                 [{**overlap[0], "missed_in_rf_case_recall": False}])


def test_fast_abstention_sentence(doc, ds):
    sentence = ("The FAST-positive abstentions (dev SYNE-0166 T1/T2, test SYNE-0033 T1/T2, test SYNE-0131 T1/T2) "
                "are misses by the C5 rule: their gold department is 12, so they are scored in the red-flag "
                "metrics, and an abstention with no alert is not a detection.")
    _, md = F.render(doc)
    assert sentence in md and sentence in (RESULTS / F.OUT_MD).read_text("utf-8")
    for split, cid in (("dev", "SYNE-0166"), ("test", "SYNE-0033"), ("test", "SYNE-0131")):
        g = json.loads((ds / "gold" / split / f"{cid}.json").read_text("utf-8"))
        for gd in g["decision_times"]:
            assert gd["target_department"] == "12"
            assert "RF-FAST" in {f["rule_id"] for f in gd["red_flags"]}
    with pytest.raises(F.PosthocError):
        F.fast_abstention_sentence([{**_miss("dev", "X", "T1", dept="NOT_EVALUABLE"), "gold_rules": ["RF-FAST"]}])


def test_md_no_python_booleans(doc):
    _, md = F.render(doc)
    for text in (md, (RESULTS / F.OUT_MD).read_text("utf-8")):
        assert not re.search(r"\b(True|False)\b", text)
    trace = md.split("### SYNE-0196 (dev) trace", 1)[1].split("###", 1)[0]
    assert "| Instrumented replay: final facts equal stored output | yes |" in trace
    assert "RF-STROKE not_evaluable yes" in trace
    assert F._cell(True) == "yes" and F._cell(False) == "no"
    t = _section(doc, "C-E1-1")["data"]["syne0196_trace"]["instrumented_replay"]
    assert t["final_facts_equal_stored"] is True  # JSON keeps booleans
    prov = t["provenance"]
    assert "hand-transcribed" in prov and "tests/e1r/test_syne0196_replay.py::test_replay_constant_recomputed" in prov
    assert prov in md


# ---------------------------------------------------------------- 5. text-rule fact counts


def test_text_rule_fact_counts(doc):
    data = _section(doc, "C-E1-2")["data"]
    assert (data["rf_text_t1_recall_frozen"]["dev"]["x"], data["rf_text_t1_recall_frozen"]["dev"]["n"]) == (0, 8)
    assert (data["rf_text_t1_recall_frozen"]["test"]["x"], data["rf_text_t1_recall_frozen"]["test"]["n"]) == (0, 6)
    rules = {r["rule"]: r for r in data["text_rules"]}
    assert set(rules) == {"RF-CHEST", "RF-STROKE", "RF-THUNDER", "RF-ANAPH"}
    assert rules["RF-CHEST"]["required_fact_kinds"] == ["symptom.acute_chest_pain"]
    assert len(rules["RF-STROKE"]["required_fact_kinds"]) == 4
    assert "symptom.allergen_exposure" in rules["RF-ANAPH"]["required_fact_kinds"]
    for r in rules.values():
        assert r["t1_dps_total"] == 80 and r["t1_dps_with_fact_total"] == 0 and r["by_construction"]
        assert r["citation"]["file"] == F.RULES_JSON and r["citation"]["commit"] == "8943cd1"
    assert data["all_by_construction"] is True
    notes = " ".join(_section(doc, "C-E1-2")["notes"])
    assert "DEF-E1R-002" in notes and "DEF-E1R-003" in notes


def test_requires_symptom_logic():
    sym, vit = {"symptom": "x"}, {"vital": "sbp", "op": "<", "value": 90}
    assert F._requires_symptom(sym) and not F._requires_symptom(vit)
    assert F._requires_symptom({"all": [sym, {"any": [sym, vit]}]})
    assert not F._requires_symptom({"any": [sym, vit]})
    assert F._requires_symptom({"at_least": 2, "of": [sym, sym, vit]})
    assert not F._requires_symptom({"at_least": 2, "of": [sym, vit, vit]})


# ---------------------------------------------------------------- 6. NOT_EVALUABLE vs red flags; dept 12


def test_not_evaluable_rf_overlap(doc):
    data = _section(doc, "C5")["data"]
    got = {(e["split"], e["case_id"], e["dp"]) for e in data["not_evaluable_and_red_flag_positive"]}
    assert got == {("dev", "SYNE-0107", "T1"), ("dev", "SYNE-0107", "T2"), ("test", "SYNE-0053", "T2")}
    assert all(e["counted_correct_abstention"] for e in data["not_evaluable_and_red_flag_positive"])
    ov = {(e["split"], e["case_id"], e["dp"]): e for e in data["not_evaluable_and_red_flag_positive"]}
    assert {k for k, e in ov.items() if e["missed_in_rf_case_recall"]} == {
        ("dev", "SYNE-0107", "T1"), ("dev", "SYNE-0107", "T2")}
    det = ov[("test", "SYNE-0053", "T2")]
    assert det["rf_case_recall_y_pred"] is True and not det["missed_in_rf_case_recall"]
    assert det["alerts"] == ["RF-CONSC", "RF-QSOFA"] and det["gold_rules"] == ["RF-QSOFA"]
    notes = " ".join(_section(doc, "C5")["notes"])
    assert "2 of them are missed in rf_case_recall (dev SYNE-0107 T1, dev SYNE-0107 T2)" in notes
    assert "test SYNE-0053 T2 (y_pred=true; S4 fired RF-CONSC, RF-QSOFA; gold RF-QSOFA)" in notes
    assert data["counts"]["dev"] == {"dept_12_dps": 22, "dept_12_gold_escalate": 22}
    assert data["counts"]["test"] == {"dept_12_dps": 21, "dept_12_gold_escalate": 21}
    assert data["precedence_for_safety_reading"] == "escalation"


def test_degenerate_f1_and_cc_coverage(doc):
    data = _section(doc, "C-E1-3")["data"]
    rows = {(r["split"], r["metric_id"]) for r in data["degenerate_f1_rows"]}
    assert rows == {(s, m) for s in ("dev", "test") for m in ("voice_dur_f1", "voice_allergy_f1")}
    for r in data["degenerate_f1_rows"]:
        assert r["precision"]["clopper_pearson_95"][1] == 1.0 and r["recall"]["clopper_pearson_95"][0] < 1.0
    cov = data["cc_coverage"]
    assert (cov["dev"]["scored"], cov["dev"]["total"], cov["dev"]["excluded_unmappable"]) == (27, 40, 13)
    assert (cov["test"]["scored"], cov["test"]["total"], cov["test"]["excluded_unmappable"]) == (24, 40, 16)


def test_voice_scope_and_bindings(doc):
    c2 = _section(doc, "C2")["data"]
    assert c2["extractor_version"] == "voice-mock-rules-0.3.0" and c2["asr"] is False and c2["audio"] is False
    c3 = _section(doc, "C3")["data"]
    assert c3["backend_diff_freeze_to_run_empty"] is True and c3["product_code_hash_bound"] is False
    assert c3["bindings_frozen"]["adapters_sha256"] == c3["bindings_rederived"]["adapters_sha256"]
    assert c3["ruleset_version"] == ["rf-1.1.0"]
    assert {v["short"] for v in c3["commits"].values()} == {"e5fcd78", "0a9f94e", "8943cd1"}
    for trees in c3["git_trees"].values():
        assert len(set(trees.values())) == 1


# ---------------------------------------------------------------- 7. defects, headline, labels


def test_defects_and_headline(doc):
    required = {"id", "severity", "target_slice", "component", "repro", "observed", "expected", "evidence"}
    ids = [x["id"] for x in doc["defects"]]
    assert ids == ["DEF-E1R-001", "DEF-E1R-002", "DEF-E1R-003"]
    for x in doc["defects"]:
        assert required <= set(x) and all(x[k] for k in required)
        assert x["severity"] == "HIGH" and x["target_slice"] == "i2"
        assert x["repro"]["case_id"] and x["repro"]["stored_file"].startswith("eval/results/e1/")
    assert doc["defects"][0]["repro"] == {**doc["defects"][0]["repro"], "split": "dev", "case_id": "SYNE-0196"}
    js, md = F.render(doc)
    head = md.split("## Headline for the progress report", 1)[1]
    bullets = [x for x in head.split("\n") if x.startswith("- ")]
    assert len(bullets) == 5 == len(doc["headline"])
    b2 = doc["headline"][1]
    for needle in ("dev 19 and test 13 gold red-flag-positive decision points got 0 alerts",
                   "dev 8 / test 5 got a department suggestion", "dev 11 / test 8 abstained",
                   "by construction (dev 0/8, test 0/6)"):
        assert needle in b2, needle
    assert "SYNE-0196" in doc["headline"][2]
    assert not any(re.search(r"artifact", b, re.IGNORECASE) for b in doc["headline"])
    assert any("FAIL" in b and "dev" in b and "test" in b and "recall" in b for b in bullets)
    assert any(b.startswith("- Claim boundary") for b in bullets)
    for text in (js, md):
        assert not FORBIDDEN.search(text), FORBIDDEN.search(text)
    assert doc["spec_deviations"] == []
    for text in (js, md, (RESULTS / F.OUT_JSON).read_text("utf-8"), (RESULTS / F.OUT_MD).read_text("utf-8")):
        assert "Correction to the e1r spec premise" not in text
    assert json.loads((RESULTS / F.OUT_JSON).read_text("utf-8"))["spec_deviations"] == []


def test_header_labels_and_sections(doc):
    js, md = F.render(doc)
    assert md.startswith(F.HEADER + "\n")
    assert json.loads(js)["header"] == F.HEADER and js.startswith('{\n "header": "' + F.HEADER + '"')
    lines = md.split("\n")
    n_tables = 0
    for i, line in enumerate(lines):
        if line.startswith("|") and not lines[i - 1].startswith("|"):
            n_tables += 1
            assert lines[i - 2] == f"> **{F.LABEL}**", (i, line)
    assert n_tables >= 10
    for s in doc["sections"]:
        assert all(t["label"] == F.LABEL for t in s["tables"])
    pos = [md.index(h) for h in SECTION_HEADINGS]
    assert pos == sorted(pos) and len(doc["sections"]) == 8


def test_posthoc_imports_stdlib_and_eval_exact_only():
    for p in sorted((REPO / "eval" / "posthoc").glob("*.py")):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for m in mods:
                top = m.split(".")[0]
                assert m == "eval.exact" or m == "__future__" or (
                    top in sys.stdlib_module_names and top not in {"socket", "urllib", "http"}), (p.name, m)
