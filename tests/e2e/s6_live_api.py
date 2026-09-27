"""s6 checker: live HTTP journey against `make dev API_PORT=8106 WEB_PORT=3106` (independent of builder tests).

Usage: python tests/e2e/s6_live_api.py <dataset_root_with_gold> <sqlite_db_path> <out_json>
The API must serve CARE_DATASET with the same inputs as <dataset_root> (tree hash checked by the caller).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from casegraph.data import CareSuggestion, banner_for  # noqa: E402

API = "http://127.0.0.1:8106"
DS = Path(sys.argv[1])
DB = sys.argv[2]
OUT = Path(sys.argv[3])
PW = {"physician": "physician1-dev-only", "nurse": "nurse1-dev-only", "pharmacist": "pharmacist1-dev-only"}
KEY_ORDER = ["alerts", "red_flag_screening", "escalation_required", "status", "case_summary", "next_information",
             "pathway_options", "missing_information", "uncertainty", "provider", "model_version",
             "contract_version", "rules_version", "request_sha256", "as_of", "decision_point", "casegraph_projection"]
CLAIM = re.compile(r"diagnos|prescrib|treat|dose|dosage|วินิจฉัย|สั่งยา|ให้ยา|รักษา", re.I)
fails: list[dict] = []
stats: Counter = Counter()


def fail(cid, what, expected, actual, req=""):
    fails.append({"case": cid, "check": what, "request": req, "expected": expected, "actual": actual})


def client(role):
    c = httpx.Client(base_url=API, timeout=60)
    if role:
        r = c.post("/api/auth/login", json={"username": f"{role}1", "password": PW[role]})
        assert r.status_code == 200, (role, r.status_code, r.text)
    return c


def audit_rows(where="1=1", args=()):
    con = sqlite3.connect(DB)
    try:
        return con.execute(f"select id, action, outcome, actor_id, actor_role, details_json, target from audit_events where {where} order by id", args).fetchall()
    finally:
        con.close()


def max_audit_id():
    con = sqlite3.connect(DB)
    try:
        return con.execute("select coalesce(max(id),0) from audit_events").fetchone()[0]
    finally:
        con.close()


phys, nurse, pharm, anon = client("physician"), client("nurse"), client("pharmacist"), client(None)

# ---------------------------------------------------------------- gold
gold = {}
for g in sorted((DS / "gold").glob("*/*.json")):
    d = json.loads(g.read_text("utf-8"))
    for row in d["decision_times"]:
        gold[(d["case_id"], row["decision_point"])] = (d["split"], d["patient_ref"], row["care"], row["red_flags"])
splits = {}
for (cid, _), (sp, *_rest) in gold.items():
    splits[cid] = sp

# ---------------------------------------------------------------- A15 list dev only
r = phys.get("/api/care/cases")
assert r.status_code == 200, r.text
served = [c["case_id"] for c in r.json()["cases"]]
dev_ids = sorted(c for c, s in splits.items() if s == "dev")
stats["cases_served"] = len(served)
stats["cases_served_non_dev"] = sum(1 for c in served if splits.get(c) != "dev")
if sorted(served) != dev_ids:
    fail("-", "A15 GET /cases == dev ids", len(dev_ids), len(served), "GET /api/care/cases")
for c in r.json()["cases"]:
    if [d["decision_point"] for d in c["decision_points"]] != ["T1", "T2"]:
        fail(c["case_id"], "A15 decision points listed", ["T1", "T2"], c["decision_points"])

# test/train case assess -> not served
for sp in ("test", "train"):
    cid = next(c for c, s in splits.items() if s == sp)
    rr = phys.post(f"/api/care/cases/{cid}/assess", json={"decision_point": "T1"})
    stats[f"assess_{sp}_status"] = rr.status_code
    if rr.status_code != 404:
        fail(cid, f"A15 {sp} case not assessable", 404, rr.status_code, f"POST /api/care/cases/{cid}/assess")

# ---------------------------------------------------------------- per dev case, T1/T2
answered, hits, sel_total = 0, 0, 0
responses = {}
for cid in dev_ids:
    for dp in ("T1", "T2"):
        sp, pref, care, rflags = gold[(cid, dp)]
        snap = json.loads((DS / "inputs" / sp / cid / f"snapshot_{dp}.json").read_text("utf-8"))
        items = {it["item_id"]: it for it in snap["items"]}
        as_of = datetime.fromisoformat(snap["as_of"])
        before = max_audit_id()
        rr = phys.post(f"/api/care/cases/{cid}/assess", json={"decision_point": dp})
        req = f"POST /api/care/cases/{cid}/assess {{decision_point:{dp}}}"
        if rr.status_code != 201:
            fail(cid, "assess 201", 201, rr.status_code, req)
            continue
        raw_text = rr.text
        a = rr.json()
        responses[(cid, dp)] = a
        stats["assessments"] += 1
        stats[f"status_{a['status']}"] += 1
        # key order (A04): alerts, screening, escalation before status; the full spec order
        keys = [k for k in a if k in KEY_ORDER]
        if keys != KEY_ORDER:
            fail(cid + dp, "A04 key order", KEY_ORDER, keys, req)
        if list(a)[:4] != ["alerts", "red_flag_screening", "escalation_required", "status"]:
            fail(cid + dp, "A04 first keys", KEY_ORDER[:4], list(a)[:4], req)
        scr = a["red_flag_screening"]
        if scr["banner"] != banner_for(scr["status"]):
            fail(cid + dp, "A04 banner_for", banner_for(scr["status"]), scr["banner"], req)
        stats[f"screening_{scr['status']}"] += 1
        if a["escalation_required"] != bool(a["alerts"]):
            fail(cid + dp, "escalation==bool(alerts)", bool(a["alerts"]), a["escalation_required"], req)
        if a["review_status"] != "pending_review":
            fail(cid + dp, "pending_review", "pending_review", a["review_status"], req)
        if a["uncertainty"] != "MOCK baseline — not calibrated":
            fail(cid + dp, "uncertainty label", "MOCK baseline — not calibrated", a["uncertainty"], req)
        new_rows = audit_rows("id > ?", (before,))
        gw = [x for x in new_rows if x[1] == "gateway.invoke"]
        assess_rows = [x for x in new_rows if x[1] == "care.assess"]
        if len(assess_rows) != 1:
            fail(cid + dp, "care.assess audit row", 1, len(assess_rows), req)
        else:
            det = json.loads(assess_rows[0][5])
            for k in ("as_of", "status", "codes", "screening_status", "alert_rule_ids", "provider", "model_version",
                      "request_sha256", "assessment_id", "case_id"):
                if k not in det:
                    fail(cid + dp, f"care.assess audit has {k}", "present", "absent", req)
        # A01 / A02
        if care["expected_action"] == "abstain":
            stats["gold_abstain"] += 1
            ok = (a["status"] == "abstained" and not a["case_summary"] and not a["next_information"]
                  and not a["pathway_options"] and a["missing_information"] == care["required_inputs_missing"]
                  and len(gw) == 0)
            if not ok:
                fail(cid + dp, "A01 abstain exact", {"status": "abstained", "missing": care["required_inputs_missing"], "gw": 0},
                     {"status": a["status"], "missing": a["missing_information"], "gw": len(gw),
                      "n_items": [len(a["case_summary"]), len(a["next_information"]), len(a["pathway_options"])]}, req)
            else:
                stats["A01_ok"] += 1
        else:
            stats["gold_suggest"] += 1
            if a["status"] == "abstained":
                fail(cid + dp, "A02 false abstention", "not abstained", a["status"], req)
            if a["status"] == "suggested":
                if len(gw) != 1 or json.loads(gw[0][5]).get("data_class") != "synthetic":
                    fail(cid + dp, "A06 one synthetic gateway row", 1, [json.loads(x[5]) for x in gw], req)
                else:
                    stats["A06_ok"] += 1
                # A07 projection
                try:
                    p = CareSuggestion.model_validate(a["casegraph_projection"])
                    exp_items = tuple([x["code"] for x in a["next_information"]] + [x["code"] for x in a["pathway_options"]])
                    if p.items != exp_items or p.red_flag_screening != scr["status"]:
                        fail(cid + dp, "A07 projection order/screening", exp_items, p.items, req)
                    else:
                        stats["A07_ok"] += 1
                except Exception as e:  # noqa: BLE001
                    fail(cid + dp, "A07 projection validates", "valid", repr(e)[:200], req)
                # A13: no LabSeries -> lab_results listed
                if not any(it["data_type"] == "LabSeries" for it in snap["items"]):
                    if "lab_results" not in a["missing_information"]:
                        fail(cid + dp, "A13 no LabSeries listed", "lab_results in missing", a["missing_information"], req)
                    else:
                        stats["A13_nolab_listed"] += 1
                # selective hit@3 (live) vs gold next_info on evaluable rows
                if care["evaluable"]:
                    answered += 1
                    top3 = [x["code"] for x in a["next_information"]][:3]
                    hits += bool(set(top3) & set(care["next_info"]))
            if a["status"] == "error":
                fail(cid + dp, "unexpected error status", "suggested", a.get("reason"), req)
        if "missing_information" not in a or not isinstance(a["missing_information"], list):
            fail(cid + dp, "A13 missing list present", "list", type(a.get("missing_information")).__name__, req)
        # A03 evidence refs
        for sect in ("case_summary", "next_information", "pathway_options"):
            for x in a[sect]:
                stats["items_total"] += 1
                if not x["evidence_refs"]:
                    fail(cid + dp, f"A03 {sect} has refs", ">=1", 0, req)
                for ref in x["evidence_refs"]:
                    stats["refs_total"] += 1
                    it = items.get(ref["item_id"])
                    if it is None:
                        fail(cid + dp, "A03 ref resolves", "in snapshot", ref["item_id"], req)
                    elif datetime.fromisoformat(it["available_at_time"]) > as_of:
                        fail(cid + dp, "A03 ref time-valid", f"<= {snap['as_of']}", it["available_at_time"], req)
                    elif datetime.fromisoformat(ref["available_at_time"]) != datetime.fromisoformat(it["available_at_time"]):
                        fail(cid + dp, "A03 shown time == item time", it["available_at_time"], ref["available_at_time"], req)
                    else:
                        stats["refs_ok"] += 1
                if sect != "case_summary" and not x.get("source_refs"):
                    fail(cid + dp, f"{sect} source_refs non-empty", ">=1", x.get("source_refs"), req)
            if sect == "next_information" and len(a[sect]) > 5 or sect == "pathway_options" and len(a[sect]) > 3:
                fail(cid + dp, f"{sect} max length", "<=5/<=3", len(a[sect]), req)
        # A16 claim scan on the full response
        m = CLAIM.search(raw_text)
        if m:
            fail(cid + dp, "A16 claim term in response", "0 matches", raw_text[max(0, m.start() - 60): m.end() + 40], req)
        # alert-driven next info rank first
        # (checked indirectly: alert codes from rules; here only report)

stats["live_selective_hit3_answered"] = answered
stats["live_selective_hit3_hits"] = hits

# ---------------------------------------------------------------- A18 determinism over HTTP
cid0 = dev_ids[0]
strip = lambda d: {k: v for k, v in d.items() if k not in ("assessment_id", "created_at", "created_by", "review", "review_status")}  # noqa: E731
r1 = phys.post(f"/api/care/cases/{cid0}/assess", json={"decision_point": "T2"}).json()
r2 = phys.post(f"/api/care/cases/{cid0}/assess", json={"decision_point": "T2"}).json()
if json.dumps(strip(r1), sort_keys=False) != json.dumps(strip(r2), sort_keys=False):
    fail(cid0, "A18 HTTP determinism", "identical", "differ")
else:
    stats["A18_http_identical"] = 1

# ---------------------------------------------------------------- A14 review flows
# pick: suggested + alert + partial (T2), abstained case
sugg_alert = next(((c, dp) for (c, dp), a in responses.items() if a["status"] == "suggested" and a["alerts"]
                   and a["red_flag_screening"]["status"] == "partially_evaluated"), None)
sugg_plain = [(c, dp) for (c, dp), a in responses.items() if a["status"] == "suggested" and not a["alerts"]]
abst = [(c, dp) for (c, dp), a in responses.items() if a["status"] == "abstained"]
stats["review_case_alert"] = str(sugg_alert)
SENT = "SENTINEL-REASON-7f3a"


def new_assessment(c, dp):
    return phys.post(f"/api/care/cases/{c}/assess", json={"decision_point": dp}).json()


def n_review_rows(aid):
    con = sqlite3.connect(DB)
    try:
        return con.execute("select count(*) from care_reviews where assessment_id=?", (aid,)).fetchone()[0]
    finally:
        con.close()


# 3 actions x 2 conditions (no alert ack; no screening ack)
c, dp = sugg_alert
for action in ("confirm", "edit", "reject"):
    for cond in ("no_alert_ack", "no_screening_ack"):
        a = new_assessment(c, dp)
        alert_ids = [x["rule_id"] for x in a["alerts"]]
        body = {"acknowledged_alert_ids": [] if cond == "no_alert_ack" else alert_ids,
                "screening_acknowledged": cond != "no_screening_ack", "reason": SENT,
                "next_information": [a["next_information"][0]["code"]] if a["next_information"] else [],
                "pathway_options": [a["pathway_options"][0]["code"]] if a["pathway_options"] else []}
        before = max_audit_id()
        rr = phys.post(f"/api/care/assessments/{a['assessment_id']}/{action}", json=body)
        den = [x for x in audit_rows("id > ?", (before,)) if x[1] == "care.review.denied"]
        if rr.status_code != 409 or n_review_rows(a["assessment_id"]) != 0 or len(den) != 1:
            fail(c + dp, f"A14 {action} {cond} -> 409, 0 rows, denied audited", (409, 0, 1),
                 (rr.status_code, n_review_rows(a["assessment_id"]), len(den)), f"POST /api/care/assessments/{{id}}/{action} {body}")
        else:
            stats["A14_ack_block_ok"] += 1

# /confirmed before review -> 404 pending_review
a = new_assessment(c, dp)
rr = phys.get(f"/api/care/cases/{c}/confirmed")
if rr.status_code != 404 or rr.json().get("detail") != "pending_review":
    fail(c, "A14 /confirmed pending before review", 404, (rr.status_code, rr.text[:200]))
alert_ids = [x["rule_id"] for x in a["alerts"]]
before = max_audit_id()
rr = phys.post(f"/api/care/assessments/{a['assessment_id']}/confirm",
               json={"acknowledged_alert_ids": alert_ids, "screening_acknowledged": True})
rows = [x for x in audit_rows("id > ?", (before,)) if x[1] == "care.review.confirm"]
if rr.status_code != 200 or len(rows) != 1:
    fail(c + dp, "A14 confirm 200 + 1 audit row", (200, 1), (rr.status_code, len(rows), rr.text[:200]))
else:
    det = json.loads(rows[0][5])
    need = {"reviewer_id", "reviewer_role", "ts_utc", "original_suggestion", "final_codes", "acknowledged_alert_ids", "reason_sha256"}
    osug = det.get("original_suggestion", {})
    if not need <= set(det) or not {"status", "codes", "missing_information", "alert_rule_ids", "screening_status"} <= set(osug):
        fail(c + dp, "A14 confirm audit fields", sorted(need), sorted(det))
    elif not det["ts_utc"].endswith("+00:00") and not det["ts_utc"].endswith("Z"):
        fail(c + dp, "A14 UTC ts", "UTC", det["ts_utc"])
    else:
        stats["A14_confirm_audit_ok"] = 1
    if rows[0][4] != "physician" or det["reviewer_role"] != "physician":
        fail(c + dp, "A14 reviewer role", "physician", det.get("reviewer_role"))
rr = phys.get(f"/api/care/cases/{c}/confirmed")
if rr.status_code != 200 or rr.json()["assessment_id"] != a["assessment_id"]:
    fail(c, "A14 /confirmed after confirm", 200, (rr.status_code, rr.text[:200]))
else:
    stats["A14_confirmed_after_confirm"] = 1
# double review
before = max_audit_id()
rr = phys.post(f"/api/care/assessments/{a['assessment_id']}/reject",
               json={"acknowledged_alert_ids": alert_ids, "screening_acknowledged": True, "reason": SENT})
den = [x for x in audit_rows("id > ?", (before,)) if x[1] == "care.review.denied"]
if rr.status_code != 409 or len(den) != 1:
    fail(c + dp, "A14 double review 409 + denied", (409, 1), (rr.status_code, len(den)))
else:
    stats["A14_double_review_ok"] = 1
# newest-only: a newer assessment (by as_of or same as_of later created) makes /confirmed pending again
a_new = new_assessment(c, dp)
rr = phys.get(f"/api/care/cases/{c}/confirmed")
if rr.status_code != 404:
    fail(c, "A14 /confirmed reflects newest only", 404, (rr.status_code, rr.text[:200]))
else:
    stats["A14_newest_only"] = 1
# older decision point after confirm of newer does not displace it: confirm newest T2, then assess T1
alert_ids2 = [x["rule_id"] for x in a_new["alerts"]]
phys.post(f"/api/care/assessments/{a_new['assessment_id']}/confirm", json={"acknowledged_alert_ids": alert_ids2, "screening_acknowledged": True})
if dp == "T2":
    new_assessment(c, "T1")
    rr = phys.get(f"/api/care/cases/{c}/confirmed")
    stats["confirmed_after_older_T1_assess"] = rr.status_code

# edit on abstained
c2, dp2 = abst[0]
a = new_assessment(c2, dp2)
ids = [x["rule_id"] for x in a["alerts"]]
base = {"acknowledged_alert_ids": ids, "screening_acknowledged": True}
rr = phys.post(f"/api/care/assessments/{a['assessment_id']}/confirm", json=base)
stats["confirm_on_abstained"] = rr.status_code
if rr.status_code < 400 or n_review_rows(a["assessment_id"]):
    fail(c2 + dp2, "confirm on abstained refused", "4xx", rr.status_code)
rr = phys.post(f"/api/care/assessments/{a['assessment_id']}/edit", json={**base, "next_information": ["NI-LAB-WBC"]})
stats["edit_no_reason"] = rr.status_code
if rr.status_code != 422:
    fail(c2 + dp2, "edit requires reason", 422, rr.status_code)
rr = phys.post(f"/api/care/assessments/{a['assessment_id']}/edit", json={**base, "reason": SENT, "next_information": ["NI-BOGUS"]})
stats["edit_bad_code"] = rr.status_code
if rr.status_code != 422:
    fail(c2 + dp2, "edit requires vocab codes", 422, rr.status_code)
before = max_audit_id()
rr = phys.post(f"/api/care/assessments/{a['assessment_id']}/edit",
               json={**base, "reason": SENT, "next_information": ["NI-LAB-WBC"], "pathway_options": []})
rows = [x for x in audit_rows("id > ?", (before,)) if x[1] == "care.review.edit"]
if rr.status_code != 200 or len(rows) != 1 or json.loads(rows[0][5])["final_codes"] != {"next_information": ["NI-LAB-WBC"], "pathway_options": []}:
    fail(c2 + dp2, "A14 edit abstained -> 200 + audit final codes", 200, (rr.status_code, rr.text[:300]))
else:
    stats["A14_edit_ok"] = 1
rr = phys.get(f"/api/care/cases/{c2}/confirmed")
stats["confirmed_after_edit_status"] = rr.status_code

# reject
c3, dp3 = abst[1]
a = new_assessment(c3, dp3)
ids = [x["rule_id"] for x in a["alerts"]]
rr = phys.post(f"/api/care/assessments/{a['assessment_id']}/reject", json={"acknowledged_alert_ids": ids, "screening_acknowledged": True})
stats["reject_no_reason"] = rr.status_code
if rr.status_code != 422:
    fail(c3 + dp3, "reject requires reason", 422, rr.status_code)
before = max_audit_id()
rr = phys.post(f"/api/care/assessments/{a['assessment_id']}/reject", json={"acknowledged_alert_ids": ids, "screening_acknowledged": True, "reason": SENT})
rows = [x for x in audit_rows("id > ?", (before,)) if x[1] == "care.review.reject"]
if rr.status_code != 200 or len(rows) != 1 or json.loads(rows[0][5])["final_codes"] is not None:
    fail(c3 + dp3, "A14 reject -> 200 + audit final null", 200, (rr.status_code, rr.text[:300]))
else:
    stats["A14_reject_ok"] = 1
rr = phys.get(f"/api/care/cases/{c3}/confirmed")
if rr.status_code != 404 or rr.json().get("detail") != "pending_review":
    fail(c3, "A14 /confirmed after reject -> 404 pending_review", 404, (rr.status_code, rr.text[:200]))
else:
    stats["A14_confirmed_after_reject_404"] = 1

# ---------------------------------------------------------------- A15 role matrix
aid = a["assessment_id"]
endpoints = [("GET", "/api/care/cases", None), ("GET", "/api/care/vocabulary", None),
             ("POST", f"/api/care/cases/{dev_ids[0]}/assess", {"decision_point": "T1"}),
             ("GET", f"/api/care/assessments/{aid}", None),
             ("POST", f"/api/care/assessments/{aid}/confirm", {}),
             ("POST", f"/api/care/assessments/{aid}/edit", {}),
             ("POST", f"/api/care/assessments/{aid}/reject", {}),
             ("GET", f"/api/care/cases/{dev_ids[0]}/confirmed", None)]
for role, cl, exp in (("nurse", nurse, 403), ("pharmacist", pharm, 403), ("anon", anon, 401)):
    for meth, path, body in endpoints:
        before = max_audit_id()
        rr = cl.request(meth, path, json=body)
        den = [x for x in audit_rows("id > ?", (before,)) if x[1] == "care.review.denied"]
        other = [x for x in audit_rows("id > ?", (before,)) if x[1] in ("care.assess", "gateway.invoke")]
        if rr.status_code != exp or len(den) != 1 or other:
            fail("-", f"A15 {role} {meth} {path}", (exp, "1 denial audit", "0 assess"), (rr.status_code, len(den), len(other)), f"{meth} {path}")
        else:
            stats["A15_denials_ok"] += 1
# physician 2xx on read endpoints
for meth, path, body in endpoints[:4]:
    rr = phys.request(meth, path, json=body)
    if rr.status_code // 100 != 2:
        fail("-", f"A15 physician {meth} {path}", "2xx", rr.status_code)
    else:
        stats["A15_physician_2xx"] += 1

# ---------------------------------------------------------------- A14 sentinel + transcript text not in audit
all_audit = "\n".join(x[5] for x in audit_rows())
stats["audit_rows_total"] = len(audit_rows())
if SENT in all_audit:
    fail("-", "A14 sentinel reason not in audit", 0, all_audit.count(SENT))
turn_texts = set()
for cid in dev_ids:
    for dp in ("T1", "T2"):
        snap = json.loads((DS / "inputs" / "dev" / cid / f"snapshot_{dp}.json").read_text("utf-8"))
        for it in snap["items"]:
            if it["data_type"] == "IntakeTranscript":
                turn_texts |= {t["text"] for t in it["turns"] if t["speaker"] == "patient" and len(t["text"]) >= 6}
leaked = [t for t in turn_texts if t in all_audit or json.dumps(t)[1:-1] in all_audit]
stats["transcript_texts_checked"] = len(turn_texts)
if leaked:
    fail("-", "A14 transcript text not in audit", 0, leaked[:3])

# ---------------------------------------------------------------- append-only on the live DB
con = sqlite3.connect(DB)
for tbl in ("care_assessments", "care_reviews"):
    for stmt in (f"update {tbl} set rowid=rowid", f"delete from {tbl}"):
        try:
            con.execute(stmt)
            con.commit()
            fail("-", f"A14 {tbl} append-only", "rejected", f"{stmt} succeeded")
        except sqlite3.DatabaseError:
            stats["append_only_rejections"] += 1
con.close()

res = {"stats": dict(stats), "failures": fails,
       "live_selective_hit3": (hits / answered) if answered else None}
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res["stats"], ensure_ascii=False, indent=1))
print("live selective hit@3", res["live_selective_hit3"], "failures", len(fails))
for f in fails[:30]:
    print(json.dumps(f, ensure_ascii=False)[:500])
