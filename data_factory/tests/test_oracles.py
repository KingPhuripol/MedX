"""Independent reference checkers. They re-implement the rules from the cited sources and must NOT import
the generator's label functions (``data_factory.generate``)."""

import ast
import json
import unicodedata
from datetime import datetime
from pathlib import Path

from .conftest import REPO_ROOT

# Thresholds copied from the sources, independently of red_flags.json.
QSOFA = {"rr_ge": 22, "sbp_le": 100}                   # Seymour 2016, PMID 26903335
NEWS3 = {"rr_le": 8, "rr_ge": 25, "spo2_le": 91, "temp_le": 35.0, "sbp_le": 90, "sbp_ge": 220,
         "hr_le": 40, "hr_ge": 131}                     # Smith 2013, PMID 23295778
ANAPH_SBP_LT = 90                                       # Sampson 2006, PMID 16461139
# NEWS 2012 Chart 1 (Royal College of Physicians), copied from the chart: [upper bound inclusive, score].
NEWS_BANDS = {
    "rr": [[8, 3], [11, 1], [20, 0], [24, 2], [None, 3]],
    "spo2": [[91, 3], [93, 2], [95, 1], [None, 0]],
    "temp_c": [[35.0, 3], [36.0, 1], [38.0, 0], [39.0, 1], [None, 2]],
    "sbp": [[90, 3], [100, 2], [110, 1], [219, 0], [None, 3]],
    "hr": [[40, 3], [50, 1], [90, 0], [110, 1], [130, 2], [None, 3]],
    "on_oxygen": {"true": 2, "false": 0},
    "consciousness": {"A": 0, "C": 0, "V": 3, "P": 3, "U": 3},
}
NEWS_AGG_MIN = 5  # "NEWS aggregate score of 5 or more ... should prompt an urgent review"
# Thai lexicons (same-turn co-occurrence for the onset-dependent rules).
ONSET = ["ทันที", "จู่ ๆ", "เฉียบพลัน", "ไม่กี่วินาที"]
FAST = ["หน้าเบี้ยว", "ปากเบี้ยว", "พูดไม่ชัด", "พูดลำบาก", "แขนขาอ่อนแรงซีกเดียว", "แขนอ่อนแรงข้างเดียว", "มือชา"]
CHEST = ["เจ็บแน่นหน้าอก", "เจ็บหน้าอก", "แน่นหน้าอก"]
THUNDER = ["ปวดศีรษะรุนแรง", "ปวดหัวรุนแรง", "ปวดศีรษะมากที่สุด"]
SKIN = ["ผื่นลมพิษ", "ลมพิษ", "ปากบวม", "ริมฝีปากบวม"]
RESP = ["หายใจลำบาก", "หายใจมีเสียงหวีด", "หายใจไม่ออก"]
ONSET_RULES = {"RF-FAST": FAST, "RF-ACUTE-CHEST-PAIN": CHEST, "RF-THUNDERCLAP": THUNDER}
TEXT_RULES = (*ONSET_RULES, "RF-ANAPHYLAXIS")
TNM_PAIR = {"TNM-CHEST-STABLE": CHEST, "TNM-HEADACHE-GRADUAL": THUNDER, "TNM-NUMB-BILATERAL": FAST,
            "TNM-URTICARIA-ONLY": SKIN, "TNM-DEFICIT-CHRONIC": FAST}
ALL_CONCEPTS = [*FAST, *CHEST, *THUNDER, *SKIN, *RESP]
ARRIVAL_QUESTION = "วันนี้มากับใครคะ"  # fixed nurse question; the next patient turn is the arrival turn
TEMPLATES = REPO_ROOT / "data_factory" / "templates"


def t(s):
    return datetime.fromisoformat(s)


def band_score(param, x):
    for upper, score in NEWS_BANDS[param]:
        if upper is None or x <= upper:
            return score


def news_param_scores(v) -> dict:
    out = {p: band_score(p, v[p]) for p in ("rr", "spo2", "temp_c", "sbp", "hr") if v[p] is not None}
    if v["on_oxygen"] is not None:
        out["on_oxygen"] = NEWS_BANDS["on_oxygen"][str(v["on_oxygen"]).lower()]
    if v["consciousness"] is not None:
        out["consciousness"] = NEWS_BANDS["consciousness"][v["consciousness"]]
    return out


def news_aggregate(v) -> int:
    return sum(news_param_scores(v).values())  # null scores 0: lower bound


