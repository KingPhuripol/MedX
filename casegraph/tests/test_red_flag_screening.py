"""s2r — Red-flag ``not_evaluated``: S2R-A02, A03, A04, A06, A08, A10 (rule level), A12.

A05 (construction invariant) and A10 (validation) live in ``test_typed_data.py``.
Rule thresholds are PLACEHOLDER — not clinical.
"""

from __future__ import annotations

import itertools
import math

import pytest
from pydantic import ValidationError

from casegraph import data as d
from casegraph.compiler import build_snapshot, compile_graph
from casegraph.executor import PENDING_KEY, Executor
from casegraph.library import RULES_VERSIONS, LibraryConfig, ProviderAssignment, ProviderConfig
from casegraph.providers import (
    RED_FLAG_RULE_IDS,
    RED_FLAG_RULE_SET_VERSION,
    LocalGateway,
    mock_gateways,
    red_flag_rules,
)
from casegraph.store import MemoryStateStore, OutputStore
from casegraph.types import NodeType as N

from .conftest import FakeProvider, compile_case, s2_config
from .fixtures import DAY, F3_T, F5_T, H, cxr, text, vitals

ALL_RULES = ["RF-PH-001", "RF-PH-002", "RF-PH-003", "RF-PH-004"]
RULE_KEY = {"RF-PH-001": "spo2", "RF-PH-002": "sbp", "RF-PH-003": "hr", "RF-PH-004": "temp_c"}
NORMAL = {"spo2": 97.0, "sbp": 124.0, "hr": 80.0, "temp_c": 37.0}
T = DAY + 12 * H


def _run(items, T=T, config=None, patient_ref=None, gateways=None):
    ex = Executor(gateways or mock_gateways(), OutputStore(), MemoryStateStore())
    return ex.run_sync(compile_graph(build_snapshot(items, T, patient_ref=patient_ref), config))


def _alerts(graph):
    return graph.node("red_flag").output["Alerts"]


def _payload(graph):
    return graph.node("human_checkpoint").output[PENDING_KEY]


def _case(pid, **values):
    return [text(pid, f"{pid}-text", DAY + 8 * H, DAY + 8 * H),
            vitals(pid, f"{pid}-vitals", DAY + 9 * H, DAY + 9 * H, **values)]


# ------------------------------------------------------------------------------------ A02


def _graph_without_vitals(case: str, env):
    if case == "text_only":
        return env.executor().run_sync(compile_case("F3", F3_T))
    if case == "cxr_only":
        return _run([cxr("SYN-RF-CXR", "rf-cxr", DAY + 8 * H, DAY + 8 * H)])
    env.gateways["project_model"] = LocalGateway(
        FakeProvider(model_version="proj-mock-0.1", mode="error", tasks={"reader_text"}))
    return env.executor().run_sync(compile_case("F3", F3_T))


@pytest.mark.parametrize("case", ["text_only", "cxr_only", "findings_errored"])
def test_red_flag_not_evaluated_without_vitals(env, case):
    graph = _graph_without_vitals(case, env)
    alerts = _alerts(graph)
    assert alerts["status"] == "not_evaluated"
    assert [r["status"] for r in alerts["rule_results"]] == ["not_evaluated"] * 4
    assert all(r["fired"] is None and r["evaluated_on"] == [] for r in alerts["rule_results"])
    assert alerts["rules_evaluated"] == [] and alerts["rules_not_evaluated"] == ALL_RULES
    assert {"Vitals", *(f"Vitals.{k}" for k in RULE_KEY.values())} <= set(alerts["missing_inputs"])
    assert alerts["alerts"] == []
    payload = _payload(graph)
    assert payload["escalation"] is True and "red_flag_not_evaluated" in payload["escalation_reasons"]
    if case != "text_only":
        assert "Findings" in alerts["missing_inputs"]


# ------------------------------------------------------------------------------------ A03


@pytest.mark.parametrize("case", ["normal", "urgent", "no_rule_keys"])
def test_red_flag_partial_per_rule(case):
    values = {"normal": {"spo2": 97.0, "hr": 80.0}, "urgent": {"spo2": 86.0, "hr": 80.0},
              "no_rule_keys": {"rr": 30.0}}[case]
    graph = _run(_case(f"SYN-RFP-{case}", **values))
    alerts, payload = _alerts(graph), _payload(graph)
    by_rule = {r["rule_id"]: r for r in alerts["rule_results"]}
    if case == "no_rule_keys":
        assert alerts["status"] == "not_evaluated" and alerts["rules_evaluated"] == []
        assert payload["escalation"] is True and "red_flag_not_evaluated" in payload["escalation_reasons"]
        return
    assert alerts["status"] == "partially_evaluated"
    assert alerts["rules_evaluated"] == ["RF-PH-001", "RF-PH-003"]
    assert alerts["rules_not_evaluated"] == ["RF-PH-002", "RF-PH-004"]
    assert by_rule["RF-PH-002"]["missing_inputs"] == ["Vitals.sbp"]
    assert by_rule["RF-PH-004"]["missing_inputs"] == ["Vitals.temp_c"]
    assert by_rule["RF-PH-001"]["evaluated_on"] == [f"SYN-RFP-{case}-vitals"]
    assert payload["escalation"] is True and "red_flag_partially_evaluated" in payload["escalation_reasons"]
    if case == "urgent":
        assert by_rule["RF-PH-001"]["fired"] is True
        assert {"urgent_red_flag", "red_flag_partially_evaluated"} <= set(payload["escalation_reasons"])
    else:
        assert by_rule["RF-PH-001"]["fired"] is False
        assert "urgent_red_flag" not in payload["escalation_reasons"]


