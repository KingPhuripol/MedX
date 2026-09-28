"""Care engine (s6): abstention, evidence, red-flag carry-through, fail-safe, projection, determinism."""

from __future__ import annotations

import copy
import json
from datetime import datetime

import pytest

from app.care import engine, redflag_adapter
from app.care.models import CareResult
from app.care.snapshot import REQUIRED_INPUTS, SnapshotView
from app.triage import redflags
from app.triage.models import IntakeFact
from casegraph.data import CareSuggestion, banner_for

from .conftest import FakeProvider, complete_dev_row, run

URGENCY = ("alerts", "red_flag_screening", "escalation_required")


@pytest.fixture(scope="module")
def results(dataset):
    """Engine result for every decision point of every split (mock provider)."""
    out = []
    for row in dataset.rows:
        r, calls = run(dataset.row_snapshot(row), row["dp"])
        out.append((row, r, calls))
    return out


# ---------------------------------------------------------------- abstention (A01, A02, A13)
def test_abstains_when_required_missing(results):
    rows = [(row, r, c) for row, r, c in results if row["care"]["expected_action"] == "abstain"]
    assert len(rows) > 50
    for row, r, calls in rows:
        assert r.status == "abstained", row["case_id"]
        assert r.case_summary == [] and r.next_information == [] and r.pathway_options == []
        assert r.missing_information == row["care"]["required_inputs_missing"]
        assert calls == 0 and r.request_sha256 is None and r.casegraph_projection is None


def test_no_false_abstention(results):
    bad = [(row["case_id"], row["dp"]) for row, r, _ in results
           if row["care"]["expected_action"] == "suggest" and r.status == "abstained"]
    assert bad == []
    assert all(r.status == "suggested" for row, r, _ in results if row["care"]["expected_action"] == "suggest")


def _drop_question(doc, question):
    for it in doc["items"]:
        if it["data_type"] == "IntakeTranscript":
            turns = it["turns"]
            i = next(i for i, t in enumerate(turns) if t["speaker"] == "nurse" and question in t["text"])
            del turns[i:i + 2]
    return doc


def _variant(doc, field):
    doc = copy.deepcopy(doc)
    items = doc["items"]
    if field in ("demographics.age", "demographics.sex"):
        key = "age_years" if field.endswith("age") else "sex"
        for it in items:
            if it["data_type"] == "Demographics":
                it[key] = None
    elif field == "chief_complaint":
        _drop_question(doc, "อาการอะไร")
    elif field == "duration":
        _drop_question(doc, "นานเท่าไร")
    elif field == "allergy_status":
        doc["items"] = [it for it in items if it["data_type"] != "AllergyList"]
    elif field == "allergy_unknown":
        for it in items:
            if it["data_type"] == "AllergyList":
                it["status"], it["entries"] = "unknown", []
    else:
        param = field.split(".")[1]
        for it in items:
            if it["data_type"] == "Vitals":
                it[param] = None
    return doc


@pytest.mark.parametrize("field", [*REQUIRED_INPUTS, "allergy_unknown"])
def test_each_required_input_individually(dataset, field):
    base = dataset.row_snapshot(complete_dev_row(dataset))
    assert run(base)[0].status == "suggested"
    r, calls = run(_variant(base, field))
    expected = "allergy_status" if field == "allergy_unknown" else field
    assert (r.status, r.missing_information, calls) == ("abstained", [expected], 0)
    assert r.next_information == [] and r.pathway_options == [] and r.case_summary == []


