import re

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.triage.fixtures import load_entries

from ..conftest import PASSWORDS

BY_REF = {e.case.case_ref: e for e in load_entries()}
RED_REF = "SYN-S4-002"  # RF-CHEST, RF-HR, RF-SBP; department suggested
PLAIN_REF = "SYN-S4-029"  # no alert; department suggested
ABSTAIN_REF = "SYN-S4-023"  # required field missing
CLAIMS = re.compile(r"diagnos|prescrib|treat", re.IGNORECASE)
REASON_SENTINEL = "SENTINEL-reason-9d41c7"


def assess(client, ref):
    resp = client.post(f"/api/triage/cases/{ref}/assess", json={"as_of": BY_REF[ref].as_of.isoformat()})
    assert resp.status_code == 201, resp.text
    return resp.json()


def as_user(client, username):
    client.cookies.clear()
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]})
    assert resp.status_code == 200


def review_body(action, a, ack=None):
    ack = [x["rule_id"] for x in a["alerts"]] if ack is None else ack
    top = a["department"]["top3"][0]["code"] if a["department"]["top3"] else "MED"
    if action == "confirm":
        return {"department_code": top, "acknowledged_alert_ids": ack}
    if action == "edit":
        return {"department_code": "MED", "reason": REASON_SENTINEL, "acknowledged_alert_ids": ack}
    return {"reason": REASON_SENTINEL, "acknowledged_alert_ids": ack}


def review_rows(app):
    with app.state.engine.connect() as conn:
        return conn.execute(text("SELECT * FROM triage_reviews")).mappings().all()


def test_assess_response_shape(client, login):
    login("nurse1")
    raw = client.post(f"/api/triage/cases/{RED_REF}/assess", json={"as_of": BY_REF[RED_REF].as_of.isoformat()})
    body = raw.text
    assert body.index('"alerts":') < body.index('"department":')
    a = raw.json()
    assert a["review_status"] == "pending_review" and a["confirmed_department"] is None
    assert a["escalation_required"] is True and a["ruleset_version"] == "rf-1.1.0"
    assert a["output_label"] == "Suggestion for nurse review"
    copy = " ".join([a["output_label"]] + [x[k] for x in a["alerts"] for k in ("message_en", "name_en")])
    assert not CLAIMS.search(copy)
    assert client.post("/api/triage/cases/NOPE/assess", json={"as_of": "2026-09-01T00:00:00Z"}).status_code == 404
    assert client.post(f"/api/triage/cases/{RED_REF}/assess", json={"as_of": "2026-09-01T00:00:00"}).status_code == 422


@pytest.mark.parametrize("action", ["confirm", "edit", "reject"])
def test_review_requires_alert_ack(app, client, login, audit_rows, action):
    login("nurse1")
    a = assess(client, RED_REF)
    ids = [x["rule_id"] for x in a["alerts"]]
    assert len(ids) == 3
    for partial in ([], ids[:1], ids[:2]):
        before = len(audit_rows())
        resp = client.post(f"/api/triage/assessments/{a['assessment_id']}/{action}",
                           json=review_body(action, a, ack=partial))
        assert resp.status_code == 409 and resp.json()["detail"] == "alerts_not_acknowledged"
        rows = audit_rows()[before:]
        assert [(r["action"], r["details"]["status"]) for r in rows] == [("triage.review.denied", 409)]
    assert review_rows(app) == []
    resp = client.post(f"/api/triage/assessments/{a['assessment_id']}/{action}", json=review_body(action, a))
    assert resp.status_code == 200, resp.text
    assert len(review_rows(app)) == 1


