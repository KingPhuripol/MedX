"""Slice i2, condition C1 (S2r HIGH): per-vital freshness windows at the Red-flag node (I2-A09), and
same-timestamp conflicts shown at the Human Checkpoint (C4, graph side). Synthetic, offline, mock only.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.triage.models import VITAL_NAMES
from casegraph.compiler import build_snapshot, compile_graph
from casegraph.data import Demographics, Vitals
from casegraph.executor import PENDING_KEY, Executor
from casegraph.store import MemoryStateStore, OutputStore
from casegraph.triage_bridge import FRESHNESS_PATH, load_freshness, rule_kinds

from .fixtures import DAY, H, _common

T = DAY + 12 * H
PID = "SYN-I2-FRESH"
ONE_S = timedelta(seconds=1)
# Normal values for every S4 vital (no rf-1.1.0 threshold hit). Keys are Vitals fields.
NORMAL = {"hr": 80.0, "rr": 16.0, "sbp": 124.0, "dbp": 78.0, "spo2": 98.0, "temp_c": 36.8,
          "capillary_glucose_mg_dl": 100.0, "on_oxygen": False}
# vital -> (Vitals fields for a reading of it, the rf-1.1.0 rule that cannot be evaluated without it)
READING = {
    "hr": ({"hr": 80.0}, "RF-HR"), "rr": ({"rr": 16.0}, "RF-RR"), "sbp": ({"sbp": 124.0}, "RF-SBP"),
    "dbp": ({"dbp": 78.0}, None),  # no rf-1.1.0 rule reads dbp: freshness is reported, no rule depends on it
    "spo2": ({"spo2": 98.0}, "RF-SPO2"), "temp_c": ({"temp_c": 36.8}, "RF-TEMP"),
    "capillary_glucose_mg_dl": ({"capillary_glucose_mg_dl": 100.0}, "RF-HYPOGLY"),
    "on_oxygen": ({"on_oxygen": False}, None),  # feeds only the aggregate rule, which is false (not unknown) at score 0
    "avpu": ({"consciousness": "A"}, "RF-CONSC"), "new_confusion": ({"new_confusion": False}, "RF-CONSC"),
}


def _demo(t=T):
    return Demographics(**_common(PID, "fr-demo", t - 2 * H, t - 2 * H), age_years=40, sex="male")


def _run(env, items, when=T):
    ex = Executor(env.gateways, OutputStore(), MemoryStateStore())  # one version per run (no GraphVersionExists)
    return ex.run_sync(compile_graph(build_snapshot(items, when)))


def _base_without(vital: str) -> Vitals:
    """A fresh reading (at T) of every other vital, so only ``vital`` can be stale."""
    values = {k: v for k, v in NORMAL.items() if k != vital}
    if vital != "avpu":
        values["consciousness"] = "A"
    if vital != "new_confusion":
        values["new_confusion"] = False
    return Vitals(**_common(PID, "fr-base", T, T), **values)


def _screen(graph):
    return graph.node("red_flag").output["Alerts"]


def test_freshness_config_cited():
    doc = json.loads(FRESHNESS_PATH.read_text(encoding="utf-8"))
    fresh = load_freshness()
    assert fresh.label == doc["label"] == "PROPOSED — pending clinical sign-off (D1)"
    assert set(fresh.windows_min) == set(VITAL_NAMES)  # every S4 vital has a window
    for vital in VITAL_NAMES:
        assert fresh.windows_min[vital] > 0
        assert "RCP NEWS2 (2017)" in fresh.sources[vital] or "NEWS2" in fresh.sources[vital], vital
    assert "D-I2-1" in doc["decision"]


@pytest.mark.parametrize("vital", VITAL_NAMES)
def test_vital_freshness_boundary(env, vital):
    window = timedelta(minutes=load_freshness().windows_min[vital])
    fields, rule = READING[vital]
    needs = {rid for rid, kinds in rule_kinds().items() if f"vital.{vital}" in kinds}
    for age, fresh in ((window, True), (window + ONE_S, False)):
        read_at = T - age
        reading = Vitals(**_common(PID, f"fr-{vital}", read_at, read_at), **fields)
        graph = _run(env, [_demo(), _base_without(vital), reading])
        alerts = _screen(graph)
        info = next(r for r in alerts["readings"] if r["vital"] == vital)
        assert (info["fresh"], info["item_id"]) == (fresh, f"fr-{vital}")
        assert info["read_at"] == read_at.isoformat().replace("+00:00", "Z") or info["read_at"] == read_at.isoformat()
        assert info["age_min"] == pytest.approx(age.total_seconds() / 60)
        results = {r["rule_id"]: r for r in alerts["rule_results"]}
        stale_inputs = [m for r in results.values() for m in r["missing_inputs"] if m.startswith(f"vital.{vital}:stale")]
        if fresh:
            assert stale_inputs == []
            if rule is not None:
                assert results[rule]["status"] == "evaluated" and results[rule]["fired"] is False
        else:
            expected = f"vital.{vital}:stale(read_at={read_at.isoformat()}, age_min={age.total_seconds() / 60:.2f})"
            if rule is not None:
                assert results[rule]["status"] == "not_evaluated"
                assert expected in results[rule]["missing_inputs"]
            # every rule that could not be evaluated because of it says so, with read time and age
            for rid in needs:
                if results[rid]["status"] == "not_evaluated":
                    assert expected in results[rid]["missing_inputs"], rid
            assert rule is None or expected in alerts["missing_inputs"]
            assert alerts["status"] != "evaluated"


def test_checkpoint_shows_reading_times(env):
    stamps = {k: T - timedelta(minutes=5 * (i + 1)) for i, k in enumerate(VITAL_NAMES)}
    items = [_demo()]
    for vital, (fields, _) in READING.items():
        items.append(Vitals(**_common(PID, f"ck-{vital}", stamps[vital], stamps[vital]), **fields))
    graph = _run(env, items)
    payload = graph.node("human_checkpoint").output[PENDING_KEY]
    readings = {r["vital"]: r for r in payload["vital_readings"]}
    assert set(readings) == set(VITAL_NAMES)  # 100% of vitals listed with read time and age
    for vital, r in readings.items():
        assert r["item_id"] == f"ck-{vital}" and r["fresh"] is True
        assert r["age_min"] == pytest.approx((T - stamps[vital]).total_seconds() / 60)
        assert r["read_at"].startswith(stamps[vital].isoformat()[:19])
    assert payload["red_flag_screening"]["readings"] == payload["vital_readings"]
    # the export carries the same block (checkpoint and export agree)
    assert [r.model_dump(mode="json") for r in graph.red_flag_screening.readings] == payload["vital_readings"]


def test_same_timestamp_conflict_shown_at_checkpoint(env):
    t = T - 10 * timedelta(minutes=1)
    items = [_demo(), _base_without("spo2"),
             Vitals(**_common(PID, "cf-a", t, t), spo2=98.0), Vitals(**_common(PID, "cf-b", t, t), spo2=88.0)]
    graph = _run(env, items)
    payload = graph.node("human_checkpoint").output[PENDING_KEY]
    (conflict,) = payload["conflicts"]
    assert conflict["kind"] == "vital.spo2" and conflict["resolution"] == "worst" and conflict["resolved_value"] == 88.0
    assert "RF-SPO2" in {a["rule_id"] for a in payload["alerts"]["alerts"]}
    assert payload["escalation"] is True and "urgent_red_flag" in payload["escalation_reasons"]
