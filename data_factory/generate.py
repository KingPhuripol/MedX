"""Seeded synthetic case factory (slice s1). Synthetic reference data for system evaluation only.

Order is fixed: roster -> patient split (splits.json written) -> scenario strata per split -> cases -> gold.
Randomness: one ``random.Random(seed)`` for roster/split/strata; one child RNG per patient derived from
``(seed, patient_ref)``. No wall clock, ``hash()``, set ordering, network, or LLM calls.
"""

from __future__ import annotations

import hashlib
import json
import random
import unicodedata
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path

from casegraph import evidence_adapter

GENERATOR_VERSION = "s1-1.0.0"
PKG_DIR = Path(__file__).resolve().parent
TEMPLATES = PKG_DIR / "templates"
TZ = timezone(timedelta(hours=7))
BASE_DATE = datetime(2030, 1, 1, tzinfo=TZ)
SPLITS = ("train", "dev", "test")
N_PATIENTS, N_REVISIT = 180, 20
SPLIT_SIZES = {"train": 108, "dev": 36, "test": 36}
REVISIT_SPLIT = {"train": 12, "dev": 4, "test": 4}  # stratify revisit patients so case shares stay 60/20/20

# Scenario quotas (fractions, spread evenly over each split's shuffled case order). Not used by the split.
QUOTAS = {
    "red_flag": "1/4",
    "missing_info": "1/5",
    "no_medication": "1/10",
    "late_items": "7/20",
    "near_miss_of_non_red_flag": "1/5",
    "injected_of_medication": "3/5",
}
RULE_CYCLE = ("RF-QSOFA", "RF-NEWS-SINGLE3", "RF-FAST", "RF-ACUTE-CHEST-PAIN", "RF-THUNDERCLAP", "RF-ANAPHYLAXIS")
VITALS_RULES = ("RF-QSOFA", "RF-NEWS-SINGLE3")
MISSING_CYCLE = (("chief_complaint",), ("duration",), ("allergy_status",), ("duration", "allergy_status"))
ISSUE_TYPES = ("duplicate_therapy", "dose_mismatch", "frequency_mismatch", "omission", "allergy_conflict")
FREQ_TH = {"OD": "วันละ 1 ครั้ง", "BID": "วันละ 2 ครั้ง", "TID": "วันละ 3 ครั้ง", "QID": "วันละ 4 ครั้ง", "HS": "ก่อนนอน"}
UNIT_TH = {"mg": "มิลลิกรัม", "mcg": "ไมโครกรัม"}
DURATION_TH = {"hour": "ชั่วโมง", "day": "วัน", "week": "สัปดาห์"}
VITAL_PARAMS = ("sbp", "dbp", "hr", "rr", "temp_c", "spo2", "consciousness", "on_oxygen")


# ---------------------------------------------------------------- utilities
def _nfc(obj):
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, list):
        return [_nfc(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _nfc(v) for k, v in obj.items()}
    return obj


def load_templates() -> dict:
    names = ("complaints", "departments", "red_flags", "references", "formulary", "allergy_classes",
             "vitals_bands", "issue_types", "labs")
    return {n: _nfc(json.loads((TEMPLATES / f"{n}.json").read_text(encoding="utf-8"))) for n in names}


def dumps(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": ")) + "\n").encode()


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _hit(i: int, q: Fraction) -> bool:
    """Even spread: exactly floor(n*q) hits among indices 0..n-1."""
    return int((i + 1) * q) > int(i * q)


