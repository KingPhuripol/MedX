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

from casegraph.data import EVIDENCE_ADAPTER

GENERATOR_VERSION = "1.2.2"
# v1.2.2 (slice s6r, ruling D-s6r-2) changes the held-out mode only: pregnancy becomes a controlled quota
# (``HELDOUT["pregnancy_cases"]``). Default-mode output is byte-identical to v1.2.1 (same tree_sha256), so it keeps
# the v1.2.1 stamp in gold ``label_version``, DATACARD and manifest ``output_version``.
V1_OUTPUT_VERSION = "1.2.1"
# v1.2.1 (slice s6r) is additive: a held-out mode (``--heldout``) with its own identity namespace that writes only
# the test split. At any seed without ``--heldout`` every inputs/** file is byte-identical to v1.2.0 and the gold is
# identical except ``label_version``.
# v1.2.0 adds gold labels only (`care`); every inputs/** file stays byte-identical to v1.1.1, so input items
# keep the item version they were generated with.
ITEM_VERSION = "1.1.1"
PKG_DIR = Path(__file__).resolve().parent
TEMPLATES = PKG_DIR / "templates"
TZ = timezone(timedelta(hours=7))
BASE_DATE = datetime(2030, 1, 1, tzinfo=TZ)
SPLITS = ("train", "dev", "test")
N_PATIENTS, N_REVISIT = 180, 20
SPLIT_SIZES = {"train": 108, "dev": 36, "test": 36}
REVISIT_SPLIT = {"train": 12, "dev": 4, "test": 4}  # stratify revisit patients so case shares stay 60/20/20
# s6r held-out set: 72 patients (8 revisit, 80 cases), test split only, patients SYNH-NNNN, cases SYNHE-NNNN
# (disjoint by construction from SYNP-/SYNE-). Fixed in slices/s6r/SPEC.md before any held-out data existed.
HELDOUT = {"n_patients": 72, "n_revisit": 8, "patient_prefix": "SYNH", "case_prefix": "SYNHE",
           "split_sizes": {"train": 0, "dev": 0, "test": 72}, "revisit_split": {"train": 0, "dev": 0, "test": 8},
           # v1.2.2 (D-s6r-2): obstetric (pregnant) cases capped at 2 x the v1 test count (1); later obstetric slots
           # take a general complaint. Fixed before any held-out prediction or result was seen.
           "pregnancy_cases": 2}

# Scenario quotas (fractions, spread evenly over each split's shuffled case order). Not used by the split.
QUOTAS = {
    "red_flag": "3/10",
    "missing_info": "1/5",
    "no_medication": "1/10",
    "late_items": "7/20",
    "near_miss_of_non_red_flag": "1/5",
    "text_near_miss_of_plain": "1/3",
    "arrival_tamtee_per_stratum": "1/3",
    "injected_of_medication": "3/5",
}
RULE_CYCLE = ("RF-QSOFA", "RF-NEWS-SINGLE3", "RF-FAST", "RF-ACUTE-CHEST-PAIN", "RF-THUNDERCLAP", "RF-ANAPHYLAXIS",
              "RF-NEWS-AGG5")
VITALS_RULES = ("RF-QSOFA", "RF-NEWS-SINGLE3", "RF-NEWS-AGG5")
TNM_CYCLE = ("TNM-CHEST-STABLE", "TNM-HEADACHE-GRADUAL", "TNM-NUMB-BILATERAL", "TNM-URTICARIA-ONLY",
             "TNM-DEFICIT-CHRONIC")
# Strata for the arrival-turn quota: the ทันที arrival variant is assigned at the same rate in every stratum.
STRATA = ("text_rf", "vitals_rf", "vitals_nm", "text_nm", "ordinary")
# Answers to the fixed nurse question about arrival. The TAMTEE ones use ทันที only in a travel/arrival sense.
ARRIVAL_PLAIN = ("มาคนเดียว", "ลูกพามา", "เพื่อนขับรถมาส่ง")
ARRIVAL_TAMTEE = ("ลูกพามาทันทีหลังเลิกงาน", "นั่งรถมาทันทีหลังเลิกงาน")
MODEL_INPUTS_GLOB = "inputs/*/*/snapshot_T*.json"
AUDIT_ONLY_GLOBS = ["inputs/*/*/journey.json", "gold/**"]
MISSING_CC_RF_EVERY = 3  # every 3rd missing-chief-complaint case (0, 3, 6, ...) carries a vitals red flag (D4)
MISSING_CYCLE = (("chief_complaint",), ("duration",), ("allergy_status",), ("duration", "allergy_status"))
ISSUE_TYPES = ("duplicate_therapy", "dose_mismatch", "frequency_mismatch", "omission", "allergy_conflict")
FREQ_TH = {"OD": "วันละ 1 ครั้ง", "BID": "วันละ 2 ครั้ง", "TID": "วันละ 3 ครั้ง", "QID": "วันละ 4 ครั้ง", "HS": "ก่อนนอน"}
UNIT_TH = {"mg": "มิลลิกรัม", "mcg": "ไมโครกรัม"}
DURATION_TH = {"minute": "นาที", "hour": "ชั่วโมง", "day": "วัน", "week": "สัปดาห์", "month": "เดือน", "year": "ปี"}
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
             "vitals_bands", "issue_types", "labs", "pregnancy_exclusions", "next_info_codes", "care_pathways",
             "care_next_info", "care_required_inputs")
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