def test_unknown_not_negative(dataset):
    base = dataset.row_snapshot(complete_dev_row(dataset))
    doc = _variant(base, "allergy_unknown")
    assert run(doc)[0].missing_information == ["allergy_status"]
    answered, _ = run(doc, abstain=False)  # always-answer comparator path still says "not known"
    text = " ".join(x.text for x in answered.case_summary)
    assert "Allergy status: not known" in text and "no known allergy" not in text
    assert "allergy_status" in answered.missing_information
    # A complaint stated as unclear is "unknown" and counts as missing.
    for it in base["items"]:
        if it["data_type"] == "IntakeTranscript":
            i = next(i for i, t in enumerate(it["turns"]) if t["speaker"] == "nurse" and "อาการอะไร" in t["text"])
            it["turns"][i + 1]["text"] = "บอกไม่ถูกค่ะ"
    assert SnapshotView(base).fields()["chief_complaint"].state == "unknown"
    assert run(base)[0].missing_information == ["chief_complaint"]


def test_missing_information_explicit(dataset, results):
    for row, r, _ in results:
        assert isinstance(r.missing_information, list)
        if r.status != "suggested":
            continue
        snap = dataset.row_snapshot(row)
        has_lab = any(it["data_type"] == "LabSeries" for it in snap["items"])
        assert ("lab_results" in r.missing_information) == (not has_lab)
        if not has_lab:  # no lab line is rendered as normal
            assert not any(x.text.startswith("Lab ") for x in r.case_summary)
    assert any(r.status == "suggested" and "lab_results" in r.missing_information
               for row, r, _ in results if row["split"] == "dev")


# ---------------------------------------------------------------- evidence (A03)
def test_evidence_refs_time_valid(dataset, results):
    n = 0
    for row, r, _ in results:
        view = SnapshotView(dataset.row_snapshot(row))
        for x in [*r.case_summary, *r.next_information, *r.pathway_options]:
            assert x.evidence_refs, (row["case_id"], x)
            for ref in x.evidence_refs:
                item = view.by_id[ref.item_id]  # KeyError = ref not in snapshot_T
                assert datetime.fromisoformat(ref.available_at_time) == item.available_at_time <= view.as_of
                n += 1
    assert n > 1000


def _bad_output(kind, t1, t2):
    extra = next(i for i in t2 if i not in t1)
    ref = {"future": [extra], "unknown": ["NOPE-ITEM"], "none": []}[kind]
    return {"next_information": [{"code": "NI-ECG-12LEAD", "evidence_refs": ref}], "pathway_options": []}


@pytest.mark.parametrize("kind", ["future", "unknown", "none"])
def test_bad_refs_fail_safe(dataset, kind):
    row = next(r for r in dataset.rows if r["split"] == "dev" and r["dp"] == "T1"
               and r["care"]["expected_action"] == "suggest"
               and len(dataset.snapshot("dev", r["case_id"], "T2")["items"])
               > len(dataset.snapshot("dev", r["case_id"], "T1")["items"]))
    t1 = dataset.snapshot("dev", row["case_id"], "T1")
    t2 = dataset.snapshot("dev", row["case_id"], "T2")
    ids1, ids2 = [i["item_id"] for i in t1["items"]], [i["item_id"] for i in t2["items"]]
    good, _ = run(t1, "T1")
    r, calls = run(t1, "T1", provider=FakeProvider(output=_bad_output(kind, ids1, ids2)))
    assert calls == 1 and r.status == "error"
    assert r.next_information == [] and r.pathway_options == [] and r.case_summary == []
    assert [getattr(r, k) for k in URGENCY] == [getattr(good, k) for k in URGENCY]


def test_snapshot_rejects_future_item(dataset):
    row = complete_dev_row(dataset)
    doc = dataset.row_snapshot(row)
    late = copy.deepcopy(doc["items"][-1])
    late["item_id"] += "-LATE"
    late["available_at_time"] = "2099-01-01T00:00:00+07:00"
    doc["items"].append(late)
    r, calls = run(doc)
    assert (r.status, r.reason, calls) == ("error", "snapshot_item_after_as_of", 0)
    assert r.next_information == [] and r.red_flag_screening.status == "unavailable"


