"""S3-A06 provenance, S3-A07 time validity, S3-A14 ClinicalText-like evidence."""

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import Settings
from app.gateway import build_provider
from app.voice.db import voice_facts, voice_turns
from app.voice.mock_rules import EXTRACTOR_VERSION
from casegraph.data import EVIDENCE_ADAPTER, Evidence

from .helpers import StubProvider, VoiceAPI, fixture, simulate_all


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _all_facts_and_turns(app):
    with app.state.engine.connect() as conn:
        facts = [dict(r) for r in conn.execute(select(voice_facts)).mappings().all()]
        turns = {r["turn_id"]: dict(r) for r in conn.execute(select(voice_turns)).mappings().all()}
    return facts, turns


def test_fact_provenance_complete(app, audit_rows):
    simulate_all(app)
    facts, turns = _all_facts_and_turns(app)
    assert len(facts) >= 60
    gw_rows = {r["details"]["request_sha256"]: r for r in audit_rows() if r["action"] == "gateway.invoke"}
    for f in facts:
        span = json.loads(f["span_turn_ids_json"])
        assert span, f
        span_turns = [turns[t] for t in span]
        assert all(t["session_id"] == f["session_id"] and t["speaker"] != "agent" for t in span_turns)
        assert _dt(f["available_at_time"]) == max(_dt(t["ended_at"]) for t in span_turns)
        assert _dt(f["event_time"]) == min(_dt(t["started_at"]) for t in span_turns)
        assert f["extractor"] == EXTRACTOR_VERSION
        row = gw_rows[f["request_sha256"]]
        assert (row["details"]["provider"], row["details"]["model_version"]) == (f["provider"], f["model_version"])
        assert row["details"]["status"] == "ok"


def test_fact_grounded_in_span(app):
    simulate_all(app)
    facts, turns = _all_facts_and_turns(app)
    known = [f for f in facts if f["state"] == "KNOWN"]
    assert known
    for f in known:
        cited = [turns[t]["text"].casefold() for t in json.loads(f["span_turn_ids_json"])]
        assert any(f["value_text"].casefold() in c for c in cited), f
        value = json.loads(f["value_json"])
        if isinstance(value, list):
            assert all(any(i.casefold() in c for c in cited) for i in value), f


@pytest.mark.parametrize("num", [1, 4, 14])
def test_facts_as_of(client, login, app, num):
    login("nurse1")
    (run,) = simulate_all(app, [fixture(num)])
    boundaries = [p["response"]["turn"]["ended_at"] for p in run.posts]
    boundaries.insert(0, run.start["session"]["created_at"])
    seen_values = []
    for b in boundaries:
        resp = client.get(f"/api/voice/sessions/{run.session_id}/facts", params={"as_of": b})
        assert resp.status_code == 200
        facts = resp.json()["facts"]
        assert all(_dt(f["available_at_time"]) <= _dt(b) for f in facts)
        assert len({f["field"] for f in facts}) == len(facts)  # latest version per field only
        seen_values.append({f["field"]: f["value"] for f in facts})
    assert seen_values[0] == {}
    if num == 4:  # duration P3D is visible before the correction turn ends, P4D after it
        durations = [v.get("onset_duration") for v in seen_values]
        assert "P3D" in durations and durations[-1] == "P4D"
        assert durations.index("P3D") < durations.index("P4D")
    latest = client.get(f"/api/voice/sessions/{run.session_id}/facts").json()["facts"]
    assert {f["field"]: f["value"] for f in latest} == seen_values[-1]
    assert client.get(f"/api/voice/sessions/{run.session_id}/facts", params={"as_of": "2026-01-01T00:00:00"}).status_code == 422


def test_extraction_sees_no_future_turns(app):
    mock = build_provider("mock", Settings())
    spy = StubProvider(lambda req: mock.invoke(req, "x" * 64))
    app.state.provider = spy
    runs = simulate_all(app, [fixture(n) for n in (1, 4, 5, 14)])
    posts = [p for r in runs for p in r.posts]
    assert len(spy.calls) == len(posts)
    for req, post in zip(spy.calls, posts):
        current_end = post["body"].ended_at
        turns = req.inputs["turns"]
        assert turns[-1]["turn_id"] == post["response"]["turn"]["turn_id"]
        assert all(_dt(t["ended_at"]) <= current_end for t in turns)
        assert set(req.inputs) == {"turns", "last_asked_field"}


TIME_CASES = {
    "reversed": lambda api: {"started_at": (api.cursor + timedelta(seconds=5)).isoformat(),
                             "ended_at": api.cursor.isoformat()},
    "out_of_order": lambda api: {"started_at": (api.cursor - timedelta(seconds=30)).isoformat(),
                                 "ended_at": (api.cursor - timedelta(seconds=28)).isoformat()},
    "future": lambda api: {"started_at": api.cursor.isoformat(),
                           "ended_at": (api.cursor + timedelta(minutes=5)).isoformat()},
}


@pytest.mark.parametrize("case", list(TIME_CASES))
def test_turn_time_validation(client, login, app, case):
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    api.turn("มีไข้ค่ะ")
    before = len(api.get().json()["turns"])
    override = TIME_CASES[case](api)
    api.clock.t = api.cursor + timedelta(seconds=10)
    resp = client.post(f"/api/voice/sessions/{api.sid}/turns",
                       json={"speaker": "patient", "text": "สามวันค่ะ", **override})
    assert resp.status_code == 422, resp.text
    assert len(api.get().json()["turns"]) == before


def test_s3_finish_evidence_loads(app):
    """i2 (C6): S3 finish evidence validates as casegraph.data types (VoiceIntakeFacts + IntakeTranscript).

    Replaces the s3 ``test_intake_evidence_validates_as_evidence_item`` (IntakeEvidence is retired).
    """
    runs = simulate_all(app)
    n = 0
    for run in runs:
        items = [EVIDENCE_ADAPTER.validate_python(i) for i in run.finish["evidence"]]
        assert all(isinstance(i, Evidence) for i in items)
        by_type = {i.data_type: i for i in items}
        assert set(by_type) <= {"VoiceIntakeFacts", "IntakeTranscript"} and len(items) == len(by_type)
        tx = by_type["IntakeTranscript"]
        turns = {t.turn_id: t for t in tx.turns}
        assert tx.available_at_time == max(t.ended_at for t in tx.turns)
        facts = by_type.get("VoiceIntakeFacts")
        for item in items:
            assert item.source == "voice_agent.cascade" and item.patient_ref.startswith("SYN-")
            assert item.data_class == "synthetic"
            assert item.provenance.startswith(f"voice_session/{run.session_id}/")
            n += 1
        if facts is not None:
            assert list(facts.missing_fields) == run.finish["missing_fields"]
            for f in facts.facts:
                assert f.available_at_time == max(turns[t].ended_at for t in f.span_turn_ids)
                assert f.request_sha256 and f.extractor
                assert f.available_at_time <= facts.available_at_time
    assert n > 15
