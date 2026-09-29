"""e2e-tester (s5r4 rev-4 checker): combinatorial differential probe, implementation vs independent reference.
Builds (prefix x connector x follower) entries around §N/§C1/§P lexemes and reports every disagreement.
Synthetic strings only. Run from repo root: .venv/bin/python tests/e2e/s5r4_r2_diff.py"""
import itertools, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.pharma.mock_rules import parse_entry  # noqa: E402
from tests.pharma_dose_reference import reference_parse  # noqa: E402

HEADS = ["Metformin 1000 mg", "Metformin 500 mg 2 tabs", "เมทฟอร์มิน 1000 มก.", "เมทฟอร์มิน 500 มก. 2 เม็ด",
         "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง", "Warfarin 3 mg 1 tab", "Metformin 1000 mg.", "Warfarin 5 mg"]
SEPS = ["", " ", ", ", " (", "-", ".", "_", " - ", ". "]
WORDS = ["daily", "day", "days", "per day", "perday", "a day", "aday", "a-day", "a.day", "a_day", "every day",
         "everyday", "daily dose", "dailydose", "daily-dose", "daily_total", "daily.total", "tdd", "TDD", "T.D.D.",
         "kg", "kgs", "per kg", "po daily", "oral daily", "take daily", "qd", "q.d.", "od", "nightly", "weekly",
         "ทุกวัน", "ต่อวัน", "ต่อ วัน", "กก.", "กิโล", "รับประทานทุกวัน", "ทั้งวัน", "ท้ังวัน", "เเบ่ง",
         "แบ่ง", "รวม", "ครึ่ง", "คร่ึง", "ค่ํา", "ค่ำ", "เช้า เย็น", "ก่อนนอน", "twice", "prn",
         "p.r.n.", "with food", "divided", "split", "total", "dose", "doses", "x", "a", "per", "and", "hlaf", ""]
TAILS = ["", " bid", ", bid", " b.i.d.", " q12h", " 2 times a day", " twice daily", " วันละ 2 ครั้ง", " ทุก 12 ชั่วโมง",
         " od", " วันละ 1 ครั้ง", " เช้า เย็น"]


def impl(t):
    e = parse_entry(t)
    return (e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"], e["dose_unverifiable_reason"])


diffs, n = [], 0
for h, s, w, tl in itertools.product(HEADS, SEPS, WORDS, TAILS):
    t = f"{h}{s}{w}{tl}"
    n += 1
    a, b = impl(t), tuple(reference_parse(t))
    if a != b:
        diffs.append({"text": t, "escaped": t.encode("unicode_escape").decode(), "impl": a, "ref": b})
print(json.dumps({"n": n, "diffs": len(diffs), "examples": diffs[:40]}, ensure_ascii=False, indent=1))
