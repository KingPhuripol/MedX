"""Slice int2: S6 care on the I2 Case Graph type system. Synthetic data, offline, mock provider, Tier 0.

Behaviour is frozen (parity with d423d15, frozen predictions reproduce); representation is the I2
``RedFlagScreening`` block with a care scope; stale vitals never drop an alert (D-int2-1).
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.care import engine, evaluate, redflag_adapter, router
from app.care.redflag_adapter import CARE_SCREENING_SCOPE
from app.care.snapshot import SnapshotView
from app.gateway import MOCK_LABEL, mock_tasks
from app.gateway import service as gateway_service
from app.gateway.contract import GatewayRequest
from app.triage import redflags
from casegraph.data import RF_110, RULE_SET_LABELS, RULE_SET_SCOPES, RedFlagScreening
from casegraph.triage_bridge import stale_input

from ..conftest import REPO_ROOT
from .conftest import _PROVIDER, complete_dev_row, factory_generate, run
from .test_api import CLAIMS, physician  # noqa: F401  (fixture)

OVERCLAIM = re.compile(r"no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)", re.IGNORECASE)
HELDOUT_SEED = 20260927
S6 = REPO_ROOT / "slices" / "s6" / "eval"
FIXTURE = Path(__file__).parent / "fixtures" / "s6_urgency_d423d15.json"
SCRIPT = REPO_ROOT / "scripts" / "int2_dump_s6_urgency.py"
WINDOW_S = 60 * 60  # casegraph/config/vital_freshness_v1.json: every mapped vital has a 60 min window


def _script():
    spec = importlib.util.spec_from_file_location("int2_dump_s6_urgency", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def heldout(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("int2_heldout") / "s6r-heldout"
    factory_generate(HELDOUT_SEED, out, heldout=True)
    return out


@pytest.fixture(scope="module")
def results(dataset, heldout):
    """(dataset name, snapshot doc, CareResult, gateway calls) for all 560 decision points."""
    out = []
    for name, root in (("v1", dataset.root), ("heldout", heldout)):
        for _split, _cid, dp, path in _script().snapshots(root):
            doc = json.loads(path.read_text("utf-8"))
            r, calls = run(doc, dp)
            out.append((name, doc, r, calls))
    assert len(out) == 560
    return out


# ----------------------------------------------------------------- frozen evidence (A06, A07, A12)


def _slices_state() -> dict[str, tuple[int, int]]:
    return {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in (REPO_ROOT / "slices").rglob("*") if p.is_file()}


@pytest.mark.parametrize("which", ["dev_0002", "test_0002"])
def test_s6_frozen_predictions_reproduce(which, dataset, heldout, monkeypatch):
    split, root = ("dev", dataset.root) if which == "dev_0002" else ("test", heldout)
    monkeypatch.setenv("CARE_DATASET", str(root))
    monkeypatch.setattr(evaluate, "V1_DATASET", dataset.root)  # train prior from v1 train, as when frozen
    before = _slices_state()
    preds, cmps, _ = evaluate.records(split)
    assert _slices_state() == before  # nothing written under slices/
    p = evaluate.paths(split, f"s6-care-{split}-0002")
    for rows, path in ((preds, p["predictions"]), (cmps, p["comparator"])):
        assert hashlib.sha256(evaluate._dump_jsonl(rows)).hexdigest() == hashlib.sha256(path.read_bytes()).hexdigest()


URGENCY_KEYS = ("dataset", "split", "case_id", "dp", "alerts", "escalation_required", "status", "reason",
                "missing_information", "screening")


@pytest.fixture(scope="module")
def parity(dataset, heldout):
    """(fixture rows recorded at d423d15, the same rows computed now by this checkout), aligned by DP."""
    doc = json.loads(FIXTURE.read_text("utf-8"))
    head = doc["header"]
    assert head["generated_from_commit"].startswith("d423d15") and "int2_dump_s6_urgency.py" in head["command"]
    assert SCRIPT.is_file()
    trees = {"v1": dataset.root, "heldout": heldout}
    for name, root in trees.items():
        meta = json.loads((root / "manifest.json").read_text("utf-8"))
        assert head["datasets"][name]["tree_sha256"] == meta["tree_sha256"], name
    now = _script().assess_all(trees)
    assert len(now) == len(doc["rows"]) == 560
    for a, b in zip(now, doc["rows"], strict=True):
        assert (a["dataset"], a["case_id"], a["dp"]) == (b["dataset"], b["case_id"], b["dp"])
    return doc["rows"], now


def _mismatches(parity, keys) -> list[tuple[str, str, str]]:
    then, now = parity
    return [(a["dataset"], a["case_id"], a["dp"]) for a, b in zip(now, then, strict=True)
            if {k: a[k] for k in keys} != {k: b[k] for k in keys}]


def test_urgency_parity_d423d15(parity):
    assert _mismatches(parity, URGENCY_KEYS) == []


def test_result_parity_d423d15(parity):
    """INT2-A07 ii / A18: the whole CareResult (incl. case_summary text) minus the I2 block and request_sha256."""
    assert _mismatches(parity, ("result_sha256",)) == []


def test_gateway_request_parity_d423d15(parity):
    """INT2-A17: same number of gateway calls, and the same request under normalisation N."""
    then, _ = parity
    assert sum(r["n_gateway_calls"] == 1 for r in then) == 442 and sum(r["n_gateway_calls"] == 0 for r in then) == 118
    assert all((r["n_gateway_calls"] == 0) == (r["request_sha256_normalised"] is None) for r in then)
    assert _mismatches(parity, ("n_gateway_calls", "request_sha256_normalised")) == []


def _captured_request(dataset):
    """A real care gateway request with at least one alert and one Vitals item."""
    for row in dataset.rows:
        reqs = []
        r = engine.assess(dataset.row_snapshot(row),
                          lambda q: (reqs.append(q), gateway_service.invoke_provider(_PROVIDER, q))[1],
                          decision_point=row["dp"])
        items = reqs[0].inputs["items"] if reqs else []
        if r.alerts and any(it["data_type"] == "Vitals" and it.get("hr") is not None for it in items):
            return reqs[0]
    raise AssertionError("no calling DP with an alert")


def _vitals(d):
    return next(it for it in d["inputs"]["items"] if it["data_type"] == "Vitals")


MUTATIONS = {
    "a": lambda d: _vitals(d).update(hr=_vitals(d)["hr"] + 1),
    "b": lambda d: _vitals(d).update(new_confusion=True),
    "c": lambda d: d["inputs"]["items"][0].update(data_class="real"),
    "d": lambda d: d["inputs"]["items"][0].update(added_key="x"),
    "e": lambda d: d["inputs"]["items"].__setitem__(slice(0, 2), d["inputs"]["items"][1::-1]),
    "f": lambda d: d["inputs"]["alerts"].pop(),
}


@pytest.mark.parametrize("which", sorted(MUTATIONS))
def test_request_normalisation_is_sensitive(which, dataset):
    """N removes only the enumerated representation deltas; every real change still changes the hash."""
    script = _script()
    req = _captured_request(dataset)
    base = script.request_sha256_normalised(req)
    d = copy.deepcopy(req.model_dump(mode="json"))
    assert len(d["inputs"]["items"]) >= 2 and d["inputs"]["alerts"]
    MUTATIONS[which](d)
    assert script.request_sha256_normalised(GatewayRequest.model_validate(d)) != base
    # the enumerated deltas themselves are absorbed: an S6-shaped request hashes the same
    s6 = copy.deepcopy(req.model_dump(mode="json"))
    for it in s6["inputs"]["items"]:
        it.pop("data_class", None)
        if it["data_type"] == "Vitals":
            for k in ("new_confusion", "capillary_glucose_mg_dl"):
                it.pop(k, None)
    assert script.request_sha256_normalised(GatewayRequest.model_validate(s6)) == base


def test_case_summary_format(dataset):
    """INT2-A18: integral counts print as at d423d15; recorded decimals are never rounded; null is not recorded."""
    doc = copy.deepcopy(dataset.row_snapshot(complete_dev_row(dataset)))
    view0 = SnapshotView(doc)
    vs_id = view0.latest("Vitals").item_id
    vs = next(it for it in doc["items"] if it["item_id"] == vs_id)
    vs.update(hr=83.5, spo2=94.5, temp_c=37.0, rr=16, sbp=120.0, dbp=None)
    view = SnapshotView(doc)
    line = next(x.text for x in engine.summary(view, view.fields()) if x.text.startswith("Latest vital signs"))
    assert "HR 83.5/min" in line and "SpO2 94.5%" in line and "temperature 37.0 °C" in line
    assert "RR 16/min" in line and "BP 120/not recorded mmHg" in line
    assert ".0/min" not in line and "120.0" not in line


def test_fixture_trees_match_recorded(dataset, heldout):
    v1 = json.loads((dataset.root / "manifest.json").read_text("utf-8"))
    h = json.loads((heldout / "manifest.json").read_text("utf-8"))
    assert v1["seed"] == 20260926 and h["seed"] == HELDOUT_SEED and h["heldout"] is True
    assert v1["tree_sha256"] == json.loads((S6 / "manifest_dev_0002.json").read_text("utf-8"))["dataset"]["version"]
    assert h["tree_sha256"] == json.loads((S6 / "manifest_test_0002.json").read_text("utf-8"))["dataset"]["version"]


# ----------------------------------------------------------------- the I2 block (A08, A09)


def _check_block(r) -> RedFlagScreening:
    block = r.red_flag_screening.model_dump(mode="json")
    x = RedFlagScreening.model_validate({k: v for k, v in block.items() if k != "summary"})
    assert x.rule_set_version == RF_110 == "rf-1.1.0"
    assert x.n_declared == 16 and x.n_evaluated + x.n_not_evaluated == 16
    assert x.n_fired == len(r.alerts)
    assert x.label == RULE_SET_LABELS[RF_110] and x.scope == CARE_SCREENING_SCOPE
    assert block["summary"] == x.summary()
    return x


def test_care_block_is_i2_screening(results, dataset, monkeypatch):
    for _name, _doc, r, _ in results:
        _check_block(r)
    doc = dataset.row_snapshot(dataset.rows[0])
    err, calls = run({**doc, "as_of": "not a time"})  # snapshot-error path
    assert err.status == "error" and calls == 0
    assert _check_block(err).status == "unavailable"
    monkeypatch.setattr(redflags, "evaluate", lambda snap: 1 / 0)  # unavailable path
    un, _ = run(doc, dataset.rows[0]["dp"])
    x = _check_block(un)
    assert x.status == "unavailable" and x.missing_inputs == ("Alerts",) and len(x.rules_not_evaluated) == 16


def test_care_block_version_mismatch_is_unavailable(dataset, monkeypatch):
    monkeypatch.setattr(redflags, "RULESET_VERSION", "rf-9.9.9")
    r, _ = run(dataset.row_snapshot(dataset.rows[0]), dataset.rows[0]["dp"])
    assert _check_block(r).status == "unavailable"


def test_care_scope_honest():
    s = CARE_SCREENING_SCOPE
    assert "rf-1.1.0" in s and "16 declared rules" in s and "not evaluated" in s and "unknown, not absent" in s
    assert "vitals and demographics only" in s and "transcript" in s
    assert s != RULE_SET_SCOPES[RF_110]
    assert not CLAIMS.search(s) and not OVERCLAIM.search(s)


def test_care_never_evaluated_without_symptoms(results):
    v1 = [r for name, _, r, _ in results if name == "v1"]
    assert len(v1) == 400 and sum(r.red_flag_screening.status == "evaluated" for r in v1) == 0


def test_care_never_no_red_flags_api(dataset, physician, monkeypatch):  # noqa: F811
    for split in ("dev", "test"):
        monkeypatch.setattr(router, "SPLIT", split)  # the API serves dev only; test is checked the same way
        listed = physician.get("/api/care/cases")
        assert listed.status_code == 200 and not OVERCLAIM.search(listed.text)
        n = 0
        for row in (r for r in dataset.rows if r["split"] == split):
            a = physician.post(f"/api/care/cases/{row['case_id']}/assess", json={"decision_point": row["dp"]})
            assert a.status_code == 201 and not OVERCLAIM.search(a.text), row
            g = physician.get(f"/api/care/assessments/{a.json()['assessment_id']}")
            assert g.status_code == 200 and not OVERCLAIM.search(g.text), row
            n += 1
        assert n > 0


# ----------------------------------------------------------------- stale vitals (A10)

NORMAL = {"hr": 80, "rr": 16, "sbp": 120, "dbp": 80, "spo2": 98, "temp_c": 36.8, "consciousness": "A"}
ABNORMAL = {"hr": 150, "rr": 30, "sbp": 85, "dbp": 130, "spo2": 88, "temp_c": 34.5, "consciousness": "V"}
ALERT = {"hr": "RF-HR", "rr": "RF-RR", "sbp": "RF-SBP", "dbp": None, "spo2": "RF-SPO2", "temp_c": "RF-TEMP",
         "consciousness": "RF-CONSC"}
# rf-1.1.0 rules (redflag_rules_v1.json) that cannot be decided without the vital when every other vital is normal
# and no symptom is known, written out independently of the code. RF-QSOFA stays decided (2 of 3 needed; the other
# two are normal); RF-ANAPH and RF-MENING are already not evaluated (symptoms) and gain the stale input.
NEEDS = {"hr": {"RF-HR"}, "rr": {"RF-RR"}, "sbp": {"RF-SBP", "RF-ANAPH"}, "dbp": set(), "spo2": {"RF-SPO2"},
         "temp_c": {"RF-TEMP", "RF-MENING"}, "consciousness": {"RF-CONSC"}}
KINDS = {"consciousness": ("avpu", "new_confusion")}
VITALS = list(NORMAL)


def _planted(dataset, vital: str, value, age_s: int) -> tuple[dict, datetime]:
    """Demographics + one fresh Vitals item (all normal, without ``vital``) + one Vitals item with ``vital`` only."""
    doc = copy.deepcopy(dataset.row_snapshot(next(r for r in dataset.rows if r["split"] == "dev")))
    demo = next(it for it in doc["items"] if it["data_type"] == "Demographics")
    vs = next(it for it in doc["items"] if it["data_type"] == "Vitals")
    as_of = datetime.fromisoformat(doc["as_of"])
    blank = {k: None for k in (*NORMAL, "new_confusion", "capillary_glucose_mg_dl")}

    def vitals(item_id: str, t: datetime, values: dict) -> dict:
        ts = t.isoformat()
        return {**vs, **blank, **values, "item_id": item_id, "event_time": ts, "observed_at": ts,
                "available_at_time": ts}

    read_at = as_of - timedelta(seconds=age_s)
    fresh = vitals("UT-INT2-VS-FRESH", as_of - timedelta(minutes=5), {k: v for k, v in NORMAL.items() if k != vital})
    doc["items"] = [demo, fresh, vitals("UT-INT2-VS-TEST", read_at, {vital: value})]
    return doc, read_at


def _reading(r, name):
    return next(x for x in r.red_flag_screening.readings if x["vital"] == name)


@pytest.mark.parametrize("vital", VITALS)
def test_care_stale_boundary(vital, dataset):
    fresh_doc, _ = _planted(dataset, vital, NORMAL[vital], WINDOW_S)
    at, _ = run(fresh_doc)
    s_at = at.red_flag_screening
    for name in KINDS.get(vital, (vital,)):
        x = _reading(at, name)
        assert x["fresh"] is True and x["age_min"] == 60 and x["item_id"] == "UT-INT2-VS-TEST"
    assert NEEDS[vital] - {"RF-ANAPH", "RF-MENING"} <= set(s_at.rules_evaluated)
    assert not at.alerts and not any("stale" in m for m in s_at.missing_inputs)

    stale_doc, read_at = _planted(dataset, vital, NORMAL[vital], WINDOW_S + 1)
    st, _ = run(stale_doc)
    s = st.red_flag_screening
    age = (WINDOW_S + 1) / 60
    for name in KINDS.get(vital, (vital,)):
        x = _reading(st, name)
        assert x["fresh"] is False and x["age_min"] == pytest.approx(age)
        assert (stale_input(f"vital.{name}", read_at, age) in s.missing_inputs) == bool(NEEDS[vital])
    assert NEEDS[vital] <= set(s.rules_not_evaluated)
    assert set(s.rules_evaluated) == set(s_at.rules_evaluated) - NEEDS[vital]
    assert s.status != "evaluated" and not st.alerts
    _check_block(st)


@pytest.mark.parametrize("vital", VITALS)
def test_care_stale_abnormal_still_alerts(vital, dataset):
    fresh_doc, _ = _planted(dataset, vital, ABNORMAL[vital], 5 * 60)
    stale_doc, _ = _planted(dataset, vital, ABNORMAL[vital], WINDOW_S + 1)
    fr, _ = run(fresh_doc)
    st, _ = run(stale_doc)
    assert [a.rule_id for a in st.alerts] == [a.rule_id for a in fr.alerts]
    assert [a.evidence_refs for a in st.alerts] == [a.evidence_refs for a in fr.alerts]
    for name in KINDS.get(vital, (vital,)):
        if any(x["vital"] == name for x in st.red_flag_screening.readings):
            assert _reading(st, name)["fresh"] is False
    if ALERT[vital] is None:  # dbp: no rf-1.1.0 rule reads it
        assert st.alerts == [] and st.escalation_required is False
        return
    assert ALERT[vital] in [a.rule_id for a in st.alerts]
    assert st.escalation_required is True
    assert ALERT[vital] in st.red_flag_screening.rules_evaluated
    _check_block(st)


# (case_id, as_of, vital) of every stale reading on v1 + held-out: SYNE-0002 T2 (train), SYNE-0053 T2 (test)
STALE_V1 = [("SYNE-0002", "2030-06-23T11:36:12+07:00", "new_confusion"),
            ("SYNE-0053", "2030-06-28T12:45:45+07:00", "avpu")]


def test_care_readings_listed(results):
    stale = []
    for _name, doc, r, _ in results:
        view = SnapshotView(doc)
        kinds = {f.kind.removeprefix("vital.") for f in redflag_adapter.to_facts(view) if f.kind.startswith("vital.")}
        reads = r.red_flag_screening.readings
        assert {x["vital"] for x in reads} == kinds
        for x in reads:
            assert x["read_at"] and x["age_min"] >= 0 and x["window_min"] == 60 and x["item_id"] in view.by_id
        stale += [(doc["case_id"], doc["as_of"], x["vital"]) for x in reads if not x["fresh"]]
    # v1 has two stale readings (an older consciousness fact that the latest Vitals item does not restate).
    # Neither leaves a non-fired rule undecidable, so D-int2-1 changes no output there (parity, A07).
    assert sorted(stale) == STALE_V1, sorted(stale)


# ----------------------------------------------------------------- one registry, MOCK label (A11)


def test_care_mock_label(results):
    assert mock_tasks.registered()["care.suggest.v1"] == "care-rules-1.1.0"
    suggested = [r for name, _, r, _ in results if name == "v1" and r.status == "suggested"]
    assert suggested and all(r.model_version == "mock-0.1.0+care-rules-1.1.0" for r in suggested)
    for _n, _d, r, _ in results:
        items = [*r.next_information, *r.pathway_options]
        assert not any(MOCK_LABEL in (x.code + x.display + x.display_th) for x in items)


# ----------------------------------------------------------------- synthetic only (A13)


@pytest.mark.parametrize("where", ["manifest", "item"])
def test_care_refuses_non_synthetic(where, dataset, physician, monkeypatch, tmp_path):  # noqa: F811
    calls = []
    monkeypatch.setattr(gateway_service, "invoke_audited", lambda *a, **k: calls.append(1))
    if where == "item":
        doc = copy.deepcopy(dataset.row_snapshot(dataset.rows[0]))
        doc["items"][0]["data_class"] = "real"
        r, n = run(doc, dataset.rows[0]["dp"])
        assert (r.status, r.reason, n) == ("error", "snapshot_item_not_synthetic", 0)
        return
    meta = json.loads((dataset.root / "manifest.json").read_text("utf-8"))
    row = next(r for r in dataset.rows if r["split"] == "dev")
    for variant in ({k: v for k, v in meta.items() if k != "data_class"}, {**meta, "data_class": "real"}):
        root = tmp_path / f"ds-{variant.get('data_class', 'none')}"
        root.mkdir()
        (root / "inputs").symlink_to(dataset.root / "inputs")
        (root / "manifest.json").write_text(json.dumps(variant), "utf-8")
        monkeypatch.setenv("CARE_DATASET", str(root))
        for resp in (physician.get("/api/care/cases"),
                     physician.post(f"/api/care/cases/{row['case_id']}/assess", json={"decision_point": row["dp"]})):
            assert (resp.status_code, resp.json()["detail"]) == (503, "dataset_not_synthetic")
        out = tmp_path / f"out-{variant.get('data_class', 'none')}"
        for extra in ([], ["--write-manifest", "--manifest", str(out / "m.json")]):
            rc = evaluate.main(["--split", "dev", "--dataset", str(root), "--out-dir", str(out), *extra])
            assert rc != 0
        assert not out.exists() or not any(out.rglob("*"))
    assert calls == []