def source_code_sha256() -> str:
    h = hashlib.sha256()
    files = sorted(p for p in PKG_DIR.rglob("*") if p.is_file() and p.suffix in {".py", ".json"}
                   and "tests" not in p.relative_to(PKG_DIR).parts and "__pycache__" not in p.parts)
    for p in files:
        h.update(p.relative_to(PKG_DIR).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------- roster and split
def make_roster(seed: int, main: random.Random) -> list[dict]:
    revisit = set(main.sample(range(N_PATIENTS), N_REVISIT))
    roster, n_case = [], 0
    for i in range(N_PATIENTS):
        ref = f"SYNP-{i + 1:04d}"
        prng = random.Random(f"{seed}:{ref}")
        day0 = prng.randint(0, 300)
        days = [day0] + ([day0 + prng.randint(14, 60)] if i in revisit else [])
        cases = []
        for d in days:
            n_case += 1
            cases.append({"case_id": f"SYNE-{n_case:04d}", "day": d})
        roster.append({"patient_ref": ref, "sex": prng.choice(["female", "male"]), "age": prng.randint(18, 90),
                       "cases": cases})
    return roster


def make_splits(main: random.Random, roster: list[dict]) -> dict[str, str]:
    splits: dict[str, str] = {}
    for multi in (True, False):
        refs = [p["patient_ref"] for p in roster if (len(p["cases"]) > 1) == multi]
        main.shuffle(refs)
        start = 0
        for s in SPLITS:
            n = REVISIT_SPLIT[s] if multi else SPLIT_SIZES[s] - REVISIT_SPLIT[s]
            splits.update({r: s for r in refs[start:start + n]})
            start += n
    return dict(sorted(splits.items()))


# ---------------------------------------------------------------- strata (after the split)
def plan_cases(main: random.Random, roster: list[dict], splits: dict[str, str], tpl: dict, quotas: dict) -> list[dict]:
    q = {k: Fraction(v) for k, v in quotas.items()}
    complaints = tpl["complaints"]
    by_group = {g: [c for c in complaints if c["group"] == g] for g in ("general", "obstetric", "gynecologic")}
    hosts = [c for c in complaints if c["vitals_rf_host"]]
    text_cc = {c["red_flag_rule"]: c for c in complaints if c["group"] == "red_flag_text"}
    variants = {r: [v for v in tpl["vitals_bands"]["red_flag_variants"] if v["rule_id"] == r] for r in VITALS_RULES}
    near = tpl["vitals_bands"]["near_miss_variants"]
    patients = {p["patient_ref"]: p for p in roster}
    ctr = dict.fromkeys(("rf", "vit", "swap", "miss", "host", "gen", "ob", "gyn", "yf", "of", "near", "inj",
                         "var_q", "var_n"), 0)
    plans = []
    for split in SPLITS:
        cases = sorted((c["case_id"], p["patient_ref"]) for p in roster if splits[p["patient_ref"]] == split
                       for c in p["cases"])
        main.shuffle(cases)
        n_nonrf = n_med = 0
        for i, (case_id, ref) in enumerate(cases):
            pat = patients[ref]
            plan = {"case_id": case_id, "patient_ref": ref, "split": split, "red_flag": None, "near_miss": None,
                    "missing": [], "injections": [], "has_meds": not _hit(i, q["no_medication"]),
                    "late": _hit(i, q["late_items"])}
            if _hit(i, q["missing_info"]):
                plan["missing"] = list(MISSING_CYCLE[ctr["miss"] % len(MISSING_CYCLE)])
                ctr["miss"] += 1
            if _hit(i, q["red_flag"]):
                rule = RULE_CYCLE[ctr["rf"] % len(RULE_CYCLE)]
                ctr["rf"] += 1
                if "chief_complaint" in plan["missing"] and rule not in VITALS_RULES:
                    rule = VITALS_RULES[ctr["swap"] % 2]  # a text red flag needs the complaint to be stated
                    ctr["swap"] += 1
                rf = {"rule_id": rule, "onset": "T1", "variant": None}
                if rule in VITALS_RULES:
                    rf["onset"] = "T2" if ctr["vit"] % 2 else "T1"
                    ctr["vit"] += 1
                    key = "var_q" if rule == "RF-QSOFA" else "var_n"
                    rf["variant"] = variants[rule][ctr[key] % len(variants[rule])]["variant_id"]
                    ctr[key] += 1
                plan["red_flag"] = rf
            else:
                if _hit(n_nonrf, q["near_miss_of_non_red_flag"]):
                    plan["near_miss"] = near[ctr["near"] % len(near)]["variant_id"]
                    ctr["near"] += 1
                n_nonrf += 1
            # complaint template
            rf = plan["red_flag"]
            if rf and rf["rule_id"] not in VITALS_RULES:
                cc = text_cc[rf["rule_id"]]
            elif rf:
                cc = hosts[ctr["host"] % len(hosts)]
                ctr["host"] += 1
            else:
                group = "general"
                if pat["sex"] == "female" and pat["age"] <= 45:
                    group = ("obstetric", "gynecologic", "general")[ctr["yf"] % 3]
                    ctr["yf"] += 1
                elif pat["sex"] == "female":
                    group = "gynecologic" if ctr["of"] % 4 == 0 else "general"
                    ctr["of"] += 1
                key = {"general": "gen", "obstetric": "ob", "gynecologic": "gyn"}[group]
                cc = by_group[group][ctr[key] % len(by_group[group])]
                ctr[key] += 1
            plan["complaint_id"] = cc["id"]
            # medication discrepancy injections
            if plan["has_meds"]:
                if _hit(n_med, q["injected_of_medication"]):
                    k = ctr["inj"]
                    ctr["inj"] += 1
                    types = [ISSUE_TYPES[k % 5]] + ([ISSUE_TYPES[(k + 2) % 5]] if k % 4 == 3 else [])
                    if "allergy_status" in plan["missing"] and "allergy_conflict" in types:
                        types = [t for t in types if t != "allergy_conflict"] or ["dose_mismatch"]
                        if types == ["dose_mismatch"] and k % 4 == 3:
                            types = ["dose_mismatch", "omission"]
                    plan["injections"] = sorted(set(types), key=ISSUE_TYPES.index)
                n_med += 1
            plans.append(plan)
    return sorted(plans, key=lambda p: p["case_id"])


# ---------------------------------------------------------------- red-flag rule interpreter (labels)
def _vitals_ok(cond: dict, v: dict) -> bool:
    x = v.get(cond["param"])
    if x is None:
        return False
    op, val = cond["op"], cond["value"]
    return {"<=": lambda: x <= val, ">=": lambda: x >= val, "<": lambda: x < val, ">": lambda: x > val,
            "in": lambda: x in val}[op]()


def eval_criterion(crit: dict, items: list[dict]) -> tuple[bool, set[str]]:
    kind = crit["kind"]
    if kind == "vitals":
        ids = {it["item_id"] for it in items if it["data_type"] == "Vitals"
               and sum(_vitals_ok(c, it) for c in crit["conditions"]) >= crit["min_count"]}
        return bool(ids), ids
    if kind == "transcript":
        ids = set()
        for it in items:
            if it["data_type"] != "IntakeTranscript":
                continue
            text = " ".join(t["text"] for t in it["turns"] if t["speaker"] == crit["speaker"])
            if all(any(ph in text for ph in group) for group in crit["all_of"]):
                ids.add(it["item_id"])
        return bool(ids), ids
    results = [eval_criterion(c, items) for c in crit["of"]]
    if kind == "all":
        ok = all(r[0] for r in results)
        return ok, set().union(*(r[1] for r in results)) if ok else set()
    if kind == "any":
        return any(r[0] for r in results), set().union(*(r[1] for r in results if r[0]))
    raise ValueError(f"unknown criterion kind {kind}")


def red_flags_at(rules: list[dict], snapshot: list[dict]) -> list[dict]:
    out = []
    for rule in sorted(rules, key=lambda r: r["rule_id"]):
        ok, ids = eval_criterion(rule["criterion"], snapshot)
        if ok:
            out.append({"rule_id": rule["rule_id"], "item_ids": sorted(ids)})
    return out


# ---------------------------------------------------------------- case content
class _Case:
    def __init__(self, seed: int, plan: dict, pat: dict, day: int, tpl: dict):
        self.plan, self.pat, self.tpl = plan, pat, tpl
        self.rng = random.Random(f"{seed}:{plan['patient_ref']}:{plan['case_id']}")
        self.allergy_rng = random.Random(f"{seed}:{plan['patient_ref']}:allergy")
        self.cid = plan["case_id"]
        self.items: list[dict] = []
        self.cc = next(c for c in tpl["complaints"] if c["id"] == plan["complaint_id"])
        self.arrival = BASE_DATE + timedelta(days=day, hours=self.rng.randint(8, 15), minutes=self.rng.randint(0, 59))
        self.form = {f["generic_name"]: f for f in tpl["formulary"]}

    def item(self, suffix, data_type, source, event, observed, available, **body) -> dict:
        it = {"item_id": f"{self.cid}-{suffix}", "data_type": data_type, "patient_ref": self.plan["patient_ref"],
              "encounter_ref": self.cid, "event_time": iso(event), "observed_at": iso(observed),
              "available_at_time": iso(available), "source": source, "provenance": "synthetic",
              "version": GENERATOR_VERSION, **body}
        self.items.append(it)
        return it

    # -- vitals
    def _band(self, name):
        b = next(x for x in self.tpl["vitals_bands"]["normal"] if x["param"] == name)
        if isinstance(b["low"], float) or isinstance(b["high"], float):
            return round(self.rng.uniform(b["low"], b["high"]), 1)
        return self.rng.randint(b["low"], b["high"])

    def vitals_values(self, variant_set: dict | None, allow_null: bool) -> dict:
        fever = self.cc["fever"]
        v = {"sbp": self._band("sbp"), "hr": self._band("hr_fever" if fever else "hr"), "rr": self._band("rr"),
             "temp_c": self._band("temp_c_fever" if fever else "temp_c"), "spo2": self._band("spo2"),
             "consciousness": "A", "on_oxygen": False}
        if self.cc["id"] == "CC-RF-ANAPHYLAXIS":
            variant_set = {**self.tpl["vitals_bands"]["anaphylaxis_host"]["set"], **(variant_set or {})}
        for k, val in (variant_set or {}).items():
            if isinstance(val, str):
                v[k] = val
            elif isinstance(val[0], float) or isinstance(val[1], float):
                v[k] = round(self.rng.uniform(val[0], val[1]), 1)
            else:
                v[k] = self.rng.randint(val[0], val[1])
        v["dbp"] = v["sbp"] - self.rng.randint(35, 55)
        if allow_null and self.rng.random() < 0.08:
            v["temp_c"] = None  # not measured: stays null, never 0
        return {k: v[k] for k in VITAL_PARAMS}

    def variant(self, key, vid):
        return next(x for x in self.tpl["vitals_bands"][key] if x["variant_id"] == vid)["set"]

    # -- medications
    def entry(self, name, dose=None, freq=None) -> dict:
        f = self.form[name]
        return {"generic_name": name, "atc_code": f["atc_code"], "dose_value": dose if dose is not None else
                self.rng.choice(f["doses"]), "dose_unit": f["unit"], "frequency": freq or self.rng.choice(f["frequencies"]),
                "route": "PO"}

    def home_list(self) -> list[dict]:
        chronic = [f for f in self.tpl["formulary"] if f["role"] == "chronic"]
        injected = self.plan["injections"]
        k = self.rng.randint(2, 4) if injected else self.rng.randint(0, 4)
        names = [f["generic_name"] for f in chronic]
        self.rng.shuffle(names)
        if "duplicate_therapy" in injected:
            with_partner = [n for n in names if "duplicate_partner" in self.form[n]]
            names = [with_partner[0]] + [n for n in names if n != with_partner[0]]
        return [self.entry(n) for n in names[:k]]

    def med_text(self, entries, p) -> str:
        if not entries:
            return f"ไม่มียาที่ใช้ประจำ{p}"
        parts = [f"{e['generic_name']} {e['dose_value']:g} {UNIT_TH[e['dose_unit']]} {FREQ_TH[e['frequency']]}"
                 for e in entries]
        return "ใช้ยา " + " และ ".join(parts) + f" {p}"

    # -- build
    def build(self) -> tuple[dict, list[dict]]:
        plan, rng, cid, A = self.plan, self.rng, self.cid, self.arrival
        m = timedelta(minutes=1)
        missing = set(plan["missing"])
        p = "ครับ" if self.pat["sex"] == "male" else "ค่ะ"
        # allergy status: missing -> unknown; forced known for allergy_conflict; else per-patient draw
        classes = self.tpl["allergy_classes"]
        allergy_class = classes[self.allergy_rng.randrange(len(classes))]
        patient_known = self.allergy_rng.random() < 0.25
        if "allergy_status" in missing:
            allergy = "unknown"
        elif "allergy_conflict" in plan["injections"] or patient_known:
            allergy = "known"
        else:
            allergy = "no_known_allergy"

        self.item("DEMO", "Demographics", "synthetic-his/registration", A, A, A, age_years=self.pat["age"],
                  sex=self.pat["sex"])
        home = self.home_list() if plan["has_meds"] else None
        if home is not None:
            t = (A - timedelta(days=rng.randint(30, 365))).replace(hour=9, minute=rng.randint(0, 59))
            home_item = self.item("HOME", "MedicationList", "synthetic-his/prior-record", t, t, t + 60 * m,
                                  list_source="home_list", entries=home, derived_from=None)
        t = (A - timedelta(days=rng.randint(30, 720))).replace(hour=10, minute=rng.randint(0, 59))
        allergy_entries = ([{"substance": allergy_class["substance"], "atc_class": allergy_class["atc_class"],
                             "reaction": allergy_class["reaction"]}] if allergy == "known" else [])
        allergy_item = self.item("ALLERGY", "AllergyList", "synthetic-his/prior-record", t, t, t + 60 * m,
                                 status=allergy, entries=allergy_entries)

        # triage vitals
        rf, nm = plan["red_flag"], plan["near_miss"]
        vs1_set = self.variant("red_flag_variants", rf["variant"]) if rf and rf["variant"] and rf["onset"] == "T1" \
            else (self.variant("near_miss_variants", nm) if nm else None)
        self.item("VS1", "Vitals", "synthetic-triage", A + 5 * m, A + 6 * m, A + 7 * m,
                  **self.vitals_values(vs1_set, allow_null=not (rf or nm)))

        # Thai nurse-patient intake dialogue
        lo, hi = self.cc["duration_range"]
        dur_value = rng.randint(lo, hi)
        dur_th = f"{dur_value} {DURATION_TH[self.cc['duration_unit']]}"
        allergy_th = f"แพ้ยา{allergy_class['th']}" if allergy == "known" else "ไม่เคยแพ้ยา"
        lines = [("nurse", "สวัสดีค่ะ วันนี้มาด้วยอาการอะไรคะ"),
                 ("patient", (f"รู้สึกไม่ค่อยสบาย บอกไม่ถูกว่าเป็นอะไร{p}" if "chief_complaint" in missing
                              else f"{self.cc['th']}{p}"))]
        if "duration" not in missing:
            lines += [("nurse", "เป็นมานานเท่าไรแล้วคะ"), ("patient", f"เป็นมา {dur_th}{p}")]
        lines += [("nurse", "มียาที่ใช้ประจำไหมคะ"), ("patient", self.med_text(home or [], p))]
        if "allergy_status" not in missing:
            lines += [("nurse", "เคยแพ้ยาอะไรไหมคะ"), ("patient", f"{allergy_th}{p}")]
        lines += [("nurse", "ขอบคุณค่ะ กรุณานั่งรอสักครู่นะคะ"), ("patient", f"ได้{p} ขอบคุณ{p}")]
        t = A + 10 * m
        turns = []
        for idx, (spk, text) in enumerate(lines):
            t += timedelta(seconds=rng.randint(20, 70))
            turns.append({"turn_index": idx, "speaker": spk, "text": unicodedata.normalize("NFC", text),
                          "spoken_at": iso(t)})
        tx = self.item("TX", "IntakeTranscript", "synthetic-voice-intake", parse(turns[0]["spoken_at"]), t, t + m,
                       language="th", turns=turns)
        tx_avail = t + m
        if home is not None:
            self.item("PR", "MedicationList", "synthetic-voice-intake/extraction", tx_avail, tx_avail, tx_avail + 2 * m,
                      list_source="patient_reported", entries=[dict(e) for e in home], derived_from=tx["item_id"])
        T1 = tx_avail + 3 * m

        # labs, physician new order, repeat vitals
        labs = [x for x in self.tpl["labs"] if not x["late"]]
        coll, res = T1 + 15 * m, T1 + 55 * m
        self.item("LAB", "LabSeries", "synthetic-lis", coll, res, res + 5 * m,
                  results=[self.lab(x, coll, res) for x in labs[: rng.randint(2, len(labs))]])
        injections = []
        if home is not None:
            order_t = T1 + 30 * m
            new = [dict(e) for e in home]
            acute = self.acute_drug(home, allergy_entries)
            if acute and rng.random() < 0.5:
                new.append(self.entry(acute))
            new, injections = self.inject(new, home, allergy_entries, home_item, allergy_item)
            self.item("NO", "MedicationList", "synthetic-cpoe", order_t, order_t + m, order_t + 2 * m,
                      list_source="new_order", entries=new, derived_from=None)
        vs2_set = self.variant("red_flag_variants", rf["variant"]) if rf and rf["variant"] else None
        self.item("VS2", "Vitals", "synthetic-triage", T1 + 50 * m, T1 + 51 * m, T1 + 52 * m,
                  **self.vitals_values(vs2_set, allow_null=False))
        T2 = T1 + 90 * m
        if plan["late"]:
            late = next(x for x in self.tpl["labs"] if x["late"])
            res = T2 + timedelta(hours=rng.randint(3, 20))
            self.item("LATE", "LabSeries", "synthetic-lis", coll, res, res + 5 * m, results=[self.lab(late, coll, res)])
        for inj in injections:
            inj["item_ids"] = sorted(f"{cid}-{s}" for s in inj["item_ids"])

        self.items.sort(key=lambda it: (parse(it["available_at_time"]), it["item_id"]))
        journey = {"case_id": cid, "encounter_ref": cid, "patient_ref": plan["patient_ref"], "split": plan["split"],
                   "intake_point": "front_door", "arrival_time": iso(A), "decision_times": [iso(T1), iso(T2)],
                   "items": self.items}
        self.fields = {
            "chief_complaint": "MISSING" if "chief_complaint" in missing else
            {"code": self.cc["id"], "icd10cm": self.cc["icd10cm"], "th_text": self.cc["th"]},
            "duration": "MISSING" if "duration" in missing else
            {"value": dur_value, "unit": self.cc["duration_unit"], "th_text": dur_th},
            "allergy_status": "MISSING" if "allergy_status" in missing else {"value": allergy, "th_text": allergy_th},
        }
        return journey, injections

    def lab(self, x, coll, res) -> dict:
        lo, hi = x["range"]
        val = round(self.rng.uniform(lo, hi), x["decimals"])
        return {"test": x["test"], "value": float(val), "unit": x["unit"], "ref_low": float(x["ref_low"]),
                "ref_high": float(x["ref_high"]), "collected_at": iso(coll), "resulted_at": iso(res)}

    def acute_drug(self, home, allergy_entries) -> str | None:
        blocked3 = {a["atc_class"][:3] for a in allergy_entries}
        atc4 = {e["atc_code"][:5] for e in home}
        pool = [f["generic_name"] for f in self.tpl["formulary"] if f["role"] == "acute"
                and f["atc_code"][:3] not in blocked3 and f["atc_code"][:5] not in atc4]
        return self.rng.choice(pool) if pool else None

    def inject(self, new, home, allergy_entries, home_item, allergy_item):
        """Apply planned discrepancies to the new order; every change is logged as a gold label."""
        rng, cid = self.rng, self.cid
        targets = [e["generic_name"] for e in home]
        rng.shuffle(targets)
        types = self.plan["injections"]
        if "duplicate_therapy" in types:  # the partner-bearing drug is reserved for the duplicate
            dup = next(n for n in targets if "duplicate_partner" in self.form[n])
            targets = [n for n in targets if n != dup] + [dup]
        log = []
        for n, itype in enumerate(types, start=1):
            rec = {"injection_id": f"INJ-{cid}-{n}", "case_id": cid, "issue_type": itype}
            if itype == "duplicate_therapy":
                base = targets.pop()
                partner = self.form[base]["duplicate_partner"]
                new.append(self.entry(partner))
                rec.update(drugs=sorted([base, partner]), item_ids=["NO"], list_sources=["new_order"],
                           field="entries", value_before=None, value_after=partner)
            elif itype == "allergy_conflict":
                probe = next(a for a in self.tpl["allergy_classes"] if a["atc_class"] == allergy_entries[0]["atc_class"])
                drug = probe["probe_drug"]
                new.append(self.entry(drug))
                rec.update(drugs=[drug], item_ids=["ALLERGY", "NO"], list_sources=["new_order"],
                           field="entries", value_before=None, value_after=drug)
            else:
                name = targets.pop(0)
                idx = next(i for i, e in enumerate(new) if e["generic_name"] == name)
                e = new[idx]
                sources = ["home_list", "patient_reported", "new_order"]
                if itype == "omission":
                    del new[idx]
                    rec.update(field="entries", value_before=name, value_after=None)
                elif itype == "dose_mismatch":
                    alts = [d for d in self.form[name]["doses"] if d != e["dose_value"]] or [e["dose_value"] * 2]
                    after = rng.choice(alts)
                    rec.update(field="dose_value", value_before=e["dose_value"], value_after=after)
                    new[idx] = {**e, "dose_value": after}
                else:
                    after = rng.choice([f for f in ("OD", "BID", "TID") if f != e["frequency"]])
                    rec.update(field="frequency", value_before=e["frequency"], value_after=after)
                    new[idx] = {**e, "frequency": after}
                rec.update(drugs=[name], item_ids=["HOME", "PR", "NO"], list_sources=sources)
            log.append(rec)
        return new, log


# ---------------------------------------------------------------- gold labels
def gold_for(case: _Case, journey: dict, injections: list[dict], rules: list[dict]) -> dict:
    rows = []
    cc_dept = case.cc["department"]
    for label, T in zip(("T1", "T2"), journey["decision_times"]):
        snap = snapshot(journey, T)
        flags = red_flags_at(rules, snap)
        visible = {it["item_id"] for it in snap}
        issues = [{"injection_id": r["injection_id"], "issue_type": r["issue_type"], "drugs": r["drugs"],
                   "item_ids": r["item_ids"]} for r in injections if f"{case.cid}-NO" in visible]
        any_missing = any(v == "MISSING" for v in case.fields.values())
        action = "escalate" if flags else ("abstain" if any_missing else "suggest")
        rows.append({"decision_point": label, "T": T, "target_department": "12" if flags else cc_dept,
                     "red_flags": flags, "required_fields": case.fields, "medication_issues": issues,
                     "expected_action": action})
    return {"case_id": case.cid, "patient_ref": case.plan["patient_ref"], "split": case.plan["split"],
            "label_version": GENERATOR_VERSION,
            "label_status": "synthetic reference labels from predeclared rules; not clinical ground truth; not expert-reviewed",
            "scenario": {k: case.plan[k] for k in ("complaint_id", "red_flag", "near_miss", "missing", "has_meds",
                                                   "injections", "late")},
            "decision_times": rows}


def snapshot(journey: dict, T: str) -> list[dict]:
    cut = parse(T)
    return [it for it in journey["items"] if parse(it["available_at_time"]) <= cut]


# ---------------------------------------------------------------- output
def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def validate_item(it: dict) -> None:
    evidence_adapter.validate_python(it)
    if it["provenance"] != "synthetic":
        raise ValueError(f"{it['item_id']}: provenance must be 'synthetic'")


def generate(seed: int, out: Path, splits_only: bool = False, quotas: dict | None = None) -> dict | None:
    out = Path(out)
    tpl = load_templates()
    main = random.Random(seed)
    roster = make_roster(seed, main)
    splits = make_splits(main, roster)
    _write(out / "splits.json", dumps(splits))  # written before any case exists
    if splits_only:
        return None
    plans = plan_cases(main, roster, splits, tpl, quotas or QUOTAS)
    patients = {p["patient_ref"]: p for p in roster}
    days = {c["case_id"]: c["day"] for p in roster for c in p["cases"]}
    rules = tpl["red_flags"]
    all_injections, golds = [], []
    for plan in plans:
        case = _Case(seed, plan, patients[plan["patient_ref"]], days[plan["case_id"]], tpl)
        journey, injections = case.build()
        for it in journey["items"]:
            validate_item(it)
        base = out / "inputs" / plan["split"] / case.cid
        _write(base / "journey.json", dumps(journey))
        for label, T in zip(("T1", "T2"), journey["decision_times"]):
            snap = {"case_id": case.cid, "encounter_ref": case.cid, "patient_ref": plan["patient_ref"],
                    "intake_point": "front_door", "as_of": T, "items": snapshot(journey, T)}
            _write(base / f"snapshot_{label}.json", dumps(snap))
        gold = gold_for(case, journey, injections, rules)
        _write(out / "gold" / plan["split"] / f"{case.cid}.json", dumps(gold))
        all_injections += injections
        golds.append(gold)
    _write(out / "gold" / "injection_log.jsonl",
           b"".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
                    for r in all_injections))
    counts = summarize(plans, golds, all_injections, splits)
    _write(out / "DATACARD.md", datacard(seed, counts).encode())
    return write_manifest(out, seed, counts)


