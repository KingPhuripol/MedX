"""Checker-owned live-API journey for slice i2 (A11, A12, A15). Not collected by pytest.

Run against a running API: python tests/e2e/i2_api_journey.py <base_url> <sqlite_db> <out.json>
Synthetic S4 author fixtures only; mock provider.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE, DB, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
OVERCLAIM = re.compile(r"no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)", re.I)
fx = {c["case"]["case_ref"]: c for c in json.loads((ROOT / "backend/app/triage/fixtures/cases_v1.json").read_text())["cases"]}
res: dict = {}


def client(user):
    c = httpx.Client(base_url=BASE, timeout=30)
    r = c.post("/api/auth/login", json={"username": user, "password": f"{user}-dev-only"})
    assert r.status_code == 200, r.text
    return c


def audits():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    t = next(t for t in tables if "audit" in t)
    rows = [dict(r) for r in con.execute(f"select * from {t} order by rowid")]
    con.close()
    return rows


nurse = client("nurse1")
suggested = {c["case_ref"]: c["suggested_as_of"] for c in nurse.get("/api/triage/cases").json()["cases"]}
res["fixture_as_of_rejected"] = sorted(
    r for r, c in fx.items()
    if nurse.post(f"/api/triage/cases/{r}/assess", json={"as_of": c["as_of"]}).status_code == 422)
ref = "SYN-S4-002"
times = [datetime.fromisoformat(f["available_at_time"]) for f in fx[ref]["case"]["facts"]]
earliest, latest = min(times), max(times)
skew, one = timedelta(minutes=5), timedelta(seconds=1)
cases = {
    "latest+skew": latest + skew, "latest+skew+1s": latest + skew + one,
    "earliest": earliest, "earliest-1s": earliest - one,
}
a11 = {}
for name, t in cases.items():
    n0 = len(audits())
    r = nurse.post(f"/api/triage/cases/{ref}/assess", json={"as_of": t.isoformat()})
    new = audits()[n0:]
    a11[name] = {"status": r.status_code, "detail": r.json().get("detail") if r.status_code != 201 else None,
                 "new_audit_actions": [(a.get("action"), a.get("outcome")) for a in new]}
res["A11"] = a11

# A15 / A12: a full assess -> review journey in each role
r = nurse.post(f"/api/triage/cases/{ref}/assess", json={"as_of": suggested[ref]})
assessment = r.json()
res["assess_keys"] = sorted(assessment)
res["assess_graph_id"] = assessment.get("graph_id")
res["assess_screening"] = assessment.get("screening")
res["assess_has_conflicts_field"] = "conflicts" in assessment
res["assess_overclaim"] = bool(OVERCLAIM.search(json.dumps(assessment, ensure_ascii=False)))
aid = assessment.get("assessment_id") or assessment.get("id")
alert_ids = [a.get("alert_id") or a.get("rule_id") for a in assessment.get("alerts", [])]
res["alert_ids"] = alert_ids
body = {"department_code": "CARD", "reason": "checker", "acknowledged_alert_ids": []}
res["confirm_unacked"] = nurse.post(f"/api/triage/assessments/{aid}/confirm", json=body).status_code
pharm = client("pharmacist1")
res["confirm_pharmacist"] = pharm.post(f"/api/triage/assessments/{aid}/confirm",
                                       json={**body, "acknowledged_alert_ids": alert_ids}).status_code
ok = nurse.post(f"/api/triage/assessments/{aid}/confirm", json={**body, "acknowledged_alert_ids": alert_ids})
res["confirm_acked"] = ok.status_code
res["confirm_body_keys"] = sorted(ok.json()) if ok.status_code < 300 else ok.text[:300]
res["confirm_graph_id"] = ok.json().get("graph_id") if ok.status_code < 300 else None
for action in ("edit", "reject"):
    a2 = nurse.post(f"/api/triage/cases/{ref}/assess", json={"as_of": suggested[ref]}).json()
    rr = nurse.post(f"/api/triage/assessments/{a2['assessment_id']}/{action}",
                    json={**body, "acknowledged_alert_ids": [x["rule_id"] for x in a2["alerts"]]})
    res[f"{action}_status"] = rr.status_code
    res[f"{action}_graph_id"] = rr.json().get("graph_id") if rr.status_code < 300 else rr.text[:200]

# Overclaim over every fixture case's API response
hits = []
for cref, c in fx.items():
    r = nurse.post(f"/api/triage/cases/{cref}/assess", json={"as_of": suggested[cref]})
    if r.status_code == 201 and OVERCLAIM.search(json.dumps(r.json(), ensure_ascii=False)):
        hits.append(cref)
res["api_overclaim_hits"] = hits
Path(OUT).write_text(json.dumps(res, indent=1, ensure_ascii=False))
print(json.dumps(res, indent=1, ensure_ascii=False))
