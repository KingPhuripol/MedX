"""e2e-tester (s5r4 rev-5 checker, 444ca3e): S5R4-A21 stopping-rule classification of the rev-5 round findings.

Each finding: text, the meaning a pharmacist reads from the displayed text, impl and reference outputs, non-PLAUSIBLE
code points, exactly one class (CONFORMANCE FAIL / BLOCKER / RESIDUAL / SAFE; NO MISREAD for controls).
'not per dose' = the entry holds a once-daily / per-day statement AND a multi-dose statement. slices/s5r4/SPEC.md §P
("Why these are safe to add") gives that combination this reading: "the strength could be a daily total, or the entry
contradicts itself. Either way, no per-dose value may be chosen", and the same content written with the listed words
gives per_unit_amount (controls C-*). Round-1/2 findings are re-run by s5r4_classify_findings.py and
s5r4_r2_classify_findings.py. Run from repo root: .venv/bin/python tests/e2e/s5r4_r3_classify_findings.py [--out FILE]
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
    # BQ5: DAILY (d1-d4) + MULTI written as the Q5 production 'N x k' (k >= 2); Q5 is not in P4 m1/m2
    ("BQ5", "BQ5-1", "Metformin 1000 mg daily 1x2", "1000 mg daily, 1 tab x 2 a day (= C-1 '1000 mg daily 1 tab bid', which is PUA)", NPD),
    ("BQ5", "BQ5-2", "Metformin 1000 mg qd 1x2", "B16 'qd bid' with bid written 1x2", NPD),
    ("BQ5", "BQ5-3", "Metformin 1000 mg 1x2 every day", "every day + 1 tab twice a day", NPD),
    ("BQ5", "BQ5-4", "Metformin 1000 mg once daily 1x2", "B20 'once daily, bid' with bid written 1x2", NPD),
    ("BQ5", "BQ5-5", "เมทฟอร์มิน 1000 มก. ทุกวัน 1x2", "B14 'ทุกวัน เช้า เย็น' / PU9 with the twice-a-day written 1x2", NPD),
    ("BQ5", "BQ5-6", "เมทฟอร์มิน 1000 มก. 1x2 หลังอาหาร ทุกวัน", "1x2 after meals, every day", NPD),
    ("BQ5", "BQ5-7", "เมทฟอร์มิน 1000 มก. วันละครั้ง 1x2", "B21 'วันละครั้ง เช้า เย็น' with the schedule written 1x2", NPD),
    ("BQ5", "BQ5-8", "Metformin 1000 mg daily 1x3", "daily + 1 tab three times a day", NPD),
    ("BQ5", "BQ5-9", "Metformin 1000 mg daily ½x2", "daily + half tab twice a day", NPD),
    # BQ7: Q7 per-DAY quantity <= 1 ('วันละ 1 เม็ด' = one tablet a day) + MULTI; Q7 > 1 is already a daily total
    ("BQ7", "BQ7-1", "วาร์ฟาริน 3 มก. วันละ 1 เม็ด เช้า เย็น", "1 tab a day, morning and evening (half tab per dose, or contradictory); = C-4 which is PUA", NPD),
    ("BQ7", "BQ7-2", "เมทฟอร์มิน 500 มก. วันละ 1 เม็ด วันละ 2 ครั้ง", "1 tab a day, twice a day", NPD),
    ("BQ7", "BQ7-3", "วาร์ฟาริน 3 มก. วันละครึ่งเม็ด เช้า เย็น", "half a tab a day, morning and evening (quarter tab per dose)", NPD),
    ("BQ7", "BQ7-4", "เมทฟอร์มิน 500 มก. วันละ 1 เม็ด 1x2", "1 tab a day, 1 x 2", NPD),
    ("BQ7", "BQ7-5", "Metformin 500 mg วันละ 1 เม็ด bid", "1 tab a day, bid (mixed EN/TH)", NPD),
    # BQ5b: Q5 'N x 1' (once a day, = d4 'วันละ 1 ครั้ง') + MULTI
    ("BQ5b", "BQ5b-1", "Metformin 1000 mg 1x1 bid", "1 tab once a day AND bid (= C-3 '1 tab once daily, bid', which is PUA)", NPD),
    ("BQ5b", "BQ5b-2", "เมทฟอร์มิน 1000 มก. 1x1 เช้า เย็น", "= C-2 '1 เม็ด วันละครั้ง เช้า เย็น', which is PUA", NPD),
    ("BQ5b", "BQ5b-3", "เมทฟอร์มิน 1000 มก. 1x1 วันละ 2 ครั้ง", "once a day and twice a day", NPD),
    # BN: 'nightly' (once a day at night; in V_EN_FREE, not in P4 DAILY) + MULTI
    ("BN", "BN-1", "Metformin 1000 mg nightly bid", "nightly (once a day) AND bid (= C-5 'daily at bedtime bid', which is PUA)", NPD),
    ("BN", "BN-2", "Metformin 500 mg 2 tabs nightly bid", "B8 shape with 'nightly'", NPD),
    # controls: same content written with the spec's listed words -> unverifiable (rev 5 P4)
    ("CTRL", "C-1", "Metformin 1000 mg daily 1 tab bid", "control for BQ5-1", NPD),
    ("CTRL", "C-2", "เมทฟอร์มิน 1000 มก. 1 เม็ด วันละครั้ง เช้า เย็น", "control for BQ5b-2", NPD),
    ("CTRL", "C-3", "Metformin 1000 mg 1 tab once daily, bid", "control for BQ5b-1", NPD),
    ("CTRL", "C-4", "วาร์ฟาริน 3 มก. 1 เม็ด ทุกวัน เช้า เย็น", "control for BQ7-1", NPD),
    ("CTRL", "C-5", "Metformin 1000 mg daily at bedtime bid", "control for BN-1", NPD),
    ("CTRL", "C-6", "เมทฟอร์มิน 500 มก. 1x2 หลังอาหาร", "1 tab twice a day after meals, no DAILY statement (Q5 alone)", (500.0, 1.0)),
    ("CTRL", "C-7", "เมทฟอร์มิน 500 มก. วันละ 1 เม็ด", "1 tab once a day (Q7 alone)", (500.0, 1.0)),
    # SAFE notes
    ("NOTE", "N-m1", "Metformin bid 1000 mg daily", "m1 'bid' in the NAME region; spec text says the dose region holds DAILY and MULTI; impl and ref read m1 over the whole entry (as rev 4; needed for A09) -> unverifiable", NPD),
    ("NOTE", "AB2", "Warfarin 3 mg 1 tab od (Coumadin)", "M11 brand after the dose (pharmacist review list)", (3.0, 1.0)),
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
        if grp == "CTRL" and cls == "SAFE":
            cls = "SAFE (control)"
        rows.append({"group": grp, "id": fid, "text": text, "text_escaped": text.encode("unicode_escape").decode(),
                     "meaning": meaning, "impl": list(impl) + [e["frequency_code"], e["drug_name_raw"]],
                     "ref": list(ref), "non_plausible_codepoints": bad, "class": cls})
        print(f"{fid:7} {cls:17} {bad or ''} impl={impl} freq={e['frequency_code']}")
    summary = {}
    for r in rows:
        summary[r["class"]] = summary.get(r["class"], 0) + 1
    print(summary)
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