def tree_sha256(files: dict, model_inputs_glob: str, audit_only_globs: list) -> str:
    """Manifest hash over per-file hashes plus the model-input / audit-only globs."""
    text = "".join(f"{k}\t{v}\n" for k, v in files.items())
    text += f"model_inputs_glob\t{model_inputs_glob}\naudit_only_globs\t{json.dumps(audit_only_globs)}\n"
    return hashlib.sha256(text.encode()).hexdigest()


def source_code_sha256() -> str:
    h = hashlib.sha256()
    files = sorted(p for p in PKG_DIR.rglob("*") if p.is_file() and p.suffix in {".py", ".json"}
                   and "tests" not in p.relative_to(PKG_DIR).parts and "__pycache__" not in p.parts)
    for p in files:
        h.update(p.relative_to(PKG_DIR).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------- roster and split
def make_roster(seed: int, main: random.Random, n_patients: int = N_PATIENTS, n_revisit: int = N_REVISIT,
                patient_prefix: str = "SYNP", case_prefix: str = "SYNE") -> list[dict]:
    revisit = set(main.sample(range(n_patients), n_revisit))
    roster, n_case = [], 0
    for i in range(n_patients):
        ref = f"{patient_prefix}-{i + 1:04d}"
        prng = random.Random(f"{seed}:{ref}")
        day0 = prng.randint(0, 300)
        days = [day0] + ([day0 + prng.randint(14, 60)] if i in revisit else [])
        cases = []
        for d in days:
            n_case += 1
            cases.append({"case_id": f"{case_prefix}-{n_case:04d}", "day": d})
        roster.append({"patient_ref": ref, "sex": prng.choice(["female", "male"]), "age": prng.randint(18, 90),
                       "cases": cases})
    return roster


def make_splits(main: random.Random, roster: list[dict], sizes: dict | None = None,
                revisit_sizes: dict | None = None) -> dict[str, str]:
    sizes, revisit_sizes = sizes or SPLIT_SIZES, revisit_sizes or REVISIT_SPLIT
    splits: dict[str, str] = {}
    for multi in (True, False):
        refs = [p["patient_ref"] for p in roster if (len(p["cases"]) > 1) == multi]
        main.shuffle(refs)
        start = 0
        for s in SPLITS:
            n = revisit_sizes[s] if multi else sizes[s] - revisit_sizes[s]
            splits.update({r: s for r in refs[start:start + n]})
            start += n
    return dict(sorted(splits.items()))


# ---------------------------------------------------------------- strata (after the split)
def plan_cases(main: random.Random, roster: list[dict], splits: dict[str, str], tpl: dict, quotas: dict,
               pregnancy_cap: int | None = None) -> list[dict]:
    q = {k: Fraction(v) for k, v in quotas.items()}
    complaints = tpl["complaints"]
    by_group = {g: [c for c in complaints if c["group"] == g and "near_miss_family" not in c]
                for g in ("general", "obstetric", "gynecologic")}
    hosts = [c for c in complaints if c["vitals_rf_host"]]
    text_cc: dict[str, list] = {}
    for c in complaints:
        if c["group"] == "red_flag_text":
            text_cc.setdefault(c["red_flag_rule"], []).append(c)
    tnm_cc: dict[str, list] = {}
    for c in complaints:
        if "near_miss_family" in c:
            tnm_cc.setdefault(c["near_miss_family"], []).append(c)
    variants = {r: [v for v in tpl["vitals_bands"]["red_flag_variants"] if v["rule_id"] == r] for r in VITALS_RULES}
    near = tpl["vitals_bands"]["near_miss_variants"]
    patients = {p["patient_ref"]: p for p in roster}
    ctr = dict.fromkeys(("rf", "vit", "swap", "miss", "host", "gen", "ob", "gyn", "yf", "of", "near", "inj",
                         "var_q", "var_n", "var_a", "tnm", "ccm", "ccm_vit", "preg"), 0)
    ctr_rule = dict.fromkeys(RULE_CYCLE, 0)
    ctr_unit = dict.fromkeys(RULE_CYCLE, 0)
    ctr_arr = dict.fromkeys(STRATA, 0)
    ctr_tnm = dict.fromkeys(TNM_CYCLE, 0)
    plans = []
    for split in SPLITS:
        cases = sorted((c["case_id"], p["patient_ref"]) for p in roster if splits[p["patient_ref"]] == split
                       for c in p["cases"])
        main.shuffle(cases)
        n_nonrf = n_med = n_plain = 0
        for i, (case_id, ref) in enumerate(cases):
            pat = patients[ref]
            plan = {"case_id": case_id, "patient_ref": ref, "split": split, "red_flag": None, "near_miss": None,
                    "text_near_miss": None, "missing": [], "injections": [],
                    "has_meds": not _hit(i, q["no_medication"]), "late": _hit(i, q["late_items"]),
                    "arrival_tamtee": False, "duration_idx": 0}
            if _hit(i, q["missing_info"]):
                plan["missing"] = list(MISSING_CYCLE[ctr["miss"] % len(MISSING_CYCLE)])
                ctr["miss"] += 1
            cc_missing = "chief_complaint" in plan["missing"]
            if cc_missing:
                # D4 path: a fixed share of missing-complaint cases carry a vitals red flag (a text red flag needs
                # the complaint stated), with onset alternating T1/T2; the others carry none.
                rf_hit = ctr["ccm"] % MISSING_CC_RF_EVERY == 0
                ctr["ccm"] += 1
            else:
                rf_hit = _hit(i, q["red_flag"])
            if rf_hit:
                if cc_missing:
                    rule = VITALS_RULES[ctr["swap"] % len(VITALS_RULES)]
                    ctr["swap"] += 1
                else:
                    rule = RULE_CYCLE[ctr["rf"] % len(RULE_CYCLE)]
                    ctr["rf"] += 1
                rf = {"rule_id": rule, "onset": "T1", "variant": None}
                if rule in VITALS_RULES:
                    key = "ccm_vit" if cc_missing else "vit"
                    rf["onset"] = "T2" if ctr[key] % 2 else "T1"
                    ctr[key] += 1
                    key = {"RF-QSOFA": "var_q", "RF-NEWS-SINGLE3": "var_n", "RF-NEWS-AGG5": "var_a"}[rule]
                    rf["variant"] = variants[rule][ctr[key] % len(variants[rule])]["variant_id"]
                    ctr[key] += 1
                plan["red_flag"] = rf
            else:
                if _hit(n_nonrf, q["near_miss_of_non_red_flag"]):
                    plan["near_miss"] = near[ctr["near"] % len(near)]["variant_id"]
                    ctr["near"] += 1
                elif "chief_complaint" not in plan["missing"]:  # a text near-miss needs the complaint stated
                    if _hit(n_plain, q["text_near_miss_of_plain"]):
                        plan["text_near_miss"] = TNM_CYCLE[ctr["tnm"] % len(TNM_CYCLE)]
                        ctr["tnm"] += 1
                    n_plain += 1
                n_nonrf += 1
            rf = plan["red_flag"]
            stratum = ("text_rf" if rf and rf["rule_id"] not in VITALS_RULES else "vitals_rf" if rf else
                       "vitals_nm" if plan["near_miss"] else "text_nm" if plan["text_near_miss"] else "ordinary")
            plan["arrival_tamtee"] = _hit(ctr_arr[stratum], q["arrival_tamtee_per_stratum"])
            ctr_arr[stratum] += 1
            # complaint template
            if rf and rf["rule_id"] not in VITALS_RULES:
                pool = text_cc[rf["rule_id"]]
                cc = pool[ctr_rule[rf["rule_id"]] % len(pool)]
                ctr_rule[rf["rule_id"]] += 1
                if "duration" not in plan["missing"]:  # alternate minutes/hours within each text rule
                    plan["duration_idx"] = ctr_unit[rf["rule_id"]] % len(cc["durations"])
                    ctr_unit[rf["rule_id"]] += 1
            elif plan["text_near_miss"]:
                pool = tnm_cc[plan["text_near_miss"]]
                cc = pool[ctr_tnm[plan["text_near_miss"]] % len(pool)]
                ctr_tnm[plan["text_near_miss"]] += 1
            elif rf:
                cc = hosts[ctr["host"] % len(hosts)]
                ctr["host"] += 1
            else:
                group = "general"
                if pat["sex"] == "female" and pat["age"] <= 45:
                    group = ("obstetric", "gynecologic", "obstetric", "general")[ctr["yf"] % 4]
                    ctr["yf"] += 1
                    if group == "obstetric" and pregnancy_cap is not None:  # held-out only (v1.2.2)
                        if ctr["preg"] >= pregnancy_cap:
                            group = "general"
                        ctr["preg"] += group == "obstetric"
                elif pat["sex"] == "female":
                    group = "gynecologic" if ctr["of"] % 4 == 0 else "general"
                    ctr["of"] += 1
                key = {"general": "gen", "obstetric": "ob", "gynecologic": "gyn"}[group]
                cc = by_group[group][ctr[key] % len(by_group[group])]
                ctr[key] += 1
            plan["complaint_id"] = cc["id"]
            plan["pregnant"] = cc["group"] == "obstetric"
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


def news_score(v: dict, bands: dict) -> int:
    """Aggregate NEWS (RCP 2012). A null parameter scores 0, so the result is a lower bound."""
    total = 0
    for param in ("rr", "spo2", "temp_c", "sbp", "hr"):
        x = v.get(param)
        if x is not None:
            total += next(score for upper, score in bands[param] if upper is None or x <= upper)
    if v.get("on_oxygen") is not None:
        total += bands["on_oxygen"][str(v["on_oxygen"]).lower()]
    if v.get("consciousness") is not None:
        total += bands["consciousness"][v["consciousness"]]
    return total


def eval_criterion(crit: dict, items: list[dict]) -> tuple[bool, set[str]]:
    kind = crit["kind"]
    if kind == "news_aggregate":
        ids = {it["item_id"] for it in items if it["data_type"] == "Vitals"
               and news_score(it, crit["bands"]) >= crit["min_score"]}
        return bool(ids), ids
    if kind == "vitals":
        ids = {it["item_id"] for it in items if it["data_type"] == "Vitals"
               and sum(_vitals_ok(c, it) for c in crit["conditions"]) >= crit["min_count"]}
        return bool(ids), ids
    if kind == "transcript":
        ids = set()
        for it in items:
            if it["data_type"] != "IntakeTranscript":
                continue
            # every term group must co-occur within one turn of the speaker
            if any(all(any(ph in t["text"] for ph in group) for group in crit["all_of"])
                   for t in it["turns"] if t["speaker"] == crit["speaker"]):
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
        self.news_bands = next(r for r in tpl["red_flags"] if r["rule_id"] == "RF-NEWS-AGG5")["criterion"]["bands"]
        # pregnancy: no renin-angiotensin-acting drug or statin in any list (pregnancy_exclusions.json)
        blocked = tuple(x["atc_prefix"] for x in tpl["pregnancy_exclusions"]) if plan["pregnant"] else ()
        self.allowed = lambda name: not self.form[name]["atc_code"].startswith(blocked) if blocked else True

    def item(self, suffix, data_type, source, event, observed, available, **body) -> dict:
        it = {"item_id": f"{self.cid}-{suffix}", "data_type": data_type, "patient_ref": self.plan["patient_ref"],
              "encounter_ref": self.cid, "event_time": iso(event), "observed_at": iso(observed),
              "available_at_time": iso(available), "source": source, "provenance": "synthetic",
              "version": ITEM_VERSION, **body}
        self.items.append(it)
        return it

    # -- vitals
    def _band(self, name):
        b = next(x for x in self.tpl["vitals_bands"]["normal"] if x["param"] == name)
        if isinstance(b["low"], float) or isinstance(b["high"], float):
            return round(self.rng.uniform(b["low"], b["high"]), 1)
        return self.rng.randint(b["low"], b["high"])

    def vitals_values(self, variant_set: dict | None, allow_null: bool, fever: bool | None = None) -> dict:
        fever = self.cc["fever"] if fever is None else fever
        v = {"sbp": self._band("sbp"), "hr": self._band("hr_fever" if fever else "hr"), "rr": self._band("rr"),
             "temp_c": self._band("temp_c_fever" if fever else "temp_c"), "spo2": self._band("spo2"),
             "consciousness": "A", "on_oxygen": False}
        if self.cc.get("red_flag_rule") == "RF-ANAPHYLAXIS":
            variant_set = {**self.tpl["vitals_bands"]["anaphylaxis_host"]["set"], **self.cc.get("vitals_set", {}),
                           **(variant_set or {})}
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
        names = [f["generic_name"] for f in chronic if self.allowed(f["generic_name"])
                 and self.allowed(f.get("duplicate_partner", f["generic_name"]))]
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
        vs1 = self.vitals_values(vs1_set, allow_null=not (rf or nm or plan["text_near_miss"]))
        if nm and news_score(vs1, self.news_bands) >= 5:  # a fever band must not push a near-miss to NEWS >= 5
            vs1 = self.vitals_values(vs1_set, allow_null=False, fever=False)
        self.item("VS1", "Vitals", "synthetic-triage", A + 5 * m, A + 6 * m, A + 7 * m, **vs1)

        # Thai nurse-patient intake dialogue
        if "durations" in self.cc:
            dur_unit, lo, hi = self.cc["durations"][plan["duration_idx"]]
        else:
            dur_unit, (lo, hi) = self.cc["duration_unit"], self.cc["duration_range"]
        dur_value = rng.randint(lo, hi)
        dur_th = f"{dur_value} {DURATION_TH[dur_unit]}"
        allergy_th = f"แพ้ยา{allergy_class['th']}" if allergy == "known" else "ไม่เคยแพ้ยา"
        arrival = ARRIVAL_TAMTEE if plan["arrival_tamtee"] else ARRIVAL_PLAIN
        # the nurse script is identical for every case; missing fields are unanswered, not unasked
        lines = [("nurse", "สวัสดีค่ะ วันนี้มาด้วยอาการอะไรคะ"),
                 ("patient", (f"รู้สึกไม่ค่อยสบาย บอกไม่ถูกว่าเป็นอะไร{p}" if "chief_complaint" in missing
                              else f"{self.cc['th']}{p}")),
                 ("nurse", "เป็นมานานเท่าไรแล้วคะ"),
                 ("patient", f"จำไม่ได้ว่าเป็นมานานเท่าไร{p}" if "duration" in missing else f"เป็นมา {dur_th}{p}"),
                 ("nurse", "วันนี้มากับใครคะ"), ("patient", f"{rng.choice(arrival)}{p}"),
                 ("nurse", "มียาที่ใช้ประจำไหมคะ"), ("patient", self.med_text(home or [], p)),
                 ("nurse", "เคยมีอาการผิดปกติหลังใช้ยาไหมคะ"),  # no "แพ้": an unanswered slot stays absent
                 ("patient", f"ไม่แน่ใจ{p} จำไม่ได้" if "allergy_status" in missing else f"{allergy_th}{p}"),
                 ("nurse", "ขอบคุณค่ะ กรุณานั่งรอสักครู่นะคะ"), ("patient", f"ได้{p} ขอบคุณ{p}")]
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
            {"value": dur_value, "unit": dur_unit, "th_text": dur_th},
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
        pool = [f["generic_name"] for f in self.tpl["formulary"] if f["role"] == "acute" and self.allowed(f["generic_name"])
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
def _field_known(snap: list[dict], data_type: str, key: str) -> bool:
    return any(it["data_type"] == data_type and it.get(key) is not None for it in snap)


def required_inputs_missing(case: "_Case", snap: list[dict], required: list[str]) -> list[str]:
    """Canonical-order required inputs that are missing or unknown at T (unknown is never read as negative)."""
    state = {
        "demographics.age": _field_known(snap, "Demographics", "age_years"),
        "demographics.sex": _field_known(snap, "Demographics", "sex"),
        **{f: case.fields[f] != "MISSING" for f in ("chief_complaint", "duration", "allergy_status")},
        **{f"vitals.{p}": _field_known(snap, "Vitals", p) for p in VITAL_PARAMS},
    }
    return [f for f in required if not state[f]]


def care_gold(case: "_Case", journey: dict, T: str, snap: list[dict], flags: list[dict], tpl: dict) -> dict:
    """Care-suggestion reference label at T (v1.2.0). Synthetic, from predeclared sourced templates (D1)."""
    cni, vocab = tpl["care_next_info"], {c["code"]: c for c in tpl["next_info_codes"]["codes"]}
    lab_loinc = {x["test"]: x["loinc"] for x in tpl["labs"]}
    code_of_loinc = {c["loinc"]: c["code"] for c in vocab.values() if c.get("loinc")}
    missing = required_inputs_missing(case, snap, [r["input"] for r in tpl["care_required_inputs"]["required_inputs"]])
    entry = cni["complaints"][case.cc["id"]]
    fired = [f["rule_id"] for f in flags]
    entries = ([] if entry.get("no_sourced_workup") else [entry]) + [
        cni["red_flag_rules"][r] for r in cni["rule_priority"] if r in fired]
    resulted = {code_of_loinc[lab_loinc[r["test"]]] for it in snap if it["data_type"] == "LabSeries"
                for r in it["results"]}
    n_vitals = sum(1 for it in snap if it["data_type"] == "Vitals")

    def observed(code: str) -> bool:
        when = vocab[code]["observed_when"]
        return (when == "lab_resulted" and code in resulted) or (when == "second_vitals_set" and n_vitals >= 2)

    sources: dict[str, set] = {}
    for e in entries:
        for code in e["next_info"]:
            sources.setdefault(code, set()).update(e["source_refs"], vocab[code]["source_refs"])
    removed = sorted(c for c in sources if observed(c))
    next_info = sorted(c for c in sources if c not in removed)
    rule_paths = [cni["red_flag_rules"][r]["pathway"] for r in cni["rule_priority"] if r in fired]
    pathway = rule_paths[0] if rule_paths else (None if entry.get("no_sourced_workup") else entry["pathway"])
    reason = ("sourced" if next_info else "no_sourced_workup" if not entries else "all_sourced_items_already_available")
    cut = parse(T)
    ordered = sorted({code_of_loinc[lab_loinc[r["test"]]] for it in journey["items"]
                      if it["data_type"] == "LabSeries" and parse(it["event_time"]) > cut for r in it["results"]})
    return {"required_inputs_missing": missing, "expected_action": "abstain" if missing else "suggest",
            "next_info": next_info, "next_info_sources": {c: sorted(sources[c]) for c in next_info},
            "already_available_at_T": removed, "pathway": pathway, "evaluable": bool(next_info), "reason": reason,
            "ordered_after_T": ordered}


def gold_for(case: _Case, journey: dict, injections: list[dict], rules: list[dict],
             version: str = V1_OUTPUT_VERSION) -> dict:
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
        # department is not derivable without a stated complaint (escalation needs no department, D4)
        cc_missing = case.fields["chief_complaint"] == "MISSING"
        dept = "NOT_EVALUABLE" if cc_missing else ("12" if flags else cc_dept)
        rows.append({"decision_point": label, "T": T, "target_department": dept,
                     "department_evaluable": not cc_missing,
                     "department_reason": "chief_complaint_missing" if cc_missing else None,
                     "red_flags": flags, "required_fields": case.fields, "medication_issues": issues,
                     "expected_action": action, "care": care_gold(case, journey, T, snap, flags, case.tpl)})
    return {"case_id": case.cid, "patient_ref": case.plan["patient_ref"], "split": case.plan["split"],
            "label_version": version,
            "label_status": "synthetic reference labels from predeclared rules; not clinical ground truth; not expert-reviewed",
            "scenario": {k: case.plan[k] for k in ("complaint_id", "red_flag", "near_miss", "text_near_miss",
                                                   "arrival_tamtee", "pregnant", "missing", "has_meds",
                                                   "injections", "late")},
            "decision_times": rows}


def snapshot(journey: dict, T: str) -> list[dict]:
    cut = parse(T)
    return [it for it in journey["items"] if parse(it["available_at_time"]) <= cut]


# ---------------------------------------------------------------- output
def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


DATA_CLASS = "synthetic"  # written to manifest.json; the S1r loader takes data_class from there (slice i2)


def validate_item(it: dict) -> None:
    # Items carry no data_class; the loader adds it from the manifest, so validate exactly that shape.
    EVIDENCE_ADAPTER.validate_python({**it, "data_class": DATA_CLASS})
    if it["provenance"] != "synthetic":
        raise ValueError(f"{it['item_id']}: provenance must be 'synthetic'")


def generate(seed: int, out: Path, splits_only: bool = False, quotas: dict | None = None,
             heldout: bool = False) -> dict | None:
    out = Path(out)
    tpl = load_templates()
    main = random.Random(seed)
    if heldout:
        h = HELDOUT
        roster = make_roster(seed, main, h["n_patients"], h["n_revisit"], h["patient_prefix"], h["case_prefix"])
        splits = make_splits(main, roster, h["split_sizes"], h["revisit_split"])
    else:
        roster = make_roster(seed, main)
        splits = make_splits(main, roster)
    _write(out / "splits.json", dumps(splits))  # written before any case exists
    if splits_only:
        return None
    plans = plan_cases(main, roster, splits, tpl, quotas or QUOTAS, HELDOUT["pregnancy_cases"] if heldout else None)
    version = GENERATOR_VERSION if heldout else V1_OUTPUT_VERSION
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
        gold = gold_for(case, journey, injections, rules, version)
        _write(out / "gold" / plan["split"] / f"{case.cid}.json", dumps(gold))
        all_injections += injections
        golds.append(gold)
    _write(out / "gold" / "injection_log.jsonl",
           b"".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
                    for r in all_injections))
    counts = summarize(plans, golds, all_injections, splits)
    _write(out / "DATACARD.md", (datacard(seed, counts, version) + (HELDOUT_CARD.format(seed=seed) if heldout else "")).encode())
    _write(out / "gold" / "README.md", GOLD_README.encode())
    return write_manifest(out, seed, counts, heldout, version)


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
        "vitals_near_miss_cases": sum(1 for p in plans if p["near_miss"]),
        "text_near_miss_cases": tally(p["text_near_miss"] for p in plans if p["text_near_miss"]),
        "pregnancy_cases": sum(1 for p in plans if p["pregnant"]),
        "department_not_evaluable_rows": sum(1 for r in rows if not r["department_evaluable"]),
        "expected_action_T1": tally(g["decision_times"][0]["expected_action"] for g in golds),
        "expected_action_T2": tally(g["decision_times"][-1]["expected_action"] for g in golds),
        "target_department_T2": tally(g["decision_times"][-1]["target_department"] for g in golds),
        "medication_cases": sum(1 for p in plans if p["has_meds"]),
        "clean_medication_cases": sum(1 for p in plans if p["has_meds"] and not p["injections"]),
        "injections_per_type": tally(r["issue_type"] for r in injections),
        "cases_with_late_items": sum(1 for p in plans if p["late"]),
        "care_expected_action": tally(r["care"]["expected_action"] for r in rows),
        "care_evaluable_rows": sum(1 for r in rows if r["care"]["evaluable"]),
        "care_reason": tally(r["care"]["reason"] for r in rows),
        "care_pathway": tally(str(r["care"]["pathway"]) for r in rows),
    }


