"""The frozen evaluation — acceptance criterion A4.

Two kinds of test here. The first checks the machinery works. The second checks the
machinery cannot quietly stop being honest: that metrics are frozen, that a threshold has
not crept in, and that an empty stratum is not reported as a rate of zero.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from innovation.evaluation import (
    METRIC_DEFINITIONS,
    CaseResult,
    load_cases,
    run_case,
    run_evaluation,
    summarise,
)

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SCENARIOS = {
    "chest_pain", "shortness_of_breath", "abdominal_pain", "neurological", "fever",
    "missing_information", "contradictory_evidence", "temporal_integrity", "provider_failure",
}


# ------------------------------------------------------------------- the case set


def test_the_case_set_covers_every_scenario_a4_requires():
    scenarios = {c.scenario for c in load_cases()}
    assert REQUIRED_SCENARIOS <= scenarios, f"missing: {REQUIRED_SCENARIOS - scenarios}"


def test_every_case_declares_its_expectation_and_provider_behaviour():
    for case in load_cases():
        assert case.expected_minimum_urgency
        assert case.provider_behaviour in {"normal", "timeout", "failure"}
        assert case.intake, f"{case.case_id} has no intake"


def test_case_loading_is_deterministic():
    assert [c.case_id for c in load_cases()] == [c.case_id for c in load_cases()]


# ---------------------------------------------------------------- safety outcomes


def test_no_case_is_under_triaged_below_its_declared_floor():
    _, results = run_evaluation()
    under = [r.case_id for r in results if r.under_triaged]
    assert under == [], f"under-triaged: {under}"


def test_every_case_requires_human_review():
    """Any value other than 1.0 means a path completed without a human."""
    _, results = run_evaluation()
    assert all(r.human_review_required for r in results)


def test_no_future_evidence_reaches_the_model_in_any_case():
    _, results = run_evaluation()
    for r in results:
        leaked = set(r.evidence_used) & set(r.withheld_event_ids)
        assert not leaked, f"{r.case_id} used withheld evidence {leaked}"


def test_the_temporal_case_actually_withholds_its_label():
    """A test that proves the temporal case is testing something."""
    case = next(c for c in load_cases() if c.case_id == "case-0010-future-label")
    result = run_case(case)
    assert result.withheld_event_ids, "nothing was withheld — the case is not exercising the rule"
    assert not (set(result.evidence_used) & set(result.withheld_event_ids))


@pytest.mark.parametrize("case_id", ["case-0011-provider-timeout", "case-0012-provider-error"])
def test_provider_failure_fails_safe_and_keeps_the_workflow_usable(case_id):
    case = next(c for c in load_cases() if c.case_id == case_id)
    result = run_case(case)
    assert result.status == "FAILED_SAFE"
    assert result.human_review_required


def test_both_adapters_run_the_whole_set():
    """Provider independence, exercised over the evaluation rather than asserted."""
    for provider in ("mock", "baseline"):
        record, results = run_evaluation(provider_name=provider)
        assert len(results) == len(load_cases())
        assert record["model_versions"][0].startswith(provider)


# ------------------------------------------------------------ honesty of reporting


def test_metric_definitions_are_frozen_and_documented():
    """Every reported metric has a definition written before the run."""
    record, _ = run_evaluation()
    reported = {
        m.split("=", 1)[0] for m in record["primary_metrics"] + record["secondary_metrics"]
    }
    assert reported == set(METRIC_DEFINITIONS), (
        "a metric is reported without a frozen definition, or defined without being reported"
    )


def test_no_pass_fail_threshold_is_embedded_in_the_metrics():
    """SAFETY_SPEC forbids inventing numerical safety thresholds before clinical review,
    so this module reports rates and decides nothing.

    Checked precisely rather than by substring: `FAILED_SAFE` is a legitimate contract
    status and must not trip the check.
    """
    import ast
    import re

    source = (ROOT / "innovation/evaluation/metrics.py").read_text()

    assert not re.search(r"\bTHRESHOLD\b", source), "metrics.py defines a threshold constant"

    # No verdict literal is produced anywhere in the module.
    tree = ast.parse(source)
    verdicts = {"PASS", "FAIL", "CONDITIONAL_PASS", "CRITICAL_FAIL"}
    emitted = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in verdicts
    }
    assert not emitted, f"metrics.py emits a verdict: {emitted}"


def test_override_rate_is_null_not_zero_on_an_unattended_run():
    """Nobody reviewed anything. Zero would claim nobody disagreed."""
    _, results = run_evaluation()
    assert summarise(results)["override_rate"] is None


def test_an_empty_stratum_is_reported_as_null_not_as_zero():
    results = (
        CaseResult(
            case_id="c", scenario="s", expected_minimum_urgency="ROUTINE_REVIEW",
            observed_urgency="ROUTINE_REVIEW", status="COMPLETED", human_review_required=True,
            provider_behaviour="normal", withheld_event_ids=(), evidence_used=(), error_codes=(),
        ),
    )
    # No provider-failure cases in this set, so safe_failure_rate has no denominator.
    assert summarise(results)["safe_failure_rate"] is None


def test_escalation_rate_is_reported_alongside_under_triage():
    """A system that escalates everything scores perfectly on under-triage. Reporting both
    is what stops that reading as success."""
    record, _ = run_evaluation()
    secondary = {m.split("=", 1)[0] for m in record["secondary_metrics"]}
    assert "escalation_rate" in secondary


def test_the_run_declares_its_limits_and_claims_no_verdict():
    record, _ = run_evaluation()
    assert record["review_verdict"] == "NOT_REVIEWED"
    joined = " ".join(record["deviations"]).lower()
    assert "synthetic" in joined
    assert "not a clinical reference standard" in joined
    assert "nothing here is evidence about medical capability" in joined


# ------------------------------------------------------------------ contract shape


def test_the_evaluation_record_validates_against_the_contract():
    record, _ = run_evaluation()
    schema = json.loads((ROOT / "schemas/evaluation-record.schema.json").read_text())
    jsonschema.validate(
        {"schema_version": "1.0.0", "updated_at": "2026-08-30T00:00:00+07:00",
         "evaluations": [record]},
        schema,
    )


def test_the_record_traces_to_a_manifest_that_exists():
    record, _ = run_evaluation()
    assert record["manifest_ids"]
    for manifest_id in record["manifest_ids"]:
        matches = list((ROOT / "experiments/manifests").glob(f"{manifest_id}_*.json"))
        assert matches, f"{manifest_id} has no manifest file"