def summarize(plans, golds, injections, splits) -> dict:
    def tally(values):
        out: dict = {}
        for v in values:
            out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items()))

    rows = [r for g in golds for r in g["decision_times"]]
    return {
        "patients": len(splits),
        "patients_per_split": tally(splits.values()),
        "cases": len(plans),
        "cases_per_split": tally(p["split"] for p in plans),
        "revisit_patients": sum(1 for r in tally(p["patient_ref"] for p in plans).values() if r > 1),
        "case_x_T": len(rows),
        "red_flag_cases": sum(1 for g in golds if any(r["red_flags"] for r in g["decision_times"])),
        "red_flag_rule_uses": tally(f["rule_id"] for g in golds for f in g["decision_times"][-1]["red_flags"]),
        "missing_info_cases": sum(1 for p in plans if p["missing"]),
        "expected_action_T1": tally(g["decision_times"][0]["expected_action"] for g in golds),
        "expected_action_T2": tally(g["decision_times"][-1]["expected_action"] for g in golds),
        "target_department_T2": tally(g["decision_times"][-1]["target_department"] for g in golds),
        "medication_cases": sum(1 for p in plans if p["has_meds"]),
        "clean_medication_cases": sum(1 for p in plans if p["has_meds"] and not p["injections"]),
        "injections_per_type": tally(r["issue_type"] for r in injections),
        "cases_with_late_items": sum(1 for p in plans if p["late"]),
    }


