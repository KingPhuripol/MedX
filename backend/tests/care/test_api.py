"""/api/care (s6): gateway audit, review gates and audit, append-only storage, roles, split exposure, claims."""

from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.care import dataset as care_dataset
from app.care.router import SPLIT

from ..conftest import PASSWORDS
from .conftest import FakeProvider

CLAIMS = re.compile(r"diagnos|prescrib|treat|dose|dosage|วินิจฉัย|สั่งยา|ให้ยา|รักษา", re.IGNORECASE)
REASON_SENTINEL = "SENTINEL-reason-7c1e02"
ACTIONS = ("confirm", "edit", "reject")


def as_user(client, username):
    client.cookies.clear()
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]})
    assert resp.status_code == 200


def assess(client, case_id, dp="T2"):
    resp = client.post(f"/api/care/cases/{case_id}/assess", json={"decision_point": dp})
    assert resp.status_code == 201, resp.text
    return resp.json()


def rows_of(dataset, split="dev"):
    return [r for r in dataset.rows if r["split"] == split]


def find(dataset, *, action, alerts=None, client=None):
    """First dev row with the given gold action (and, when asked, with/without alerts)."""
    for r in rows_of(dataset):
        if r["care"]["expected_action"] != action:
            continue
        if alerts is None:
            return r
        a = assess(client, r["case_id"], r["dp"])
        if bool(a["alerts"]) == alerts:
            return r
    raise AssertionError("no row")


def body(action, a, *, ack=None, screening=True):
    ack = [x["rule_id"] for x in a["alerts"]] if ack is None else ack
    b = {"acknowledged_alert_ids": ack, "screening_acknowledged": screening}
    if action == "edit":
        b |= {"reason": REASON_SENTINEL, "next_information": ["NI-ECG-12LEAD"], "pathway_options": []}
    if action == "reject":
        b |= {"reason": REASON_SENTINEL}
    return b


def table(app, name):
    with app.state.engine.connect() as conn:
        return conn.execute(text(f"SELECT * FROM {name}")).mappings().all()


@pytest.fixture
def physician(client):
    as_user(client, "physician1")
    return client


@pytest.fixture
def red(dataset, physician):
    row = find(dataset, action="suggest", alerts=True, client=physician)
    return row, assess(physician, row["case_id"], row["dp"])


def test_care_via_gateway(dataset, physician, audit_rows):
    for r in rows_of(dataset)[:20]:
        before = len(audit_rows())
        a = assess(physician, r["case_id"], r["dp"])
        new = audit_rows()[before:]
        gw = [x for x in new if x["action"] == "gateway.invoke"]
        assert [x["action"] for x in new if x["action"] == "care.assess"] == ["care.assess"]
        if a["status"] == "abstained":
            assert gw == []
        else:
            assert a["status"] == "suggested" and len(gw) == 1
            d = gw[0]["details"]
            assert gw[0]["target"] == "task/care.suggest.v1" and d["data_class"] == "synthetic"
            assert d["request_sha256"] == a["request_sha256"]
        assert a["review_status"] == "pending_review" and a["review"] is None


@pytest.mark.parametrize("mode", ["error", "rejected", "invalid", "timeout"])
def test_api_fail_safe(app, dataset, physician, mode):
    app.state.provider = {"error": FakeProvider(status="error", reason="provider_http_error"),
                          "rejected": FakeProvider(status="rejected", reason="policy"),
                          "invalid": FakeProvider(output={"alerts": []}),
                          "timeout": FakeProvider(raises=TimeoutError())}[mode]
    row = find(dataset, action="suggest")
    a = assess(physician, row["case_id"], row["dp"])
    assert a["status"] == "error" and a["next_information"] == [] and a["pathway_options"] == []