SNAPSHOT_ONLY = ("Only `inputs/<split>/<case_id>/snapshot_T*.json` files are valid model inputs. `journey.json` is the "
                 "full timeline, including items after every decision time, for audit only; it must never be given to "
                 "a model.")
DEPT_EVALUABLE = ("Department accuracy is computed only over rows with `department_evaluable == true`. Rows with "
                  "`target_department == \"NOT_EVALUABLE\"` (chief complaint missing) are excluded from department "
                  "accuracy and enter the abstention/coverage metric instead (PROPOSAL 3.6).")
CARE_LABELS = ("`care` (v1.2.0, slice s6) holds care-suggestion reference labels per decision point: "
               "`required_inputs_missing` (canonical order, `care_required_inputs.json`; unknown counts as missing), "
               "`expected_action` (`abstain` iff that list is non-empty), `next_info` (sourced template items plus "
               "fired red-flag rule items, minus items already resulted or observed in snapshot_T), "
               "`next_info_sources`, `pathway`, `evaluable` (false when no sourced work-up applies or `next_info` is "
               "empty), `reason` and `ordered_after_T` (lab items whose LabSeries `event_time` is after T; proxy for "
               "tests ordered after the decision time, PROPOSAL 3.6(3)). These are synthetic reference labels from "
               "guideline-sourced templates written by the builder, not expert-reviewed (D1), not clinical ground "
               "truth; results against them are a System Evaluation, not clinical performance.")
