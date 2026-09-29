"""e2e-tester (s5r4 checker): S5R4-A21 stopping-rule classification with the PLAUSIBLE check as a script.

Each finding: the text, the meaning a pharmacist reads from the displayed text, the value that meaning implies,
the implementation and reference outputs, the non-PLAUSIBLE code points, and exactly one class:
  CONFORMANCE FAIL  implementation != reference (or != s5r3 rev-3 row)       (none expected here; checked)
  SAFE              implementation unverifiable / not_stated
  BLOCKER           both resolve to a value != intended, entry fully PLAUSIBLE, outside any rule
  RESIDUAL          same MISREAD, entry has >= 1 non-PLAUSIBLE code point
Invisible characters are \\uXXXX escapes. Synthetic strings only.
Run from repo root: .venv/bin/python tests/e2e/s5r4_classify_findings.py [--out FILE]
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

# s5r4 SPEC stopping rule: PLAUSIBLE = ASCII U+0020-U+007E, Thai U+0E00-U+0E7F, str.isspace(), and these.
PLAUSIBLE_EXTRA = set("½¼¾×–—µ‘’“”…")


def non_plausible(text: str) -> list[str]:
    return [f"U+{ord(c):04X}" for c in text
            if not (0x20 <= ord(c) <= 0x7E or 0x0E00 <= ord(c) <= 0x0E7F or c.isspace() or c in PLAUSIBLE_EXTRA)]


# (finding group, id, text, meaning read from the displayed text, intended (value, qty) or "not per dose")
F = [
    ("B-HALF", "HT1", "วาร์ฟาริน 3 มก. 1 เม็ดคร่ึง วันละ 1 ครั้ง", "1 1/2 tab (tone mark keyed before sara ue; renders as ครึ่ง)", (3.0, 1.5)),
    ("B-HALF", "HT2", "วาร์ฟาริน 3 มก. 1 เม็ดครื่ง วันละ 1 ครั้ง", "1 1/2 tab (sara uee typo: ครื่ง)", (3.0, 1.5)),
    ("B-HALF", "HT3", "วาร์ฟาริน 3 มก. 1 เม็ด คร่ึง วันละ 1 ครั้ง", "1 1/2 tab (spaced, tone-mark order)", (3.0, 1.5)),
    ("B-HALF", "HT4", "วาร์ฟาริน 3 มก. 1 เม็ดครึง วันละ 1 ครั้ง", "1 1/2 tab (tone mark omitted: ครึง)", (3.0, 1.5)),
    ("B-HALF", "HT5", "วาร์ฟาริน 3 มก. 1 เม็ดคึ่ง วันละ 1 ครั้ง", "1 1/2 tab (ร dropped: คึ่ง)", (3.0, 1.5)),
    ("B-HALF", "HT7", "วาร์ฟาริน 3 มก. ครั้งละ 1 เม็ดคร่ึง", "1 1/2 tab via Q6 (tone-mark order)", (3.0, 1.5)),
    ("B-HALF", "HT8", "วาร์ฟาริน 3 มก. 2 เม็ดคร่ึง ก่อนนอน", "2 1/2 tab (tone-mark order)", (3.0, 2.5)),
    ("B-HALF", "HT9", "โอเมพราโซล 20 มก. 1 แคปซูลคร่ึง ก่อนนอน", "1 1/2 cap (tone-mark order)", (20.0, 1.5)),
    ("B-D1TH", "DD1", "เมทฟอร์มิน 1000 มก. เเบ่งวันละ 2 ครั้ง", "1000 mg/day divided bid (เเ = 2x U+0E40 for แ; renders as แบ่ง)", "not per dose"),
    ("B-D1TH", "DD2", "เมทฟอร์มิน 1000 มก. เเบ่ง วันละ 2 ครั้ง", "same, spaced", "not per dose"),
    ("B-D1TH", "DD3", "เมทฟอร์มิน 1000 มก. เเบ่งทาน เช้า-เย็น", "1000 mg/day divided morning-evening", "not per dose"),
    ("B-D1TH", "DD4", "เมทฟอร์มิน 1000 มก. ท้ังวัน", "1000 mg for the whole day (tone-mark order in ทั้งวัน)", "not per dose"),
    ("B-D1TH", "DD5", "เมทฟอร์มิน 1000 มก. ท้ังหมด วันละ 2 ครั้ง", "total 1000 mg, bid (tone-mark order in ทั้งหมด)", "not per dose"),
    ("B-PER", "PD1", "Metformin 1000 mg perday", "1000 mg per day (joined 'per day'; R1 b accepts joined 'aday')", "not per dose"),
    ("B-PER", "PD2", "Metformin 1000 mg TDD bid", "total daily dose 1000 mg, split bid", "not per dose"),
    ("B-PER", "PD3", "Metformin 1000 mg daily dose, bid", "daily dose 1000 mg, split bid", "not per dose"),
    ("B-PER", "PD4", "Warfarin 5 mg kg q24h", "5 mg/kg (slash omitted)", "not per dose"),
    ("B-PER", "PD5", "Warfarin 5 mg.kg q24h", "5 mg.kg (mg per kg)", "not per dose"),
    ("B-PER", "PD6", "Metformin 1000 mg a-day", "1000 mg a day (hyphenated)", "not per dose"),
    ("RESID", "RS1", "Metformin 1000 mg а day", "1000 mg a day (Cyrillic a)", "not per dose"),
    ("RESID", "RS2", "Metformin 1000 mg рer day", "1000 mg per day (Cyrillic er)", "not per dose"),
    ("RESID", "RS3", "Metformin 1000 mg ｐｅｒ day", "1000 mg per day (full-width per)", "not per dose"),
    ("RESID", "RS4", "Metformin 1000 mg дivided bid", "1000 mg divided bid (Cyrillic de)", "not per dose"),
    ("RESID", "RS5", "Metformin 1000 mg dіvided bid", "1000 mg divided bid (Cyrillic i)", "not per dose"),
    ("SAFE", "SF1", "เมทฟอร์มิน วันละ 1000 มก.", "D6 row: marker before strength", "not per dose"),
    ("SAFE", "SF2", "Metformin total 1000 mg bid", "D10 row: marker before strength", "not per dose"),
    ("SAFE", "SF3", "Metformin 1000 mg╱day", "box-drawing diagonal (not SLASH-LIKE by name)", "not per dose"),
    ("SAFE", "SF4", "Warfarin 3 mg 1 tab and a half od", "1 1/2 tab EN wording", (3.0, 1.5)),
    ("SAFE", "SF5", "วาร์ฟาริน 3 มก. 1 เม็ดกับอีกครึ่ง วันละ 1 ครั้ง", "1 tab and another half", (3.0, 1.5)),
    ("SAFE", "SF6", "Metformin 1000 mg in 2 дivided doses", "homoglyph, but 'doses' still marks D1", "not per dose"),
]


def classify(impl, ref, intended, bad):
    if impl[:5] != ref:
        return "CONFORMANCE FAIL"
    if impl[0] != "resolved":
        return "SAFE"
    if intended == "not per dose":
        wrong = True
    else:
        wrong = (impl[1], impl[3]) != intended
    if not wrong:
        return "NO MISREAD"
    return "RESIDUAL" if bad else "BLOCKER"


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
        print(f"{fid:4} {cls:17} {bad or ''} impl={impl} name={e['drug_name_raw']!r}")
    summary = {}
    for r in rows:
        summary[r["class"]] = summary.get(r["class"], 0) + 1
    print(summary)
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
