"""g2 selfcheck: scoring definitions on hand cases, loader glob, and the DRAFT/test refusal. No held-out data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.errors import RunRefused
from eval_g2 import pipeline, protocol as P
from eval_g2.score import dp_flags, gold_tasks, rows_for_case
from eval_i2.score import s1r_targets

FAST = s1r_targets()["RF-FAST"][0]
CHEST = s1r_targets()["RF-ACUTE-CHEST-PAIN"][0]


def _gold(flags_by_dp: dict[str, list[str]]) -> dict:
    return {"case_id": "SYNHE-0001", "patient_ref": "SYNH-0001", "split": "test",
            "decision_times": [{"decision_point": dp, "red_flags": [{"rule_id": r, "item_ids": []} for r in rs]}
                               for dp, rs in flags_by_dp.items()]}


def _rec(dp: str, fired: list[str], not_evaluated: list[str] = ()) -> dict:
    return {"dp_id": f"SYNHE-0001/{dp}", "case_id": "SYNHE-0001", "decision_point": dp, "patient_ref": "SYNH-0001",
            "case_graph": {"red_flag": {"fired": fired, "not_evaluated": list(not_evaluated)}}}


def _by_task(rows):
    return {(r["task"], r["decision_point_id"]): r["y_pred"] for r in rows}


def test_primary_counts_any_alert_but_rulematched_does_not():
    g = _gold({"T1": ["RF-FAST"], "T2": []})
    rows = rows_for_case([_rec("T1", [CHEST]), _rec("T2", [CHEST])], g)
    t = _by_task(rows)
    assert t[("rf_case_recall", "SYNHE-0001/T1")] is True          # wrong-rule alert still counts (e1 definition)
    assert t[("rf_rulematched_dp", "SYNHE-0001/T1")] is False
    assert t[("rf_rule_RF-FAST", "SYNHE-0001/T1")] is False
    assert t[("rf_fpr", "SYNHE-0001/T2")] is True                    # alert on a gold-negative DP
    assert t[("rf_case_agg", "SYNHE-0001")] is True and t[("rf_case_agg_rulematched", "SYNHE-0001")] is False


def test_silent_miss_vs_surfaced_gap():
    g = _gold({"T1": ["RF-FAST"]})
    d = g["decision_times"][0]
    silent = dp_flags(_rec("T1", []), d)
    gap = dp_flags(_rec("T1", [], [FAST]), d)
    assert (silent["any"], silent["surfaced"]) == (False, False)
    assert (gap["any"], gap["surfaced"]) == (False, True)


def test_memberships_equal_scored_rows():
    g = _gold({"T1": ["RF-FAST", "RF-QSOFA"], "T2": []})
    rows = rows_for_case([_rec("T1", [FAST]), _rec("T2", [])], g)
    assert sorted((r["task"], r["decision_point_id"]) for r in rows) == sorted(gold_tasks(g))


def test_loader_globs_synhe_ids(tmp_path: Path):
    d = tmp_path / "gold" / "test"
    d.mkdir(parents=True)
    (d / "SYNHE-0001.json").write_text(json.dumps(_gold({"T1": []})))
    assert list(P.load_gold(tmp_path, "test")) == ["SYNHE-0001"]


def test_protocol_hash_ignores_status_only():
    p = {"a": 1, "status": "DRAFT"}
    assert P.protocol_sha256(p) == P.protocol_sha256({**p, "status": "FROZEN"})
    assert P.protocol_sha256(p) != P.protocol_sha256({**p, "a": 2})


def test_committed_draft_manifest_refuses_test_run(tmp_path: Path):
    mp = P.MANIFEST_DIR / f"{P.EVALUATION_ID}.json"
    pp = P.MANIFEST_DIR / f"{P.EVALUATION_ID}.protocol.json"
    if not mp.exists():
        pytest.skip("draft manifest not present")
    assert json.loads(pp.read_text())["status"] == "DRAFT"
    with pytest.raises(RunRefused):  # refuses before touching any system code or data (hash or DRAFT/ledger gate)
        pipeline.run_split("test", tmp_path / "absent", mp, pp, tmp_path / "out", None)