# ------------------------------------------------------------------------------------ A04


def test_red_flag_status_truth_table():
    violations, n = [], 0
    for idx, (subset_bits, has_vitals, has_text) in enumerate(
        itertools.product(itertools.product([0, 1], repeat=4), [True, False], [True, False])
    ):
        pid = f"SYN-TT{idx:03d}"
        subset = {k for k, bit in zip(NORMAL, subset_bits) if bit}
        items = []
        if has_text:
            items.append(text(pid, f"{pid}-text", DAY + 8 * H, DAY + 8 * H))
        if has_vitals:  # rr keeps the values dict non-empty; no placeholder rule reads it
            items.append(vitals(pid, f"{pid}-vitals", DAY + 9 * H, DAY + 9 * H,
                                rr=16.0, **{k: NORMAL[k] for k in subset}))
        graph = _run(items, patient_ref=pid)
        status, payload = _alerts(graph)["status"], _payload(graph)
        full = has_vitals and subset == set(NORMAL)
        if (status == "evaluated") != full:
            violations.append((subset_bits, has_vitals, has_text, status))
        if (payload["escalation"] is False) != (status == "evaluated" and not _alerts(graph)["alerts"]):
            violations.append(("escalation", subset_bits, has_vitals, has_text, payload["escalation_reasons"]))
        n += 1
    assert n == 64 and violations == []


# ------------------------------------------------------------------------------------ A06


def _screening_case(case, env, monkeypatch):
    if case == "not_evaluated":
        return env.executor().run_sync(compile_case("F3", F3_T))
    if case == "partial":
        return _run(_case("SYN-RFS-P", spo2=97.0, hr=80.0))
    if case == "unavailable":
        def _boom(self, ctx):
            raise RuntimeError("red-flag body failed")

        monkeypatch.setattr(Executor, "_red_flag", _boom)
        return env.executor().run_sync(compile_case("F5", F5_T))
    return env.executor().run_sync(compile_case("F5", F5_T))


EXPECTED_BLOCK = {
    "not_evaluated": dict(status="not_evaluated", performed=False, banner="RED-FLAG SCREENING NOT PERFORMED",
                          rules_evaluated=[], rules_not_evaluated=ALL_RULES,
                          missing_inputs=["Vitals", "Vitals.hr", "Vitals.sbp", "Vitals.spo2", "Vitals.temp_c"]),
    "partial": dict(status="partially_evaluated", performed=False, banner="RED-FLAG SCREENING INCOMPLETE",
                    rules_evaluated=["RF-PH-001", "RF-PH-003"], rules_not_evaluated=["RF-PH-002", "RF-PH-004"],
                    missing_inputs=["Vitals.sbp", "Vitals.temp_c"]),
    "unavailable": dict(status="unavailable", performed=False, banner="RED-FLAG SCREENING NOT PERFORMED",
                        rules_evaluated=[], rules_not_evaluated=ALL_RULES, missing_inputs=["Alerts"]),
    "evaluated": dict(status="evaluated", performed=True, banner=None, rules_evaluated=ALL_RULES,
                      rules_not_evaluated=[], missing_inputs=[]),
}
EXPECTED_REASONS = {
    "not_evaluated": ["red_flag_not_evaluated"],
    "partial": ["red_flag_partially_evaluated"],
    "unavailable": ["red_flag_unavailable"],
    "evaluated": ["urgent_red_flag"],  # F5 is full-input with urgent vitals
}


@pytest.mark.parametrize("case", ["not_evaluated", "partial", "unavailable", "evaluated"])
def test_checkpoint_red_flag_screening_block(env, case, monkeypatch):
    graph = _screening_case(case, env, monkeypatch)
    payload = _payload(graph)
    assert "red_flag_screening" in payload
    assert payload["red_flag_screening"] == EXPECTED_BLOCK[case]
    assert payload["red_flag_screening"]["performed"] is (case == "evaluated")
    assert payload["escalation_reasons"] == EXPECTED_REASONS[case]
    assert payload["escalation"] is True  # evaluated F5 escalates on the urgent alert only
    assert graph.red_flag_screening.model_dump(mode="json") == payload["red_flag_screening"]
    if case == "unavailable":
        assert graph.node("red_flag").status == "error" and payload["alerts"] is None


def test_evaluated_without_urgent_does_not_escalate():
    graph = _run(_case("SYN-RFS-OK", **NORMAL))
    payload = _payload(graph)
    assert payload["red_flag_screening"]["status"] == "evaluated"
    assert payload["escalation"] is False and payload["escalation_reasons"] == []


