"""s6 checker: in-process probes of the care engine over ALL splits (train+dev+test, T1+T2) plus adversarial
provider modes. Independent of the builder's tests; reads gold only to compare.

Usage: PYTHONPATH=backend:. python tests/e2e/s6_engine_probes.py <dataset_root> <out_json> [--outputs <jsonl>]
"""

from __future__ import annotations

import copy
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.care import engine
from app.care.snapshot import REQUIRED_INPUTS
from app.config import Settings
from app.gateway import build_provider
from app.gateway import service as gs
from app.gateway.contract import CONTRACT_VERSION, GatewayResponse
from casegraph.data import CareSuggestion, banner_for

DS = Path(sys.argv[1])
OUT = Path(sys.argv[2])
OUTPUTS = Path(sys.argv[sys.argv.index("--outputs") + 1]) if "--outputs" in sys.argv else None
PROVIDER = build_provider("mock", Settings())
CLAIM = re.compile(r"diagnos|prescrib|treat|dose|dosage|วินิจฉัย|สั่งยา|ให้ยา|รักษา", re.I)
fails: list[dict] = []
st: Counter = Counter()


def fail(cid, what, exp, act):
    fails.append({"case": cid, "check": what, "expected": exp, "actual": act})


class Inv:
    def __init__(self, fn=None):
        self.calls = 0
        self.fn = fn

    def __call__(self, req):
        self.calls += 1
        base = gs.invoke_provider(PROVIDER, req)
        return self.fn(base) if self.fn else base


def resp(base, **kw):
    d = base.model_dump()
    d.update(kw)
    return GatewayResponse(**d)


gold = []
for g in sorted((DS / "gold").glob("*/*.json")):
    d = json.loads(g.read_text("utf-8"))
    for r in d["decision_times"]:
        gold.append((d["split"], d["case_id"], r["decision_point"], r["care"], r["red_flags"]))


def snap(split, cid, dp):
    return json.loads((DS / "inputs" / split / cid / f"snapshot_{dp}.json").read_text("utf-8"))


outputs = []
for split, cid, dp, care, rflags in gold:
    doc = snap(split, cid, dp)
    items = {it["item_id"]: it for it in doc["items"]}
    as_of = datetime.fromisoformat(doc["as_of"])
    inv = Inv()
    res = engine.assess(doc, inv, decision_point=dp)
    j = json.loads(res.model_dump_json())
    outputs.append({"split": split, "case_id": cid, "dp": dp, "out": j})
    key = f"{split}/{cid}/{dp}"
    st["rows"] += 1
    st[f"{split}_rows"] += 1
    if list(j)[:4] != ["alerts", "red_flag_screening", "escalation_required", "status"]:
        fail(key, "A04 key order", "alerts,screening,escalation,status", list(j)[:4])
    if j["red_flag_screening"]["banner"] != banner_for(j["red_flag_screening"]["status"]):
        fail(key, "A04 banner", banner_for(j["red_flag_screening"]["status"]), j["red_flag_screening"]["banner"])
    if care["expected_action"] == "abstain":
        st["gold_abstain"] += 1
        if not (j["status"] == "abstained" and j["missing_information"] == care["required_inputs_missing"]
                and not j["case_summary"] and not j["next_information"] and not j["pathway_options"] and inv.calls == 0):
            fail(key, "A01", care["required_inputs_missing"], (j["status"], j["missing_information"], inv.calls))
        else:
            st["A01_ok"] += 1
    else:
        st["gold_suggest"] += 1
        if j["status"] == "abstained":
            fail(key, "A02 false abstention", "suggested", j["missing_information"])
        elif j["status"] != "suggested":
            fail(key, "suggest->status", "suggested", (j["status"], j["reason"]))
        else:
            st["A02_ok"] += 1
            if inv.calls != 1:
                fail(key, "A06 exactly one call", 1, inv.calls)
            try:
                p = CareSuggestion.model_validate(j["casegraph_projection"])
                exp = tuple([x["code"] for x in j["next_information"]] + [x["code"] for x in j["pathway_options"]])
                assert p.items == exp and p.red_flag_screening == j["red_flag_screening"]["status"]
                st["A07_ok"] += 1
            except Exception as e:  # noqa: BLE001
                fail(key, "A07", "valid projection", repr(e)[:200])
    for sect in ("case_summary", "next_information", "pathway_options"):
        for x in j[sect]:
            st["items"] += 1
            if not x["evidence_refs"]:
                fail(key, "A03 no refs", ">=1", 0)
            for r in x["evidence_refs"]:
                st["refs"] += 1
                it = items.get(r["item_id"])
                if it is None or datetime.fromisoformat(it["available_at_time"]) > as_of:
                    fail(key, "A03 ref", "in snapshot and <= T", r)
    if split in ("dev", "test"):
        m = CLAIM.search(json.dumps(j, ensure_ascii=False))
        if m:
            fail(key, "A16 claim term (engine output)", 0, m.group(0))
    # A13: unknown/absent never rendered negative/normal
    txt = " ".join(x["text"] for x in j["case_summary"])
    for bad in ("no allergy", "not pregnant", "normal", "negative", "none reported"):
        if bad in txt.lower() and "not read as" not in txt.lower():
            st[f"A13_phrase_{bad}"] += 1
    if any(v is None for v in [j.get("missing_information")]):
        fail(key, "A13 missing list", "list", None)