@pytest.mark.parametrize("action", ACTIONS)
def test_care_review_audit(app, physician, audit_rows, red, action):
    _, a = red
    before = len(audit_rows())
    resp = physician.post(f"/api/care/assessments/{a['assessment_id']}/{action}", json=body(action, a))
    assert resp.status_code == 200, resp.text
    rows = [r for r in audit_rows()[before:] if r["action"].startswith("care.review.")]
    assert len(rows) == 1
    row, d = rows[0], rows[0]["details"]
    assert row["action"] == f"care.review.{action}" and row["actor_role"] == "physician"
    assert d["reviewer_id"] == row["actor_id"] and d["reviewer_role"] == "physician" and d["ts_utc"].endswith("+00:00")
    orig = d["original_suggestion"]
    assert orig == {"status": a["status"],
                    "codes": {"next_information": [x["code"] for x in a["next_information"]],
                              "pathway_options": [x["code"] for x in a["pathway_options"]]},
                    "missing_information": a["missing_information"],
                    "alert_rule_ids": [x["rule_id"] for x in a["alerts"]],
                    "screening_status": a["red_flag_screening"]["status"]}
    expected_final = {"confirm": orig["codes"], "edit": {"next_information": ["NI-ECG-12LEAD"], "pathway_options": []},
                      "reject": None}[action]
    assert d["final_codes"] == expected_final
    assert d["acknowledged_alert_ids"] == sorted(x["rule_id"] for x in a["alerts"])
    assert (d["reason_sha256"] is None) == (action == "confirm")
    assert resp.json()["review_status"] == {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}[action]


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("condition", ["alerts", "screening"])
def test_review_requires_ack(app, physician, audit_rows, red, action, condition):
    _, a = red
    assert a["alerts"] and a["red_flag_screening"]["status"] != "evaluated"
    b = body(action, a, ack=[] if condition == "alerts" else None, screening=condition != "screening")
    before = len(audit_rows())
    resp = physician.post(f"/api/care/assessments/{a['assessment_id']}/{action}", json=b)
    assert resp.status_code == 409
    assert resp.json()["detail"] == {"alerts": "alerts_not_acknowledged", "screening": "screening_not_acknowledged"}[condition]
    assert [(r["action"], r["details"]["status"]) for r in audit_rows()[before:]] == [("care.review.denied", 409)]
    assert table(app, "care_reviews") == []


def test_edit_requires_reason_and_valid_codes(app, dataset, physician):
    row = find(dataset, action="abstain")
    a = assess(physician, row["case_id"], row["dp"])
    assert a["status"] == "abstained" and a["next_information"] == [] and a["case_summary"] == []
    url = f"/api/care/assessments/{a['assessment_id']}"
    ack = {"acknowledged_alert_ids": [x["rule_id"] for x in a["alerts"]], "screening_acknowledged": True}
    assert physician.post(f"{url}/confirm", json=ack).json()["detail"] == "nothing_to_confirm"
    assert physician.post(f"{url}/edit", json=ack | {"next_information": ["NI-ECG-12LEAD"]}).json()["detail"] \
        == "reason_required"
    assert physician.post(f"{url}/edit", json=ack | {"reason": "x", "next_information": ["NI-NOPE"]}).json()[
        "detail"] == "code_outside_vocabulary"
    assert physician.post(f"{url}/edit", json=ack | {"reason": "x", "pathway_options": ["CP-NOPE"]}).status_code == 422
    assert physician.post(f"{url}/reject", json=ack).json()["detail"] == "reason_required"
    assert table(app, "care_reviews") == []
    resp = physician.post(f"{url}/edit", json=ack | {"reason": "manual choice", "pathway_options": ["CP-CHEST-PAIN-EVAL"]})
    assert resp.status_code == 200 and resp.json()["review_status"] == "edited"


def test_double_review_409(app, physician, audit_rows, red):
    _, a = red
    url = f"/api/care/assessments/{a['assessment_id']}"
    assert physician.post(f"{url}/confirm", json=body("confirm", a)).status_code == 200
    before = len(audit_rows())
    for action in ACTIONS:
        resp = physician.post(f"{url}/{action}", json=body(action, a))
        assert resp.status_code == 409 and resp.json()["detail"] == "already_reviewed"
    assert [r["action"] for r in audit_rows()[before:]] == ["care.review.denied"] * 3
    assert len(table(app, "care_reviews")) == 1


def test_care_audit_no_raw_text(app, dataset, physician, audit_rows, red):
    _, a = red
    for action in ("edit", "reject"):
        b = assess(physician, a["case_id"], a["decision_point"])
        physician.post(f"/api/care/assessments/{b['assessment_id']}/{action}", json=body(action, b))
    blob = json.dumps([r["details"] for r in audit_rows()], ensure_ascii=False)
    assert REASON_SENTINEL not in blob
    transcripts = [t["text"] for r in rows_of(dataset) for it in dataset.row_snapshot(r)["items"]
                   if it["data_type"] == "IntakeTranscript" for t in it["turns"] if t["speaker"] == "patient"]
    assert transcripts and not [t for t in transcripts if len(t) > 6 and t in blob]


def test_care_tables_append_only(app, physician, red):
    _, a = red
    physician.post(f"/api/care/assessments/{a['assessment_id']}/confirm", json=body("confirm", a))
    counts = (len(table(app, "care_assessments")), len(table(app, "care_reviews")))
    for stmt in ("UPDATE care_assessments SET rules_version = 'x'", "DELETE FROM care_assessments",
                 "UPDATE care_reviews SET action = 'reject'", "DELETE FROM care_reviews"):
        with pytest.raises(DBAPIError, match="append-only"):
            with app.state.engine.begin() as conn:
                conn.execute(text(stmt))
    assert (len(table(app, "care_assessments")), len(table(app, "care_reviews"))) == counts
    assert counts[1] == 1