def test_edit_requires_reason_and_valid_code(app, client, login):
    login("nurse1")
    a = assess(client, ABSTAIN_REF)
    url = f"/api/triage/assessments/{a['assessment_id']}/edit"
    assert client.post(url, json={"department_code": "ORTHO"}).json()["detail"] == "reason_required"
    assert client.post(url, json={"department_code": "ORTHO", "reason": "   "}).status_code == 422
    assert client.post(url, json={"department_code": "ER", "reason": "x"}).json()["detail"] == "unknown_department"
    assert review_rows(app) == []
    # Edit is the only way to set a department on an abstained assessment.
    resp = client.post(url, json={"department_code": "ORTHO", "reason": "knee injury, manual choice"})
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "edited" and resp.json()["confirmed_department"] == "ORTHO"
    b = assess(client, ABSTAIN_REF)
    reject = f"/api/triage/assessments/{b['assessment_id']}/reject"
    assert client.post(reject, json={}).json()["detail"] == "reason_required"


def test_confirm_code_must_be_in_top3(app, client, login):
    login("nurse1")
    a = assess(client, PLAIN_REF)
    top = {d["code"] for d in a["department"]["top3"]}
    outside = next(c for c in ("PSY", "EYE", "ENT") if c not in top)
    url = f"/api/triage/assessments/{a['assessment_id']}/confirm"
    assert client.post(url, json={"department_code": outside}).json()["detail"] == "department_not_in_top3"
    b = assess(client, ABSTAIN_REF)  # abstained: nothing to confirm
    resp = client.post(f"/api/triage/assessments/{b['assessment_id']}/confirm", json={"department_code": "ORTHO"})
    assert resp.status_code == 422
    assert review_rows(app) == []


@pytest.mark.parametrize("action", ["confirm", "edit", "reject"])
def test_review_audit(client, login, audit_rows, action):
    login("nurse1")
    a = assess(client, RED_REF)
    before = len(audit_rows())
    resp = client.post(f"/api/triage/assessments/{a['assessment_id']}/{action}", json=review_body(action, a))
    assert resp.status_code == 200
    rows = [r for r in audit_rows()[before:] if r["action"].startswith("triage.review.")]
    assert len(rows) == 1
    row, d = rows[0], rows[0]["details"]
    assert row["action"] == f"triage.review.{action}" and row["actor_role"] == "nurse"
    assert d["reviewer_id"] == row["actor_id"] and d["reviewer_role"] == "nurse"
    assert d["ts_utc"].endswith("+00:00")
    assert d["assessment_id"] == a["assessment_id"]
    orig = d["original_suggestion"]
    assert orig["status"] == a["department"]["status"]
    assert orig["top3"] == [{"code": x["code"], "score": x["score"]} for x in a["department"]["top3"]]
    assert orig["alert_rule_ids"] == [x["rule_id"] for x in a["alerts"]]
    assert "missing_information" in orig
    expected_final = {"confirm": a["department"]["top3"][0]["code"], "edit": "MED", "reject": None}[action]
    assert d["final_department"] == expected_final
    assert sorted(d["acknowledged_alert_ids"]) == sorted(x["rule_id"] for x in a["alerts"])
    assert (d["reason_sha256"] is None) == (action == "confirm")
    view = resp.json()
    assert view["review_status"] == {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}[action]


def test_double_review_409(app, client, login, audit_rows):
    login("nurse1")
    a = assess(client, PLAIN_REF)
    url = f"/api/triage/assessments/{a['assessment_id']}"
    assert client.post(f"{url}/confirm", json=review_body("confirm", a)).status_code == 200
    for action in ("confirm", "edit", "reject"):
        before = len(audit_rows())
        resp = client.post(f"{url}/{action}", json=review_body(action, a))
        assert resp.status_code == 409 and resp.json()["detail"] == "already_reviewed"
        assert [r["action"] for r in audit_rows()[before:]] == ["triage.review.denied"]
    assert len(review_rows(app)) == 1


def test_audit_no_raw_text(client, login, audit_rows):
    login("nurse1")
    cc_texts = []
    for ref in (RED_REF, PLAIN_REF, ABSTAIN_REF, "SYN-S4-001"):
        a = assess(client, ref)
        cc_texts += [f.value for f in BY_REF[ref].case.facts if f.kind == "chief_complaint"]
        action = "reject" if ref != "SYN-S4-001" else "edit"
        assert client.post(f"/api/triage/assessments/{a['assessment_id']}/{action}",
                           json=review_body(action, a)).status_code == 200
    dump = "\n".join(repr(r) for r in audit_rows())
    assert REASON_SENTINEL not in dump
    for cc in cc_texts:
        assert cc not in dump


