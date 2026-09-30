"""Slice v2a: ambient intake mode + DEF-E1R-001 (a)+(b). Synthetic text only, mock provider, offline."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.db import create_schema
from app.gateway import ProviderResult, build_provider
from app.voice import service
from app.voice.db import create_voice_schema, voice_extractions, voice_facts, voice_sessions, voice_turns
from app.voice.eval_ambient import expected_final, load_fixtures
from app.voice.intent_th import classify_turn
from app.voice.models import ASK_ORDER
from app.voice.simulate import simulate_ambient
from app.voice.utterances_th import UTTERANCES_TH
from casegraph.data import EVIDENCE_ADAPTER

from ..conftest import PASSWORDS
from .helpers import StubProvider, VoiceAPI, dict_keys_deep, nurse_ctx
from .test_intent_th import LEADING, QUESTIONS, SCREENING

AMBIENT_KEYS = {"kind", "field", "suggested_question_id", "suggested_question_th", "reason", "missing_fields"}
GUIDED_KEYS = {"action", "field", "utterance_id", "utterance_th", "reason", "missing_fields"}
HELD_KEYS = {"turn_id", "field", "state", "value", "span_turn_ids", "reason"}
SENTINEL = "SENTINEL-แอมเบียนต์-4b2d"


class AmbientAPI(VoiceAPI):
    """VoiceAPI for mode "ambient": turns are ASR text with an unknown speaker."""

    def start(self, ref: str = "SYN-V2A-T1", expect: int = 201, mode: str | None = "ambient"):
        self.clock.t = self.cursor
        body = {"patient_ref": ref, "data_class": "synthetic"} | ({"mode": mode} if mode else {})
        resp = self.c.post("/api/voice/sessions", json=body)
        assert resp.status_code == expect, resp.text
        if resp.status_code == 201:
            self.sid = resp.json()["session"]["session_id"]
        self.cursor += timedelta(seconds=1)
        return resp

    def turn(self, text: str, speaker: str = "unknown", **kw):  # type: ignore[override]
        return super().turn(text, speaker=speaker, source="asr", asr_model="fixture-text", **kw)


def _spy(app) -> StubProvider:
    mock = build_provider("mock", Settings())
    spy = StubProvider(lambda req: mock.invoke(req, "x" * 64))
    app.state.provider = spy
    return spy


def _ambient(client, login, app) -> AmbientAPI:
    login("nurse1")
    api = AmbientAPI(client, app)
    api.start()
    return api


def _rows(app, table, sid=None):
    with app.state.engine.connect() as conn:
        q = select(table)
        if sid is not None:
            q = q.where(table.c.session_id == sid)
        return [dict(r) for r in conn.execute(q).mappings().all()]


def _replays(app, fixtures=None):
    ctx = nurse_ctx(app)
    fixtures = fixtures or load_fixtures()
    return fixtures, [simulate_ambient(ctx, fx) for fx in fixtures]


def _actions(run):
    return [d["action"] for d in run.decisions]


# ---------------------------------------------------------------- A11 mode contract


def test_mode_default_and_validation(client, login, app):
    login("nurse1")
    guided = VoiceAPI(client, app)
    body = guided.start().json()
    assert body["session"]["mode"] == "guided" and set(body["next_action"]) == GUIDED_KEYS
    for bad in ("x", "AMBIENT", "", None, 1):
        resp = client.post("/api/voice/sessions", json={"patient_ref": "SYN-V2A-X", "data_class": "synthetic",
                                                        "mode": bad})
        assert resp.status_code == 422, bad
    api = AmbientAPI(client, app)
    start = api.start().json()
    turn = api.turn("มีไข้ค่ะ").json()
    got = api.get().json()
    fin = api.finish().json()
    for payload in (start, turn, got, fin):
        assert payload["session"]["mode"] == "ambient"
        assert payload["session"]["chief_complaint_conflict"] is False
    assert set(start["next_action"]) == AMBIENT_KEYS


def test_mode_immutable(client, login, app):
    api = _ambient(client, login, app)
    engine = app.state.engine
    for stmt in ("UPDATE voice_sessions SET mode = 'guided'", "UPDATE voice_sessions SET mode = NULL"):
        with pytest.raises(DBAPIError, match="only voice_sessions.status"):
            with engine.begin() as conn:
                conn.execute(text(stmt))
    with engine.begin() as conn:
        conn.execute(text("UPDATE voice_sessions SET status = 'active'"))
    assert api.get().json()["session"]["mode"] == "ambient"


PRE_V2A = [
    """CREATE TABLE voice_sessions (session_id VARCHAR(32) PRIMARY KEY, patient_ref VARCHAR(64) NOT NULL,
       data_class VARCHAR(16) NOT NULL, created_at VARCHAR(40) NOT NULL, created_by INTEGER NOT NULL,
       status VARCHAR(16) NOT NULL)""",
    """CREATE TABLE voice_extractions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id VARCHAR(32) NOT NULL,
       turn_id VARCHAR(32) NOT NULL, status VARCHAR(16) NOT NULL, reason VARCHAR(64),
       provider VARCHAR(64) NOT NULL, model_version VARCHAR(128) NOT NULL, request_sha256 VARCHAR(64) NOT NULL,
       latency_ms VARCHAR(32) NOT NULL)""",
    """CREATE TRIGGER voice_sessions_fixed_cols BEFORE UPDATE OF session_id, patient_ref, data_class, created_at,
       created_by ON voice_sessions BEGIN SELECT RAISE(ABORT, 'only voice_sessions.status is mutable'); END""",
    """INSERT INTO voice_sessions VALUES ('old1', 'SYN-OLD', 'synthetic', '2026-01-01T00:00:00+00:00', 1, 'active')""",
]


def test_voice_schema_upgrade_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pre_v2a.db'}")
    with engine.begin() as conn:
        for stmt in PRE_V2A:
            conn.execute(text(stmt))
    create_schema(engine)
    create_voice_schema(engine)
    create_voice_schema(engine)  # idempotent
    insp = inspect(engine)
    assert "mode" in {c["name"] for c in insp.get_columns("voice_sessions")}
    assert "held_json" in {c["name"] for c in insp.get_columns("voice_extractions")}
    with engine.connect() as conn:
        row = conn.execute(select(voice_sessions)).mappings().one()
        assert service._mode(row) == "guided"  # an existing row without a mode reads as guided
        assert service._session_payload(row, [], False)["mode"] == "guided"
    with pytest.raises(DBAPIError, match="only voice_sessions.status"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE voice_sessions SET mode = 'ambient'"))
    engine.dispose()


def test_ambient_no_agent_turns(app):
    fixtures, runs = _replays(app)
    sids = {r.session_id for r in runs}
    speakers = [t["speaker"] for t in _rows(app, voice_turns) if t["session_id"] in sids]
    assert len(speakers) == sum(len(fx["turns"]) for fx in fixtures) and set(speakers) == {"unknown"}
    for run in runs:  # nothing speakable anywhere in the ambient responses
        for payload in [run.start, *(p["response"] for p in run.posts), run.finish]:
            keys = dict_keys_deep(payload)
            assert "utterance_th" not in keys and "action" not in keys


# ---------------------------------------------------------------- A04 nurse questions


@pytest.mark.parametrize(("field", "q"), [(f, t) for f, ts in QUESTIONS.items() for t in ts])
def test_question_turn_no_facts_no_gateway(client, login, app, audit_rows, field, q):
    api = _ambient(client, login, app)
    before = len(audit_rows())
    body = api.turn(q).json()
    rows = audit_rows()[before:]
    assert body["new_facts"] == [] and not [r for r in rows if r["action"] == "gateway.invoke"]
    (add,) = [r for r in rows if r["action"] == "voice.turn.add"]
    assert (add["details"]["question_field"], add["details"]["mode"], add["details"]["extraction"]) == (
        field, "ambient", "skipped")
    (ext,) = _rows(app, voice_extractions, api.sid)
    assert (ext["status"], ext["reason"]) == ("skipped", "nurse_question")
    statuses = {s["field"]: s for s in body["field_statuses"]}
    assert statuses[field]["times_asked"] == 1 and statuses[field]["status"] == "MISSING"
    assert body["extraction_error"] is False


def test_guided_nurse_question_no_gateway(client, login, app, audit_rows):
    login("nurse1")
    api = VoiceAPI(client, app)
    api.start()
    before = len(audit_rows())
    body = api.turn("แพ้ยาอะไรไหมคะ", speaker="nurse").json()
    assert body["new_facts"] == [] and set(body["next_action"]) == GUIDED_KEYS
    assert not [r for r in audit_rows()[before:] if r["action"] == "gateway.invoke"]
    # unknown in guided mode is treated like a patient turn: no classifier, extracted as usual
    assert api.turn("มาด้วยอาการอะไรคะ", speaker="unknown").json()["extraction_error"] is False
    assert len([r for r in audit_rows()[before:] if r["action"] == "gateway.invoke"]) == 1


@pytest.mark.parametrize("q", LEADING)
def test_leading_question_no_facts(client, login, app, q):
    api = _ambient(client, login, app)
    assert api.turn(q).json()["new_facts"] == []
    assert _rows(app, voice_facts, api.sid) == []


# ---------------------------------------------------------------- A03 merged segments / B2 window


@pytest.mark.parametrize("text_", ["แพ้ยาอะไรไหมคะ ไม่แพ้ค่ะ", "แพ้ยาอะไรไหมคะไม่แพ้ค่ะ"])
@pytest.mark.parametrize("mode", ["ambient", "guided"])
def test_merged_segment_allergy_never_present_or_false_none(client, login, app, text_, mode):
    login("nurse1")
    api = AmbientAPI(client, app)
    api.start(mode=mode)
    body = api.turn(text_, speaker="unknown" if mode == "ambient" else "nurse").json()
    allergy = [f for f in _rows(app, voice_facts, api.sid) if f["field"] == "allergy_status"]
    assert all(f["state"] != "KNOWN" for f in allergy), allergy  # never present, never none
    assert {h["reason"] for h in body["held_facts"]} <= {"merged_segment_allergy_negative"}
    assert body["allergy_conflict"] is False


def test_merged_segment_duration(client, login, app):
    api = _ambient(client, login, app)
    body = api.turn("เป็นมากี่วันแล้วคะ สองวันค่ะ").json()
    assert [(f["field"], f["value"]) for f in body["new_facts"]] == [("onset_duration", "P2D")]
    statuses = {s["field"]: s for s in body["field_statuses"]}
    assert statuses["onset_duration"]["times_asked"] == 1


def test_stale_window_closes(client, login, app):
    """B2(ii) with the current turn counted: the window covers the first turn after the question only."""
    spy = _spy(app)
    api = _ambient(client, login, app)
    api.turn("มีโรคประจำตัวไหมคะ")
    api.turn("เบาหวานค่ะ")
    api.turn("เดี๋ยววัดความดันนะคะ")
    assert [c.inputs["last_asked_field"] for c in spy.calls] == ["relevant_history", None]
    facts = {f["field"]: f["value"] for f in api.get().json()["facts"]}
    assert facts["relevant_history"] == ["เบาหวาน"]


def test_stale_window_closes_after_merged_turn(client, login, app):
    """A merged question + answer turn is the first window turn, so the next remark is outside the window."""
    spy = _spy(app)
    api = _ambient(client, login, app)
    api.turn("มีโรคประจำตัวไหมคะ เบาหวานค่ะ")
    api.turn("เดี๋ยววัดความดันนะคะ")
    assert [c.inputs["last_asked_field"] for c in spy.calls] == ["relevant_history", None]
    facts = {f["field"]: f["value"] for f in api.get().json()["facts"]}
    assert facts["relevant_history"] == ["เบาหวาน"]


@pytest.mark.parametrize("q", SCREENING)
def test_screening_question_no_facts(client, login, app, audit_rows, q):
    """A yes/no symptom or history question with no field intent is never recorded as a patient fact."""
    api = _ambient(client, login, app)
    before = len(audit_rows())
    body = api.turn(q).json()
    assert body["new_facts"] == [] and _rows(app, voice_facts, api.sid) == []
    assert not [r for r in audit_rows()[before:] if r["action"] == "gateway.invoke"]
    (ext,) = _rows(app, voice_extractions, api.sid)
    assert (ext["status"], ext["reason"]) == ("skipped", "nurse_question")
    statuses = {s["field"]: s for s in body["field_statuses"]}
    assert all(s["status"] == "MISSING" and s["times_asked"] == 0 for s in statuses.values())
    assert (body["next_action"]["kind"], body["next_action"]["field"]) == ("prompt_nurse", "chief_complaint")


def test_screening_question_does_not_become_chief_complaint(client, login, app):
    api = _ambient(client, login, app)
    for t in ("มีไข้ไหมคะ", "ไม่มีค่ะ", "แล้วมาด้วยอาการอะไรคะ", "ปวดท้องค่ะ"):
        body = api.turn(t).json()
    assert body["chief_complaint_conflict"] is False and body["held_facts"] == []
    got = api.get().json()
    assert {f["field"]: f["value"] for f in got["facts"]} == {"chief_complaint": "abdominal_pain"}
    assert got["held_facts"] == []


@pytest.mark.parametrize("turns", [
    ["แพ้ยาอะไรไหมคะ", "ไม่แพ้ยาค่ะ", "อ้อ แพ้เพนิซิลลินด้วย จะเป็นอะไรไหมคะ"],
    ["ไม่แพ้ยาค่ะ", "อ้อ แพ้เพนิซิลลินด้วย จะเป็นอะไรไหมคะ"],
    ["แพ้ยาอะไรไหมคะ", "ไม่แพ้ยาค่ะ", "อ๋อ จริงๆเคยแพ้ยาซัลฟาค่ะ ทานยาอะไรประจำไหมคะ"],
    ["ไม่แพ้ยาค่ะ", "อ๋อ จริงๆเคยแพ้ยาซัลฟาค่ะ ทานยาอะไรประจำไหมคะ"],
    ["แพ้ยาอะไรไหมคะ", "แพ้ยาซัลฟาค่ะ ทานยาอะไรประจำไหมคะ"],
    ["แพ้เพนิซิลลินค่ะ ทานยาอะไรประจำไหมคะ"],
])
def test_allergy_before_question_is_kept(client, login, app, turns):
    """An allergy disclosed before a question in the same segment is extracted, never lost, and a later
    disclosure replaces an earlier 'none' (the allergy is never left as a false none)."""
    api = _ambient(client, login, app)
    for t in turns:
        api.turn(t)
    facts = {f["field"]: f for f in api.get().json()["facts"]}
    assert (facts["allergy_status"]["state"], facts["allergy_status"]["value"]) == ("KNOWN", "present")
    assert facts["allergens"]["value"] and "allergy_status" not in api.get().json()["next_action"]["missing_fields"]


def test_answer_before_question_uses_the_earlier_window(client, login, app):
    spy = _spy(app)
    api = _ambient(client, login, app)
    api.turn("แพ้ยาอะไรไหมคะ")
    api.turn("แพ้ยาซัลฟาค่ะ ทานยาอะไรประจำไหมคะ")  # the answer belongs to the allergy question
    api.turn("เมทฟอร์มินค่ะ")  # the answer to the medication question
    assert [c.inputs["last_asked_field"] for c in spy.calls] == ["allergy_status", "current_medications"]
    assert spy.calls[0].inputs["turns"][-1]["text"] == "แพ้ยาซัลฟาค่ะ"
    facts = {f["field"]: f["value"] for f in api.get().json()["facts"]}
    assert facts["allergens"] == ["ซัลฟา"] and facts["current_medications"] == ["เมทฟอร์มิน"]


def test_merged_negative_before_question_is_held(client, login, app):
    """'none' said in the same segment as a question stays held (never recorded), so the nurse asks again."""
    api = _ambient(client, login, app)
    api.turn("แพ้ยาอะไรไหมคะ")
    body = api.turn("ไม่แพ้ยาค่ะ ทานยาอะไรประจำไหมคะ").json()
    assert [(h["field"], h["reason"]) for h in body["held_facts"]] == [
        ("allergy_status", "merged_segment_allergy_negative")]
    assert not [f for f in _rows(app, voice_facts, api.sid) if f["field"] == "allergy_status"]
    assert "allergy_status" in body["next_action"]["missing_fields"]


def test_scalar_window_closes_after_fact(client, login, app):
    spy = _spy(app)
    api = _ambient(client, login, app)
    api.turn("เป็นมากี่วันแล้วคะ สองวันค่ะ")  # merged: fact written inside the window
    api.turn("ค่ะ")
    assert [c.inputs["last_asked_field"] for c in spy.calls] == ["onset_duration", None]


def test_volunteered_facts_without_window(client, login, app):
    api = _ambient(client, login, app)
    body = api.turn("เจ็บคอ ไอด้วยค่ะ เป็นมาสองวันแล้ว").json()
    assert {f["field"]: f["value"] for f in body["new_facts"]} == {"chief_complaint": "sore_throat",
                                                                  "onset_duration": "P2D"}


# ---------------------------------------------------------------- A05 next action


def test_ambient_next_action_keys(app):
    _, runs = _replays(app)
    for run in runs:
        for action in _actions(run):
            assert set(action) == AMBIENT_KEYS


def test_ambient_prompt_only_missing(app):
    _, runs = _replays(app)
    for run in runs:
        left: set[str] = set()
        for d in run.decisions:
            a, st = d["action"], d["statuses"]
            left |= {f for f in ASK_ORDER if st[f]["status"] != "MISSING"}
            if a["kind"] == "prompt_nurse":
                assert st[a["field"]]["status"] == "MISSING" and a["field"] not in left
                assert a["field"] == a["missing_fields"][0]


def test_ambient_prompt_allowlist(app):
    _, runs = _replays(app)
    n = 0
    for run in runs:
        for d in run.decisions:
            a = d["action"]
            if a["kind"] != "prompt_nurse":
                assert a["suggested_question_id"] is None and a["suggested_question_th"] is None
                continue
            n += 1
            prefix = "ask" if d["statuses"][a["field"]]["times_asked"] == 0 else "reask"
            assert a["suggested_question_id"] == f"{prefix}.{a['field']}"
            assert a["suggested_question_th"] == UTTERANCES_TH[a["suggested_question_id"]]
    assert n > 50
    with pytest.raises(KeyError):
        service.utterance("ask.diagnosis")


def test_ambient_final_action_matches_gold(app):
    fixtures, runs = _replays(app)
    matched = {"dev": 0, "heldout": 0}
    for fx, run in zip(fixtures, runs):
        final, exp = _actions(run)[-1], expected_final(fx)
        split = "heldout" if "heldout" in fx["scenario_tags"] else "dev"
        matched[split] += (final["kind"], final["field"]) == (exp["kind"], exp["field"])
        reason = {"prompt_nurse": "finished_by_nurse"}.get(final["kind"], final["reason"])
        assert run.finish["handoff_reason"] == reason
    assert matched["dev"] == 10 and matched["heldout"] >= 4


# ---------------------------------------------------------------- A06 red flag


def test_ambient_attention_preempts(client, login, app):
    fixtures, runs = _replays(app, [fx for fx in load_fixtures() if fx["dialogue_id"][-2:] in ("06", "09", "12")])
    for fx, run in zip(fixtures, runs):
        hits = [i for i, p in enumerate(run.posts) if p["response"]["nurse_attention"]]
        assert hits, fx["dialogue_id"]
        for i, p in enumerate(run.posts):
            a = p["response"]["next_action"]
            if i >= hits[0]:
                assert (a["kind"], a["reason"]) == ("handoff", "nurse_attention_phrase")
            else:
                assert a["kind"] != "handoff"
        assert run.finish["handoff_reason"] == "nurse_attention_phrase"
    api = _ambient(client, login, app)
    body = api.turn("เมื่อกี้ลูกชักด้วยค่ะ").json()
    assert body["nurse_attention"] is True and body["session"]["nurse_attention"] is True
    assert (body["next_action"]["kind"], body["next_action"]["reason"]) == ("handoff", "nurse_attention_phrase")
    assert body["next_action"]["missing_fields"] == list(ASK_ORDER)
    assert api.turn("มีไข้ค่ะ").json()["next_action"]["kind"] == "handoff"  # sticky
    assert api.get().json()["next_action"]["reason"] == "nurse_attention_phrase"


def test_ambient_question_with_red_flag_still_fires(client, login, app, audit_rows):
    api = _ambient(client, login, app)
    before = len(audit_rows())
    body = api.turn("เคยป่วยเป็นโรคลมชักมาก่อนไหมคะ").json()
    (add,) = [r for r in audit_rows()[before:] if r["action"] == "voice.turn.add"]
    assert add["details"]["question_field"] == "relevant_history"
    assert body["nurse_attention"] is True and body["new_facts"] == []
    assert (body["next_action"]["kind"], body["next_action"]["reason"]) == ("handoff", "nurse_attention_phrase")


def test_ambient_gateway_failure_fails_safe(client, login, app):
    app.state.provider = StubProvider(lambda req: ProviderResult(status="error", model_version="stub-1",
                                                                 reason="provider_timeout"))
    api = _ambient(client, login, app)
    body = api.turn("มีไข้ค่ะ").json()
    assert body["new_facts"] == [] and body["extraction_error"] is True
    assert (body["next_action"]["kind"], body["next_action"]["reason"]) == ("handoff", "extraction_unavailable")
    assert api.turn("แพ้ยาอะไรไหมคะ").json()["next_action"]["reason"] == "extraction_unavailable"  # sticky
    assert _rows(app, voice_facts, api.sid) == []
    assert api.finish().json()["handoff_reason"] == "extraction_unavailable"


# ---------------------------------------------------------------- A07 DEF-E1R-001


def test_def_e1r_001_last_asked_reset(client, login, app):
    spy = _spy(app)
    login("nurse1")
    guided = VoiceAPI(client, app)
    guided.start()
    guided.turn("ลูกชักค่ะ")  # nurse-attention handoff (agent turn with no field)
    guided.turn("ปวดข้อค่ะ")
    guided.turn("แพ้ยาอะไรไหมคะ", speaker="nurse")  # classified nurse question: no gateway call
    guided.turn("แพ้เพนิซิลลินค่ะ")
    assert [c.inputs["last_asked_field"] for c in spy.calls] == ["chief_complaint", None, "allergy_status"]
    spy.calls.clear()
    ambient = AmbientAPI(client, app)
    ambient.start()
    ambient.turn("มาด้วยอาการอะไรคะ")
    ambient.turn("ลูกชักค่ะ")  # the attention turn keeps the pre-attention window
    ambient.turn("ปวดข้อค่ะ")
    assert [c.inputs["last_asked_field"] for c in spy.calls] == ["chief_complaint", None]


def _check_cc_held(app, api, resp, kept: str, held: str) -> None:
    assert resp["chief_complaint_conflict"] is True and resp["session"]["chief_complaint_conflict"] is True
    assert [(h["field"], h["value"], h["reason"]) for h in resp["held_facts"]] == [
        ("chief_complaint", held, "chief_complaint_conflict")]
    got = api.get().json()
    assert got["chief_complaint_conflict"] is True
    cc_held = [h for h in got["held_facts"] if h["reason"] == "chief_complaint_conflict"]
    assert len(cc_held) == 1 and set(cc_held[0]) == HELD_KEYS and cc_held[0]["value"] == held
    assert {f["field"]: f["value"] for f in got["facts"]}["chief_complaint"] == kept
    rows = [f for f in _rows(app, voice_facts, api.sid) if f["field"] == "chief_complaint"]
    assert [json.loads(r["value_json"]) for r in rows] == [kept] and rows[0]["supersedes_fact_id"] is None
    ext = [e for e in _rows(app, voice_extractions, api.sid) if e["held_json"]]
    assert ext and ext[-1]["reason"] == "chief_complaint_conflict"


def test_def_e1r_001_cc_conflict_held(client, login, app, audit_rows):
    login("nurse1")
    guided = VoiceAPI(client, app)
    guided.start()
    guided.turn("มีไข้ค่ะ")
    guided.turn("ลูกชักค่ะ")
    resp = guided.turn("ปวดหัวค่ะ").json()
    _check_cc_held(app, guided, resp, "fever", "headache")
    ambient = AmbientAPI(client, app)
    ambient.start()
    ambient.turn("มีไข้ค่ะ")
    before = len(audit_rows())
    resp = ambient.turn("ตอนนี้ปวดหัวค่ะ").json()
    _check_cc_held(app, ambient, resp, "fever", "headache")
    (add,) = [r for r in audit_rows()[before:] if r["action"] == "voice.turn.add"]
    assert [set(h) for h in add["details"]["held"]] == [{"field", "state", "value", "span_turn_ids", "reason"}]
    # The same value again is deduplicated, not held.
    same = ambient.turn("ไข้ค่ะ").json()
    assert same["held_facts"] == [] and same["new_facts"] == []
    assert ambient.finish().json()["chief_complaint_conflict"] is True


@pytest.mark.parametrize("mode", ["guided", "ambient"])
def test_def_e1r_001_syne0196_shape(client, login, app, mode):
    """Red-flag turn 1 -> nurse drug-reaction question -> NSAID allergy answer: the CC is not changed."""
    login("nurse1")
    api = AmbientAPI(client, app)
    api.start(mode=mode)
    patient, nurse = ("unknown", "unknown") if mode == "ambient" else ("patient", "nurse")
    first = api.turn("จู่ ๆ ก็ปากเบี้ยวและแขนอ่อนแรงข้างเดียวค่ะ", speaker=patient).json()
    assert first["nurse_attention"] is True
    api.turn("เคยมีอาการผิดปกติหลังใช้ยาไหมคะ", speaker=nurse)
    api.turn("แพ้ยาแก้ปวดข้อกลุ่มเอ็นเสดค่ะ", speaker=patient)
    facts = {f["field"]: f["value"] for f in api.get().json()["facts"]}
    assert facts["chief_complaint"] == "fatigue" and facts["allergy_status"] == "present"
    assert "current_medications" not in facts
    cc_rows = [f for f in _rows(app, voice_facts, api.sid) if f["field"] == "chief_complaint"]
    assert len(cc_rows) == 1


# ---------------------------------------------------------------- A08 gateway + audit


def test_ambient_gateway_audit_counts(app, audit_rows):
    before = len(audit_rows())
    fixtures, runs = _replays(app)
    rows = audit_rows()[before:]
    gw = [r for r in rows if r["action"] == "gateway.invoke"]
    texts = [t["text"] for fx in fixtures for t in fx["turns"]]
    pure_questions = sum(1 for t in texts if (c := classify_turn(t)) and not c.remainder)
    ext = [e for e in _rows(app, voice_extractions)]
    assert len(gw) == len(texts) - pure_questions == sum(1 for e in ext if e["status"] in ("ok", "error"))
    assert sum(1 for e in ext if e["status"] == "skipped") == pure_questions > 60
    adds = [r for r in rows if r["action"] == "voice.turn.add"]
    assert len(adds) == len(texts) and all(r["details"]["mode"] == "ambient" for r in adds)
    skipped = [r for r in adds if r["details"]["extraction"] == "skipped"]
    assert len(skipped) == pure_questions and all(r["details"]["question_field"] in ASK_ORDER for r in skipped
                                                  if r["details"]["question_field"] is not None)
    # the only field-less pure question in the fixtures is th_ambient_07 t14 "ขอไปเข้าห้องน้ำก่อนได้ไหมครับ"
    assert sum(1 for r in skipped if r["details"]["question_field"] is None) == sum(
        1 for t in texts if (c := classify_turn(t)) and not c.remainder and c.field is None) >= 1
    assert all(r["details"]["request_sha256"] is None for r in skipped)


def test_ambient_audit_no_transcript_text(client, login, app, audit_rows):
    api = _ambient(client, login, app)
    api.turn(f"มีไข้ค่ะ {SENTINEL}")
    api.turn(f"แพ้ยาอะไรไหมคะ {SENTINEL}")
    api.turn(f"ตอนนี้ปวดหัวค่ะ {SENTINEL}")  # held CC conflict is audited without value_text
    api.finish()
    _, runs = _replays(app)
    dump = "\n".join(repr(r) for r in audit_rows())
    assert SENTINEL not in dump
    for run in runs:
        for post in run.posts:
            if len(post["body"].text) >= 6:
                assert post["body"].text not in dump, post["body"].text


def test_ambient_gateway_inputs_unchanged(app):
    spy = _spy(app)
    _replays(app)
    assert len(spy.calls) > 60
    for req in spy.calls:
        assert req.task == "voice.intake_extract" and req.data_class == "synthetic"
        assert set(req.inputs) == {"turns", "last_asked_field"}
        assert req.inputs["last_asked_field"] in (None, *ASK_ORDER)


# ---------------------------------------------------------------- A12 evidence


def test_ambient_finish_evidence(app):
    _, runs = _replays(app)
    for run in runs:
        items = {i.data_type: i for i in (EVIDENCE_ADAPTER.validate_python(e) for e in run.finish["evidence"])}
        tx = items["IntakeTranscript"]
        assert {t.speaker for t in tx.turns} == {"unknown"}
        ends = {t.turn_id: t.ended_at for t in tx.turns}
        for f in items["VoiceIntakeFacts"].facts:
            assert f.available_at_time == max(ends[t] for t in f.span_turn_ids)


def test_ambient_facts_as_of(client, login, app):
    login("nurse1")
    _, runs = _replays(app, [fx for fx in load_fixtures() if fx["dialogue_id"][-2:] in ("04", "05", "14")])
    for run in runs:
        for post in run.posts:
            b = post["response"]["turn"]["ended_at"]
            facts = client.get(f"/api/voice/sessions/{run.session_id}/facts", params={"as_of": b}).json()["facts"]
            assert all(datetime.fromisoformat(f["available_at_time"]) <= datetime.fromisoformat(b) for f in facts)


# ---------------------------------------------------------------- A14 RBAC / A01 guided keys


def _switch(client, username):
    client.post("/api/auth/logout")
    if username:
        assert client.post("/api/auth/login",
                           json={"username": username, "password": PASSWORDS[username]}).status_code == 200


def test_voice_auth_matrix_ambient(client, login, app):
    api = _ambient(client, login, app)
    sid = api.sid
    body = {"speaker": "unknown", "text": "มีไข้ค่ะ", "started_at": api.cursor.isoformat(),
            "ended_at": api.cursor.isoformat(), "source": "asr", "asr_model": "fixture-text"}
    calls = [
        lambda: client.post("/api/voice/sessions", json={"patient_ref": "SYN-V2A-M", "data_class": "synthetic",
                                                         "mode": "ambient"}),
        lambda: client.post(f"/api/voice/sessions/{sid}/turns", json=body),
        lambda: client.get(f"/api/voice/sessions/{sid}"),
        lambda: client.get(f"/api/voice/sessions/{sid}/facts"),
        lambda: client.post(f"/api/voice/sessions/{sid}/finish"),
    ]
    for who, expected in (("physician1", 403), ("pharmacist1", 403), (None, 401)):
        _switch(client, who)
        assert [c().status_code for c in calls] == [expected] * 5, who
    with app.state.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(voice_turns)).scalar_one() == 0


def test_guided_next_action_keys_unchanged(client, login, app):
    login("nurse1")
    api = VoiceAPI(client, app)
    responses = [api.start().json(), api.turn("มีไข้ค่ะ").json(), api.turn("ลูกชักค่ะ").json()]
    responses.append(api.get().json())
    for r in responses:
        assert set(r["next_action"]) == GUIDED_KEYS