def test_confirmed_only_after_review(physician, red):
    row, a = red
    cid = row["case_id"]
    url = f"/api/care/cases/{cid}/confirmed"
    resp = physician.get(url)
    assert resp.status_code == 404 and resp.json()["detail"] == "pending_review"
    assert resp.json()["newest_assessment"]["alert_rule_ids"] == [x["rule_id"] for x in a["alerts"]]
    physician.post(f"/api/care/assessments/{a['assessment_id']}/reject", json=body("reject", a))
    assert physician.get(url).status_code == 404
    b = assess(physician, cid, row["dp"])
    physician.post(f"/api/care/assessments/{b['assessment_id']}/confirm", json=body("confirm", b))
    got = physician.get(url)
    assert got.status_code == 200 and got.json()["assessment_id"] == b["assessment_id"]
    assert got.json()["final_codes"]["next_information"] == [x["code"] for x in b["next_information"]]
    other = "T1" if row["dp"] == "T2" else "T2"
    assess(physician, cid, other)  # older by clinical time (T1) never replaces; newer (T2) makes it pending
    c = assess(physician, cid, "T2")  # newest by clinical time, created later: pending review
    assert physician.get(url).status_code == 404  # newest (same as_of, created later) is pending
    assert physician.get(url).json()["newest_assessment"]["assessment_id"] == c["assessment_id"]


def test_care_role_matrix(dataset, client, audit_rows):
    row = find(dataset, action="suggest")
    as_user(client, "physician1")
    a = assess(client, row["case_id"], row["dp"])
    calls = [("get", "/api/care/cases", None), ("get", "/api/care/vocabulary", None),
             ("post", f"/api/care/cases/{row['case_id']}/assess", {"decision_point": row["dp"]}),
             ("get", f"/api/care/assessments/{a['assessment_id']}", None),
             ("get", f"/api/care/cases/{row['case_id']}/confirmed", None)] + [
        ("post", f"/api/care/assessments/{a['assessment_id']}/{x}", body(x, a)) for x in ACTIONS]
    for who, expected in (("nurse1", 403), ("pharmacist1", 403), (None, 401)):
        client.cookies.clear()
        if who:
            as_user(client, who)
        for method, url, payload in calls:
            before = len(audit_rows())
            resp = getattr(client, method)(url, **({"json": payload} if payload is not None else {}))
            assert resp.status_code == expected, (who, url)
            new = audit_rows()[before:]
            assert [(r["action"], r["details"]["status"]) for r in new] == [("care.review.denied", expected)], url
    as_user(client, "physician1")
    assert client.get("/api/care/cases").status_code == 200
    assert client.get(f"/api/care/assessments/{a['assessment_id']}").status_code == 200


def test_cases_dev_only(dataset, physician):
    resp = physician.get("/api/care/cases")
    assert resp.status_code == 200 and SPLIT == "dev"
    served = {c["case_id"] for c in resp.json()["cases"]}
    by_split = {s: {r["case_id"] for r in dataset.rows if r["split"] == s} for s in ("train", "dev", "test")}
    assert served == by_split["dev"]
    assert not served & (by_split["train"] | by_split["test"])
    for cid in sorted(by_split["test"])[:5] + sorted(by_split["train"])[:5]:
        assert physician.post(f"/api/care/cases/{cid}/assess", json={"decision_point": "T1"}).status_code == 404
    assert physician.post("/api/care/cases/..%2Fgold/assess", json={"decision_point": "T1"}).status_code == 404


def test_dataset_missing_503(physician, monkeypatch, tmp_path):
    monkeypatch.setenv("CARE_DATASET", str(tmp_path / "absent"))
    resp = physician.get("/api/care/cases")
    assert resp.status_code == 503 and resp.json()["detail"] == "dataset_missing: run make data"
    assert care_dataset.root() == tmp_path / "absent"


def test_care_claim_scan(dataset, physician, monkeypatch):
    """Every API response for all dev + test assessments (T1, T2) is free of claim terms (A16)."""
    monkeypatch.setattr("app.care.router.SPLIT", "test")  # test cases scanned here only; never served by default
    n = 0
    for split in ("dev", "test"):
        monkeypatch.setattr("app.care.router.SPLIT", split)
        for r in rows_of(dataset, split):
            resp = physician.post(f"/api/care/cases/{r['case_id']}/assess", json={"decision_point": r["dp"]})
            assert resp.status_code == 201
            m = CLAIMS.search(resp.text)
            assert m is None, (r["case_id"], r["dp"], m and m.group(0))
            assert "Suggestion for physician review" in resp.json()["output_label"]
            n += 1
    assert n == len(rows_of(dataset, "dev")) + len(rows_of(dataset, "test"))
    for url in ("/api/care/cases", "/api/care/vocabulary"):
        assert CLAIMS.search(physician.get(url).text) is None
