"""e2e-tester (s5r4 checker, commit 6b2a67a): independent sibling probes beyond the declared rev-3 tables.

For each probe: implementation parse_entry vs builder reference_parse, the checker's expected reading from
s5r3 rev 3 (spec-literal), the PLAUSIBLE check of s5r4 SPEC (stopping rule), and a classification.
Invisible characters are written as \\uXXXX escapes. Synthetic unit-level strings; no eval split.
Run from repo root: .venv/bin/python tests/e2e/s5r4_checker_probes.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.pharma.mock_rules import parse_entry  # noqa: E402
from tests.pharma_dose_reference import reference_parse  # noqa: E402

PLAUSIBLE_EXTRA = set("½¼¾×–—µ‘’“”…")


def non_plausible(text: str) -> list[str]:
    bad = []
    for c in text:
        cp = ord(c)
        if 0x20 <= cp <= 0x7E or 0x0E00 <= cp <= 0x0E7F or c.isspace() or c in PLAUSIBLE_EXTRA:
            continue
        bad.append(f"U+{cp:04X}")
    return bad


def impl(text):
    e = parse_entry(text)
    return [e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"], e["dose_unverifiable_reason"],
            e["frequency_code"]]


# id, text, intended clinical meaning (value, qty) or note, spec-literal expectation note
PROBES = [
    # --- Thai half-tablet word with typing variants (Q4b sibling: the half is silently dropped)
    ("HT1", "วาร์ฟาริน 3 มก. 1 เม็ดคร่ึง วันละ 1 ครั้ง", "1.5 tab (tone mark typed before the vowel)"),
    ("HT2", "วาร์ฟาริน 3 มก. 1 เม็ดครื่ง วันละ 1 ครั้ง", "1.5 tab (sara uee for sara ue: ครื่ง)"),
    ("HT3", "วาร์ฟาริน 3 มก. 1 เม็ด คร่ึง วันละ 1 ครั้ง", "1.5 tab (spaced, tone-mark order)"),
    ("HT4", "วาร์ฟาริน 3 มก. 1 เม็ดครึง วันละ 1 ครั้ง", "1.5 tab (tone mark omitted: ครึง)"),
    ("HT5", "วาร์ฟาริน 3 มก. 1 เม็ดคึ่ง วันละ 1 ครั้ง", "1.5 tab (dropped ร: คึ่ง)"),
    ("HT6", "วาร์ฟาริน 3 มก. 1 เม็ดกับอีกครึ่ง วันละ 1 ครั้ง", "1.5 tab (1 tab and another half)"),
    ("HT7", "วาร์ฟาริน 3 มก. ครั้งละ 1 เม็ดคร่ึง", "1.5 tab via Q6, tone-mark order"),
    ("HT8", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง วันละ 1 ครั้ง", "control: 1.5 resolved"),
    ("HT9", "Warfarin 3 mg 1 tab and a half od", "1.5 tab EN"),
    ("HT10", "Warfarin 3 mg 1 tab + half od", "1.5 tab EN"),
    ("HT11", "Warfarin 3 mg 1 and half tab od", "1.5 tab EN"),
    ("HT12", "Warfarin 3 mg 1 tab hlf od", "1.5 tab EN misspelled half (implausible wording)"),
    # --- daily total / per-unit markers not in D1/R1
    ("DT_a", "Metformin 1000 mg perday", "1000 mg per day (joined 'per day'; 'aday' is covered by R1 b)"),
    ("DT_b", "Metformin TDD 1000 mg bid", "total daily dose 1000 mg, split bid"),
    ("DT_c", "Metformin daily dose 1000 mg bid", "daily dose 1000 mg, split bid"),
    ("DT_d", "Metformin 1000 mg/d", "control: per_unit"),
    ("DT_e", "Metformin 1000 mg a-day", "1000 mg per day (hyphen)"),
    ("DT_f", "Metformin 1000 mg each day bid", "1000 mg per day split bid"),
    ("DT_g", "Metformin 1000 mg per24h", "per 24 h joined"),
    ("DT_h", "Gentamicin 5 mg kg q24h", "5 mg/kg with slash omitted"),
    ("DT_i", "Metformin 1000 mg in two doses", "control: 'doses' D1"),
    ("DT_j", "เมทฟอร์มิน 1000 มก.ต่อวัน แบ่ง 2 ครั้ง", "control D1"),
    ("DT_k", "เมทฟอร์มิน 1000 มก. ใน 1 วัน", "1000 mg in 1 day"),
    ("DT_l", "เมทฟอร์มิน ขนาดยาต่อวัน 1000 มก.", "control D1 ต่อวัน"),
    ("DT_m", "เมทฟอร์มิน 1000 มก./ 24 ชม.", "control slash"),
    ("DT_n", "Metformin 1000 mg qd divided", "control D1"),
    ("DT_o", "Metformin 1000 mg daily in 2 dose", "daily in 2 dose -> number unconsumed"),
    ("DT_p", "Metformin 1000 mg/day.", "control"),
    ("DT_q", "Metformin 1000 mg per", "dangling per"),
    ("DT_r", "Metformin 1000 mg p.d.", "p.d. = per day abbreviation"),
    ("DT_s", "Metformin 1000mg PER DAY", "casefold control"),
    ("DT_t", "Metformin 1000 mg A DAY", "casefold control"),
    ("DT_u", "Metformin 1000 mg a  day", "double space control"),
    ("DT_v", "Metformin 1000 mg\tper\tday", "tab whitespace control"),
    ("DT_w", "Metformin 1000 mg; per day", "NEUTRAL tail then per"),
    ("DT_x", "Metformin 1000 mg, a day", "NEUTRAL tail then a day"),
    ("DT_y", "Metformin 1000 mg ‘per day’", "curly quotes tail (plausible, non-NEUTRAL)"),
    ("DT_z", "Metformin 1000 mg… bid", "ellipsis tail"),
    # --- slash/invisible spot checks outside the tables
    ("SX1", "Metformin 1000 mg⁄day", "fraction slash"),
    ("SX2", "Metformin 1000 mg ∕ day", "division slash spaced"),
    ("SX3", "Warfarin 3 mg ½ tab od", "control Q2"),
    ("SX4", "Warfarin 3 mg 1/2tab od", "control Q2 joined"),
    ("SX5", "Warfarin 3 mg 1 / 2 tab od", "control Q2 spaced"),
    ("SX6", "Warfarin 3/1 mg od", "S2 look: 3/1 mg"),
    ("SX7", "Warfarin 3 mg 1 tab od  ", "NBSP (isspace) control"),
    ("SX8", "Warfarin 3 mg 1 tab od　", "ideographic space control"),
    ("SX9", "Warfarin 3 mg 1 tab od ", "line separator (isspace)"),
    ("SX10", "Warfarin 3 mg 1 tab od\u0085", "NEL (Cc, isspace)"),
    ("SX11", "Warfarin 3 mg 1 tab od\u001f", "US (Cc, isspace)"),
    ("SX12", "Warfarin 3 mg 1 tab od\u000b", "VT (Cc, isspace)"),
    ("SX13", "Warfarin 3 mg 1 tab od\u0000", "NUL Cc not space"),
    # --- QF edges
    ("QX1", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ก่อนอาหาร", "control resolved 1.5"),
    ("QX2", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง.", "dot after ครึ่ง"),
    ("QX3", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง OD", "casefold QF en"),
    ("QX4", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง q 8 h", "F1 start"),
    ("QX5", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ครึ่ง ชม. ก่อนอาหาร", "T1 start"),
    ("QX6", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง-ก่อนอาหาร", "hyphen follower"),
    ("QX7", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง นาน 7 วัน", "Thai non-QF"),
    ("QX8", "วาร์ฟาริน 3 มก. วันละ 1 เม็ดครึ่ง", "Q7 1.5 > 1 ambiguous"),
    ("QX9", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง twice a day", "F2 start"),
    ("QX10", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง 2 times a day", "F2 start INT"),
    ("QX11", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง เช้าเย็น", "Thai QF"),
    ("QX12", "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ชั่วโมง", "TW directly: fails QF"),
    # --- D1 edges
    ("DX1", "เมทฟอร์มิน 1000 มก. กินต่อ วันละ 1 ครั้ง", "exception control (but R1 b ต่อ?)"),
    ("DX2", "เมทฟอร์มิน 500 มก. 1 เม็ด กินต่อวันละ 1 ครั้ง", "exception joined"),
    ("DX3", "Metformin 1000 mg Divided BID", "casefold"),
    ("DX4", "Metformin 1000 mg total-daily bid", "total hyphen"),
    ("DX5", "เมทฟอร์มิน 1000 มก. แ บ่ง วันละ 2 ครั้ง", "spaced inside word -> whitespace removed -> marker"),
    ("DX6", "เมทฟอร์มิน วันละ 500 มก. 2 ครั้ง", "วันละ S1"),
    ("DX7", "เมทฟอร์มิน 500 มก. 1 เม็ด วันละ 2 ครั้ง ต่อ กก.", "ต่อ กก marker"),
]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out"); a = ap.parse_args()
    rows = []
    for pid, text, meaning in PROBES:
        i = impl(text); r = list(reference_parse(text))
        agree = (i[0], i[1], i[2], i[3], i[4]) == (r[0], r[1], r[2], r[3], r[4])
        rows.append({"id": pid, "text": text, "codepoints_non_plausible": non_plausible(text), "meaning": meaning,
                     "impl": i, "ref": r, "impl_ref_agree": agree})
        print(json.dumps(rows[-1], ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
