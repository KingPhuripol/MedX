"""e2e-tester (s5r4 checker, commit 6b2a67a). Drives the LIVE API on 127.0.0.1:8105 as pharmacist1 (rules_only).

Part A (S5R4-A04..A08, A10): every rev-3 probe row (I, SL, DT, D, QF) as a home-list entry paired with a partner order
        of a formulary drug; checks extraction (status, reason, value, unit, qty), Freq, and for unverifiable rows
        1 missing_field(dose) (field_status=unverifiable, reason) and 0 dose_mismatch, unchecked +1.
Part B: checker findings end to end. Each pair is built so that the true order differs from the home-list dose;
        'silent' means the run raised neither dose_mismatch nor missing_field(dose).
Part C (S5R4-A16): versions on the run record; role denial for a nurse.
Invisible characters are \\uXXXX escapes. All data synthetic.
Run: .venv/bin/python tests/e2e/s5r4_live_e2e.py [--api URL] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import s5_independent_e2e as base  # noqa: E402
import s5r3_live_e2e as r1  # noqa: E402

AMB = ["unverifiable", "ambiguous_quantity", None, None, None]
UNP = ["unverifiable", "unparsed_token", None, None, None]
PER = ["unverifiable", "per_unit_amount", None, None, None]
R = "resolved"
W, M = "Warfarin 3 mg 1 tab od", "Metformin 500 mg 1 tab bid"
I1 = "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง{}ชั่วโมงก่อนอาหาร"
# id: (text, expected, Freq or None, partner). SL5 uses Warfarin (Gentamicin is not in the formulary: no pair forms).
PROBES = {
    "I1": (I1.format("​"), AMB, None, W), "I2": (I1.format("‌"), AMB, None, W),
    "I3": (I1.format("⁠"), AMB, None, W), "I4": (I1.format("­"), AMB, None, W),
    "I5": (I1.format("﻿"), AMB, None, W),
    "I6": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ครึ่ง​ชั่วโมงก่อนอาหาร", AMB, None, W),
    "I7": ("Warfarin 3 mg 1 tab od​", UNP, None, W),
    "I8": ("วาร์ฟาริน 3 มก. 1 เม็ด วันละ 1 ครั้ง⁦", UNP, None, W),
    "I9": ("Warfarin 3 mg 1️ tab od", UNP, None, W),
    "I10": ("Warfarin 3 mg 1 tab‍/day", PER, None, W),
    "SL1": ("Metformin 1000 mg／day", PER, None, M), "SL2": ("Metformin 1000 mg∕day", PER, None, M),
    "SL3": ("Metformin 1000 mg\\day", PER, None, M), "SL4": ("เมทฟอร์มิน 1000 มก.／วัน", PER, None, M),
    "SL5": ("Warfarin 5 mg⧸kg q24h", PER, "q24h", W),
    "SL6": ("Metformin 500 mg 2 tabs∕day", PER, None, M), "SL7": ("Metformin 1000 mg ⁄ day", PER, None, M),
    "SL8": ("Warfarin 3 mg 1⁄2 tab od", UNP, "q24h", W),
    "SL9": ("Losartan/HCTZ 50 mg 1 tab od", UNP, "q24h", "Losartan 50 mg 1 tab od"),
    "SL10": ("Warfarin 3 mg 1 tab od ก่อนอาหาร/หลังอาหาร", UNP, "q24h", W),
    "SL11": ("Warfarin 3 mg 1/2 tab od", [R, None, 3.0, "mg", 0.5], "q24h", W),
    "DT1": ("Metformin 1000 mg./day", PER, None, M), "DT2": ("Metformin 1000 mg. per day", PER, None, M),
    "DT3": ("Levothyroxine 50 mcg./kg", PER, None, "Levothyroxine 50 mcg 1 tab od"),
    "DT4": ("Metformin 500 mg 2 tab./day", PER, None, M), "DT5": ("Metformin 500 mg 2 tabs. per day", PER, None, M),
    "DT6": ("เมทฟอร์มิน 1000 mg. ต่อวัน", PER, None, M), "DT7": ("Metformin 1000 mg (per day)", PER, None, M),
    "DT8": ("Metformin 1000 mg a day", PER, None, M), "DT9": ("Metformin 500 mg 2 tabs a day", PER, None, M),
    "DT10": ("เมทฟอร์มิน 1000 มก.่/วัน", PER, None, M), "DT11": ("Metformin 1000 mg | day", UNP, None, M),
    "DT12": ("Metformin 500 mg. bid", [R, None, 500.0, "mg", None], "q12h", M),
    "DT13": ("Metformin 500 mg 1 tab. bid", [R, None, 500.0, "mg", 1.0], "q12h", M),
    "DT14": ("Metformin 500 mg (1 tab) bid", [R, None, 500.0, "mg", 1.0], "q12h", M),
    "DT15": ("Metformin 500 mg once a day", [R, None, 500.0, "mg", None], "q24h", M),
    "D1": ("เมทฟอร์มิน 1000 มก. แบ่งวันละ 2 ครั้ง", PER, "q12h", M),
    "D2": ("เมทฟอร์มิน 1000 มก. แบ่ง วันละ 2 ครั้ง", PER, "q12h", M),
    "D3": ("เมทฟอร์มิน 1000 มก. แบ่งให้วันละ 2 ครั้ง", PER, "q12h", M),
    "D4": ("เมทฟอร์มิน 1000 มก. รวมวันละ 2 ครั้ง", PER, "q12h", M),
    "D5": ("เมทฟอร์มิน 1000 มก. ทั้งหมดต่อวัน", PER, None, M), "D6": ("เมทฟอร์มิน วันละ 1000 มก.", PER, None, M),
    "D7": ("Metformin 1000 mg in 2 divided doses", PER, None, M), "D8": ("Metformin 1000 mg divided bid", PER, "q12h", M),
    "D9": ("Metformin 1000 mg daily, split bid", PER, None, M), "D10": ("Metformin total 1000 mg bid", PER, "q12h", M),
    "D11": ("เมทฟอร์มิน 500 มก. วันละ 2 ครั้ง", [R, None, 500.0, "mg", None], "q12h", M),
    "D12": ("เมทฟอร์มิน 500 มก. ครั้งละ 1 เม็ด วันละ 2 ครั้ง", [R, None, 500.0, "mg", 1.0], "q12h", M),
    "QF1": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่งชัวโมงก่อนอาหาร", AMB, None, W),
    "QF2": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่งช.ม ก่อนอาหาร", AMB, None, W),
    "QF3": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง mn ac", AMB, None, W),
    "QF4": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง(ก่อนอาหาร)", AMB, None, W),
    "QF5": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง 30 นาทีก่อนอาหาร", AMB, None, W),
    "QF6": ("วาร์ฟาริน 3 มก. ครั้งละ 1 เม็ดครึ่งชัวโมง", AMB, None, W),
    "QF7": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง", [R, None, 3.0, "mg", 1.5], None, W),
    "QF8": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่งหลังอาหาร", [R, None, 3.0, "mg", 1.5], None, W),
    "QF9": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่งพร้อมอาหาร", [R, None, 3.0, "mg", 1.5], None, W),
    "QF10": ("Warfarin 3 mg 1 เม็ดครึ่ง od", [R, None, 3.0, "mg", 1.5], "q24h", W),
    "QF11": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ทุก 12 ชั่วโมง", [R, None, 3.0, "mg", 1.5], "q12h", W),
    "QF12": ("โอเมพราโซล 20 มก. 1 แคปซูลครึ่ง ก่อนนอน", [R, None, 20.0, "mg", 1.5], None, "Omeprazole 20 mg 1 cap hs"),
}

# Checker findings: (home entry, new order whose true dose differs from what the home entry means)
FINDINGS = {
    # B-HALF: warfarin 1.5 tab written with a Thai 'half' typing variant; order is 1 tab (a real 1.5x difference)
    "HT1_tone_order": ("วาร์ฟาริน 3 มก. 1 เม็ดคร่ึง วันละ 1 ครั้ง", W),
    "HT2_sara_uee": ("วาร์ฟาริน 3 มก. 1 เม็ดครื่ง วันละ 1 ครั้ง", W),
    "HT4_no_tone": ("วาร์ฟาริน 3 มก. 1 เม็ดครึง วันละ 1 ครั้ง", W),
    "HT7_q6_tone_order": ("วาร์ฟาริน 3 มก. ครั้งละ 1 เม็ดคร่ึง วันละ 1 ครั้ง", W),
    "HT_control_correct_spelling": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง วันละ 1 ครั้ง", W),
    # B-D1TH: divided daily total with a visually identical Thai spelling (เเ = two U+0E40 for แ); order 1000 mg bid
    "DD1_double_sara_e": ("เมทฟอร์มิน 1000 มก. เเบ่งวันละ 2 ครั้ง", "Metformin 1000 mg bid"),
    "DD2_tone_order_thangwan": ("เมทฟอร์มิน 1000 มก. ท้ังวัน", "Metformin 1000 mg bid"),
    "DD_control_D1": ("เมทฟอร์มิน 1000 มก. แบ่งวันละ 2 ครั้ง", "Metformin 1000 mg bid"),
    # B-PER: per-day / per-kg written without an R1/D1 marker form; order is the same number per dose
    "PD1_perday": ("Metformin 1000 mg perday", "Metformin 1000 mg bid"),
    "PD2_TDD": ("Metformin TDD 1000 mg bid", "Metformin 1000 mg bid"),
    "PD3_daily_dose": ("Metformin daily dose 1000 mg bid", "Metformin 1000 mg bid"),
    "PD4_mg_kg_no_slash": ("Warfarin 5 mg kg q24h", "Warfarin 5 mg 1 tab q24h"),
    # RESIDUAL (not plausibly typed): homoglyph letters in an R1/D1 marker
    "RS1_cyrillic_a_day": ("Metformin 1000 mg а day", "Metformin 1000 mg bid"),
    "RS2_fullwidth_per": ("Metformin 1000 mg ｐｅｒ day", "Metformin 1000 mg bid"),
    "RS3_cyrillic_divided": ("Metformin 1000 mg дivided bid", "Metformin 1000 mg bid"),
}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--api", default="http://127.0.0.1:8105"); ap.add_argument("--out")
    a = ap.parse_args()
    rn = r1.Runner(a.api)
    base_run = rn.run({"home_list": ["Amlodipine 5 mg od"], "new_order": ["Amlodipine 5 mg od"]})
    base_unv = (base_run.get("unchecked_by_reason") or {}).get("unverifiable", 0)
    rows = []
    for pid, (text, exp, freq, partner) in PROBES.items():
        r = rn.run({"home_list": [text], "new_order": [partner]})
        e = r1.entry(r, "home_list"); got = r1.ex(e); mf, dm = r1.dose_issues(r)
        ok = got == exp and (freq is None or e["frequency_code"] == freq)
        if exp[0] == "unverifiable":
            unv = (r.get("unchecked_by_reason") or {}).get("unverifiable", 0)
            ok = ok and len(mf) == 1 and mf[0]["detail"].get("field_status") == "unverifiable" and \
                mf[0]["detail"].get("unverifiable_reason") == exp[1] and len(dm) == 0 and unv - base_unv == 1
        rows.append({"id": pid, "run_id": r["run_id"], "text": text, "partner": partner, "extraction": got,
                     "freq": e["frequency_code"], "missing_dose": len(mf), "dose_mismatch": len(dm),
                     "unchecked_by_reason": r.get("unchecked_by_reason"), "pass": ok})
    fnd = {}
    for k, (home, order) in FINDINGS.items():
        r = rn.run({"home_list": [home], "new_order": [order]}); mf, dm = r1.dose_issues(r)
        fnd[k] = {"run_id": r["run_id"], "home": home, "order": order, "home_extraction": r1.ex(r1.entry(r, "home_list")),
                  "home_freq": r1.entry(r, "home_list")["frequency_code"], "order_extraction": r1.ex(r1.entry(r, "new_order")),
                  "issues": sorted((i["type"], i.get("field")) for i in r["issues"]), "missing_dose": len(mf),
                  "dose_mismatch": len(dm), "silent_no_dose_issue": not mf and not dm}
    versions = {k: base_run.get(k) for k in base_run if k.endswith("version")}
    nurse = base.Client(a.api).login("nurse1")
    s, _ = nurse.call("POST", "/api/pharma/reconcile", {"snapshot": r1.snap("s5r4chk-nurse", {"home_list": ["Amlodipine 5 mg od"]}),
                                                         "mode": "rules_only"})
    out = {"part_a": {"n": len(rows), "pass": sum(x["pass"] for x in rows),
                      "failed": [x for x in rows if not x["pass"]], "rows": rows},
           "part_b_findings": fnd, "part_c": {"run_versions": versions, "nurse_reconcile_status": s}}
    s_ = json.dumps(out, ensure_ascii=False, indent=1)
    print(json.dumps({"part_a": f"{out['part_a']['pass']}/{out['part_a']['n']}", "failed": [x["id"] for x in out["part_a"]["failed"]],
                      "findings": {k: (v["home_extraction"], v["issues"], "SILENT" if v["silent_no_dose_issue"] else "")
                                   for k, v in fnd.items()}, "part_c": out["part_c"]}, ensure_ascii=False, indent=1))
    if a.out:
        Path(a.out).write_text(s_, encoding="utf-8")


if __name__ == "__main__":
    main()
