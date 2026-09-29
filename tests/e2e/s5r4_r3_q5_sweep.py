"""e2e-tester (s5r4 rev-5 checker, 444ca3e): P4 sibling sweep, DAILY x MULTI written with the Q5 'N x k' production.

Q5 ("1x2", "1×2", "1 x 2", "½x2") is a grammar production that carries a times-per-day frequency (k=2 -> q12h,
k=3 -> q8h, k=4 -> q6h, k=1 -> q24h). Spec rev 5 P4 lists MULTI as m1 (bd/bid/tid/qid/twice/thrice, F1 1-23 h, F2 >= 2,
F3 >= 2) or m2 (>= 2 TIME_SLOTS); DAILY as d1-d4. Q5 is in neither list. This sweep builds
  heads x DAILY (d1-d4 spellings) x Q5 multi (k >= 2) x order x joiner
  heads x Q5 once-daily (k = 1) x MULTI (m1/m2)                         [contradiction, reported separately]
  heads x Q7 once-daily quantity ('วันละ 1 เม็ด', 'วันละครึ่งเม็ด', ...: a per-DAY amount <= 1) x MULTI (m1/m2/Q5)
  controls: the same entries with the Q5 written as the equivalent m1 words ('1 tab bid'), which rev 5 makes PUA
and counts entries both the implementation and the independent reference resolve.
Run from repo root: .venv/bin/python tests/e2e/s5r4_r3_q5_sweep.py [--out FILE]
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s5r4_classify_findings import non_plausible, parse_entry, reference_parse  # noqa: E402

HEADS_EN = ["Metformin 1000 mg", "Metformin 500 mg", "Metformin 1000 mg po"]
HEADS_TH = ["เมทฟอร์มิน 1000 มก.", "เมทฟอร์มิน 500 มก.", "เมทฟอร์มิน 1000 มก. รับประทาน"]
DAILY_EN = ["daily", "qd", "q.d.", "od", "o.d.", "every day", "everyday", "once daily", "once a day", "q24h",
            "every 24 hours"]
DAILY_TH = ["ทุกวัน", "วันละครั้ง", "วันละ 1 ครั้ง", "ทุก 24 ชม.", "รับประทานทุกวัน"]
Q5_MULTI = ["1x2", "1×2", "1 x 2", "1X2", "½x2", "1x3", "2x2"]
Q5_ONCE = ["1x1", "1×1", "1 x 1"]
MULTI_EN = ["bid", "b.i.d.", "q12h", "twice daily", "2 times a day", "morning, evening"]
MULTI_TH = ["วันละ 2 ครั้ง", "เช้า เย็น", "เช้า-เย็น", "ทุก 12 ชั่วโมง"]
JOIN = [" ", ", "]
EQUIV = {"1x2": "1 tab bid", "1×2": "1 tab bid", "1 x 2": "1 tab bid", "1X2": "1 tab bid", "½x2": "½ tab bid",
         "1x3": "1 tab tid", "2x2": "2 tabs bid"}
EQUIV_TH = {"1x2": "1 เม็ด วันละ 2 ครั้ง", "1×2": "1 เม็ด วันละ 2 ครั้ง", "1 x 2": "1 เม็ด วันละ 2 ครั้ง",
            "1X2": "1 เม็ด วันละ 2 ครั้ง", "½x2": "½ เม็ด วันละ 2 ครั้ง", "1x3": "1 เม็ด วันละ 3 ครั้ง",
            "2x2": "2 เม็ด วันละ 2 ครั้ง"}


HEADS_Q7 = ["เมทฟอร์มิน 500 มก.", "วาร์ฟาริน 3 มก.", "Metformin 500 mg"]
Q7_ONCE = ["วันละ 1 เม็ด", "วันละ 1 แคปซูล", "วันละครึ่งเม็ด", "วันละ ½ เม็ด", "วันละ 1/2 เม็ด"]
MULTI_Q7 = ["วันละ 2 ครั้ง", "เช้า เย็น", "เช้า-เย็น", "หลังอาหารเช้า เย็น", "เช้า ก่อนนอน", "ทุก 12 ชม.", "bid", "1x2"]
Q7_EQUIV = {"วันละ 1 เม็ด": "1 เม็ด ทุกวัน", "วันละ 1 แคปซูล": "1 แคปซูล ทุกวัน", "วันละครึ่งเม็ด": "ครึ่งเม็ด ทุกวัน",
            "วันละ ½ เม็ด": "½ เม็ด ทุกวัน", "วันละ 1/2 เม็ด": "1/2 เม็ด ทุกวัน"}


def run(text: str) -> dict:
    e = parse_entry(text)
    r = tuple(reference_parse(text))
    return {"text": text, "impl": [e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"],
                                    e["dose_unverifiable_reason"], e["frequency_code"]],
            "ref": list(r), "both_resolved": e["dose_status"] == "resolved" and r[0] == "resolved",
            "agree": (e["dose_status"], e["dose_unverifiable_reason"]) == (r[0], r[4]),
            "non_plausible": non_plausible(text)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out"); a = ap.parse_args()
    groups: dict[str, list[dict]] = {}
    for heads, dailies, lang in ((HEADS_EN, DAILY_EN, "en"), (HEADS_TH, DAILY_TH, "th")):
        for h, d, q, j, order in itertools.product(heads, dailies, Q5_MULTI, JOIN, ("dq", "qd")):
            body = f"{d}{j}{q}" if order == "dq" else f"{q}{j}{d}"
            groups.setdefault(f"BQ5_{lang}_daily_x_multi", []).append(run(f"{h} {body}"))
            equiv = (EQUIV if lang == "en" else EQUIV_TH)[q]
            ebody = f"{d}{j}{equiv}" if order == "dq" else f"{equiv}{j}{d}"
            groups.setdefault(f"CTRL_{lang}_daily_equiv_words", []).append(run(f"{h} {ebody}"))
    for heads, multis, lang in ((HEADS_EN, MULTI_EN, "en"), (HEADS_TH, MULTI_TH, "th")):
        for h, q, m, j in itertools.product(heads, Q5_ONCE, multis, JOIN):
            groups.setdefault(f"BQ5b_{lang}_x1_with_multi", []).append(run(f"{h} {q}{j}{m}"))
    for h, q, m in itertools.product(HEADS_Q7, Q7_ONCE, MULTI_Q7):
        groups.setdefault("BQ7_th_per_day_qty_x_multi", []).append(run(f"{h} {q} {m}"))
        groups.setdefault("CTRL_q7_equiv_thukwan", []).append(run(f"{h} {Q7_EQUIV[q]} {m}"))
    summary = {}
    for g, rows in groups.items():
        c = Counter(r["impl"][0] if r["impl"][0] != "unverifiable" else f"unverifiable/{r['impl'][4]}" for r in rows)
        summary[g] = {"n": len(rows), "both_resolved": sum(r["both_resolved"] for r in rows),
                      "impl_ref_disagree": sum(not r["agree"] for r in rows), "status": dict(c)}
        print(f"{g:32} n={len(rows):4} both_resolved={summary[g]['both_resolved']:4} disagree={summary[g]['impl_ref_disagree']} {dict(c)}")
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": summary, "groups": groups}, ensure_ascii=False, indent=1),
                               encoding="utf-8")


if __name__ == "__main__":
    main()