def datacard(seed: int, counts: dict) -> str:
    return f"""# DATACARD — synthetic case factory v1 ({GENERATOR_VERSION})

**synthetic, not for clinical use, not expert-reviewed, system evaluation only.**

- Every patient, encounter, dialogue, vital sign, lab and medication list here is generated from templates by a
  seeded program (seed `{seed}`). No real patient records or external clinical databases were used.
- Labels are *synthetic reference labels* computed from predeclared rules (`data_factory/templates/`); they are
  not clinical ground truth and have not been reviewed by clinical experts (pending decision D1).
- Adults 18-95 only. No names, dates of birth, addresses, phone numbers or national IDs.

## Label rules
- `red_flags`: rules in `red_flags.json` (qSOFA PMID 26903335; NEWS single-parameter 3 PMID 23295778; FAST
  PMID 12511753; acute chest pain PMID 34709879; thunderclap PMID 24065011; anaphylaxis PMID 16461139),
  evaluated over the snapshot at each decision time.
- `target_department`: SIL-TH cs-chi-clinic v0.1.2 code; `12` whenever a red flag is present, else the complaint
  template's department (synthetic map pending expert review).
- `expected_action`: `escalate` if any red flag, else `abstain` if any required intake field is missing, else
  `suggest`.
- `medication_issues`: deliberately injected discrepancies (AHRQ MATCH; ASHP 2021), each logged in
  `gold/injection_log.jsonl`; present only at decision times where the new order is available.

## Leakage controls
Patients are split before cases are generated (`splits.json`). Snapshot at T contains only items with
`available_at_time <= T`. Gold lives only under `gold/`.

## Counts
```
{json.dumps(counts, indent=2, sort_keys=True)}
```
"""


def write_manifest(out: Path, seed: int, counts: dict) -> dict:
    files = {}
    for p in sorted(out.rglob("*")):
        rel = p.relative_to(out).as_posix()
        if p.is_file() and rel != "manifest.json" and not rel.endswith("audit_report.json"):
            files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    tree = hashlib.sha256("".join(f"{k}\t{v}\n" for k, v in files.items()).encode()).hexdigest()
    manifest = {"seed": seed, "generator_version": GENERATOR_VERSION, "source_code_sha256": source_code_sha256(),
                "counts": counts, "split_sizes": counts["patients_per_split"], "files": files, "tree_sha256": tree}
    _write(out / "manifest.json", dumps(manifest))
    return manifest