# ---------------------------------------------------------------- A05 provider cannot alter urgency (dev red-flag rows)
MODES = {
    "ok": None,
    "error": lambda b: resp(b, status="error", output=None, reason="forced_error"),
    "rejected": lambda b: resp(b, status="rejected", output=None, reason="forced_rejected"),
    "invalid": lambda b: resp(b, output={"next_information": "garbage"}),
    "clear_alerts": lambda b: resp(b, output={**(b.output or {}), "alerts": [], "escalation_required": False,
                                              "red_flag_screening": {"status": "evaluated"}}),
}
URG = ("alerts", "red_flag_screening", "escalation_required")
for split, cid, dp, care, rflags in gold:
    if split != "dev":
        continue
    doc = snap(split, cid, dp)
    base = engine.assess(doc, Inv(), decision_point=dp)
    if not base.alerts:
        continue
    st["A05_redflag_rows"] += 1
    ref = json.dumps({k: json.loads(base.model_dump_json())[k] for k in URG}, sort_keys=True)
    for name, fn in MODES.items():
        r = engine.assess(copy.deepcopy(doc), Inv(fn), decision_point=dp)
        cur = json.dumps({k: json.loads(r.model_dump_json())[k] for k in URG}, sort_keys=True)
        if cur != ref:
            fail(f"{cid}/{dp}", f"A05 mode {name}", "urgency identical", "changed")
        elif name != "ok" and base.status == "suggested" and (r.status != "error" or r.next_information or r.pathway_options):
            fail(f"{cid}/{dp}", f"A05/A06 mode {name} fail-safe", "error, 0 items", (r.status, len(r.next_information)))
        else:
            st["A05_mode_ok"] += 1

# ---------------------------------------------------------------- A06 timeout + provider exception, A03 bad refs
dev_sugg = next((s, c, d) for s, c, d, care, _ in gold if s == "dev" and care["expected_action"] == "suggest"
                and care["evaluable"])
doc = snap(*dev_sugg)
future_doc = copy.deepcopy(doc)
bad_modes = {
    "timeout": lambda b: resp(b, status="error", output=None, reason="timeout"),
    "ref_future": lambda b: resp(b, output={"next_information": [{"code": b.output["next_information"][0]["code"], "evidence_refs": ["FUTURE-ITEM"]}], "pathway_options": []}),
    "ref_unknown": lambda b: resp(b, output={"next_information": [{"code": b.output["next_information"][0]["code"], "evidence_refs": ["NOPE-1"]}], "pathway_options": []}),
    "ref_none": lambda b: resp(b, output={"next_information": [{"code": b.output["next_information"][0]["code"], "evidence_refs": []}], "pathway_options": []}),
    "code_outside_vocab": lambda b: resp(b, output={"next_information": [{"code": "NI-MADE-UP", "evidence_refs": [doc["items"][0]["item_id"]]}], "pathway_options": []}),
    "extra_field": lambda b: resp(b, output={**b.output, "summary": "x"}),
    "ref_to_other_case_item": lambda b: resp(b, output={"next_information": [{"code": b.output["next_information"][0]["code"], "evidence_refs": ["SYNE-9999-VS1"]}], "pathway_options": []}),
    "too_many": lambda b: resp(b, output={"next_information": [{"code": c, "evidence_refs": [doc["items"][0]["item_id"]]} for c in ["NI-LAB-WBC", "NI-LAB-HGB", "NI-LAB-CREAT", "NI-LAB-GLU", "NI-LAB-CRP", "NI-LAB-LACTATE"]], "pathway_options": []}),
}
for name, fn in bad_modes.items():
    r = engine.assess(copy.deepcopy(doc), Inv(fn), decision_point=dev_sugg[2])
    if r.status != "error" or r.next_information or r.pathway_options or r.case_summary:
        fail(f"{dev_sugg}", f"fail-safe {name}", "error, 0 items", (r.status, len(r.next_information), len(r.case_summary)))
    else:
        st["failsafe_ok"] += 1


