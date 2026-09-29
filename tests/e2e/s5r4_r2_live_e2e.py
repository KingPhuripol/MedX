"""e2e-tester (s5r4 rev-4 checker, commit d2ff98c). Drives the LIVE API on 127.0.0.1:8105 as pharmacist1 (rules_only).

Part A: every rev-3 probe row (I, SL, DT, D, QF; reused from s5r4_live_e2e) and every rev-4 row (N, M, PU, K) from
        slices/s5r4/SPEC.md as a home-list entry paired with a formulary order; exact extraction and listed Freq.
        A10 rows (I1, SL1, DT1, D1, QF1, M1, M6, PU1, N6): 1 missing_field(dose) (unverifiable, reason), 0 dose_mismatch,
        unchecked_by_reason.unverifiable +1.
Part B: rev-4 checker findings end to end, each paired with an order whose true daily amount differs from what the
        home entry means; 'silent' = neither dose_mismatch nor missing_field(dose).
Part C: versions on the run record; nurse denied.
Non-ASCII invisible / mis-ordered marks are \\uXXXX escapes. All data synthetic.
Run: .venv/bin/python tests/e2e/s5r4_r2_live_e2e.py [--api URL] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import s5_independent_e2e as base  # noqa: E402
import s5r3_live_e2e as r1  # noqa: E402
from s5r4_live_e2e import PROBES as REV3_PROBES  # noqa: E402

UNP = ["unverifiable", "unparsed_token", None, None, None]
PER = ["unverifiable", "per_unit_amount", None, None, None]
R = "resolved"
W, M = "Warfarin 3 mg 1 tab od", "Metformin 1000 mg bid"


def res(v, q=None):
    return [R, None, v, "mg", q]


TONE_HALF = "คร่ึง"
DD = "เเบ่ง"
THANG = "ท้ัง"
REV4 = {
    "N1": (f"วาร์ฟาริน 3 มก. 1 เม็ด{TONE_HALF} วันละ 1 ครั้ง", res(3.0, 1.5), "q24h", W),
    "N2": (f"วาร์ฟาริน 3 มก. 1 เม็ด {TONE_HALF} วันละ 1 ครั้ง", res(3.0, 1.5), "q24h", W),
    "N3": (f"วาร์ฟาริน 3 มก. ครั้งละ 1 เม็ด{TONE_HALF}", res(3.0, 1.5), None, W),
    "N4": (f"วาร์ฟาริน 3 มก. 2 เม็ด{TONE_HALF} ก่อนนอน", res(3.0, 2.5), None, W),
    "N5": (f"โอเมพราโซล 20 มก. 1 แคปซูล{TONE_HALF} ก่อนนอน", [R, None, 20.0, "mg", 1.5], None, "Omeprazole 20 mg 1 cap hs"),
    "N6": (f"เมทฟอร์มิน 1000 มก. {DD}วันละ 2 ครั้ง", PER, "q12h", M),
    "N7": (f"เมทฟอร์มิน 1000 มก. {DD} วันละ 2 ครั้ง", PER, "q12h", M),
    "N8": (f"เมทฟอร์มิน 1000 มก. {DD}ทาน เช้า-เย็น", PER, None, M),
    "N9": (f"เมทฟอร์มิน 1000 มก. {THANG}วัน", PER, None, M),
    "N10": (f"เมทฟอร์มิน 1000 มก. {THANG}หมด วันละ 2 ครั้ง", PER, "q12h", M),
    "N11": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ค่ํา", res(3.0, 1.5), None, W),
    "N12": ("วาร์ฟาริน 3 มก. 1 เเคปซูล วันละ 1 ครั้ง", res(3.0, 1.0), "q24h", W),
    "N13": ("วาร์ฟาริน 3 มก. 1 เม็ดคร่่ึง", UNP, None, W),
    "M1": ("วาร์ฟาริน 3 มก. 1 เม็ดครื่ง วันละ 1 ครั้ง", UNP, None, W),
    "M2": ("วาร์ฟาริน 3 มก. 1 เม็ดครึง วันละ 1 ครั้ง", UNP, None, W),
    "M3": ("วาร์ฟาริน 3 มก. 1 เม็ดคึ่ง วันละ 1 ครั้ง", UNP, None, W),
    "M4": ("เมทฟอร์มิน 1000 มก. แบงวันละ 2 ครั้ง", UNP, None, M),
    "M5": ("Warfarin 3 mg 1 tab and a hlaf od", UNP, None, W),
    "M6": ("Metformin 1000 mg а day", UNP, None, M),
    "M7": ("Metformin 1000 mg рer day", UNP, None, M),
    "M8": ("Metformin 1000 mg ｐｅｒ day", UNP, None, M),
    "M9": ("Metformin 1000 mg дivided bid", UNP, None, M),
    "M10": ("Metformin 1000 mg dіvided bid", UNP, None, M),
    "M11": ("Warfarin 3 mg 1 tab od (Coumadin)", UNP, "q24h", W),
    "PU1": ("Metformin 1000 mg perday", PER, None, M),
    "PU2": ("Metformin 1000 mg TDD bid", PER, "q12h", M),
    "PU3": ("Metformin 1000 mg daily dose, bid", PER, None, M),
    "PU4": ("Warfarin 5 mg kg q24h", PER, "q24h", W),
    "PU5": ("Warfarin 5 mg.kg q24h", PER, "q24h", W),
    "PU6": ("Metformin 1000 mg a-day", PER, None, M),
    "PU7": ("Metformin 1000 mg daily, bid", PER, None, M),
    "PU8": ("Metformin 1000 mg every day bid", PER, None, M),
    "PU9": ("เมทฟอร์มิน 1000 มก. ทุกวัน วันละ 2 ครั้ง", PER, "q12h", M),
    "PU10": ("Metformin per day 1000 mg bid", PER, "q12h", M),
    "PU11": ("Metformin TDD 1000 mg bid", PER, "q12h", M),
    "K1": ("Atenolol 50 mg daily", res(50.0), "q24h", "Atenolol 50 mg od"),
    "K2": ("Metformin 500 mg daily pc", res(500.0), "q24h", M),
    "K3": ("Paracetamol 500 mg PO as needed", res(500.0), None, "Paracetamol 500 mg 1 tab prn"),
    "K4": ("Metformin 500 mg q.d.", res(500.0), "q24h", M),
    "K5": ("Metformin 500 mg every other day", res(500.0), None, M),
    "K6": ("เมทฟอร์มิน 500 มก. 1 เม็ด รับประทานหลังอาหาร", res(500.0, 1.0), None, M),
    "K7": ("ซาร่า 500 มก. 2 แคปซูล เวลาปวด", res(500.0, 2.0), None, "Paracetamol 500 mg 1 tab prn"),
    "K8": ("Metformin 500 mg once a day", res(500.0), "q24h", M),
}
A10 = {"I1", "SL1", "DT1", "D1", "QF1", "M1", "M6", "PU1", "N6"}

# Part B: (home entry, order). The order's true per-dose amount differs from what the home entry means.
FINDINGS = {
    "B1a_mg_day": ("Metformin 1000 mg day", "Metformin 1000 mg bid"),
    "B1b_mg_day_bid": ("Metformin 1000 mg day, bid", "Metformin 1000 mg bid"),
    "B1c_tabs_day_bid": ("Metformin 500 mg 2 tabs day bid", "Metformin 500 mg 2 tabs bid"),
    "B2a_po_daily_bid": ("Metformin 1000 mg po daily bid", "Metformin 1000 mg bid"),
    "B2b_oral_daily_bid": ("Metformin 1000 mg oral daily, bid", "Metformin 1000 mg bid"),
    "B2c_tabs_po_daily_bid": ("Metformin 500 mg 2 tabs po daily bid", "Metformin 500 mg 2 tabs bid"),
    "B2d_th_rapprathan_thukwan": ("เมทฟอร์มิน 1000 มก. รับประทานทุกวัน วันละ 2 ครั้ง", "Metformin 1000 mg bid"),
    "B2e_th_kin_thukwan": ("เมทฟอร์มิน 1000 มก. กินทุกวัน วันละ 2 ครั้ง", "Metformin 1000 mg bid"),
    "B2f_th_tab_thukwan": ("เมทฟอร์มิน 500 มก. 2 เม็ด รับประทานทุกวัน วันละ 2 ครั้ง", "Metformin 500 mg 2 tabs bid"),
    "B3a_daily_morning_evening": ("Metformin 1000 mg daily morning, evening", "Metformin 1000 mg bid"),
    "B3b_th_thukwan_chao_yen": ("เมทฟอร์มิน 1000 มก. ทุกวัน เช้า เย็น", "Metformin 1000 mg bid"),
    "B3c_th_thukwan_chao_yen_joined": ("เมทฟอร์มิน 1000 มก. ทุกวัน เช้า-เย็น", "Metformin 1000 mg bid"),
    "B4_qd_bid": ("Metformin 1000 mg qd bid", "Metformin 1000 mg bid"),
    "CTRL_PU7": ("Metformin 1000 mg daily, bid", "Metformin 1000 mg bid"),
    "CTRL_PU9": ("เมทฟอร์มิน 1000 มก. ทุกวัน วันละ 2 ครั้ง", "Metformin 1000 mg bid"),
    "CTRL_round1_HT1": (f"วาร์ฟาริน 3 มก. 1 เม็ด{TONE_HALF} วันละ 1 ครั้ง", W),
    "CTRL_round1_DD1": (f"เมทฟอร์มิน 1000 มก. {DD}วันละ 2 ครั้ง", M),
    "CTRL_round1_PD1": ("Metformin 1000 mg perday", M),
    "NOTE_perindopril_P3": ("Perindopril 4 mg od", "Perindopril 4 mg od"),
}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--api", default="http://127.0.0.1:8105"); ap.add_argument("--out")
    a = ap.parse_args()
    rn = r1.Runner(a.api)
    base_run = rn.run({"home_list": ["Amlodipine 5 mg od"], "new_order": ["Amlodipine 5 mg od"]})
    base_unv = (base_run.get("unchecked_by_reason") or {}).get("unverifiable", 0)
    rows = []
    for pid, (text, exp, freq, partner) in {**REV3_PROBES, **REV4}.items():
        r = rn.run({"home_list": [text], "new_order": [partner]})
        e = r1.entry(r, "home_list"); got = r1.ex(e); mf, dm = r1.dose_issues(r)
        ok = got == exp and (freq is None or e["frequency_code"] == freq)
        unv = (r.get("unchecked_by_reason") or {}).get("unverifiable", 0)
        a10 = None
        if pid in A10:
            a10 = (len(mf) == 1 and mf[0]["detail"].get("field_status") == "unverifiable"
                   and mf[0]["detail"].get("unverifiable_reason") == exp[1] and len(dm) == 0 and unv - base_unv == 1)
            ok = ok and a10
        rows.append({"id": pid, "run_id": r["run_id"], "text": text, "escaped": text.encode("unicode_escape").decode(),
                     "partner": partner, "expected": exp, "extraction": got, "freq": e["frequency_code"],
                     "freq_expected": freq, "missing_dose": len(mf), "dose_mismatch": len(dm),
                     "unchecked_unverifiable_delta": unv - base_unv, "a10": a10, "pass": ok})
    fnd = {}
    for k, (home, order) in FINDINGS.items():
        r = rn.run({"home_list": [home], "new_order": [order]}); mf, dm = r1.dose_issues(r)
        fnd[k] = {"run_id": r["run_id"], "home": home, "order": order,
                  "home_extraction": r1.ex(r1.entry(r, "home_list")), "home_freq": r1.entry(r, "home_list")["frequency_code"],
                  "order_extraction": r1.ex(r1.entry(r, "new_order")), "order_freq": r1.entry(r, "new_order")["frequency_code"],
                  "issues": sorted((i["type"], i.get("field") or "") for i in r["issues"]), "missing_dose": len(mf),
                  "dose_mismatch": len(dm), "silent_no_dose_issue": not mf and not dm}
    versions = {k: base_run.get(k) for k in base_run if k.endswith("version")}
    nurse = base.Client(a.api).login("nurse1")
    s, _ = nurse.call("POST", "/api/pharma/reconcile", {"snapshot": r1.snap("s5r4r2chk-nurse", {"home_list": ["Amlodipine 5 mg od"]}),
                                                         "mode": "rules_only"})
    out = {"part_a": {"n": len(rows), "pass": sum(x["pass"] for x in rows), "a10": f"{sum(bool(x['a10']) for x in rows if x['a10'] is not None)}/{len(A10)}",
                      "failed": [x for x in rows if not x["pass"]], "rows": rows},
           "part_b_findings": fnd, "part_c": {"run_versions": versions, "nurse_reconcile_status": s}}
    print(json.dumps({"part_a": f"{out['part_a']['pass']}/{out['part_a']['n']}", "a10": out["part_a"]["a10"],
                      "failed": [(x["id"], x["extraction"], x["freq"]) for x in out["part_a"]["failed"]],
                      "findings": {k: (v["home_extraction"], v["home_freq"], v["issues"], "SILENT" if v["silent_no_dose_issue"] else "")
                                   for k, v in fnd.items()}, "part_c": out["part_c"]}, ensure_ascii=False, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
