"""s6 evaluation harness: deterministic predictions, manifests reproducible from dataset + gold (A10, A18)."""

from __future__ import annotations

import json

from app.care import evaluate


def test_care_eval_deterministic_and_complete(dataset):
    preds, cmps, summary = evaluate.records("dev")
    again = evaluate.records("dev")
    assert evaluate._dump_jsonl(preds) == evaluate._dump_jsonl(again[0])
    assert evaluate._dump_jsonl(cmps) == evaluate._dump_jsonl(again[1]) and summary == again[2]
    dev = [r for r in dataset.rows if r["split"] == "dev"]
    cov = [p for p in preds if p["task"] == "care_coverage"]
    assert len(cov) == len(dev) == summary["n_decision_points"]
    # coverage rows: answered iff gold says suggest (A01/A02 hold on dev)
    by_key = {(r["case_id"], r["dp"]): r["care"]["expected_action"] for r in dev}
    assert all((p["y_pred"] is None) == (by_key[tuple(p["decision_point_id"].split(":"))] == "abstain") for p in cov)
    ni = [p for p in preds if p["task"] == "care_next_info"]
    assert len(ni) == sum(r["care"]["evaluable"] for r in dev)
    assert {c["comparator"] for c in cmps} == {"always_answer", "always_answer_on_answered", "train_prior"}
    assert all(c["suggested"] is not None for c in cmps if c["comparator"] == "always_answer")


def test_committed_manifests_reproduce_from_gold(dataset):
    for split in ("dev", "test"):
        committed = json.loads((evaluate.EVAL_DIR / f"manifest_{split}.json").read_text("utf-8"))
        assert evaluate.manifest(split) == committed
        assert committed["dataset"]["version"] == json.loads((dataset.root / "manifest.json").read_text())["tree_sha256"]


def test_train_prior_uses_train_split_only(dataset):
    from collections import Counter

    c = Counter(x for r in dataset.rows if r["split"] == "train" and r["care"]["evaluable"] for x in r["care"]["next_info"])
    assert evaluate.train_prior(dataset.root) == [k for k, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