class Boom:
    name = "boom"

    def invoke(self, request, sha):
        raise RuntimeError("boom")


r = engine.assess(copy.deepcopy(doc), lambda req: gs.invoke_provider(Boom(), req), decision_point=dev_sugg[2])
st["provider_exception_status"] = r.status
if r.status != "error" or r.next_information:
    fail("-", "provider exception fail-safe", "error", r.status)

# snapshot with a future item -> error (never silently dropped)
fd = copy.deepcopy(doc)
it = copy.deepcopy(next(i for i in fd["items"] if i["data_type"] == "Vitals"))
it["item_id"] = "FUTURE-ITEM"
for f in ("event_time", "observed_at", "available_at_time"):
    it[f] = "2099-01-01T00:00:00+07:00"
fd["items"].append(it)
r = engine.assess(fd, Inv(), decision_point=dev_sugg[2])
st["future_item_status"] = r.status
if r.status != "error":
    fail("-", "future item rejected", "error", r.status)

# ---------------------------------------------------------------- 13 fixtures (independent construction)
def drop(doc, name):
    d = copy.deepcopy(doc)
    if name.startswith("demographics."):
        k = {"demographics.age": "age_years", "demographics.sex": "sex"}[name]
        for i in d["items"]:
            if i["data_type"] == "Demographics":
                i[k] = None
    elif name == "chief_complaint" or name == "duration":
        q = {"chief_complaint": "อาการอะไร", "duration": "นานเท่าไร"}[name]
        for i in d["items"]:
            if i["data_type"] == "IntakeTranscript":
                i["turns"] = [t for t in i["turns"] if not (t["speaker"] == "nurse" and q in t["text"])]
    elif name == "allergy_status":
        d["items"] = [i for i in d["items"] if i["data_type"] != "AllergyList"]
    elif name == "allergy_unknown":
        for i in d["items"]:
            if i["data_type"] == "AllergyList":
                i["status"], i["entries"] = "unknown", []
    else:
        p = name.split(".")[1]
        for i in d["items"]:
            if i["data_type"] == "Vitals":
                i[p] = None
    return d


for name in [*REQUIRED_INPUTS, "allergy_unknown"]:
    r = engine.assess(drop(doc, name), Inv(), decision_point=dev_sugg[2])
    exp = ["allergy_status" if name == "allergy_unknown" else name]
    if r.status != "abstained" or r.missing_information != exp:
        fail(name, "A01 fixture", exp, (r.status, r.missing_information, r.reason))
    else:
        st["A01_fixtures_ok"] += 1
st["required_inputs"] = ",".join(REQUIRED_INPUTS)

# ---------------------------------------------------------------- A13 probe: allergy unknown + always-answer rendering
d_unk = drop(doc, "allergy_unknown")
r = engine.assess(d_unk, Inv(), decision_point=dev_sugg[2], abstain=False)
txt = " ".join(x.text for x in r.case_summary)
st["always_answer_unknown_allergy_line"] = next((x.text for x in r.case_summary if "Allergy" in x.text), None)
if "no known allergy" in txt:
    fail("-", "A13 unknown allergy rendered negative", "not negative", txt)

if OUTPUTS:
    OUTPUTS.write_text("\n".join(json.dumps(o, ensure_ascii=False, sort_keys=True) for o in outputs) + "\n", "utf-8")
OUT.write_text(json.dumps({"stats": dict(st), "failures": fails}, ensure_ascii=False, indent=1))
print(json.dumps(dict(st), ensure_ascii=False, indent=1))
print("failures", len(fails))
for f in fails[:40]:
    print(json.dumps(f, ensure_ascii=False)[:400])
