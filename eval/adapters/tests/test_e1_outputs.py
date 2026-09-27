"""Statistics and outputs: degenerate rule (A06), comparators (A10), hash-bound wrapper (A14), summary
completeness (A09, A11), labels (A13) and byte reproducibility (A12). Every ledger is a tmp ledger."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from eval.adapters import baselines, hashes, pipeline, protocol, summary
from eval.adapters.__main__ import main
from eval.adapters.mapping import BANNER
from eval.exact import clopper_pearson, wilson
from eval.ledger_chain import Ledger
from eval.manifest import freeze

REPO = Path(__file__).resolve().parents[3]
SCOPE4 = {
    "voice": ["voice_cc_precision", "voice_cc_recall", "voice_cc_f1", "voice_dur_precision", "voice_dur_recall",
              "voice_dur_f1", "voice_allergy_precision", "voice_allergy_recall", "voice_allergy_f1",
              "voice_micro_precision", "voice_micro_recall", "voice_micro_f1", "voice_allergy_false_none_rate"],
    "triage": ["rf_case_recall", "rf_rule_recall", "rf_rule_recall_mappable", "rf_fpr", "rf_fpr_mapped",
               "rf_text_t1_recall", "rf_text_t1_fpr", "dept_top1", "dept_top3", "abst_coverage",
               "abst_selective_top1", "abst_rate_not_evaluable", "abst_false_abstain_rate",
               "abst_expected_action_agreement"]
    + [f"rf_rule_{r}" for r in ("RF-NEWS-SINGLE3", "RF-NEWS-AGG5", "RF-QSOFA", "RF-ACUTE-CHEST-PAIN", "RF-FAST",
                                "RF-THUNDERCLAP", "RF-ANAPHYLAXIS")],
}
CLAIMS = re.compile(r"diagnos|clinical efficacy demonstrated|accuracy of diagnosis", re.IGNORECASE)


def _summary(e1_run) -> dict:
    return json.loads((e1_run["out"] / "e1_summary.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- A06


def test_degenerate_uses_exact(e1_run):
    # unit: each degenerate trigger -> Clopper-Pearson; otherwise the bootstrap interval is kept
    ok = summary.interval_fields(0.5, 5, 10, 0.2, 0.8, False, True)
    assert ok["interval_method"] == "bootstrap_percentile" and ok["interval"] == [0.2, 0.8]
    assert ok["wilson"] == list(wilson(5, 10)) and ok["clopper_pearson"] == list(clopper_pearson(5, 10))
    for args in ((0.5, 5, 10, 0.2, 0.8, True, True), (0.5, 5, 10, 0.5, 0.5, False, True),
                 (0.0, 0, 10, 0.0, 0.2, False, True), (1.0, 10, 10, 0.9, 1.0, False, True)):
        r = summary.interval_fields(*args)
        assert r["degenerate"] and r["interval_method"] == "clopper_pearson"
        assert r["interval"] == list(clopper_pearson(args[1], args[2]))
    # scan of the real summary: every proportion row carries Wilson and CP; the rule is applied to 100% of rows
    n_deg = n_boot = 0
    for split in ("dev", "test"):
        for r in _summary(e1_run)["splits"][split]["metric_rows"]:
            if r["point"] is None:
                continue
            b = r["bootstrap"]
            deg = b["unstable"] or b["ci_low"] == b["ci_high"] or (r["proportion"] and r["x"] in (0, r["n"]))
            assert r["degenerate"] == deg, r["metric_id"]
            if r["proportion"]:
                assert r["wilson"] == list(wilson(r["x"], r["n"])), r["metric_id"]
                assert r["clopper_pearson"] == list(clopper_pearson(r["x"], r["n"])), r["metric_id"]
                assert abs(r["x"] / r["n"] - r["point"]) <= 1e-12
                if deg:
                    n_deg += 1
                    assert r["interval_method"] == "clopper_pearson" and r["interval"] == r["clopper_pearson"]
                else:
                    n_boot += 1
                    assert r["interval_method"] == "bootstrap_percentile"
                    assert r["interval"] == [b["ci_low"], b["ci_high"]]
            else:
                assert r["params"]["component"] == "f1" and r["wilson"] is None and r["exact_reason"]
    assert n_deg > 0 and n_boot > 0


# ---------------------------------------------------------------- A10


def _perturb_text(ds: Path, split: str) -> None:
    for p in sorted((ds / "inputs" / split).glob("*/snapshot_T*.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        for it in s["items"]:
            if it["data_type"] == "IntakeTranscript":
                for turn in it["turns"]:
                    if turn["speaker"] == "patient":
                        turn["text"] = "ทันทีทันใด " + turn["text"] + " อยู่ดี ๆ ก็เป็น"
        p.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")


def test_shortcut_selected_on_train_only(ds, ds_copy):
    ref = baselines.select_shortcut(ds)
    assert ref["s_star"] and ref["train"]["n_cases"] == 120
    _perturb_text(ds_copy, "dev")
    _perturb_text(ds_copy, "test")
    for split in ("dev", "test"):  # and the dev/test gold is irrelevant too
        shutil.rmtree(ds_copy / "gold" / split)
    assert baselines.select_shortcut(ds_copy) == ref
    assert baselines.train_majority_e(ds_copy) == baselines.train_majority_e(ds)
    # control: the selection does react to train text
    _perturb_text(ds_copy, "train")
    assert baselines.select_shortcut(ds_copy)["train"] != ref["train"]


def test_always_answer_full_coverage(e1_run):
    assert baselines.always_answer([], "E-MED") == ["E-MED"]
    assert baselines.always_answer(["CARD", "MED", "URO"], "E-EYE") == ["E-MED", "E-SURG"]
    for split in ("dev", "test"):
        v = _summary(e1_run)["splits"][split]
        rows = {(r["metric_id"], r["arm"]): r for r in v["metric_rows"]}
        aa = rows[("abst_coverage", "comparator:always_answer")]
        assert aa["point"] == 1.0 and aa["x"] == aa["n"] > 0
        assert aa["paired_difference_system_minus_comparator"]["point"] is not None
        for mid in ("dept_top1", "dept_top3", "abst_selective_top1"):
            assert rows[(mid, "comparator:always_answer")]["paired_difference_system_minus_comparator"] is not None
        for mid in ("rf_text_t1_recall", "rf_text_t1_fpr"):
            for arm in ("comparator:shortcut_s_star", "comparator:shortcut_tamtee"):
                d = rows[(mid, arm)]["paired_difference_system_minus_comparator"]
                assert d is not None and "point" in d
        preds = [json.loads(x) for x in (e1_run["out"] / split / "triage" / "comparator.jsonl")
                 .read_text(encoding="utf-8").splitlines()]
        assert all(r["y_pred"] is not None for r in preds if r["task"] == "abstention")


# ---------------------------------------------------------------- A14


def _break(kind: str, ds_copy: Path, tmp_path: Path, monkeypatch) -> None:
    if kind == "dataset":
        p = sorted((ds_copy / "inputs" / "dev").glob("*/snapshot_T1.json"))[0]
        p.write_bytes(p.read_bytes().replace(b"\"as_of\"", b"\"as_of\" "))
    elif kind == "split":
        p = ds_copy / "splits.json"
        p.write_bytes(p.read_bytes() + b"\n")
    elif kind == "mapping":
        m = tmp_path / "e1_mapping_v1.json"
        m.write_bytes(hashes.MAPPING_PATH.read_bytes() + b" ")
        monkeypatch.setattr(hashes, "MAPPING_PATH", m)
    else:
        a = tmp_path / "adapters"
        shutil.copytree(hashes.ADAPTERS_DIR, a, ignore=shutil.ignore_patterns("__pycache__"))
        (a / "score.py").write_bytes((a / "score.py").read_bytes() + b"\n# changed\n")
        monkeypatch.setattr(hashes, "ADAPTERS_DIR", a)


@pytest.mark.parametrize("kind", ["dataset", "split", "mapping", "adapter"])
def test_wrapper_refuses_hash_mismatch(kind, ds, ds_copy, e1_run, tmp_path, monkeypatch, capsys):
    ledger = tmp_path / "ledger"
    shutil.copytree(e1_run["ledger_after_freeze"], ledger)
    before = {p.name: p.read_bytes() for p in ledger.iterdir()}
    _break(kind, ds_copy, tmp_path, monkeypatch)
    key = {"dataset": "dataset_tree_sha256", "split": "split_sha256", "mapping": "mapping_sha256",
           "adapter": "adapters_sha256"}[kind]
    m = json.loads(protocol.manifest_path(e1_run["manifests"], "triage", "dev").read_text(encoding="utf-8"))
    assert key in protocol.hash_mismatches(m, ds_copy)
    out = tmp_path / "out"
    for split in ("dev", "test"):
        rc = main(["run", "--split", split, "--dataset", str(ds_copy), "--manifest-dir", str(e1_run["manifests"]),
                   "--out-root", str(out), "--ledger-dir", str(ledger)])
        assert rc == 2 and "REFUSED" in capsys.readouterr().err
    assert not out.exists() or not any(p.is_file() for p in out.rglob("*"))
    assert {p.name: p.read_bytes() for p in ledger.iterdir()} == before


def test_test_split_refused_unless_frozen(ds, tmp_path):
    mdir = tmp_path / "m"
    pipeline.make_manifests(ds, mdir, n_boot=50)
    ledger = Ledger(tmp_path / "ledger")
    ledger.init()
    rc = main(["run", "--split", "test", "--dataset", str(ds), "--manifest-dir", str(mdir), "--out-root",
               str(tmp_path / "out"), "--ledger-dir", str(tmp_path / "ledger")])
    assert rc == 2 and not (tmp_path / "out").exists()
    # an unfrozen dev run is exploratory: UNFROZEN stamp, scratch ledger, the real ledger is untouched
    before = {p.name: p.read_bytes() for p in (tmp_path / "ledger").iterdir()}
    out = pipeline.run_split("dev", ds, mdir, tmp_path / "out", tmp_path / "ledger")
    assert out == tmp_path / "out" / "unfrozen" / "dev"
    assert json.loads((out / "triage" / "results.json").read_text())["stamp"].startswith("UNFROZEN")
    assert {p.name: p.read_bytes() for p in (tmp_path / "ledger").iterdir()} == before


# ---------------------------------------------------------------- A09, A11


def test_e1_summary_complete(e1_run):
    s = _summary(e1_run)
    assert s["banner"] == BANNER and s["not_evaluated"]
    assert {x["row"] for x in s["not_evaluated"]} == {"Voice Agent: comparison with form filling",
                                                      "Voice Agent: response latency and total time"}
    assert all(x["reason"] for x in s["not_evaluated"])
    assert [(h["split"], h["metric_id"]) for h in s["red_flag_recall_verdicts"]] == [
        ("dev", "rf_case_recall"), ("dev", "rf_rule_recall"), ("test", "rf_case_recall"), ("test", "rf_rule_recall")]
    assert all(h["verdict"] in ("PASS", "FAIL") for h in s["red_flag_recall_verdicts"])
    for split in ("dev", "test"):
        v = s["splits"][split]
        assert v["status"] == "run" and v["frozen"] is True
        system = {r["metric_id"]: r for r in v["metric_rows"] if r["arm"] == "system"}
        nulls = {r["metric_id"]: r for r in v["null_rows"]}
        for mid in SCOPE4["voice"] + SCOPE4["triage"]:
            assert (mid in system) != (mid in nulls), (split, mid)
            if mid in nulls:
                assert nulls[mid]["point"] is None and nulls[mid]["reason"] and "n_decision_points" in nulls[mid]
                continue
            r = system[mid]
            for k in ("point", "bootstrap", "n_patients", "n_decision_points", "interval", "interval_method"):
                assert k in r, (mid, k)
            if r["point"] is None:
                assert r["reason"]
            else:
                assert r["bootstrap"]["ci_low"] is not None and r["n_patients"] > 0
                if r["proportion"]:
                    assert r["wilson"] and r["clopper_pearson"]
        assert "rf_rule_RF-NEWS-AGG5" in nulls and "UNMAPPABLE" in nulls["rf_rule_RF-NEWS-AGG5"]["reason"]
        # threshold verdicts: the predeclared rule only, on the point estimate
        rules = {t["metric_id"]: t for t in v["threshold_verdicts"]}
        assert set(rules) == {"voice_cc_f1", "voice_dur_f1", "voice_allergy_f1", "voice_allergy_false_none_rate",
                              "rf_case_recall", "rf_rule_recall", "dept_top3"}
        for mid, t in rules.items():
            op, val = {"voice_allergy_false_none_rate": ("<=", 0.0), "rf_case_recall": (">=", 1.0),
                       "rf_rule_recall": (">=", 1.0), "dept_top3": (">=", 0.8)}.get(mid, (">=", 0.8))
            assert t["rule"].startswith(f"{op} ") and t["rule"].endswith(" on point")
            p = system[mid]["point"]
            met = p >= val if op == ">=" else p <= val
            assert t["verdict"] == ("PASS" if met else "FAIL") and t["compared_value"] == p
        # A11: every gold red-flag DP that got no alert is listed (case_id, T, rule)
        preds = [json.loads(x) for x in (e1_run["out"] / split / "triage" / "predictions.jsonl")
                 .read_text(encoding="utf-8").splitlines()]
        missed = {(r["case_id"], r["T"], rule) for r in preds if r["task"] == "rf_case_recall" and not r["fired_s4"]
                  for rule in r["gold_rules"]}
        listed = {(m["case_id"], m["T"], m["rule"]) for m in v["safety"]["missed_gold_red_flag_dps"]}
        assert listed == missed
        pairs = {(r["case_id"], r["T"], rule) for r in preds if r["task"] == "rf_rule_recall" for rule in r["ordered"]
                 if rule not in r["suggested"]}
        assert {(m["case_id"], m["T"], m["rule"]) for m in v["safety"]["missed_gold_red_flag_pairs"]} == pairs
    md = (e1_run["out"] / "e1_summary.md").read_text(encoding="utf-8")
    top = md.split("## Split:")[0]
    assert "Red-flag recall verdicts" in top and top.count("| dev | rf_") == 2 and top.count("| test | rf_") == 2


# ---------------------------------------------------------------- A13


def _tables_have_banner(text: str) -> None:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("|") and (i == 0 or not lines[i - 1].startswith("|")):
            assert i >= 2 and lines[i - 2] == f"> **{BANNER}**", (i, line)


def test_e1_labels(e1_run):
    files = [e1_run["out"] / "e1_summary.md"] + sorted(e1_run["out"].glob("*/*/results.md"))
    assert len(files) == 5
    for p in files:
        text = p.read_text(encoding="utf-8")
        assert BANNER in text
        _tables_have_banner(text)
        assert not CLAIMS.search(text.replace(BANNER, "")), (p, CLAIMS.search(text))
    for p in sorted(e1_run["out"].glob("*/*/results.html")):
        h = p.read_text(encoding="utf-8")
        assert h.count("<table") <= h.count(f'<div class="banner">{BANNER}</div>')
    assert not CLAIMS.search((e1_run["out"] / "e1_summary.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- A12


def _tree(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_e1_byte_reproducible(ds, e1_run, tmp_path):
    committed = {p: p.read_bytes() for p in sorted((REPO / "eval" / "ledger").glob("*.jsonl"))}
    ledger = tmp_path / "ledger"
    shutil.copytree(e1_run["ledger_after_freeze"], ledger)
    out = tmp_path / "out"
    for split in ("dev", "test"):
        pipeline.run_split(split, ds, e1_run["manifests"], out, ledger)
    assert _tree(out) == _tree(e1_run["out"])
    assert len(_tree(out)) == 2 * (3 + 4 + 5) + 2
    # a frozen run never overwrites its outputs
    with pytest.raises(Exception, match="never overwritten"):
        pipeline.run_split("dev", ds, e1_run["manifests"], out, ledger)
    assert {p: p.read_bytes() for p in sorted((REPO / "eval" / "ledger").glob("*.jsonl"))} == committed
    # manifests carry the split patient list and gold-derived task lists; the four evaluation IDs
    for kind in ("voice", "triage"):
        for split in ("dev", "test"):
            m = json.loads(protocol.manifest_path(e1_run["manifests"], kind, split).read_text(encoding="utf-8"))
            assert m["evaluation_id"] == f"e1-{kind}-{split}-v1" and m["split_patient_list"]
            assert m["task_patient_lists"] and m["dataset"]["version"].startswith("s1r-1.1.1+tree:")
            assert m["split_version"] == hashes.split_sha256(ds)
            assert set(protocol.parse_hashes(m)) >= {"dataset_tree_sha256", "split_sha256", "mapping_sha256",
                                                     "adapters_sha256"}
