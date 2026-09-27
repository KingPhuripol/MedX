"""Slice e1r: post-hoc findings computed from the frozen, stored e1 outputs (no metric change, no new run).

The S1r dataset is generated into a tmp dir with ``python -m data_factory generate`` in a subprocess (no import
of data_factory under eval/). Nothing here writes under eval/results or eval/ledger. Research prototype.
"""

from __future__ import annotations

import ast
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
    assert t["classification"] in ("S3_DEFECT", "REPLAY_ARTIFACT", "BOTH")
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
                   "superseded by joint_pain from turn 9", "allergy", "equal the stored output: True"):
        assert needle in stmt, needle
    notes = " ".join(_section(doc, "C-E1-1")["notes"])
    assert stmt in notes
    rat = t["classification_rationale"]
    assert "agent-led live use (S3_DEFECT)" in rat and "nurse-led replay (REPLAY_ARTIFACT)" in rat
    assert {"mock_rules.py:195", "service.py:401"} <= set(re.findall(r"\w+\.py:\d+", rat))
    js, md = F.render(doc)
    for text in (js, md):
        assert not re.search(r"yielded no|no CC|0 agent turns|no agent turns", text, re.IGNORECASE)


# ---------------------------------------------------------------- 4. silent escalations


def test_silent_escalations(doc):
    got = {(e["split"], e["case_id"], e["dp"]) for e in _section(doc, "C-E1-2")["data"]["silent_escalations"]}
    dev = {("dev", c, dp) for c in ("SYNE-0081", "SYNE-0108", "SYNE-0127", "SYNE-0196") for dp in ("T1", "T2")}
    test = {("test", "SYNE-0039", "T2")} | {("test", c, dp) for c in ("SYNE-0101", "SYNE-0187")
                                          for dp in ("T1", "T2")}
    assert got == dev | test
    for e in _section(doc, "C-E1-2")["data"]["silent_escalations"]:
        assert e["n_alerts"] == 0 and e["system_top3"] and e["gold_target_department"]


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