def qsofa(v) -> int:
    return sum([v["rr"] is not None and v["rr"] >= QSOFA["rr_ge"], v["sbp"] is not None and v["sbp"] <= QSOFA["sbp_le"],
                v["consciousness"] is not None and v["consciousness"] != "A"])


def patient_turns(tx):
    return [turn["text"] for turn in tx["turns"] if turn["speaker"] == "patient"]


def oracle_red_flags(items) -> dict[str, list[str]]:
    flags: dict[str, set] = {}
    vitals = [i for i in items if i["data_type"] == "Vitals"]
    for v in vitals:
        rr, sbp, hr, spo2, temp, avpu = v["rr"], v["sbp"], v["hr"], v["spo2"], v["temp_c"], v["consciousness"]
        if qsofa(v) >= 2:
            flags.setdefault("RF-QSOFA", set()).add(v["item_id"])
        news = [rr is not None and (rr <= NEWS3["rr_le"] or rr >= NEWS3["rr_ge"]),
                spo2 is not None and spo2 <= NEWS3["spo2_le"],
                temp is not None and temp <= NEWS3["temp_le"],
                sbp is not None and (sbp <= NEWS3["sbp_le"] or sbp >= NEWS3["sbp_ge"]),
                hr is not None and (hr <= NEWS3["hr_le"] or hr >= NEWS3["hr_ge"]),
                avpu in ("V", "P", "U")]
        if any(news):
            flags.setdefault("RF-NEWS-SINGLE3", set()).add(v["item_id"])
        if news_aggregate(v) >= NEWS_AGG_MIN:
            flags.setdefault("RF-NEWS-AGG5", set()).add(v["item_id"])
    low_bp = {v["item_id"] for v in vitals if v["sbp"] is not None and v["sbp"] < ANAPH_SBP_LT}
    for tx in (i for i in items if i["data_type"] == "IntakeTranscript"):
        turns = patient_turns(tx)
        for rule, concept in ONSET_RULES.items():
            if any(any(c in s for c in concept) and any(o in s for o in ONSET) for s in turns):
                flags.setdefault(rule, set()).add(tx["item_id"])
        skin = any(w in s for s in turns for w in SKIN)
        resp = any(w in s for s in turns for w in RESP)
        if skin and (resp or low_bp):
            flags.setdefault("RF-ANAPHYLAXIS", set()).update({tx["item_id"], *low_bp})
    return {k: sorted(v) for k, v in sorted(flags.items())}


def oracle_med_issues(items) -> set[tuple[str, tuple[str, ...]]]:
    lists = {i["list_source"]: i["entries"] for i in items if i["data_type"] == "MedicationList"}
    home, new = lists.get("home_list", []), lists.get("new_order")
    if new is None:
        return set()
    issues = set()
    by_drug: dict[str, list[dict]] = {}
    for entries in lists.values():
        for e in entries:
            by_drug.setdefault(e["generic_name"], []).append(e)
    for drug, es in by_drug.items():
        if len(es) >= 2 and len({(e["dose_value"], e["dose_unit"]) for e in es}) > 1:
            issues.add(("dose_mismatch", (drug,)))
        if len(es) >= 2 and len({e["frequency"] for e in es}) > 1:
            issues.add(("frequency_mismatch", (drug,)))
    new_names = {e["generic_name"] for e in new}
    issues |= {("omission", (e["generic_name"],)) for e in home if e["generic_name"] not in new_names}
    for a in new:
        for b in new:
            if a["generic_name"] < b["generic_name"] and a["atc_code"][:5] == b["atc_code"][:5]:
                issues.add(("duplicate_therapy", (a["generic_name"], b["generic_name"])))
    classes = [e["atc_class"] for i in items if i["data_type"] == "AllergyList" and i["status"] == "known"
               for e in i["entries"]]
    issues |= {("allergy_conflict", (e["generic_name"],)) for e in new for c in classes if e["atc_code"].startswith(c)}
    return issues


def _rules():
    return {r["rule_id"]: r for r in json.loads((TEMPLATES / "red_flags.json").read_text("utf-8"))}


def test_oracle_does_not_import_generator():
    tree = ast.parse(Path(__file__).read_text("utf-8"))
    mods = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [m for m in mods if "generate" in m or m.startswith("data_factory")], mods


