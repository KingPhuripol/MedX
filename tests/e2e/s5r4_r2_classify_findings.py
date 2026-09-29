"""e2e-tester (s5r4 rev-4 checker, d2ff98c): S5R4-A21 stopping-rule classification of the rev-4 round findings.

Each finding records the text, the meaning a pharmacist reads from the displayed text, the implementation and
reference outputs, the non-PLAUSIBLE code points, and exactly one class (CONFORMANCE FAIL / BLOCKER / RESIDUAL / SAFE,
or NO MISREAD for controls). 'not per dose' = the written amount is a per-day total (or per-day amount) to be split,
which is the reading slices/s5r4/SPEC.md itself gives the same wording in PU1/PU7/PU8/PU9 (P1/P4).
Round-1 findings (HT/DD/PD/RS/SF) are re-run by tests/e2e/s5r4_classify_findings.py.
Run from repo root: .venv/bin/python tests/e2e/s5r4_r2_classify_findings.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5r4_classify_findings import classify, non_plausible, parse_entry, reference_parse  # noqa: E402

NPD = "not per dose"
F = [
    # B1: a per-day word right after the unit / quantity, with '/', 'per' or 'a' dropped (sibling of PD1 perday, PD4 mg kg)
    ("B1", "B1a", "Metformin 1000 mg day", "1000 mg per day ('/day' with the slash dropped; same class as PD4 'mg kg')", NPD),
    ("B1", "B1b", "Metformin 1000 mg day, bid", "1000 mg per day, given twice a day (500 mg per dose)", NPD),
    ("B1", "B1c", "Metformin 500 mg 2 tabs day bid", "2 tablets per day, given twice a day (1 tab per dose)", NPD),
    ("B1", "B1d", "เมทฟอร์มิน 1000 มก. วัน", "1000 mg per day ('มก./วัน' with the slash dropped)", NPD),
    ("B1", "B1e", "เมทฟอร์มิน 1000 มก. วัน วันละ 2 ครั้ง", "1000 mg per day, twice a day", NPD),
    # B2: the P4 'daily' / 'ทุกวัน' word separated from the anchor by one closed-vocabulary word (route, verb, meal)
    ("B2", "B2a", "Metformin 1000 mg po daily bid", "same as PU7 '1000 mg daily, bid' with the route word PO inserted", NPD),
    ("B2", "B2b", "Metformin 1000 mg oral daily, bid", "same as PU7 with 'oral' inserted", NPD),
    ("B2", "B2c", "Metformin 500 mg 2 tabs po daily bid", "2 tabs daily, bid (1 tab per dose), route inserted", NPD),
    ("B2", "B2d", "Metformin 1000 mg with meals daily q12h", "1000 mg daily with meals, q12h (daily total split)", NPD),
    ("B2", "B2e", "เมทฟอร์มิน 1000 มก. รับประทานทุกวัน วันละ 2 ครั้ง", "same as PU9 with the verb รับประทาน ('take') inserted", NPD),
    ("B2", "B2f", "เมทฟอร์มิน 1000 มก. กินทุกวัน วันละ 2 ครั้ง", "same as PU9 with กิน ('take') inserted", NPD),
    ("B2", "B2g", "เมทฟอร์มิน 500 มก. 2 เม็ด รับประทานทุกวัน วันละ 2 ครั้ง", "2 tabs every day, twice a day (PU9 wording on the quantity)", NPD),
    # B3: 'daily' / 'ทุกวัน' + a twice-a-day schedule written as time-of-day words (not in the P4 multi-dose list)
    ("B3", "B3a", "Metformin 1000 mg daily morning, evening", "1000 mg daily, split morning and evening", NPD),
    ("B3", "B3b", "Metformin 1000 mg daily, before breakfast, before dinner", "1000 mg daily, split before breakfast and dinner", NPD),
    ("B3", "B3c", "เมทฟอร์มิน 1000 มก. ทุกวัน เช้า เย็น", "1000 mg every day, morning and evening (PU9 with the bid written as เช้า เย็น)", NPD),
    ("B3", "B3d", "เมทฟอร์มิน 1000 มก. ทุกวัน เช้า-เย็น", "same, joined with '-'", NPD),
    # B4: daily written as the abbreviation qd with a multi-dose frequency (PU7 with 'daily' abbreviated)
    ("B4", "B4a", "Metformin 1000 mg qd bid", "1000 mg daily (qd), given bid", NPD),
    ("B4", "B4b", "Metformin 1000 mg q.d., bid", "same, dotted", NPD),
    # controls that the spec requires to stay resolved / the rev-4 fixes that now hold
    ("CTRL", "K1", "Atenolol 50 mg daily", "50 mg once daily", (50.0, None)),
    ("CTRL", "N1", "วาร์ฟาริน 3 มก. 1 เม็ดคร่ึง วันละ 1 ครั้ง", "1 1/2 tab (tone mark before vowel)", (3.0, 1.5)),
    ("CTRL", "D11", "เมทฟอร์มิน 500 มก. วันละ 2 ครั้ง", "500 mg twice a day (RR-01 shape, per-dose reading)", (500.0, None)),
    # alert-burden notes (SAFE): spec-mandated unverifiable results on ordinary entries
    ("NOTE", "AB1", "Perindopril 4 mg od", "4 mg once daily (P3: a name-region word starting with 'per')", (4.0, None)),
    ("NOTE", "AB2", "Warfarin 3 mg 1 tab od (Coumadin)", "M11: brand after the dose", (3.0, 1.0)),
]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out"); a = ap.parse_args()
    rows = []
    for grp, fid, text, meaning, intended in F:
        e = parse_entry(text)
        impl = (e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"], e["dose_unverifiable_reason"])
        ref = tuple(reference_parse(text))
        bad = non_plausible(text)
        cls = classify(impl, ref, intended, bad)
        rows.append({"group": grp, "id": fid, "text": text, "text_escaped": text.encode("unicode_escape").decode(),
                     "meaning": meaning, "impl": list(impl) + [e["frequency_code"], e["drug_name_raw"]],
                     "ref": list(ref), "non_plausible_codepoints": bad, "class": cls})
        print(f"{fid:4} {cls:17} {bad or ''} impl={impl} freq={e['frequency_code']}")
    summary = {}
    for r in rows:
        summary[r["class"]] = summary.get(r["class"], 0) + 1
    print(summary)
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
