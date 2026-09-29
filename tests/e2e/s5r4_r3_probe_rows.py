"""e2e-tester (s5r4 rev-5 checker, 444ca3e): independent check of the rev-5 probe rows B1-B24, K9-K19 (S5R4-A06/A07).

Rows are transcribed by the checker from slices/s5r4/SPEC.md "Rev-5 probe tables" (not imported from the builder's
test file). Each row is checked on the implementation (parse_entry) and the independent reference.
Run from repo root: .venv/bin/python tests/e2e/s5r4_r3_probe_rows.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5r4_classify_findings import parse_entry, reference_parse  # noqa: E402

UT = ("unverifiable", "unparsed_token")
PUA = ("unverifiable", "per_unit_amount")
B = [
    ("B1", "Metformin 1000 mg day", UT, None), ("B2", "Metformin 1000 mg day, bid", UT, "q12h"),
    ("B3", "Metformin 500 mg 2 tabs day bid", UT, "q12h"), ("B4", "เมทฟอร์มิน 1000 มก. วัน", UT, None),
    ("B5", "เมทฟอร์มิน 1000 มก. วัน วันละ 2 ครั้ง", UT, "q12h"), ("B6", "Metformin 1000 mg po daily bid", PUA, None),
    ("B7", "Metformin 1000 mg oral daily, bid", PUA, None), ("B8", "Metformin 500 mg 2 tabs po daily bid", PUA, None),
    ("B9", "Metformin 1000 mg with meals daily q12h", PUA, None),
    ("B10", "เมทฟอร์มิน 1000 มก. รับประทานทุกวัน วันละ 2 ครั้ง", PUA, "q12h"),
    ("B11", "เมทฟอร์มิน 1000 มก. กินทุกวัน วันละ 2 ครั้ง", PUA, "q12h"),
    ("B12", "Metformin 1000 mg daily morning, evening", PUA, None),
    ("B13", "Metformin 1000 mg daily, before breakfast, before dinner", PUA, None),
    ("B14", "เมทฟอร์มิน 1000 มก. ทุกวัน เช้า เย็น", PUA, "q12h"), ("B15", "เมทฟอร์มิน 1000 มก. ทุกวัน เช้า-เย็น", PUA, "q12h"),
    ("B16", "Metformin 1000 mg qd bid", PUA, None), ("B17", "Metformin 1000 mg q.d., bid", PUA, None),
    ("B18", "Metformin 1000 mg od bid", PUA, None), ("B19", "Metformin 1000 mg q24h bid", PUA, None),
    ("B20", "Metformin 1000 mg once daily, bid", PUA, None), ("B21", "เมทฟอร์มิน 1000 มก. วันละครั้ง เช้า เย็น", PUA, None),
    ("B22", "Metformin 1000 mg po day", UT, None), ("B23", "เมทฟอร์มิน 1000 มก. รับประทาน วัน วันละ 2 ครั้ง", UT, "q12h"),
    ("B24", "เมทฟอร์มิน 500 มก. 2 เม็ด ทุกวัน เช้า ก่อนนอน", PUA, None),
]
K = [  # (id, text, value, unit, quantity, freq or None = not asserted)
    ("K9", "Alendronate 70 mg weekly", 70.0, "mg", None, None), ("K10", "Alendronate 70 mg every week", 70.0, "mg", None, None),
    ("K11", "Metformin 500 mg every day", 500.0, "mg", None, "q24h"),
    ("K12", "เมทฟอร์มิน 500 มก. 1 เม็ด ทุกวัน", 500.0, "mg", 1.0, None),
    ("K13", "เมทฟอร์มิน 500 มก. 1 เม็ด หลังอาหารเช้า ทุกวัน", 500.0, "mg", 1.0, None),
    ("K14", "เมทฟอร์มิน 500 มก. 1 เม็ด เช้า-เย็น", 500.0, "mg", 1.0, "q12h"),
    ("K15", "Metformin 500 mg daily at bedtime", 500.0, "mg", None, "q24h"),
    ("K16", "Perindopril 4 mg od", 4.0, "mg", None, "q24h"), ("K17", "Perphenazine 4 mg tid", 4.0, "mg", None, "q8h"),
    ("K18", "เมทฟอร์มิน 500 มก. วันเว้นวัน", 500.0, "mg", None, None),
    ("K19", "Metformin 500 mg daily with breakfast", 500.0, "mg", None, "q24h"),
]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out"); a = ap.parse_args()
    rows, ok_n = [], 0
    for pid, text, exp, freq in B:
        e = parse_entry(text); r = tuple(reference_parse(text))
        got = (e["dose_status"], e["dose_unverifiable_reason"])
        ok = got == exp and (r[0], r[4]) == exp and (freq is None or e["frequency_code"] == freq)
        rows.append({"id": pid, "text": text, "expected": list(exp), "freq_expected": freq, "impl": list(got),
                     "freq": e["frequency_code"], "ref": list(r), "pass": ok})
    for pid, text, v, u, q, freq in K:
        e = parse_entry(text); r = tuple(reference_parse(text))
        got = (e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"])
        exp = ("resolved", v, u, q)
        ok = got == exp and tuple(r[:4]) == exp and (freq is None or e["frequency_code"] == freq)
        rows.append({"id": pid, "text": text, "expected": list(exp), "freq_expected": freq, "impl": list(got),
                     "freq": e["frequency_code"], "ref": list(r), "pass": ok})
    for row in rows:
        ok_n += row["pass"]
        print(f"{row['id']:4} {'ok  ' if row['pass'] else 'FAIL'} impl={row['impl']} freq={row['freq']} ref={row['ref']}")
    nb = sum(r["pass"] for r in rows if r["id"].startswith("B")); nk = sum(r["pass"] for r in rows if r["id"].startswith("K"))
    print(f"B {nb}/24  K {nk}/11")
    if a.out:
        Path(a.out).write_text(json.dumps({"B_pass": nb, "K_pass": nk, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