GOLD_README = f"""# gold/ — synthetic reference labels (audit and evaluation only; never model input)

Labels are synthetic reference labels from predeclared rules, not clinical ground truth, not expert-reviewed (D1).
A "no red flag" row means only that no rule in the registry fires; it does not mean the patient is clinically safe.

{DEPT_EVALUABLE}

{CARE_LABELS}

{SNAPSHOT_ONLY}
"""


def datacard(seed: int, counts: dict, version: str = V1_OUTPUT_VERSION) -> str:
    return f"""# DATACARD — synthetic case factory v1 ({version})

**synthetic, not for clinical use, not expert-reviewed, system evaluation only.**

- Every patient, encounter, dialogue, vital sign, lab and medication list here is generated from templates by a
  seeded program (seed `{seed}`). No real patient records or external clinical databases were used.
- Labels are *synthetic reference labels* computed from predeclared rules (`data_factory/templates/`); they are
  not clinical ground truth and have not been reviewed by clinical experts (pending decision D1).
- Adults 18-95 only. No names, dates of birth, addresses, phone numbers or national IDs.

## Label rules
- `red_flags`: rules in `red_flags.json` (qSOFA PMID 26903335; NEWS single-parameter 3 PMID 23295778; NEWS
  aggregate >= 5, RCP 2012 Chart 1; FAST PMID 12511753; acute chest pain PMID 34709879; thunderclap PMID 24065011;
  anaphylaxis PMID 16461139), evaluated over the snapshot at each decision time. Text rules need a concept term and
  a sudden-onset term in the same patient turn. "No red flag" means no registry rule fires, not clinically safe.
- Negatives: vitals near-miss cases (every NEWS input present, aggregate <= 4, no parameter scoring 3, qSOFA <= 1)
  and five text near-miss families (stable chest pain, gradual headache, bilateral numbness, urticaria/lip swelling
  only, chronic unchanged post-stroke deficit) that reuse the concept terms without a sudden-onset term. The arrival
  answer uses `ทันที` (travel sense) in 1/3 of every stratum; the nurse script is identical for every case.
- `target_department`: SIL-TH cs-chi-clinic v0.1.2 code; `12` whenever a red flag is present, else the complaint
  template's department (synthetic map pending expert review); `NOT_EVALUABLE` when the chief complaint is missing.
- {DEPT_EVALUABLE}
- `expected_action`: `escalate` if any red flag, else `abstain` if any required intake field is missing, else
  `suggest`.
- `medication_issues`: deliberately injected discrepancies (AHRQ MATCH; ASHP 2021), each logged in
  `gold/injection_log.jsonl`; present only at decision times where the new order is available.
- {CARE_LABELS}
- v1.2.0 changes gold only: every `inputs/**` file is byte-identical to v1.1.1 at the same seed (input items keep
  `version` {ITEM_VERSION}); existing gold keys are unchanged except `label_version`.

## Leakage controls
Patients are split before cases are generated (`splits.json`). Snapshot at T contains only items with
`available_at_time <= T`. Gold lives only under `gold/`.

{SNAPSHOT_ONLY}

## Pregnancy
Obstetric-complaint cases carry no drug with ATC `C09*` or `C10AA*` in any list (`pregnancy_exclusions.json`).

## Counts
```
{json.dumps(counts, indent=2, sort_keys=True)}
```
"""


