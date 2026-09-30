"""V2D-D7 (SQLite part): review tables are append-only; audit rows are complete and carry no text."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .review_helpers import Intake

EDIT = "EDIT-SENTINEL สี่วัน"
REASON = "REASON-SENTINEL ผู้ป่วยแก้คำตอบ"


def _submit_with_reason(client, app, n: int) -> tuple[dict, Intake]:
    it = Intake(client, app, n)
    it.finish()
    body = it.payload({"onset_duration": ("edit", EDIT), "relevant_history": ("reject", None)} if n == 1 else None)
    for d in body["decisions"]:
        d["reason"] = REASON
    return it.review(body).json(), it


@pytest.mark.parametrize("table", ["voice_reviews", "voice_review_decisions"])
def test_append_only_sqlite(client, app, login, table):
    login("nurse1")
    _submit_with_reason(client, app, 1)
    for stmt in (f"UPDATE {table} SET session_id = 'x'", f"DELETE FROM {table}"):
        with pytest.raises(DBAPIError, match="append-only"):
            with app.state.engine.begin() as conn:
                conn.execute(text(stmt))


def _variants(s: str) -> set[str]:
    return {s, json.dumps(s)[1:-1]}  # raw and \\u-escaped (details_json is ASCII-escaped JSON)


def test_audit_rows_and_no_text(client, app, login, audit_rows):
    login("nurse1")
    out, it = _submit_with_reason(client, app, 1)
    rows = audit_rows()
    by = {a: [r for r in rows if r["action"] == a] for a in
          ("voice.review.submit", "voice.review.consent_ack", "voice.review.handoff", "voice.review.red_flag_ack")}
    assert [len(by[a]) for a in by] == [1, 1, 1, 0]
    for a in ("voice.review.submit", "voice.review.consent_ack", "voice.review.handoff"):
        r = by[a][0]
        assert r["actor_id"] is not None and r["actor_role"] == "nurse" and r["ts_utc"]
    submit = by["voice.review.submit"][0]["details"]
    assert submit["review_id"] == out["review_id"] and submit["mode"] == "ambient"
    assert [d["changed"] for d in submit["decisions"]] == [False, True, False, False, False, True]
    assert set(submit["reason_sha256"]) == set(out["confirmed_fields"]) | {"relevant_history"}
    handoff = by["voice.review.handoff"][0]["details"]
    assert handoff["assessment_id"] == out["department_suggestion"]["assessment_id"] and handoff["error_type"] is None
    assert any(r["action"] == "triage.assess" for r in rows)

    red, it6 = _submit_with_reason(client, app, 6)
    rows = audit_rows()
    rf = [r for r in rows if r["action"] == "voice.review.red_flag_ack"]
    assert len(rf) == 1 and rf[0]["actor_role"] == "nurse" and rf[0]["details"]["review_id"] == red["review_id"]

    secrets = {EDIT, REASON} | {t["text"] for x in (it, it6) for t in x.fx["turns"]}
    for r in rows:
        for s in secrets:
            assert not any(v in r["details_json"] for v in _variants(s)), (r["action"], s)