def test_oracle_thresholds_match_registry():
    rules = _rules()
    q = {(c["param"], c["op"]): c["value"] for c in rules["RF-QSOFA"]["criterion"]["conditions"]}
    assert q[("rr", ">=")] == QSOFA["rr_ge"] and q[("sbp", "<=")] == QSOFA["sbp_le"]
    n = {(c["param"], c["op"]): c["value"] for c in rules["RF-NEWS-SINGLE3"]["criterion"]["conditions"]}
    assert n == {("rr", "<="): 8, ("rr", ">="): 25, ("spo2", "<="): 91, ("temp_c", "<="): 35.0, ("sbp", "<="): 90,
                 ("sbp", ">="): 220, ("hr", "<="): 40, ("hr", ">="): 131, ("consciousness", "in"): ["V", "P", "U"]}
    agg = rules["RF-NEWS-AGG5"]["criterion"]
    assert agg["kind"] == "news_aggregate" and agg["min_score"] == NEWS_AGG_MIN and agg["bands"] == NEWS_BANDS
    for rule, concept in ONSET_RULES.items():
        assert rules[rule]["criterion"]["all_of"] == [concept, ONSET], rule
    an = rules["RF-ANAPHYLAXIS"]["criterion"]["of"]
    assert an[0]["all_of"] == [SKIN] and an[1]["of"][0]["all_of"] == [RESP]
    assert an[1]["of"][1]["conditions"] == [{"param": "sbp", "op": "<", "value": ANAPH_SBP_LT}]


BASE = {"rr": 16, "spo2": 98, "temp_c": 37.0, "sbp": 120, "hr": 70, "on_oxygen": False, "consciousness": "A"}
# (parameter, value, NEWS 2012 score) read off Chart 1: both sides of every band edge.
CHART = [
    ("rr", 8, 3), ("rr", 9, 1), ("rr", 11, 1), ("rr", 12, 0), ("rr", 20, 0), ("rr", 21, 2), ("rr", 24, 2), ("rr", 25, 3),
    ("spo2", 91, 3), ("spo2", 92, 2), ("spo2", 93, 2), ("spo2", 94, 1), ("spo2", 95, 1), ("spo2", 96, 0),
    ("temp_c", 35.0, 3), ("temp_c", 35.1, 1), ("temp_c", 36.0, 1), ("temp_c", 36.1, 0), ("temp_c", 38.0, 0),
    ("temp_c", 38.1, 1), ("temp_c", 39.0, 1), ("temp_c", 39.1, 2),
    ("sbp", 90, 3), ("sbp", 91, 2), ("sbp", 100, 2), ("sbp", 101, 1), ("sbp", 110, 1), ("sbp", 111, 0),
    ("sbp", 219, 0), ("sbp", 220, 3),
    ("hr", 40, 3), ("hr", 41, 1), ("hr", 50, 1), ("hr", 51, 0), ("hr", 90, 0), ("hr", 91, 1), ("hr", 110, 1),
    ("hr", 111, 2), ("hr", 130, 2), ("hr", 131, 3),
    ("on_oxygen", True, 2), ("on_oxygen", False, 0),
    ("consciousness", "A", 0), ("consciousness", "C", 0), ("consciousness", "V", 3), ("consciousness", "P", 3),
    ("consciousness", "U", 3),
]


def test_news_score_bands():
    assert len(CHART) >= 30 and news_aggregate(BASE) == 0
    for param, value, want in CHART:
        assert news_aggregate({**BASE, param: value}) == want, (param, value)
    assert news_aggregate({**BASE, "rr": None, "temp_c": None}) == 0  # nulls contribute 0


def test_red_flag_oracle_agrees(dataset):
    pairs = 0
    for cid, c in dataset.cases.items():
        for row in c["gold"]["decision_times"]:
            snap = c["snapshots"][row["decision_point"]]
            gold = {f["rule_id"]: f["item_ids"] for f in row["red_flags"]}
            assert oracle_red_flags(snap["items"]) == gold, (cid, row["decision_point"])
            pairs += 1
    assert pairs >= 400
    agg = [cid for cid, c in dataset.cases.items()
           if any(f["rule_id"] == "RF-NEWS-AGG5" for r in c["gold"]["decision_times"] for f in r["red_flags"])]
    only = [cid for cid in agg if all({f["rule_id"] for f in r["red_flags"]} <= {"RF-NEWS-AGG5"}
                                      for r in dataset.cases[cid]["gold"]["decision_times"])]
    assert len(agg) >= 5 and len(only) >= 3, (len(agg), len(only))