# ---------------------------------------------------------------- red flags (A04, A05)
def _symptom_facts(state="absent"):
    names = sorted({c["symptom"] for rule in redflags.rules() for c in _leaves(rule["condition"]) if "symptom" in c})
    return [IntakeFact(fact_id=f"UT-S{i:02d}", kind=f"symptom.{n}", value=state,
                       available_at_time="2000-01-01T00:00:00+00:00", source="unit-test",
                       provenance="synthetic unit test", version="t1") for i, n in enumerate(names)] + [
        IntakeFact(fact_id="UT-GLU", kind="vital.capillary_glucose_mg_dl", value=100,
                   available_at_time="2000-01-01T00:00:00+00:00", source="unit-test",
                   provenance="synthetic unit test", version="t1")]


def _leaves(cond):
    if any(k in cond for k in ("any", "all", "at_least")):
        for c in cond.get("any") or cond.get("all") or cond["of"]:
            yield from _leaves(c)
    else:
        yield cond


def _alert_row(dataset, split="dev"):
    for row in dataset.rows:
        if row["split"] == split and row["care"]["expected_action"] == "suggest":
            r, _ = run(dataset.row_snapshot(row), row["dp"])
            if r.alerts:
                return row, r
    raise AssertionError("no alert row")


@pytest.mark.parametrize("state", ["evaluated", "partially_evaluated", "not_evaluated", "unavailable"])
def test_screening_carried(dataset, monkeypatch, state):
    row, _ = _alert_row(dataset)
    doc = dataset.row_snapshot(row)
    kw = {}
    if state == "evaluated":
        kw["extra_facts"] = _symptom_facts()
    elif state == "not_evaluated":
        doc["items"] = [it for it in doc["items"] if it["data_type"] not in ("Vitals", "Demographics")]
    elif state == "unavailable":
        monkeypatch.setattr(redflags, "evaluate", lambda snap: 1 / 0)
    r, _ = run(doc, row["dp"], **kw)
    s = r.red_flag_screening
    assert s.status == state and s.banner == banner_for(state) and s.performed == (state == "evaluated")
    if state == "evaluated":
        assert r.alerts and r.escalation_required and s.rules_not_evaluated == [] and r.status == "suggested"
    if state == "partially_evaluated":
        assert s.banner == "RED-FLAG SCREENING INCOMPLETE" and s.rules_not_evaluated
    if state in ("not_evaluated", "unavailable"):
        assert s.banner == "RED-FLAG SCREENING NOT PERFORMED" and r.status == "abstained" and not r.alerts


def test_alerts_serialized_first(results):
    for _, r, _ in results[:40]:
        keys = list(json.loads(r.model_dump_json()))
        assert keys[:4] == ["alerts", "red_flag_screening", "escalation_required", "status"]
        assert keys.index("status") < keys.index("case_summary") < keys.index("next_information")


def _clear_alerts(out):
    return {**out, "alerts": [], "red_flag_screening": {"status": "evaluated"}, "escalation_required": False}


PROVIDER_MODES = {
    "ok": lambda: None,
    "error": lambda: FakeProvider(status="error", reason="provider_exception"),
    "rejected": lambda: FakeProvider(status="rejected", reason="policy"),
    "invalid": lambda: FakeProvider(output={"next_information": "not a list"}),
    "clears_alerts": lambda: FakeProvider(mutate=_clear_alerts),
}


def test_model_cannot_change_alerts(dataset, results):
    red = [(row, r) for row, r, _ in results if row["split"] == "dev" and r.alerts]
    assert red
    for row, base in red:
        doc = dataset.row_snapshot(row)
        seen = set()
        for mode, make in PROVIDER_MODES.items():
            p = make()
            r, _ = run(doc, row["dp"], **({} if p is None else {"provider": p}))
            blob = json.dumps([r.model_dump(mode="json")[k] for k in URGENCY], sort_keys=True)
            seen.add(blob)
            if mode != "ok" and base.status == "suggested":
                assert r.status == "error" and r.next_information == [], mode
        assert len(seen) == 1, row["case_id"]