# ------------------------------------------------------------------------------------ A08


def test_reasoning_output_carries_screening_status(env):
    cfg = ProviderConfig(library=LibraryConfig(reasoning_required_inputs=("Findings<-ClinicalText",)))
    for name, T_, expected in (("F3", F3_T, "not_evaluated"), ("F5", F5_T, "evaluated")):
        graph = env.executor().run_sync(compile_case(name, T_, cfg))
        r = graph.node("reasoning")
        assert r.status == "ok", r.reason
        types = ("CaseSummary", "DepartmentSuggestion", "CareSuggestion")
        assert [r.output[t]["red_flag_screening"] for t in types] == [expected] * 3
        for_review = _payload(graph)["for_review"]
        assert for_review and all(entry["red_flag_screening"] == expected for entry in for_review.values())
        assert for_review["reasoning"]["red_flag_screening"] == expected


@pytest.mark.parametrize("cls,payload", [
    (d.CaseSummary, {"text": "t"}),
    (d.DepartmentSuggestion, {"department": None}),
    (d.CareSuggestion, {"items": ()}),
])
def test_suggestion_requires_screening_field(cls, payload):
    prov = {"produced_by": "reasoning", "input_refs": (), "provider": "project_model", "model_version": "m"}
    with pytest.raises(ValidationError, match="red_flag_screening"):
        cls(**prov, **payload)
    with pytest.raises(ValidationError):
        cls(**prov, **payload, red_flag_screening="passed")
    assert cls(**prov, **payload, red_flag_screening="unavailable").red_flag_screening == "unavailable"


# ------------------------------------------------------------------------------------ A10


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf], ids=["nan", "inf", "-inf"])
def test_rule_treats_non_finite_as_missing(bad):
    item = vitals("SYN-NF", "nf-vitals", DAY, DAY, **NORMAL)
    # model_construct bypasses validation (S2R-A10): the rule must still not read the value as normal
    corrupted = d.Vitals.model_construct(**{**dict(item), **NORMAL, "spo2": bad})
    assert math.isnan(corrupted.spo2) or math.isinf(corrupted.spo2)
    results, alerts = red_flag_rules([corrupted])
    by_rule = {r.rule_id: r for r in results}
    assert by_rule["RF-PH-001"].status == "not_evaluated"
    assert by_rule["RF-PH-001"].missing_inputs == ("Vitals.spo2",) and by_rule["RF-PH-001"].fired is None
    assert [r.status for r in results if r.rule_id != "RF-PH-001"] == ["evaluated"] * 3
    assert d.screening_status(results) == "partially_evaluated" and alerts == ()


# ------------------------------------------------------------------------------------ A12


def test_red_flag_rule_set_version_and_label(env):
    assert RULES_VERSIONS[N.RED_FLAG] == RED_FLAG_RULE_SET_VERSION == "placeholder-redflag-0.2"
    assert tuple(ALL_RULES) == RED_FLAG_RULE_IDS
    graph = env.executor().run_sync(compile_case("F5", F5_T))
    alerts = _alerts(graph)
    assert alerts["rule_set_version"] == "placeholder-redflag-0.2" and alerts["label"] == d.PLACEHOLDER_LABEL
    assert len(alerts["rule_results"]) == 4 and alerts["alerts"]
    assert all(r["label"] == "PLACEHOLDER — not clinical" for r in alerts["rule_results"])
    assert all("PLACEHOLDER — not clinical" in a["message"] for a in alerts["alerts"])
    # same inputs, rule set 0.1 -> a different cache key (0.1 outputs are never served for 0.2)
    old = s2_config().with_assignment(
        N.RED_FLAG, ProviderAssignment(provider="rules", model_version="placeholder-redflag-0.1"))
    graph_old = _run(compile_case("F5", F5_T).snapshot.items, T=F5_T, config=old)
    graph_new = _run(compile_case("F5", F5_T).snapshot.items, T=F5_T)
    assert graph_old.node("red_flag").cache_key != graph_new.node("red_flag").cache_key
    assert graph_old.node("reader_text").cache_key == graph_new.node("reader_text").cache_key


def test_errored_findings_producer_blocks_evaluated_even_with_full_vitals():
    """s2r: all 4 rules evaluated, but an errored Findings producer is a missing input -> never ``evaluated``."""
    gateways = mock_gateways()
    gateways["project_model"] = LocalGateway(
        FakeProvider(model_version="proj-mock-0.1", mode="error", tasks={"reader_text"}))
    graph = _run(_case("SYN-RF-FE", **NORMAL), gateways=gateways)
    alerts, payload = _alerts(graph), _payload(graph)
    assert alerts["rules_evaluated"] == ALL_RULES and "Findings" in alerts["missing_inputs"]
    assert alerts["status"] == "partially_evaluated"
    assert payload["red_flag_screening"]["performed"] is False
    assert payload["escalation"] is True and "red_flag_partially_evaluated" in payload["escalation_reasons"]
