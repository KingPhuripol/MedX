"""e2e-tester (s5r4 rev-4 checker): sibling sweep of the rev-4 BLOCKER classes B1-B4 (fully PLAUSIBLE, plausibly typed,
contain a per-unit or daily word). Counts entries that implementation AND reference resolve to a per-dose value.
Run from repo root: .venv/bin/python tests/e2e/s5r4_r2_sibling_sweep.py [--out FILE]"""
import argparse, itertools, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.pharma.mock_rules import parse_entry  # noqa: E402
from tests.pharma_dose_reference import reference_parse  # noqa: E402

EN_HEADS = ["Metformin 1000 mg", "Metformin 500 mg 2 tabs", "Metformin 1000 mg,"]
TH_HEADS = ["เมทฟอร์มิน 1000 มก.", "เมทฟอร์มิน 500 มก. 2 เม็ด"]
EN_MULTI = [" bid", ", bid", " b.i.d.", " twice", " q12h", " every 12 hours", " 2 times a day", " tid", " bd"]
TH_MULTI = [" วันละ 2 ครั้ง", " ทุก 12 ชั่วโมง", " เช้า เย็น", " เช้า-เย็น"]
CLASSES = {
    # B1: per-day word right after the unit/quantity with the slash / 'per' / 'a' dropped
    "B1_en_day": [f"{h} {w}{m}" for h in EN_HEADS for w in ("day", "days") for m in [""] + EN_MULTI],
    "B1_th_wan": [f"{h} วัน{m}" for h in TH_HEADS for m in [""] + TH_MULTI],
    # B2: P4 'daily' / 'ทุกวัน' separated from the anchor by a closed-vocabulary word (route, verb, meal timing)
    "B2_en_word_daily": [f"{h} {v} daily{m}" for h in EN_HEADS for v in ("po", "PO", "oral", "orally", "by mouth", "take",
                         "with food", "with meals", "pc", "ac", "after meals") for m in EN_MULTI],
    "B2_th_word_thukwan": [f"{h} {v}ทุกวัน{m}" for h in TH_HEADS for v in ("รับประทาน", "กิน", "ทาน", "ให้", "หลังอาหาร", "ก่อนอาหาร")
                           for m in (" วันละ 2 ครั้ง", " ทุก 12 ชั่วโมง")],
    # B3: 'daily' / 'ทุกวัน' + a two-a-day schedule written with time-of-day words (not in the P4 multi-dose list)
    "B3_en_daily_times": [f"{h} daily {t}" for h in EN_HEADS for t in ("morning evening", "morning, evening",
                          "before breakfast, before dinner", "breakfast dinner", "morning night")],
    "B3_th_thukwan_times": [f"{h} ทุกวัน {t}" for h in TH_HEADS for t in ("เช้า เย็น", "เช้า-เย็น", "เช้าเย็น",
                            "ก่อนอาหารเช้า เย็น", "หลังอาหารเช้า เย็น", "เช้า ก่อนนอน")],
    # B4: daily written as qd / q.d. / od with a multi-dose frequency
    "B4_qd_multi": [f"{h} {q}{m}" for h in EN_HEADS for q in ("qd", "q.d.", "QD") for m in (" bid", ", bid", " tid", " q12h")],
}


def impl(t):
    e = parse_entry(t)
    return (e["dose_status"], e["dose_value"], e["dose_unit"], e["quantity"], e["dose_unverifiable_reason"]), e["frequency_code"]


ap = argparse.ArgumentParser(); ap.add_argument("--out"); a = ap.parse_args()
out = {}
for cls, texts in CLASSES.items():
    rows = []
    for t in texts:
        (i, f), r = impl(t), tuple(reference_parse(t))
        rows.append({"text": t, "impl": i, "freq": f, "ref": r, "ref_agrees": i == r})
    out[cls] = {"n": len(rows), "resolved_both": sum(x["impl"][0] == "resolved" and x["ref"][0] == "resolved" for x in rows),
                "ref_disagree": sum(not x["ref_agrees"] for x in rows),
                "resolved_examples": [x["text"] for x in rows if x["impl"][0] == "resolved"][:8],
                "safe_examples": [(x["text"], x["impl"][4]) for x in rows if x["impl"][0] != "resolved"][:4], "rows": rows}
    print(f"{cls:22} n={len(rows):3} resolved(both)={out[cls]['resolved_both']:3} ref_disagree={out[cls]['ref_disagree']}")
if a.out:
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
