"""Slice i2 wiring: Red-flag = rf-1.1.0 (I2-A08, C2), Alerts/import validation (I2-A13, C5), screening never
overclaims (I2-A10, C2), Reasoning = S4 department (I2-A14), Pharma hook (I2-A16), lossless S1r loader (I2-A02).

Synthetic S4 author fixtures and S1r at seed 20260926 only; mock providers; offline. Rules, fixtures and gold
share authors (circular): these are wiring checks, not clinical performance.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.gateway import build_provider
from app.gateway.service import invoke_provider
from app.triage import department, redflags
from app.triage.fixtures import load_entries
from app.triage.models import Snapshot as S4Snapshot
from casegraph import data as d
from casegraph import providers
from casegraph.compiler import build_snapshot, compile_graph
from casegraph.executor import PENDING_KEY, Executor
from casegraph.export import ImportValidationError, import_graph, inspect_lines, to_json
from casegraph.library import RULES_VERSIONS, ProviderAssignment, ProviderConfig
from casegraph.providers import PLACEHOLDER_PHARMA_VERSION, mock_gateways, pharma_rules, resolve_pharma
from casegraph.sources.s1r import load_snapshot, load_split, manifest_data_class, roundtrip, snapshot_paths
from casegraph.store import MemoryStateStore, OutputStore
from casegraph.triage_bridge import evidence_from_case
from casegraph.types import NodeType

ENTRIES = load_entries()  # S4 author fixtures, dev + holdout (40)
OVERCLAIM = re.compile(r"no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)", re.IGNORECASE)
RF_IDS = tuple(r["id"] for r in redflags.rules())


def _run(items, T, patient_ref=None, config=None, gateways=None):
    gateways = gateways or mock_gateways()
    ex = Executor(gateways, OutputStore(), MemoryStateStore())
    return ex.run_sync(compile_graph(build_snapshot(items, T, patient_ref), config or ProviderConfig())), gateways


def _fixture_graph(entry, **kw):
    return _run(evidence_from_case(entry.case), entry.as_of, entry.case.case_ref, **kw)


def _s4_suggest(snap: S4Snapshot) -> department.DepartmentSuggestion:
    provider = build_provider("mock", Settings())
    return department.suggest(snap, lambda request: invoke_provider(provider, request))


@pytest.fixture(scope="module")
def dev_graphs(s1r_dataset):
    """Every S1r dev DP executed with the default config (train/dev only; never the test split)."""
    out = []
    for snap in load_split(s1r_dataset, "dev"):
        graph, _ = _run(snap.items, snap.T, snap.patient_ref)
        out.append((snap, graph))
    return out


# ------------------------------------------------------------------------------------ I2-A08 / C2


def test_red_flag_node_rf110(dev_graphs):
    assert set(RF_IDS) == set(d.DECLARED_RULES[d.RF_110]) and len(RF_IDS) == 16
    assert redflags.RULESET_VERSION == d.RF_110
    graphs = [g for _, g in dev_graphs] + [_fixture_graph(e)[0] for e in ENTRIES]
    for graph in graphs:
        rf = graph.by_type(NodeType.RED_FLAG)
        assert (rf.provider, rf.model_version, rf.status) == ("rules", d.RF_110, "ok")
        alerts = rf.output["Alerts"]
        assert alerts["rule_set_version"] == d.RF_110
        assert sorted(r["rule_id"] for r in alerts["rule_results"]) == sorted(RF_IDS)  # 16, each once
        assert alerts["label"] == d.RULE_SET_LABELS[d.RF_110] and "pending clinical expert review" in alerts["label"]
        assert alerts["scope"] == d.RULE_SET_SCOPES[d.RF_110]
        rfs = graph.red_flag_screening
        assert (rfs.rule_set_version, rfs.n_declared) == (d.RF_110, 16)
        assert rfs.n_evaluated + rfs.n_not_evaluated == 16
        assert rfs.n_fired == len({a["rule_id"] for a in alerts["alerts"]})


def test_placeholder_rules_unreachable(dev_graphs):
    config = ProviderConfig()
    assert config.assignments[NodeType.RED_FLAG].model_version == RULES_VERSIONS[NodeType.RED_FLAG] == d.RF_110
    assert all(a.model_version != d.PLACEHOLDER_RULE_SET for a in config.assignments.values())
    graphs = [g for _, g in dev_graphs] + [_fixture_graph(e)[0] for e in ENTRIES]
    for graph in graphs:
        text = to_json(graph)
        assert "RF-PH-" not in text and d.PLACEHOLDER_RULE_SET not in text
    # reachable only by an explicit assignment (the s2/s2r tests pin it that way)
    explicit = config.with_assignment(NodeType.RED_FLAG, ProviderAssignment(provider="rules",
                                                                         model_version=d.PLACEHOLDER_RULE_SET))
    graph, _ = _fixture_graph(ENTRIES[0], config=explicit)
    assert graph.by_type(NodeType.RED_FLAG).output["Alerts"]["rule_set_version"] == d.PLACEHOLDER_RULE_SET


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.case.case_ref)
def test_red_flag_parity_s4_fixtures(entry):
    graph, _ = _fixture_graph(entry)
    alerts = graph.by_type(NodeType.RED_FLAG).output["Alerts"]
    s4_alerts, s4_not_evaluable = redflags.evaluate(S4Snapshot(entry.case, entry.as_of))
    assert sorted({a["rule_id"] for a in alerts["alerts"]}) == sorted(a.rule_id for a in s4_alerts)
    assert sorted(alerts["rules_not_evaluated"]) == sorted(n.rule_id for n in s4_not_evaluable)


# ------------------------------------------------------------------------------------ I2-A10 / C2


def test_never_no_red_flags(dev_graphs):
    statuses = set()
    for _, graph in dev_graphs:
        rfs = graph.red_flag_screening
        statuses.add(rfs.status)
        for field in ("rule_set_version", "label", "scope"):
            assert getattr(rfs, field)
        assert rfs.n_declared == 16
        payload = graph.by_type(NodeType.HUMAN_CHECKPOINT).output[PENDING_KEY]
        rendered = [to_json(graph), *inspect_lines(graph), payload["screening_summary"], json.dumps(payload,
                                                                                               ensure_ascii=False)]
        assert not any(OVERCLAIM.search(x) for x in rendered)
        if rfs.status == "evaluated" and rfs.n_fired == 0:
            assert rfs.summary().startswith("0 of 16 declared rules fired")
        if rfs.status == "partially_evaluated":
            assert payload["screening_summary"].startswith(d.BANNER_INCOMPLETE)
    assert statuses  # the status distribution is reported by run-s1r; here every status is checked
    # an evaluated 0-alert screen states counts and scope, never "no red flags"
    zero = d.RedFlagScreening(status="evaluated", performed=True, banner=None, rules_evaluated=RF_IDS,
                              rules_not_evaluated=(), missing_inputs=(), rule_set_version=d.RF_110,
                              label=d.RULE_SET_LABELS[d.RF_110], scope=d.RULE_SET_SCOPES[d.RF_110], n_declared=16,
                              n_evaluated=16, n_not_evaluated=0, n_fired=0)
    assert zero.summary().startswith("0 of 16 declared rules fired") and d.RULE_SET_SCOPES[d.RF_110] in zero.summary()
    assert not OVERCLAIM.search(zero.summary())


# ------------------------------------------------------------------------------------ I2-A13 / C5


def _alerts_kwargs(rule_ids):
    results = tuple(d.RuleResult(rule_id=r, status="not_evaluated", missing_inputs=(f"in:{r}",), evaluated_on=(),
                                 fired=None) for r in rule_ids)
    ids = sorted(set(rule_ids))
    return dict(produced_by="red_flag", input_refs=(), provider="rules", model_version=d.RF_110,
                status="not_evaluated", alerts=(), rule_results=results, rules_evaluated=(), rules_not_evaluated=tuple(ids),
                missing_inputs=tuple(sorted({f"in:{r}" for r in rule_ids})), rule_set_version=d.RF_110)


def test_alerts_equals_declared_rules():
    declared = list(d.DECLARED_RULES[d.RF_110])
    d.Alerts(**_alerts_kwargs(declared))  # exactly the declared set is accepted
    cases = {"missing": declared[1:], "extra": [*declared, "RF-EXTRA"], "duplicate": [*declared, declared[0]]}
    rejected = []
    for name, ids in cases.items():
        with pytest.raises(ValidationError):
            d.Alerts(**_alerts_kwargs(ids))
        rejected.append(name)
    assert rejected == ["missing", "extra", "duplicate"]  # 3/3
    with pytest.raises(ValidationError):  # an undeclared rule set is never accepted
        d.Alerts(**{**_alerts_kwargs(declared), "rule_set_version": "rf-9.9.9"})


def _exported(entry=ENTRIES[0]) -> dict:
    graph, _ = _fixture_graph(entry)
    return json.loads(to_json(graph))


def test_import_revalidates():
    good = _exported()
    assert import_graph(json.dumps(good)).graph_id == good["graph_id"]
    rf = next(i for i, n in enumerate(good["nodes"]) if n["type"] == NodeType.RED_FLAG.value)
    reasoning = next(i for i, n in enumerate(good["nodes"]) if n["type"] == NodeType.REASONING.value)

    tampered_output = json.loads(json.dumps(good))  # 1) output changed, hash kept
    tampered_output["nodes"][reasoning]["output"]["DepartmentSuggestion"]["reason"] = "tampered"
    tampered_hash = json.loads(json.dumps(good))  # 2) hash changed, output kept
    tampered_hash["nodes"][reasoning]["output_sha256"] = "0" * 64
    invalid_alerts = json.loads(json.dumps(good))  # 3) Alerts missing a declared rule, hash recomputed
    node = invalid_alerts["nodes"][rf]
    dropped = node["output"]["Alerts"]["rule_results"].pop()
    for key in ("rules_evaluated", "rules_not_evaluated"):
        node["output"]["Alerts"][key] = [r for r in node["output"]["Alerts"][key] if r != dropped["rule_id"]]
    node["output_sha256"] = d.sha256_json(node["output"])
    rejected = 0
    for doc in (tampered_output, tampered_hash, invalid_alerts):
        with pytest.raises(ImportValidationError):
            import_graph(json.dumps(doc))
        rejected += 1
    assert rejected == 3


# ------------------------------------------------------------------------------------ I2-A14


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.case.case_ref)
def test_reasoning_equals_s4_department(entry):
    graph, _ = _fixture_graph(entry)
    node = graph.by_type(NodeType.REASONING)
    ours = node.output["DepartmentSuggestion"]
    s4 = _s4_suggest(S4Snapshot(entry.case, entry.as_of))
    assert ours["status"] == s4.status
    assert [(e["code"], e["score"]) for e in ours["top3"]] == [(e.code, e.score) for e in s4.top3]
    assert ours["uncertainty"] == s4.uncertainty and ours["reason"] == s4.reason
    assert ours["missing_information"] == s4.missing_information
    assert ours["gateway_model_version"] == s4.model_version
    assert (ours["request_sha256"] is None) == (s4.request_sha256 is None)


def test_reasoning_abstain_no_call():
    abstaining = [e for e in ENTRIES if S4Snapshot(e.case, e.as_of).missing_required()]
    assert abstaining  # the S4 fixtures include required-field-missing cases
    for entry in abstaining:
        graph, gateways = _fixture_graph(entry)
        node = graph.by_type(NodeType.REASONING)
        ours = node.output["DepartmentSuggestion"]
        assert (node.status, node.gateway_calls, ours["status"]) == ("abstained", 0, "abstained")
        assert gateways["project_model"].calls == 0  # no department call, no summary call
        assert ours["missing_information"] == S4Snapshot(entry.case, entry.as_of).missing_required()
        assert list(node.missing_inputs) == ours["missing_information"] and ours["request_sha256"] is None
        payload = graph.by_type(NodeType.HUMAN_CHECKPOINT).output[PENDING_KEY]
        assert payload["abstained"][node.id] == ours["missing_information"]


# ------------------------------------------------------------------------------------ I2-A16


def _with_meds(dev_graphs):
    return [(s, g) for s, g in dev_graphs if any(isinstance(i, d.MedicationList) for i in s.items)]


def test_pharma_hook_default(dev_graphs):
    config = ProviderConfig()
    assert config.assignments[NodeType.PHARMA_AGENT].model_version == PLACEHOLDER_PHARMA_VERSION
    hook = resolve_pharma(PLACEHOLDER_PHARMA_VERSION)
    assert hook.fn is pharma_rules and hook.label == d.PLACEHOLDER_LABEL
    with_meds = _with_meds(dev_graphs)
    assert with_meds
    for snap, graph in with_meds:
        node = graph.by_type(NodeType.PHARMA_AGENT)
        assert node.status == "ok" and node.model_version == PLACEHOLDER_PHARMA_VERSION
        issues = node.output["MedicationIssues"]
        assert issues["label"] == d.PLACEHOLDER_LABEL and issues["rule_set_version"] == PLACEHOLDER_PHARMA_VERSION
        names = {m.generic_name.strip().lower() for i in snap.items if isinstance(i, d.MedicationList)
                 for m in i.entries}
        assert {c["medication"] for c in issues["check_results"]} == names  # S1r entries -> placeholder inputs


def test_pharma_hook_swap(dev_graphs, monkeypatch):
    seen: list[int] = []

    def test_pharma(lists):
        seen.append(len(lists))
        checks = tuple(d.MedicationCheck(medication=m.generic_name, check="listed", missing_inputs=(),
                                         evaluated_on=(ml.item_id,), fired=False, status="evaluated",
                                         label="TEST PROVIDER — not clinical")
                       for ml in lists for m in ml.entries)
        return checks, ()

    monkeypatch.setattr(providers, "_PHARMA_PROVIDERS", dict(providers._PHARMA_PROVIDERS))
    providers.register_pharma_provider("test-pharma-0.1", test_pharma, label="TEST PROVIDER — not clinical")
    with pytest.raises(ValueError):
        providers.register_pharma_provider("test-pharma-0.1", pharma_rules, label="x")
    config = ProviderConfig().with_assignment(NodeType.PHARMA_AGENT,
                                              ProviderAssignment(provider="rules", model_version="test-pharma-0.1"))
    with_meds = _with_meds(dev_graphs)
    for snap, _ in with_meds:  # 100% of dev DPs with a MedicationList, 0 errors, no executor change
        graph, _ = _run(snap.items, snap.T, snap.patient_ref, config=config)
        assert not [n.id for n in graph.nodes if n.status == "error"]
        issues = graph.by_type(NodeType.PHARMA_AGENT).output["MedicationIssues"]
        assert issues["rule_set_version"] == "test-pharma-0.1" and issues["label"] == "TEST PROVIDER — not clinical"
    assert len(seen) == len(with_meds)


# ------------------------------------------------------------------------------------ I2-A02 / C6


def test_s1r_snapshot_loads_lossless(s1r_dataset):
    dc = manifest_data_class(s1r_dataset)
    assert dc == "synthetic"
    n_snap = n_items = 0
    for split in ("train", "dev", "test"):  # loading inputs only; the test split is never compiled here
        for path in snapshot_paths(s1r_dataset, split):
            source = json.loads(path.read_text(encoding="utf-8"))
            snap = load_snapshot(path, dc, split)
            assert len(snap.items) == len(source["items"])
            for item, raw in zip(snap.items, source["items"]):
                assert isinstance(item, d.Evidence) and item.data_class == dc
                back = roundtrip(item)
                assert set(back) == set(raw) | {"data_class"}  # only data_class is added
                reparsed = d.EVIDENCE_ADAPTER.validate_python({**raw, "data_class": dc})
                assert reparsed == item and d.EVIDENCE_ADAPTER.validate_python(back) == item
                n_items += 1
            n_snap += 1
    assert n_snap == 400 and n_items > 0


def test_s4_fixture_evidence_roundtrip():
    """The triage API's S4 Case -> Case Graph evidence is lossless for every fact (bridge used by /assess)."""
    for entry in ENTRIES:
        items = evidence_from_case(entry.case)
        assert [i.item_id for i in items] == [f.fact_id for f in entry.case.facts]
        assert all(i.available_at_time == f.available_at_time and i.data_class == "synthetic"
                   for i, f in zip(items, entry.case.facts))
    late = ENTRIES[0].as_of + timedelta(days=1)
    snap = build_snapshot(evidence_from_case(ENTRIES[0].case), late, ENTRIES[0].case.case_ref)
    assert len(snap.items) == len(ENTRIES[0].case.facts)