def near_threshold(v) -> bool:
    s = news_param_scores(v)
    return sum(s.values()) == 4 or 2 in s.values() or (qsofa(v) == 1 and (v["rr"] == 22 or v["sbp"] == 100))


def test_near_miss_negatives(dataset):
    vit = [(cid, c) for cid, c in dataset.cases.items() if c["gold"]["scenario"]["near_miss"]]
    txt = [(cid, c) for cid, c in dataset.cases.items() if c["gold"]["scenario"]["text_near_miss"]]
    n_tagged = len(vit) + len(txt)
    n_asserted = 0
    for cid, c in vit:
        for row in c["gold"]["decision_times"]:
            assert oracle_red_flags(c["snapshots"][row["decision_point"]]["items"]) == {}, cid
            assert row["red_flags"] == [], cid
        items = [i for i in c["journey"]["items"] if i["data_type"] == "Vitals"]
        assert len(items) >= 2, cid
        for v in items:
            s = news_param_scores(v)
            assert all(v[p] is not None for p in ("rr", "spo2", "temp_c", "sbp", "hr", "on_oxygen", "consciousness"))
            assert v["consciousness"] == "A" and 3 not in s.values(), (cid, v)
            assert sum(s.values()) <= 4 and qsofa(v) <= 1 and v["sbp"] >= 90, (cid, v)
        assert any(near_threshold(v) for v in items), cid
        n_asserted += 1
    for cid, c in txt:
        for row in c["gold"]["decision_times"]:
            assert oracle_red_flags(c["snapshots"][row["decision_point"]]["items"]) == {}, cid
            assert row["red_flags"] == [], cid
        n_asserted += 1
    assert n_asserted == n_tagged and len(vit) >= 20 and len(txt) >= 30


def test_text_near_miss_negatives(dataset):
    tagged = [(c["gold"]["scenario"]["text_near_miss"], c) for c in dataset.cases.values()
              if c["gold"]["scenario"]["text_near_miss"]]
    per = {f: sum(1 for x, _ in tagged if x == f) for f in TNM_PAIR}
    assert len(tagged) >= 30 and all(n >= 6 for n in per.values()), per
    complaints = {x["id"]: x for x in json.loads((TEMPLATES / "complaints.json").read_text("utf-8"))}
    refs = {r["ref_id"] for r in json.loads((TEMPLATES / "references.json").read_text("utf-8"))}
    with_tamtee = 0
    for fam, c in tagged:
        cc = complaints[c["gold"]["scenario"]["complaint_id"]]
        assert cc["group"] == "general" and cc["near_miss_family"] == fam
        assert cc["near_miss_ref"] in refs and cc["near_miss_reason"]
        assert all(not r["red_flags"] for r in c["gold"]["decision_times"])
        assert all(news_aggregate(v) <= 2 for v in c["journey"]["items"] if v["data_type"] == "Vitals")
        turns = patient_turns(next(i for i in c["journey"]["items"] if i["data_type"] == "IntakeTranscript"))
        concept_turns = [k for k, s in enumerate(turns) if any(w in s for w in TNM_PAIR[fam])]
        assert concept_turns, (fam, turns)
        assert not any(o in turns[k] for k in concept_turns for o in ONSET)
        tamtee_turns = [k for k, s in enumerate(turns) if "ทันที" in s]
        with_tamtee += bool(tamtee_turns) and not set(tamtee_turns) & set(concept_turns)
    assert with_tamtee >= 5
    ordinary = [c for c in dataset.cases.values() if not c["gold"]["scenario"]["text_near_miss"]
                and not any(r["red_flags"] for r in c["gold"]["decision_times"])
                and any("ทันที" in s for s in patient_turns(next(i for i in c["journey"]["items"]
                                                                 if i["data_type"] == "IntakeTranscript")))]
    assert len(ordinary) >= 5


def test_red_flag_paraphrase_templates(dataset):
    complaints = [x for x in json.loads((TEMPLATES / "complaints.json").read_text("utf-8"))
                  if x["group"] == "red_flag_text"]
    used = {c["gold"]["scenario"]["complaint_id"] for c in dataset.cases.values()}
    for rule in TEXT_RULES:
        tpl = [x for x in complaints if x["red_flag_rule"] == rule]
        assert len(tpl) >= 3, rule
        if rule in ONSET_RULES:
            assert sum("ทันที" not in x["th"] for x in tpl) >= 2, rule
        assert all(x["id"] in used for x in tpl), rule
    assert len(ONSET) >= 3 and all(len(v) >= 2 for v in ONSET_RULES.values())


