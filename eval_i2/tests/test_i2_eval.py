"""Slice i2 comparison harness: Case Graph (Arm A) vs single prompt (Arm B). I2-A07, A18 (arms matched,
completeness), A19 (labels), A20 (byte reproducible) and the harness isolation. Every ledger is a tmp ledger.
System Evaluation on synthetic data - not clinical performance."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

from casegraph import single_prompt
from eval.errors import RunRefused
from eval.adapters import mapping
from eval_i2 import pipeline, protocol
from eval_i2.summary import BANNER, CIRCULARITY

REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "eval_i2"
COMPARED = ("dept_top1", "dept_top3", "coverage", "selective_top1", "calls_per_dp")
S1R_RULES = {"RF-ACUTE-CHEST-PAIN", "RF-ANAPHYLAXIS", "RF-FAST", "RF-NEWS-AGG5", "RF-NEWS-SINGLE3", "RF-QSOFA",
             "RF-THUNDERCLAP"}
CLAIMS = re.compile(r"diagnos|clinically validated|superior", re.I)
OVERCLAIM = re.compile(r"no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)", re.I)


def _imports(p: Path) -> list[tuple[str, int]]:
    out = []
    for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [(a.name, 0) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append((node.module or "", node.level))
    return out


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != "timing.json"}


def _split(i2_run, split):
    return json.loads((i2_run["out"] / split / "split_summary.json").read_text(encoding="utf-8"))


def test_i2_harness_isolation():
    """eval_i2 lives outside eval/adapters/ (the e1 allowlist forbids casegraph there) and imports only stdlib,
    eval core, the e1 gold/mapping/hashes modules, casegraph and app.{voice,triage,gateway,config}."""
    allowed_app = ("app.voice", "app.triage", "app.gateway", "app.config")
    allowed_eval = ("eval.errors", "eval.jsonio", "eval.ledger_chain", "eval.manifest", "eval.runner", "eval.exact",
                    "eval.adapters.gold", "eval.adapters.mapping", "eval.adapters.hashes", "eval.adapters")
    files = sorted(p for p in PKG.rglob("*.py") if "tests" not in p.relative_to(PKG).parts)
    assert len(files) >= 6
    bad = []
    for p in files:
        for mod, level in _imports(p):
            top = mod.split(".")[0]
            if level > 0 or mod == "__future__" or top in sys.stdlib_module_names and top not in {
                    "socket", "urllib", "http"}:
                continue
            if top == "app" and mod.startswith(allowed_app):
                continue
            if top == "eval" and mod in allowed_eval:
                continue
            if top == "casegraph":
                continue
            bad.append(f"{p.name}: {mod}")
    assert bad == []
    assert not (REPO / "eval" / "adapters" / "i2").exists()


def test_arms_matched(i2_run):
    for split in ("dev", "test"):
        s = _split(i2_run, split)
        m = s["arms_matched"]
        assert m["handler_versions_manifest"] == single_prompt.handler_versions()
        assert m["identical_handler_versions"] is True
        assert m["n_both_answer"] > 0 and m["n_identical_top3_where_both_answer"] == m["n_both_answer"]
        assert m["only_case_graph_answers"] == 0
        assert s["calls"]["single_prompt"]["total"] == s["n_dp"]  # exactly one gateway call per DP
        assert s["replay"]["checked"] == s["replay"]["identical"] == s["n_dp"]
    for split, n in (("dev", 80), ("test", 80)):
        assert _split(i2_run, split)["n_dp"] == n
    hv = protocol.parse_hashes(json.loads(protocol.manifest_path(i2_run["manifests"], "dev").read_text()))
    assert hv["handler_versions"] == single_prompt.handler_versions()


def test_i2_summary_complete(i2_run):
    s = json.loads((i2_run["out"] / "i2_summary.json").read_text(encoding="utf-8"))
    assert s["label"] == BANNER and s["circularity_note"] == CIRCULARITY
    for split in ("dev", "test"):
        v = s["splits"][split]
        assert v["frozen"] is True and v["evaluation_id"] == f"i2-cg-vs-sp-{split}-v1"
        for mid in COMPARED:
            e = v["comparison"][mid]
            assert e["case_graph"]["point"] is not None and e["single_prompt"]["point"] is not None
            d = e["paired_difference_A_minus_B"]
            assert d is not None and {"point", "ci_low", "ci_high"} <= set(d)
        rf = v["red_flags"]
        assert set(rf["per_s1r_rule_recall"]) == S1R_RULES
        agg5 = rf["per_s1r_rule_recall"]["RF-NEWS-AGG5"]
        assert agg5["point"] is not None or agg5["n_gold_pairs"] == 0  # rf-1.2.0: mappable via AGG5_OVERLAY
        for rule, e in rf["per_s1r_rule_recall"].items():
            if rule != "RF-NEWS-AGG5" and e.get("n"):
                assert {"x", "n", "n_patients", "wilson", "clopper_pearson", "bootstrap", "reported_interval"} <= set(e)
        assert rf["single_prompt"].startswith("null:")
        assert set(rf["false_alerts_per_s4_rule"]) == {"gold_negative_dps", "text_near_miss_dps"}
        assert all(m["reason"] for m in rf["missed_gold_red_flags"])
        assert set(rf["predeclared_targets_not_gating"]["text_rule_recall_equals_1"]) == set(mapping.TEXT_RULES_S1R)
        assert v["graph_shape_histogram"] and v["not_evaluated"]["CareSuggestion"].startswith("not evaluated")
        t = json.loads((i2_run["out"] / split / "timing.json").read_text(encoding="utf-8"))
        for arm in ("case_graph", "single_prompt"):
            assert t[arm]["n"] == v["n_dp"] and t[arm]["median_ms"] is not None and t[arm]["p95_ms"] is not None
    # A07 on dev: each text rule fires on >= 1 gold-positive DP (4/4)
    assert all(n >= 1 for n in s["splits"]["dev"]["red_flags"]["text_rule_fired_on_gold_positive_dps"].values())


def test_i2_labels(i2_run):
    out = i2_run["out"]
    texts = [p for p in sorted(out.rglob("*")) if p.suffix in (".md", ".html", ".json") and p.name != "timing.json"]
    assert texts
    for p in out.rglob("*.md"):
        lines = p.read_text(encoding="utf-8").split("\n")
        for i, line in enumerate(lines):
            if line.startswith("|") and (i == 0 or not lines[i - 1].startswith("|")):
                above = "\n".join(lines[max(0, i - 5):i])
                assert BANNER in above and "Circularity note" in above, (p.name, i)
    for p in out.rglob("*.html"):
        h = p.read_text(encoding="utf-8")
        assert h.count("<table>") and h.count(BANNER) > h.count("<table>")
    for p in texts:
        t = p.read_text(encoding="utf-8").replace(BANNER, "").replace(CIRCULARITY, "")
        assert not CLAIMS.search(t), (p.name, CLAIMS.search(t))
        assert not OVERCLAIM.search(t), (p.name, OVERCLAIM.search(t))


def test_i2_byte_reproducible(ds, i2_run, tmp_path):
    committed = {p: p.read_bytes() for p in sorted((REPO / "eval" / "ledger").glob("*.jsonl"))}
    ledger = tmp_path / "ledger"
    shutil.copytree(i2_run["ledger_after_freeze"], ledger)
    out = tmp_path / "out"
    for split in ("dev", "test"):
        pipeline.run_split(split, ds, i2_run["manifests"], out, ledger)
    assert _tree(out) == _tree(i2_run["out"])
    assert len(_tree(out)) >= 2 * 7 + 2
    with pytest.raises(RunRefused, match="never overwritten"):
        pipeline.run_split("dev", ds, i2_run["manifests"], out, ledger)
    assert {p: p.read_bytes() for p in sorted((REPO / "eval" / "ledger").glob("*.jsonl"))} == committed


def test_test_split_refused_unless_frozen(ds, tmp_path):
    mdir = tmp_path / "m"
    pipeline.make_manifests(ds, mdir, n_boot=50)
    from eval.ledger_chain import Ledger

    ledger = Ledger(tmp_path / "ledger")
    ledger.init()
    with pytest.raises(RunRefused, match="frozen"):
        pipeline.run_split("test", ds, mdir, tmp_path / "out", tmp_path / "ledger")
    assert not (tmp_path / "out").exists()


def test_refuses_hash_mismatch(ds, tmp_path):
    mdir = tmp_path / "m"
    pipeline.make_manifests(ds, mdir, n_boot=50, splits=("dev",))
    p = protocol.manifest_path(mdir, "dev")
    m = json.loads(p.read_text(encoding="utf-8"))
    h = protocol.parse_hashes(m)
    h["handler_versions"] = {**h["handler_versions"], "triage.department.v1": "tampered"}
    m["$comment"] = protocol.hash_comment(h)
    protocol.write_manifest(p, m)
    from eval.ledger_chain import Ledger

    Ledger(tmp_path / "ledger").init()
    with pytest.raises(RunRefused, match="handler_versions"):
        pipeline.run_split("dev", ds, mdir, tmp_path / "out", tmp_path / "ledger")
    assert not (tmp_path / "out").exists()
