"""e2e-tester (s5r5 checker, commit 7382c7c; spec = slices/s5r4/SPEC.md rev 5 @ 86ccf86 + s5r5 closing rule).

Rev-5-round probes that are new in this round (the rev-4/rev-5 round-1..3 findings are re-run by
s5r4_classify_findings.py, s5r4_r2_classify_findings.py and s5r4_r3_classify_findings.py).
Each row: text, the meaning a pharmacist reads from the displayed text, intended (value, qty) or "not per dose",
implementation and independent-reference outputs, non-PLAUSIBLE code points and exactly one class of the s5r4
stopping-rule table (CONFORMANCE FAIL / BLOCKER / RESIDUAL / SAFE; NO MISREAD for rows that resolve correctly).
A row in a declared residual class (RR-01 unmarked total, RR-07 name-region modifier) that misreads is RESIDUAL.
Synthetic strings only. Run from repo root: .venv/bin/python tests/e2e/s5r5_probes.py [--out FILE]
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5r4_classify_findings import classify, non_plausible, parse_entry, reference_parse  # noqa: E402

NPD = "not per dose"
# (group, id, text, meaning, intended, declared residual class or None)
F = [
    # BE: an 'every <time-of-day slot>' once-daily statement (EN every morning/evening/night, TH ทุกเช้า/ทุกเย็น/ทุกค่ำ)
    # + MULTI. Same meaning as BN ('nightly bid'): a once-a-day statement next to a multi-dose schedule.
    ("BE", "BE-1", "Metformin 1000 mg every morning bid", "every morning (once a day) AND bid", NPD, None),
    ("BE", "BE-2", "Metformin 1000 mg every evening, bid", "every evening AND bid", NPD, None),
    ("BE", "BE-3", "Metformin 1000 mg every night bid", "every night AND bid (= BN 'nightly bid')", NPD, None),
    ("BE", "BE-4", "Metformin 500 mg 2 tabs every morning q12h", "every morning AND q12h", NPD, None),
    ("BE", "BE-5", "เมทฟอร์มิน 1000 มก. ทุกเช้า วันละ 2 ครั้ง", "every morning, twice a day", NPD, None),
    ("BE", "BE-6", "เมทฟอร์มิน 1000 มก. ทุกเย็น วันละ 2 ครั้ง", "every evening, twice a day", NPD, None),
    ("BE", "BE-7", "เมทฟอร์มิน 1000 มก. รับประทานทุกเช้า วันละ 2 ครั้ง", "take every morning, twice a day", NPD, None),
    ("BE", "BE-8", "เมทฟอร์มิน 1000 มก. ทุกเช้า 1x2", "every morning, 1 x 2", NPD, None),
    ("BE", "BE-9", "เมทฟอร์มิน 1000 มก. ทุกค่ำ วันละ 2 ครั้ง", "every evening (ค่ำ), twice a day", NPD, None),
    # BQ7en: EN per-DAY quantity <= 1 ('1 tab a day') + MULTI (EN analogue of BQ7 'วันละ 1 เม็ด')
    ("BQ7en", "BQ7en-1", "Metformin 500 mg 1 tab a day bid", "1 tab a day, bid", NPD, None),
    ("BQ7en", "BQ7en-2", "Metformin 500 mg 1 tab per day bid", "1 tab per day, bid", NPD, None),
    ("BQ7en", "BQ7en-3", "Warfarin 3 mg 1 tab/day bid", "1 tab/day, bid", NPD, None),
    ("BQ7en", "BQ7en-4", "Warfarin 3 mg 1 tab daily morning evening", "1 tab daily, morning and evening", NPD, None),
    # name-region DAILY (before the first numeric-ish token): RR-07 declares name-region modifiers
    ("NR", "NR-1", "Metformin od 1000 mg bid", "od (once daily) AND bid; DAILY written in the name region", NPD, "RR-07"),
    ("NR", "NR-2", "Metformin q24h po 1000 mg bid", "q24h AND bid; DAILY in the name region", NPD, "RR-07"),
    ("NR", "NR-3", "เมทฟอร์มิน ทุกวัน 1000 มก. วันละ 2 ครั้ง", "every day, 1000 mg, twice a day; DAILY in the name region", NPD, "RR-07"),
    ("NR", "NR-4", "Metformin daily 1000 mg bid", "P3 control (P3_WORDS 'daily')", NPD, None),
    # spec-internal vocabulary inconsistencies (alert burden): a DAILY / slot word that C1 always rejects
    ("VOC", "VOC-1", "Metformin 500 mg everyday", "500 mg every day (d1 lists 'everyday'; V_EN_FREE lacks it)", (500.0, None), None),
    ("VOC", "VOC-2", "Metformin 500 mg 1 tab midday", "1 tab at midday (TIME_SLOTS MID lists 'midday'; V_EN_FREE lacks it)", (500.0, 1.0), None),
    ("VOC", "VOC-3", "เมทฟอร์มิน 500 มก. 1 เม็ด ทุกๆ วัน", "1 tab every day (ทุกๆ วัน, repetition mark U+0E46)", (500.0, 1.0), None),
    ("VOC", "VOC-4", "Amoxicillin 500 mg tid x 7 days", "500 mg tid for 7 days (course length)", (500.0, None), None),
    ("VOC", "VOC-5", "อะม็อกซีซิลลิน 500 มก. 1x3 นาน 7 วัน", "500 mg 1 x 3 for 7 days", (500.0, 1.0), None),
    # d2/d3/d4 spelling variants + MULTI (DAILY forms the grammar may or may not accept)
    ("DV", "DV-1", "Metformin 1000 mg every 24 hr bid", "every 24 h AND bid", NPD, None),
    ("DV", "DV-2", "Metformin 1000 mg q 24 h bid", "q 24 h AND bid", NPD, None),
    ("DV", "DV-3", "Metformin 1000 mg one time daily, bid", "one time daily AND bid", NPD, None),
    ("DV", "DV-4", "Metformin 1000 mg 1 time a day bid", "1 time a day AND bid", NPD, None),
    ("DV", "DV-5", "เมทฟอร์มิน 1000 มก. วันละ1ครั้ง เช้า เย็น", "once a day (no spaces), morning evening", NPD, None),
    ("DV", "DV-6", "เมทฟอร์มิน 1000 มก. ทุก 24 ชั่วโมง วันละ 2 ครั้ง", "every 24 h, twice a day", NPD, None),
    ("DV", "DV-7", "Metformin 1000 mg DAILY B.I.D.", "upper case, dotted", NPD, None),
    ("DV", "DV-8", "Metformin 1000 mg daily, morning & evening", "daily + 2 slots joined by '&' (NEUTRAL)", NPD, None),
    ("DV", "DV-9", "Metformin 1000 mg every-day bid", "every-day (J = '-') AND bid", NPD, None),
    # MULTI written in forms outside m1/m2 with a DAILY (Q5 'N x k' is BQ5, already reported)
    ("MV", "MV-1", "Metformin 1000 mg daily 1 tab x 2", "daily + 1 tab x 2", NPD, None),
    ("MV", "MV-2", "เมทฟอร์มิน 1000 มก. ทุกวัน 1 เม็ด x 2", "every day + 1 tab x 2", NPD, None),
    ("MV", "MV-3", "Metformin 1000 mg daily ac", "daily before meals ('ac' is not a multi-dose word)", (1000.0, None), None),
    ("MV", "MV-4", "Metformin 1000 mg daily, 2 times", "daily, 2 times", NPD, None),
    ("MV", "MV-5", "Metformin 1000 mg daily x2", "daily x2", NPD, None),
    ("MV", "MV-6", "เมทฟอร์มิน 1000 มก. ทุกวัน ครั้งละ 1 เม็ด เช้า เย็น", "every day, 1 tab per time, morning evening", NPD, None),
    # number formats (fuzz has thousands / dot_five / thai_digit classes; re-checked end to end here)
    ("NUM", "NUM-1", "Metformin 1,000 mg bid", "1000 mg bid", (1000.0, None), None),
    ("NUM", "NUM-2", "Warfarin .5 mg od", "0.5 mg od", (0.5, None), None),
    ("NUM", "NUM-3", "วาร์ฟาริน ๓ มก. ๑ เม็ด วันละ ๑ ครั้ง", "3 mg 1 tab once a day, Thai digits", (3.0, 1.0), None),
    ("NUM", "NUM-4", "Metformin 1 000 mg bid", "1000 mg bid (space as thousands separator)", (1000.0, None), None),
    ("NUM", "NUM-5", "Warfarin 2.5mg od", "2.5 mg od", (2.5, None), None),
    ("NUM", "NUM-6", "Warfarin 5. mg od", "5 mg od (trailing point)", (5.0, None), None),
    ("NUM", "NUM-7", "Metformin 1g bid", "1 g bid", (1.0, None), None),
    ("NUM", "NUM-8", "Warfarin 3 mg 1½ tab od", "1 1/2 tab", (3.0, 1.5), None),
    ("NUM", "NUM-9", "Warfarin 3 mg 1 1/2 tab od", "1 1/2 tab", (3.0, 1.5), None),
]

# BE sweep: EN 'every <slot>' / TH 'ทุก<slot>' once-daily x MULTI (m1, F1, F3, m2-with-one-extra-slot, Q5)
HEADS_EN = ["Metformin 1000 mg", "Metformin 500 mg 2 tabs", "Metformin 1000 mg po"]
HEADS_TH = ["เมทฟอร์มิน 1000 มก.", "เมทฟอร์มิน 500 มก. 2 เม็ด", "เมทฟอร์มิน 1000 มก. รับประทาน"]
EVERY_EN = ["every morning", "every evening", "every night", "every bedtime", "every noon", "nightly"]
EVERY_TH = ["ทุกเช้า", "ทุกเย็น", "ทุกค่ำ", "ทุกเที่ยง", "ก่อนนอนทุกคืน"]
MULTI_EN = ["bid", "tid", "twice daily", "q12h", "2 times a day", "1x2"]
MULTI_TH = ["วันละ 2 ครั้ง", "วันละ 3 ครั้ง", "ทุก 12 ชม.", "1x2", "bid"]
CTRL_EN = {"every morning": "daily in the morning", "every evening": "daily in the evening", "every night": "daily at night",
           "every bedtime": "daily at bedtime", "every noon": "daily at noon", "nightly": "daily at night"}


def one(text: str) -> dict:
    e = parse_entry(text)
    r = tuple(reference_parse(text))
    return {"text": text, "impl": [e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"],
                                    e["dose_unverifiable_reason"], e["frequency_code"]], "ref": list(r),
            "both_resolved": e["dose_status"] == "resolved" and r[0] == "resolved",
            "agree": [e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"], e["dose_unverifiable_reason"]] == list(r)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out"); a = ap.parse_args()
    rows = []
    for grp, fid, text, meaning, intended, rr in F:
        e = parse_entry(text)
        impl = (e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"], e["dose_unverifiable_reason"])
        ref = tuple(reference_parse(text))
        bad = non_plausible(text)
        cls = classify(impl, ref, intended, bad)
        if cls == "BLOCKER" and rr:
            cls = f"RESIDUAL ({rr})"
        rows.append({"group": grp, "id": fid, "text": text, "text_escaped": text.encode("unicode_escape").decode(),
                     "meaning": meaning, "intended": intended, "impl": list(impl) + [e["frequency_code"], e["drug_name_raw"]],
                     "ref": list(ref), "non_plausible_codepoints": bad, "declared_residual": rr, "class": cls})
        print(f"{fid:8} {cls:18} {bad or ''} impl={impl} freq={e['frequency_code']} name={e['drug_name_raw']!r}")
    sweep: dict[str, list[dict]] = {}
    for heads, evs, mus, lang in ((HEADS_EN, EVERY_EN, MULTI_EN, "en"), (HEADS_TH, EVERY_TH, MULTI_TH, "th")):
        for h, ev, m, order in itertools.product(heads, evs, mus, ("em", "me")):
            body = f"{ev} {m}" if order == "em" else f"{m} {ev}"
            sweep.setdefault(f"BE_{lang}_every_slot_x_multi", []).append(one(f"{h} {body}"))
            if lang == "en":
                cb = f"{CTRL_EN[ev]} {m}" if order == "em" else f"{m} {CTRL_EN[ev]}"
                sweep.setdefault("CTRL_en_daily_slot_x_multi", []).append(one(f"{h} {cb}"))
    summary = {}
    for g, rs in sweep.items():
        c = Counter(r["impl"][0] if r["impl"][0] != "unverifiable" else f"unverifiable/{r['impl'][4]}" for r in rs)
        summary[g] = {"n": len(rs), "both_resolved": sum(r["both_resolved"] for r in rs),
                      "impl_ref_disagree": sum(not r["agree"] for r in rs), "status": dict(c)}
        print(f"{g:30} n={len(rs):4} both_resolved={summary[g]['both_resolved']:4} disagree={summary[g]['impl_ref_disagree']} {dict(c)}")
    counts = Counter(r["class"] for r in rows)
    print(dict(counts))
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": dict(counts), "rows": rows, "sweep_summary": summary, "sweep": sweep},
                                          ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
