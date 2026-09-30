"""V2D-D6: every validation failure of SPEC 3.2 gives the exact status + detail and makes zero case writes."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from .review_helpers import ALLERGY_CONFLICT_TURNS, UNCLEAR_TH, Intake, counts, hand_turns


def _dec(body: dict, field: str) -> dict:
    return next(d for d in body["decisions"] if d["field"] == field)


def _set(field: str, **kv):
    def mutate(body: dict, it: Intake) -> dict:
        _dec(body, field).update(kv)
        return body
    return mutate


def _decisions(fn):
    def mutate(body: dict, it: Intake) -> dict:
        body["decisions"] = fn(body["decisions"])
        return body
    return mutate


def _allergens(ds):
    return ds + [{"field": "allergens", "action": "confirm", "value": "x", "original": "x"}]


def _swap_allergens(ds):
    return [d if d["field"] != "relevant_history" else d | {"field": "allergens"} for d in ds]


# name -> (source, finish, mutate(body, intake) -> body, status, detail)
CASES = {
    "session_id_mismatch": (1, True, lambda b, it: b | {"session_id": "0" * 32}, 422, "session_id_mismatch"),
    "active_session": (1, False, None, 409, "session_not_finished"),
    "patient_ref_mismatch": (1, True, lambda b, it: b | {"patient_ref": "SYN-OTHER"}, 422, "patient_ref_mismatch"),
    "consent_after_first_turn": (1, True, lambda b, it: b | {
        "consent_acknowledged_at": (it.first_start + timedelta(seconds=1)).isoformat()}, 422, "consent_time_invalid"),
    "consent_in_future": (1, True, lambda b, it: b | {
        "consent_acknowledged_at": (it.clock.t + timedelta(minutes=5)).isoformat()}, 422, "consent_time_invalid"),
    "red_flag_ack_missing": (6, True, lambda b, it: b | {"red_flag_acknowledged_at": None}, 422,
                             "red_flag_ack_required"),
    "red_flag_ack_unexpected": (1, True, lambda b, it: b | {"red_flag_acknowledged_at": it.last_end.isoformat()},
                                422, "red_flag_ack_unexpected"),
    "red_flag_ack_before_turn": (6, True, lambda b, it: b | {
        "red_flag_acknowledged_at": it.first_start.isoformat()}, 422, "red_flag_ack_time_invalid"),
    "red_flag_ack_in_future": (6, True, lambda b, it: b | {
        "red_flag_acknowledged_at": (it.clock.t + timedelta(minutes=5)).isoformat()}, 422,
        "red_flag_ack_time_invalid"),
    "five_decisions": (1, True, _decisions(lambda ds: ds[:5]), 422, "decision_fields_mismatch"),
    "seven_decisions": (1, True, _decisions(_allergens), 422, "decision_fields_mismatch"),
    "duplicate_field": (1, True, _decisions(lambda ds: ds[:5] + [ds[0]]), 422, "decision_fields_mismatch"),
    "allergens_as_field": (1, True, _decisions(_swap_allergens), 422, "decision_fields_mismatch"),
    "add_on_known": (1, True, _set("severity", action="add", value="มาก", original=None), 422, "action_not_allowed"),
    "unknown_on_known": (1, True, _set("severity", action="unknown", value=None, original=None), 422,
                         "action_not_allowed"),
    "confirm_on_missing": (6, True, _set("severity", action="confirm", value="มาก"), 422, "action_not_allowed"),
    "edit_on_missing": (6, True, _set("severity", action="edit", value="มาก"), 422, "action_not_allowed"),
    "reject_on_missing": (6, True, _set("severity", action="reject"), 422, "action_not_allowed"),
    "original_changed": (1, True, _set("chief_complaint", original="ปวดหัว"), 422, "original_mismatch"),
    "original_on_add": (6, True, _set("severity", action="add", value="มาก", original="มาก"), 422,
                        "original_mismatch"),
    "confirm_value_changed": (1, True, _set("chief_complaint", value="ปวดหัว"), 422, "confirm_value_mismatch"),
    "confirm_raw_none": (1, True, _set("allergy_status", value="none"), 422, "confirm_value_mismatch"),
    "confirm_raw_none_on_unclear": ("conflict", True, _set("allergy_status", value="none"), 422,
                                    "confirm_value_mismatch"),
    "edit_blank": (1, True, _set("severity", action="edit", value="   "), 422, "value_invalid"),
    "edit_too_long": (1, True, _set("severity", action="edit", value="ก" * 501), 422, "value_invalid"),
    "edit_null": (1, True, _set("severity", action="edit", value=None), 422, "value_invalid"),
    "reject_with_value": (1, True, _set("severity", action="reject", value="x"), 422, "value_invalid"),
    "unknown_other_value": (6, True, _set("severity", value="มาก"), 422, "value_invalid"),
    "add_blank": (6, True, _set("severity", action="add", value=""), 422, "value_invalid"),
}

SCHEMA = {
    "extra_key": lambda b: b | {"extra": 1},
    "missing_key": lambda b: {k: v for k, v in b.items() if k != "red_flag_acknowledged_at"},
    "bad_action": lambda b: b | {"decisions": [b["decisions"][0] | {"action": "accept"}] + b["decisions"][1:]},
    "decision_extra_key": lambda b: b | {"decisions": [b["decisions"][0] | {"x": 1}] + b["decisions"][1:]},
    "decision_missing_value": lambda b: b | {
        "decisions": [{k: v for k, v in b["decisions"][0].items() if k != "value"}] + b["decisions"][1:]},
    "naive_datetime": lambda b: b | {"consent_acknowledged_at": "2026-01-05T01:00:00"},
    "reason_too_long": lambda b: b | {"decisions": [b["decisions"][0] | {"reason": "x" * 201}] + b["decisions"][1:]},
    "no_decisions": lambda b: b | {"decisions": []},
    "seventeen_decisions": lambda b: b | {"decisions": b["decisions"] * 3},
    "int_value": lambda b: b | {"decisions": [b["decisions"][0] | {"value": 3}] + b["decisions"][1:]},
}


def _snapshot(client, app):
    return counts(app), client.get("/api/triage/cases").json()["cases"]


def _denied(audit_rows) -> list[dict]:
    return [r for r in audit_rows() if r["action"] == "voice.review.denied"]


@pytest.mark.parametrize("name", list(CASES))
def test_validation_rejects_without_writes(client, app, login, audit_rows, name):
    src, finish, mutate, status, detail = CASES[name]
    login("nurse1")
    it = Intake(client, app, hand_turns("SYN-V2D-AC", ALLERGY_CONFLICT_TURNS) if src == "conflict" else src)
    if finish:
        it.finish()
    body = it.payload()
    if src == "conflict":
        assert _dec(body, "allergy_status")["original"] == UNCLEAR_TH
    if mutate:
        body = mutate(body, it)
    before = _snapshot(client, app)
    r = it.review(body, expect=None)
    assert (r.status_code, r.json()["detail"]) == (status, detail), r.text
    assert _snapshot(client, app) == before
    assert [d["details"] for d in _denied(audit_rows)] == [{"status": status, "reason": detail}]


@pytest.mark.parametrize("name", list(SCHEMA))
def test_schema_422(client, app, login, audit_rows, name):
    login("nurse1")
    it = Intake(client, app, 1)
    it.finish()
    before = _snapshot(client, app)
    r = it.review(SCHEMA[name](it.payload()), expect=None)
    assert r.status_code == 422 and isinstance(r.json()["detail"], list), r.text
    assert _snapshot(client, app) == before
    assert [d["details"] for d in _denied(audit_rows)] == [{"status": 422, "reason": "schema_invalid"}]


def test_unknown_session_404(client, app, login, audit_rows):
    login("nurse1")
    it = Intake(client, app, 1)
    it.finish()
    before = _snapshot(client, app)
    r = client.post(f"/api/voice/sessions/{'f' * 32}/review", json=it.payload() | {"session_id": "f" * 32})
    assert (r.status_code, r.json()["detail"]) == (404, "voice session not found")
    assert _snapshot(client, app) == before
    assert _denied(audit_rows)[-1]["details"] == {"status": 404, "reason": "voice session not found"}


def test_second_review_409(client, app, login):
    login("nurse1")
    it = Intake(client, app, 1)
    body = it.payload()
    it.finish()
    it.review(it.payload())
    before = _snapshot(client, app)
    r = it.review(body, expect=None)
    assert (r.status_code, r.json()["detail"]) == (409, "review_exists")
    assert _snapshot(client, app) == before


def test_guided_session_422(client, app, login):
    login("nurse1")
    it = Intake(client, app, 1)
    it.finish()
    body = it.payload()
    r = client.post("/api/voice/sessions", json={"patient_ref": "SYN-V2A-01", "data_class": "synthetic"})
    gid = r.json()["session"]["session_id"]
    assert client.post(f"/api/voice/sessions/{gid}/finish").status_code == 200
    before = _snapshot(client, app)
    r = client.post(f"/api/voice/sessions/{gid}/review", json=body | {"session_id": gid})
    assert (r.status_code, r.json()["detail"]) == (422, "session_not_ambient")
    assert _snapshot(client, app) == before


def test_not_synthetic_422(client, app, login):
    login("nurse1")
    it = Intake(client, app, 1)
    it.finish()
    body = it.payload()
    with app.state.engine.begin() as conn:  # a session row the API could never create
        conn.execute(text(
            "INSERT INTO voice_sessions (session_id, patient_ref, data_class, created_at, created_by, status, mode) "
            "VALUES ('nonsyn', 'PT-0001', 'synthetic', '2026-01-01T00:00:00+00:00', 1, 'finished', 'ambient')"))
    before = _snapshot(client, app)
    r = client.post("/api/voice/sessions/nonsyn/review", json=body | {"session_id": "nonsyn", "patient_ref": "PT-0001"})
    assert (r.status_code, r.json()["detail"]) == (422, "not_synthetic")
    assert _snapshot(client, app) == before


def test_case_ref_too_long_422(client, app, login):
    login("nurse1")
    ref = "SYN-" + "A" * 59  # 63 chars: "V-" + ref is 65 > 64
    it = Intake(client, app, hand_turns(ref, ["มาด้วยอาการอะไรคะ", "ปวดหัวค่ะ"]))
    it.finish()
    before = _snapshot(client, app)
    r = it.review(expect=None)
    assert (r.status_code, r.json()["detail"]) == (422, "case_ref_too_long")
    assert _snapshot(client, app) == before


@pytest.mark.parametrize("user", ["physician1", "pharmacist1", None])
def test_role_and_login(client, app, login, user):
    login("nurse1")
    it = Intake(client, app, 1)
    it.finish()
    body = it.payload()
    client.post("/api/auth/logout")
    if user:
        login(user)
    before = counts(app)
    r = it.review(body, expect=None)
    assert r.status_code == (403 if user else 401)
    assert counts(app) == before
