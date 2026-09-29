"""Checker-owned live-API journey for slice i2 at 8cde5dd (A09, A10, A11, A12, A15). Not collected by pytest.

Run against `make dev` (mock provider, synthetic S4 author fixtures only):
  PYTHONPATH=backend:. .venv/bin/python tests/e2e/i2_live_journey.py <api_base> <sqlite_db_path> <out.json>
The Case Graph state DB is read from <db stem>.casegraph.db beside the app DB (casegraph_run.stores_for).
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
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from casegraph.data import ConfirmedEvidence  # noqa: E402
from casegraph.export import import_graph  # noqa: E402
from casegraph.store import SQLiteStateStore  # noqa: E402
from casegraph.types import NodeType  # noqa: E402

BASE, DB, OUT = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
GRAPH_DB = DB.with_name(DB.stem + ".casegraph.db")
OVERCLAIM = re.compile(r"no red.?flags?|all clear|ไม่มี.*(สัญญาณอันตราย|red flag)", re.I)
S4_VITALS = {"hr", "rr", "sbp", "dbp", "spo2", "temp_c", "capillary_glucose_mg_dl", "avpu", "new_confusion"}
fx = {c["case"]["case_ref"]: c for c in json.loads((ROOT / "backend/app/triage/fixtures/cases_v1.json").read_text())["cases"]}
res: dict = {"base": BASE}


def client(user):
    c = httpx.Client(base_url=BASE, timeout=60)
    r = c.post("/api/auth/login", json={"username": user, "password": f"{user}-dev-only"})
    assert r.status_code == 200, (user, r.text)
    return c


def audits():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    t = next(r[0] for r in con.execute("select name from sqlite_master where type='table'") if "audit" in r[0])
    rows = [dict(r) for r in con.execute(f"select * from {t} order by rowid")]
    con.close()
    return rows


def graph(gid):
    return import_graph(SQLiteStateStore(GRAPH_DB).load_run(gid))


nurse = client("nurse1")
listed = {c["case_ref"]: c["suggested_as_of"] for c in nurse.get("/api/triage/cases").json()["cases"]}
res["n_cases_listed"] = len(listed)

# ---- every S4 fixture, assessed as the UI does (suggested_as_of): A10 regex, A09 readings, graph vs engine alerts
per_case, overclaim_hits, bad = {}, [], []
for ref, as_of in sorted(listed.items()):
    r = nurse.post(f"/api/triage/cases/{ref}/assess", json={"as_of": as_of})
    if r.status_code != 201:
        bad.append((ref, r.status_code, r.text[:200]))
        continue
    a = r.json()
    view = nurse.get(f"/api/triage/assessments/{a['assessment_id']}")
    for text in (r.text, view.text):
        if OVERCLAIM.search(text):
            overclaim_hits.append(ref)
    s = a.get("screening") or {}
    g = graph(a["graph_id"]) if a.get("graph_id") else None
    rf = g.by_type(NodeType.RED_FLAG) if g else None
    hc = g.by_type(NodeType.HUMAN_CHECKPOINT) if g else None
    graph_alerts = sorted(x["rule_id"] for x in rf.output["Alerts"]["alerts"]) if rf and rf.output else None
    engine_alerts = sorted(x["rule_id"] for x in a["alerts"])
    vitals_in_case = sorted({f["kind"].split(".", 1)[1] for f in fx[ref]["case"]["facts"]
                             if f["kind"].startswith("vital.") and f["kind"].split(".", 1)[1] in S4_VITALS})
    readings = {x["vital"]: x for x in s.get("readings", [])}
    per_case[ref] = {
        "graph_id": a.get("graph_id"),
        "screening_status": s.get("status"),
        "fields_ok": all(k in s for k in ("rule_set_version", "label", "scope", "n_declared", "n_evaluated",
                                          "n_not_evaluated", "n_fired")),
        "rule_set_version": s.get("rule_set_version"),
        "n_declared": s.get("n_declared"), "n_evaluated": s.get("n_evaluated"), "n_fired": s.get("n_fired"),
        "summary": s.get("summary"),
        "rf_model_version": rf.model_version if rf else None,
        "n_rule_results": len(rf.output["Alerts"]["rule_results"]) if rf and rf.output else None,
        "hc": (hc.provider, hc.status) if hc else None,
        "engine_alerts": engine_alerts, "graph_alerts": graph_alerts,
        "graph_alerts_subset_of_engine": graph_alerts is not None and set(graph_alerts) <= set(engine_alerts),
        "vitals_in_case": vitals_in_case,
        "readings_missing_time_or_age": [v for v in readings.values() if not v.get("read_at") or v.get("age_min") is None],
        "vitals_without_reading": [v for v in vitals_in_case if v not in readings and not (v == "new_confusion" and "avpu" in readings)],
        "escalation_required": a["escalation_required"],
        "conflicts_key": "conflicts" in a,
        "graph_checkpoint_status_view": view.json().get("graph_checkpoint_status"),
    }
res["assess_non_201"] = bad
res["overclaim_hits"] = sorted(set(overclaim_hits))
res["per_case"] = per_case
res["screening_status_hist"] = {k: sum(1 for v in per_case.values() if v["screening_status"] == k)
                                for k in {v["screening_status"] for v in per_case.values()}}
res["graph_engine_alert_mismatch"] = {k: (v["engine_alerts"], v["graph_alerts"]) for k, v in per_case.items()
                                      if v["engine_alerts"] != v["graph_alerts"]}

# ---- A11 as_of bounds on three cases, with audit rows
a11 = {}
for ref in ("SYN-S4-002", "SYN-S4-020", "SYN-S4-031"):
    times = [datetime.fromisoformat(f["available_at_time"]) for f in fx[ref]["case"]["facts"]]
    earliest, latest = min(times), max(times)
    probes = {"latest+skew": (latest + timedelta(minutes=5), 201, None),
              "latest+skew+1s": (latest + timedelta(minutes=5, seconds=1), 422, "as_of_beyond_evidence"),
              "earliest": (earliest, 201, None),
              "earliest-1s": (earliest - timedelta(seconds=1), 422, "as_of_before_evidence")}
    for name, (t, want, detail) in probes.items():
        n0 = len(audits())
        r = nurse.post(f"/api/triage/cases/{ref}/assess", json={"as_of": t.isoformat()})
        new = audits()[n0:]
        got_detail = r.json().get("detail") if r.status_code != 201 else None
        rejected_audited = any(x["action"] == "triage.assess.rejected" for x in new)
        a11[f"{ref}:{name}"] = {"status": r.status_code, "detail": got_detail,
                                "ok": r.status_code == want and got_detail == detail
                                and (want == 201 or rejected_audited),
                                "audited_rejection": rejected_audited if want == 422 else None}
res["A11"] = a11

# ---- A15 full review journey in each action and role
pharm, phys = client("pharmacist1"), client("physician1")
a15 = {}
for action, ref in (("confirm", "SYN-S4-002"), ("edit", "SYN-S4-011"), ("reject", "SYN-S4-020"), ("confirm", "SYN-S4-029")):
    a = nurse.post(f"/api/triage/cases/{ref}/assess", json={"as_of": listed[ref]}).json()
    aid, gid = a["assessment_id"], a["graph_id"]
    g0 = graph(gid)
    ev0 = [e for e in SQLiteStateStore(GRAPH_DB).evidence(g0.patient_ref) if isinstance(e, ConfirmedEvidence)]
    ack = [x["rule_id"] for x in a["alerts"]]
    if action == "confirm":
        body = {"department_code": a["department"]["top3"][0]["code"] if a["department"]["top3"] else "MED",
                "acknowledged_alert_ids": ack}
    elif action == "edit":
        body = {"department_code": "MED", "reason": "checker edit", "acknowledged_alert_ids": ack}
    else:
        body = {"reason": "checker reject", "acknowledged_alert_ids": ack}
    url = f"/api/triage/assessments/{aid}/{action}"
    row = {"case": ref, "alerts": ack, "dept_status": a["department"]["status"]}
    row["unacked"] = nurse.post(url, json={**body, "acknowledged_alert_ids": []}).status_code if ack else "n/a (no alerts)"
    row["pharmacist"] = pharm.post(url, json=body).status_code
    row["physician"] = phys.post(url, json=body).status_code
    row["status_after_denials"] = graph(gid).by_type(NodeType.HUMAN_CHECKPOINT).status
    r = nurse.post(url, json=body)
    row["nurse"] = r.status_code
    row["nurse_detail"] = r.text[:200] if r.status_code != 200 else None
    g1 = graph(gid)
    hc = g1.by_type(NodeType.HUMAN_CHECKPOINT)
    row["hc_status"], row["view_status"] = hc.status, (r.json().get("graph_checkpoint_status") if r.status_code == 200 else None)
    ev1 = [e for e in SQLiteStateStore(GRAPH_DB).evidence(g0.patient_ref) if isinstance(e, ConfirmedEvidence)]
    new = [e for e in ev1 if e.item_id not in {x.item_id for x in ev0}]
    row["confirmed_evidence_appended"] = len(new)
    row["confirmed_at_ge_T"] = all(e.available_at_time >= g0.T for e in new) if new else None
    row["T"] = g0.T.isoformat()
    row["confirmed_at"] = [e.available_at_time.isoformat() for e in new]
    row["second_review"] = nurse.post(url, json=body).status_code
    row["pass"] = (row["pharmacist"] == 403 and row["physician"] == 403 and row["nurse"] == 200
                   and row["status_after_denials"] == "pending_confirmation"
                   and row["hc_status"] == {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}[action]
                   and row["confirmed_evidence_appended"] == (0 if action == "reject" else 1)
                   and (row["unacked"] in (409, "n/a (no alerts)")))
    a15[f"{action}:{ref}"] = row
res["A15"] = a15

Path(OUT).write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
summary = {k: res[k] for k in ("n_cases_listed", "assess_non_201", "overclaim_hits", "screening_status_hist",
                               "graph_engine_alert_mismatch")}
summary["A11_all_ok"] = all(v["ok"] for v in a11.values())
summary["A15"] = {k: v["pass"] for k, v in a15.items()}
print(json.dumps(summary, indent=1, ensure_ascii=False, default=str))