def _turns(items):
    tx = next(i for i in items if i["data_type"] == "IntakeTranscript")
    return [unicodedata.normalize("NFC", s) for s in patient_turns(tx)]


def _any_rf(c):
    return {f["rule_id"] for r in c["gold"]["decision_times"] for f in r["red_flags"]}


def _text_negative(c):
    return not _any_rf(c) & set(TEXT_RULES)


def test_single_token_baseline_fails(dataset):
    """S1R-A08: V = every substring (length 1-30) of each T1 patient turn + whitespace tokens + lexicon terms.
    For every s in V and every target, the rule 'predict positive iff s occurs in a patient turn' has F1 < 0.75."""
    turns = {cid: _turns(c["snapshots"]["T1"]["items"]) for cid, c in dataset.cases.items()}
    occ: dict[str, set] = {}
    for cid, ts in turns.items():
        for x in {s[i:j] for s in ts for i in range(len(s)) for j in range(i + 1, min(i + 30, len(s)) + 1)}:
            occ.setdefault(x, set()).add(cid)
    extra = {w for ts in turns.values() for s in ts for w in s.split()} | set(ONSET) | set(ALL_CONCEPTS)
    for w in extra - set(occ):
        occ[w] = {cid for cid, ts in turns.items() if any(w in s for s in ts)}
    t1 = {cid: {f["rule_id"] for f in c["gold"]["decision_times"][0]["red_flags"]} for cid, c in dataset.cases.items()}
    targets = {"any_text": {cid for cid, r in t1.items() if r & set(TEXT_RULES)}}
    targets |= {rule: {cid for cid, r in t1.items() if rule in r} for rule in TEXT_RULES}
    assert len(targets["any_text"]) >= 28 and all(len(v) >= 7 for v in targets.values()), \
        {k: len(v) for k, v in targets.items()}

    def score(pred, pos):
        tp = len(pred & pos)
        p, r = (tp / len(pred) if pred else 0.0), tp / len(pos)
        return (2 * p * r / (p + r) if tp else 0.0), p, r

    f1, p, r = score(occ["ทันที"], targets["any_text"])
    print(f"'ทันที' any_text: P={p:.2f} R={r:.2f} F1={f1:.2f}")
    assert p < 0.8 and r < 0.8
    worst = {}
    for name, pos in targets.items():
        ranked = sorted(((*score(pred, pos), len(pred), s) for s, pred in occ.items() if pred & pos), reverse=True)
        for f, pp, rr, support, sub in ranked[:5]:
            print(f"{name} (n={len(pos)}): {sub!r} F1={f:.2f} P={pp:.2f} R={rr:.2f} support={support}")
        worst[name] = ranked[0][:1] + ranked[0][4:]
    assert all(f < 0.75 for f, _ in worst.values()), worst


def test_minimal_pairs(dataset):
    """S1R-A15: no single criterion term is sufficient."""
    turns = {cid: _turns(c["journey"]["items"]) for cid, c in dataset.cases.items()}
    neg = [cid for cid, c in dataset.cases.items() if _text_negative(c)]
    t1 = {cid: {f["rule_id"] for f in c["gold"]["decision_times"][0]["red_flags"]} for cid, c in dataset.cases.items()}
    counts = {}
    for rule, concept in ONSET_RULES.items():
        pos_turns = [s for cid, r in t1.items() if rule in r for s in turns[cid]]
        for term in (w for w in concept if any(w in s for s in pos_turns)):
            n = sum(any(term in s and not any(o in s for o in ONSET) for s in turns[cid]) for cid in neg)
            counts[(rule, term)] = n
        for term in (o for o in ONSET if any(o in s for s in pos_turns)):
            n = sum(any(term in s and not any(w in s for w in ALL_CONCEPTS) for s in turns[cid]) for cid in neg)
            counts[(rule, term)] = n
    pos_turns = [s for cid, r in t1.items() if "RF-ANAPHYLAXIS" in r for s in turns[cid]]
    for term in (w for w in SKIN if any(w in s for s in pos_turns)):
        counts[("RF-ANAPHYLAXIS", term)] = sum(any(term in s for s in turns[cid])
                                               and not any(w in s for s in turns[cid] for w in RESP) for cid in neg)
    print(counts)
    assert len(counts) >= 3 * 4 and all(n >= 3 for n in counts.values()), counts
    assert not [cid for cid in neg if any(w in s for s in turns[cid] for w in RESP)]
    upper_airway = [s for cid in neg for s in turns[cid] if "หายใจ" in s]
    assert upper_airway and all("จมูก" in s for s in upper_airway), upper_airway