HELDOUT_CARD = """
## Held-out mode (v1.2.1-v1.2.2, slice s6r)
Fresh held-out set for `s6-care-test-0002`: seed `{seed}`, 72 patients (8 revisit), 80 cases, `test` split only,
patients `SYNH-NNNN` and cases `SYNHE-NNNN` (disjoint from every `SYNP-`/`SYNE-` identity). Same templates and
quotas as v1, plus a pregnancy quota (v1.2.2, ruling D-s6r-2): at most 2 obstetric cases (2 x the v1 test count);
later obstetric slots take a general complaint. Generated after `care-rules-1.1.0` was committed; evaluated once
against a frozen manifest.
"""


def write_manifest(out: Path, seed: int, counts: dict, heldout: bool = False,
                   version: str = V1_OUTPUT_VERSION) -> dict:
    files = {}
    for p in sorted(out.rglob("*")):
        rel = p.relative_to(out).as_posix()
        if p.is_file() and rel != "manifest.json" and not rel.endswith("audit_report.json"):
            files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {"seed": seed, "generator_version": GENERATOR_VERSION, "output_version": version, "data_class": DATA_CLASS,
                "source_code_sha256": source_code_sha256(),
                **({"heldout": True, "heldout_spec": HELDOUT} if heldout else {}),
                "counts": counts, "split_sizes": counts["patients_per_split"],
                "model_inputs_glob": MODEL_INPUTS_GLOB, "audit_only_globs": AUDIT_ONLY_GLOBS, "files": files,
                "tree_sha256": tree_sha256(files, MODEL_INPUTS_GLOB, AUDIT_ONLY_GLOBS)}
    _write(out / "manifest.json", dumps(manifest))
    return manifest