def test_screening_unavailable_abstains(dataset, monkeypatch):
    row = complete_dev_row(dataset)
    monkeypatch.setattr(redflag_adapter, "declared_rules", lambda: 1 / 0)
    r, calls = run(dataset.row_snapshot(row), row["dp"])
    assert r.red_flag_screening.status == "unavailable" and r.status == "abstained" and calls == 0
    assert r.missing_information == ["red_flag_screening"]


@pytest.mark.parametrize("consc,expected", [
    ("A", {"vital.avpu": "A", "vital.new_confusion": False}),
    ("C", {"vital.new_confusion": True}),
    ("V", {"vital.avpu": "V"}), ("P", {"vital.avpu": "P"}), ("U", {"vital.avpu": "U"}),
    (None, {}),
])
def test_redflag_adapter_mapping(dataset, consc, expected):
    doc = dataset.row_snapshot(complete_dev_row(dataset))
    for it in doc["items"]:
        if it["data_type"] == "Vitals":
            it["consciousness"] = consc
            it["hr"] = None
    facts = redflag_adapter.to_facts(SnapshotView(doc))
    kinds = {f.kind: f.value for f in facts}
    assert {k: v for k, v in kinds.items() if k in ("vital.avpu", "vital.new_confusion")} == expected
    assert "vital.hr" not in kinds  # null -> no fact -> rule not evaluable, never "normal"
    assert {"age", "sex"} <= set(kinds) and not any(k.startswith("symptom.") for k in kinds)
    view = SnapshotView(doc)
    assert all(f.available_at_time <= view.as_of for f in facts)
    scr = redflag_adapter.screen(view).screening
    assert "RF-HR" in scr.rules_not_evaluated and scr.status == "partially_evaluated"


# ---------------------------------------------------------------- gateway, fail safe, projection (A06, A07)
@pytest.mark.parametrize("mode", ["error", "rejected", "invalid", "timeout"])
def test_care_fail_safe(dataset, mode):
    row = complete_dev_row(dataset)
    p = {"error": FakeProvider(status="error", reason="provider_http_error"),
         "rejected": FakeProvider(status="rejected", reason="policy_non_synthetic"),
         "invalid": FakeProvider(output={"text": "free text"}),
         "timeout": FakeProvider(raises=TimeoutError("timed out"))}[mode]
    r, calls = run(dataset.row_snapshot(row), row["dp"], provider=p)
    assert calls == 1 and r.status == "error"
    assert r.next_information == [] and r.pathway_options == [] and r.case_summary == []
    assert r.casegraph_projection is None and r.reason


def test_code_outside_vocabulary_fails_safe(dataset):
    row = complete_dev_row(dataset)
    doc = dataset.row_snapshot(row)
    ref = doc["items"][0]["item_id"]
    bad = {"next_information": [{"code": "NI-MADE-UP", "evidence_refs": [ref]}], "pathway_options": []}
    assert run(doc, row["dp"], provider=FakeProvider(output=bad))[0].status == "error"


def test_projection_is_care_suggestion(results):
    n = 0
    for _, r, _ in results:
        if r.status != "suggested":
            continue
        p = CareSuggestion.model_validate(r.casegraph_projection)
        assert list(p.items) == [x.code for x in [*r.next_information, *r.pathway_options]]
        assert p.red_flag_screening == r.red_flag_screening.status
        assert list(p.input_refs) == sorted({e.item_id for x in [*r.next_information, *r.pathway_options]
                                             for e in x.evidence_refs})
        n += 1
    assert n > 100


def test_alert_items_rank_first(results):
    for _, r, _ in results:
        if r.status == "suggested" and r.alerts:
            codes = [x.code for x in r.next_information]
            assert codes == sorted(codes, key=lambda c: c not in engine._alert_codes(r.alerts))


def test_care_deterministic(dataset):
    for row in dataset.rows[:30]:
        a, _ = run(dataset.row_snapshot(row), row["dp"])
        b, _ = run(dataset.row_snapshot(row), row["dp"])
        assert a.model_dump_json() == b.model_dump_json()
    assert isinstance(a, CareResult)
