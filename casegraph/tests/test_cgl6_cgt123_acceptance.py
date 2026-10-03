"""cg-l6 (CONDITIONS L6): the cg-t123 in-process acceptance check (A1-A7b) runs in `make test`.

Loads tests/e2e/cgt123_inprocess_check.py by file path (tests/ is not a package) and calls `run_check`.
Synthetic S1r seed 20260926 only, offline, mock gateways, Tier 0. Structural correctness of staged versions;
NOT a clinical-performance or Pharma-accuracy claim (A7b secondary gold agreement stays NOT_MEASURABLE).
The test split is only loaded/planned by A1, never compiled or executed.
"""
from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

CHECK_PATH = Path(__file__).resolve().parents[2] / "tests" / "e2e" / "cgt123_inprocess_check.py"
METRICS = ("A1", "A2", "A3a", "A3b", "A4", "A5", "A6", "A7a", "A7b")


def load_check():
    spec = importlib.util.spec_from_file_location("cgt123_inprocess_check_l6", CHECK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def assert_acceptance(check, R: dict) -> None:
    """Every metric PASS, no step errors, and the Baseline reference values (counts pinned with ==)."""
    assert "errors" not in R, R.get("errors")
    failed = [m for m in METRICS if check.status(R.get(m)) != "PASS"]
    assert not failed, f"metrics not PASS: {failed}"
    a1 = R["A1"]
    assert a1["lists"] == 400 and a1["counts_T1"] == {"T1": 200} and a1["counts_T2"] == {"T1/T3/T2": 180, "T1/T2": 20}
    assert a1["mismatch"] == [] and a1["adversarial_cases"] == 11 and a1["adversarial_mismatch"] == []
    assert a1["fixture_mismatch"] == []
    assert (R["A2"]["versions"], R["A2"]["bad"]) == (131, [])
    assert (R["A3a"]["nodes"], R["A3a"]["bad"]) == (657, [])
    a3b = R["A3b"]
    assert (a3b["cached_nodes_checked"], a3b["bad"]) == (127, [])
    assert a3b["fstale_t1_fresh_t3_stale"] is True and a3b["fstale_t3_screening"] == "not_evaluated"
    a4 = R["A4"]
    assert a4["future_evidence_in_versions"] == [] and a4["f_future_versions"] == 1 and a4["adversarial_issues"] == []
    assert a4["lateconfirm_absent_t2"] is True and a4["lateconfirm_present_t3"] is True
    assert a4["leakage_audit_version_failures"] == [] and a4["leakage_audit_dataset_rc"] == 0
    a5 = R["A5"]
    for k in ("t1_spec_identical", "t1_items_identical", "t1_run_identical", "t1_outputs_identical"):
        assert a5[k] is True, k
    assert a5["resave_issues"] == [] and a5["replay_calls"] == 0 and a5["replay_issues"] == []
    assert a5["role_guard_issues"] == []
    assert (R["A6"]["runs"], R["A6"]["lost"]) == (36, [])
    assert (R["A7a"]["t3_versions"], R["A7a"]["bad"]) == (41, [])
    assert (R["A7b"]["parity_checked"], R["A7b"]["parity_bad"]) == (37, [])
    assert R["A7b"]["secondary_gold_med_issues"].startswith("NOT_MEASURABLE")


@pytest.fixture(scope="module")
def check():
    return load_check()


def test_cgt123_acceptance_reference_values(check, s1r_dataset, tmp_path):
    assert_acceptance(check, check.run_check(s1r_dataset, tmp_path / "scratch", quiet=True))


def test_two_calls_in_one_process_are_independent(check, s1r_dataset, tmp_path):
    a = check.run_check(s1r_dataset, tmp_path / "a", quiet=True)
    b = check.run_check(s1r_dataset, tmp_path / "b", quiet=True)
    assert a == b


def test_planted_planner_regression_fails(check, s1r_dataset, tmp_path, monkeypatch):
    real = check.plan_stages

    def dropping(items, t1, horizon):
        # planted: a stage plan loses its last trigger item (multi-trigger stages only)
        return [replace(p, trigger_item_ids=p.trigger_item_ids[:-1]) if len(p.trigger_item_ids) > 1 else p
                for p in real(items, t1, horizon)]

    monkeypatch.setattr(check, "plan_stages", dropping)
    R = check.run_check(s1r_dataset, tmp_path / "s", quiet=True)
    assert "errors" not in R, list(R.get("errors", {}))  # ran to the end
    assert check.status(R["A1"]) == "FAIL/ERR" and (R["A1"]["mismatch"] or R["A1"]["adversarial_mismatch"])
    assert check.status(R["A6"]) == "PASS"  # unaffected metric still computed
    with pytest.raises(AssertionError):
        assert_acceptance(check, R)


def test_planted_alert_suppression_fails(check, s1r_dataset, tmp_path, monkeypatch):
    from casegraph import executor

    real = executor.Executor._checkpoint

    def suppressed(self, ctx):  # planted: the pending payload no longer escalates despite an urgent Red flag
        res = real(self, ctx)
        res.output[executor.PENDING_KEY]["escalation"] = False
        return res

    monkeypatch.setattr(executor.Executor, "_checkpoint", suppressed)
    R = check.run_check(s1r_dataset, tmp_path / "s", quiet=True)
    assert "errors" not in R, list(R.get("errors", {}))
    assert check.status(R["A6"]) == "FAIL/ERR" and R["A6"]["lost"]
    assert check.status(R["A1"]) == "PASS"
    with pytest.raises(AssertionError):
        assert_acceptance(check, R)


def test_helper_negative_control(check):
    good = {m: {"pass": True} for m in METRICS}
    with pytest.raises(AssertionError):
        assert_acceptance(check, {**good, "A2": {"pass": False}})
    with pytest.raises(AssertionError):
        assert_acceptance(check, {**good, "errors": {"A1": "boom"}})