def _stratum(c):
    sc = c["gold"]["scenario"]
    if sc["red_flag"]:
        return "text_rf" if sc["red_flag"]["rule_id"] in TEXT_RULES else "vitals_rf"
    return "vitals_nm" if sc["near_miss"] else "text_nm" if sc["text_near_miss"] else "ordinary"


def _arrival_turn(c):
    turns = next(i for i in c["journey"]["items"] if i["data_type"] == "IntakeTranscript")["turns"]
    k = next(k for k, t_ in enumerate(turns) if t_["speaker"] == "nurse" and t_["text"] == ARRIVAL_QUESTION)
    assert turns[k + 1]["speaker"] == "patient"
    return turns[k + 1]["text"]


def test_arrival_turn_label_independent(dataset):
    by: dict[str, list] = {}
    for c in dataset.cases.values():
        by.setdefault(_stratum(c), []).append("ทันที" in _arrival_turn(c))
    share = {k: sum(v) / len(v) for k, v in by.items()}
    print({k: f"{sum(v)}/{len(v)}" for k, v in by.items()})
    assert set(share) == {"text_rf", "vitals_rf", "vitals_nm", "text_nm", "ordinary"}
    assert all(abs(x - 1 / 3) <= 0.05 for x in share.values()), share
    assert sum(by["text_nm"]) >= 5 and sum(by["ordinary"]) >= 5


def test_duration_unit_not_a_cue(dataset):
    units: dict[str, list] = {}
    benign = 0
    for c in dataset.cases.values():
        d = c["gold"]["decision_times"][0]["required_fields"]["duration"]
        sc = c["gold"]["scenario"]
        if d == "MISSING":
            continue
        assert d["th_text"].split()[1] == {"minute": "นาที", "hour": "ชั่วโมง", "day": "วัน", "week": "สัปดาห์",
                                           "month": "เดือน", "year": "ปี"}[d["unit"]]
        if sc["red_flag"] and sc["red_flag"]["rule_id"] in TEXT_RULES:
            units.setdefault(sc["red_flag"]["rule_id"], []).append(d["unit"])
        elif not _any_rf(c) and d["unit"] in ("minute", "hour"):
            benign += 1
    print(units, "benign minute/hour:", benign)
    for rule in TEXT_RULES:
        u = units[rule]
        assert set(u) == {"minute", "hour"}, rule
        assert max(u.count(x) for x in set(u)) / len(u) <= 0.70, (rule, u)
    assert benign >= 15


def test_nurse_script_fixed(dataset):
    scripts = {tuple(t_["text"] for t_ in next(i for i in c["journey"]["items"]
                                              if i["data_type"] == "IntakeTranscript")["turns"] if t_["speaker"] == "nurse")
               for c in dataset.cases.values()}
    assert len(scripts) == 1


def test_template_balance(dataset):
    per_rule: dict[str, list] = {}
    per_fam: dict[str, list] = {}
    for c in dataset.cases.values():
        cc = c["gold"]["scenario"]["complaint_id"]
        for rule in {f["rule_id"] for f in c["gold"]["decision_times"][0]["red_flags"]} & set(TEXT_RULES):
            per_rule.setdefault(rule, []).append(cc)
        if c["gold"]["scenario"]["text_near_miss"]:
            per_fam.setdefault(c["gold"]["scenario"]["text_near_miss"], []).append(cc)
    share = lambda v: max(v.count(x) for x in set(v)) / len(v)  # noqa: E731
    print({k: round(share(v), 2) for k, v in (per_rule | per_fam).items()})
    assert set(per_rule) == set(TEXT_RULES) and all(share(v) <= 0.40 for v in per_rule.values())
    assert set(per_fam) == set(TNM_PAIR) and all(share(v) <= 0.60 for v in per_fam.values())


def test_medication_oracle_agrees(dataset):
    logged: dict[str, set] = {}
    for r in dataset.injections:
        logged.setdefault(r["case_id"], set()).add((r["issue_type"], tuple(sorted(r["drugs"]))))
    for cid, c in dataset.cases.items():
        found = oracle_med_issues(c["snapshots"]["T2"]["items"])
        assert found == logged.get(cid, set()), cid
        assert oracle_med_issues(c["snapshots"]["T1"]["items"]) == set(), cid