def test_triage_tables_append_only(app, client, login):
    login("nurse1")
    a = assess(client, PLAIN_REF)
    client.post(f"/api/triage/assessments/{a['assessment_id']}/confirm", json=review_body("confirm", a))
    for stmt in (
        "UPDATE triage_assessments SET case_ref = 'x'",
        "DELETE FROM triage_assessments",
        "UPDATE triage_reviews SET final_department = 'PSY'",
        "DELETE FROM triage_reviews",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            with app.state.engine.begin() as conn:
                conn.execute(text(stmt))
    assert client.get(f"/api/triage/assessments/{a['assessment_id']}").json()["review_status"] == "confirmed"


def test_confirmed_only_after_review(client, login):
    login("nurse1")
    url = f"/api/triage/cases/{RED_REF}/confirmed"
    resp = client.get(url)
    assert resp.status_code == 404 and resp.json()["detail"] == "pending_review"
    a = assess(client, RED_REF)
    assert a["confirmed_department"] is None
    assert client.get(url).json()["detail"] == "pending_review"
    client.post(f"/api/triage/assessments/{a['assessment_id']}/reject", json=review_body("reject", a))
    assert client.get(url).status_code == 404
    b = assess(client, RED_REF)
    assert b["confirmed_department"] is None and b["assessment_id"] != a["assessment_id"]
    code = b["department"]["top3"][0]["code"]
    client.post(f"/api/triage/assessments/{b['assessment_id']}/confirm", json=review_body("confirm", b))
    got = client.get(url)
    assert got.status_code == 200
    assert got.json()["department"]["code"] == code and got.json()["assessment_id"] == b["assessment_id"]
    assert got.json()["review"]["action"] == "confirm"
    # The earlier assessment is unchanged (re-assessing never mutates an old one).
    assert client.get(f"/api/triage/assessments/{a['assessment_id']}").json()["review_status"] == "rejected"
    c = assess(client, ABSTAIN_REF)
    client.post(f"/api/triage/assessments/{c['assessment_id']}/edit",
                json={"department_code": "ORTHO", "reason": "manual"})
    assert client.get(f"/api/triage/cases/{ABSTAIN_REF}/confirmed").json()["department"]["code"] == "ORTHO"
    assert client.get("/api/triage/cases/NOPE/confirmed").status_code == 404


def test_triage_role_matrix(client, audit_rows):
    as_user(client, "nurse1")
    a = assess(client, PLAIN_REF)
    aid = a["assessment_id"]
    as_of = BY_REF[PLAIN_REF].as_of.isoformat()
    writes = [
        (f"/api/triage/cases/{PLAIN_REF}/assess", {"as_of": as_of}),
        (f"/api/triage/assessments/{aid}/confirm", review_body("confirm", a)),
        (f"/api/triage/assessments/{aid}/edit", review_body("edit", a)),
        (f"/api/triage/assessments/{aid}/reject", review_body("reject", a)),
    ]
    reads = ["/api/triage/cases", "/api/triage/departments", f"/api/triage/assessments/{aid}",
             f"/api/triage/cases/{PLAIN_REF}/confirmed"]
    for username in ("physician1", "pharmacist1"):
        as_user(client, username)
        for url, body in writes:
            before = len(audit_rows())
            assert client.post(url, json=body).status_code == 403, (username, url)
            assert [r["action"] for r in audit_rows()[before:]] == ["triage.review.denied"]
    as_user(client, "pharmacist1")
    for url in reads:
        before = len(audit_rows())
        assert client.get(url).status_code == 403
        assert [r["action"] for r in audit_rows()[before:]] == ["triage.review.denied"]
    as_user(client, "physician1")
    assert client.get("/api/triage/cases").status_code == 200
    assert client.get(f"/api/triage/assessments/{aid}").status_code == 200
    assert client.get(f"/api/triage/cases/{PLAIN_REF}/confirmed").status_code == 404  # pending, not forbidden
    client.cookies.clear()
    for url, body in writes:
        assert client.post(url, json=body).status_code == 401
    for url in reads:
        assert client.get(url).status_code == 401
    as_user(client, "nurse1")
    listing = client.get("/api/triage/cases").json()
    assert len(listing["cases"]) == 40 and set(listing["cases"][0]) == {"case_ref", "chief_complaint", "suggested_as_of"}
    assert client.post(writes[1][0], json=writes[1][1]).status_code == 200  # nurse write succeeds


TEMPORAL_REFS = sorted(ref for ref, e in BY_REF.items() if e.gold.temporal is not None)


def _assess_at(client, ref, as_of):
    resp = client.post(f"/api/triage/cases/{ref}/assess", json={"as_of": as_of.isoformat()})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _confirm(client, a):
    resp = client.post(f"/api/triage/assessments/{a['assessment_id']}/confirm", json=review_body("confirm", a))
    assert resp.status_code == 200, resp.text


def _ids(a):
    return sorted(x["rule_id"] for x in a["alerts"])


def test_temporal_fixtures_present():
    assert TEMPORAL_REFS == ["SYN-S4-009", "SYN-S4-017", "SYN-S4-019"]


@pytest.mark.parametrize("ref", TEMPORAL_REFS)
@pytest.mark.parametrize("order", ["early_first", "late_first"])
def test_confirmed_not_stale_after_reassessment(client, login, ref, order):
    """/confirmed resolves against the newest assessment by as_of, never by review order (S4-A15)."""
    login("nurse1")
    url = f"/api/triage/cases/{ref}/confirmed"
    entry = BY_REF[ref]
    early_at, late_at = entry.gold.temporal.early_as_of, entry.as_of

    if order == "early_first":
        # Confirm the early snapshot, then a later snapshot adds red flags and is still pending.
        early = _assess_at(client, ref, early_at)
        _confirm(client, early)
        assert client.get(url).json()["assessment_id"] == early["assessment_id"]
        late = _assess_at(client, ref, late_at)
    else:
        # Later snapshot is assessed and confirmed first; an earlier snapshot is assessed afterwards.
        late = _assess_at(client, ref, late_at)
        _confirm(client, late)
        early = _assess_at(client, ref, early_at)
    assert set(_ids(late)) > set(_ids(early)) and late["escalation_required"] is True

    if order == "early_first":
        # Newer assessment unreviewed: no care-facing department, and its urgency is surfaced.
        got = client.get(url)
        assert got.status_code == 404 and got.json()["detail"] == "pending_review"
        pending = got.json()["newest_assessment"]
        assert pending["assessment_id"] == late["assessment_id"]
        assert pending["review_status"] == "pending_review"
        assert pending["escalation_required"] is True and sorted(pending["alert_rule_ids"]) == _ids(late)
        _confirm(client, late)
    else:
        # Reviewing an older snapshot later must not override the newer confirmed one.
        _confirm(client, early)

    got = client.get(url)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["assessment_id"] == late["assessment_id"]
    assert sorted(body["alert_rule_ids"]) == _ids(late) and body["escalation_required"] is True


def test_confirmed_pending_when_newest_rejected(client, login):
    login("nurse1")
    ref = "SYN-S4-019"
    url = f"/api/triage/cases/{ref}/confirmed"
    early = _assess_at(client, ref, BY_REF[ref].gold.temporal.early_as_of)
    _confirm(client, early)
    late = _assess_at(client, ref, BY_REF[ref].as_of)
    resp = client.post(f"/api/triage/assessments/{late['assessment_id']}/reject", json=review_body("reject", late))
    assert resp.status_code == 200
    got = client.get(url)
    assert got.status_code == 404 and got.json()["detail"] == "pending_review"
    assert got.json()["newest_assessment"]["review_status"] == "rejected"
    assert got.json()["newest_assessment"]["escalation_required"] is True
