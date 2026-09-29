"""e2e-tester (s5r4 rev-5 checker, commit 444ca3e). Drives the LIVE API on 127.0.0.1:8105 as pharmacist1 (rules_only).

Part A: every rev-3 probe row (I, SL, DT, D, QF), every rev-4 row (N, M, PU, K1-K8) and every rev-5 row (B1-B24,
        K9-K19, transcribed from slices/s5r4/SPEC.md) as a home-list entry paired with a formulary order; exact
        extraction and listed Freq. A10 rows (I1, SL1, DT1, D1, QF1, M1, M6, PU1, N6, B1, B6, B12, B16): exactly 1
        missing_field(dose) (unverifiable, reason), 0 dose_mismatch, unchecked_by_reason.unverifiable +1.
Part B: rev-5 round findings end to end (Q5 'N x k' as the MULTI / once-daily statement), each paired with an order
        whose per-dose amount differs from the daily-total reading; 'silent' = neither dose_mismatch nor
        missing_field(dose). Controls: the same entry with '1 tab bid' in words (rev 5 -> per_unit_amount).
Part C: versions on the run record; nurse denied.
All data synthetic. Run: .venv/bin/python tests/e2e/s5r4_r3_live_e2e.py [--api URL] [--out FILE]
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
from s5r4_r2_live_e2e import REV4, UNP, PER, res  # noqa: E402
from s5r4_r3_probe_rows import B as B_ROWS, K as K_ROWS  # noqa: E402

M, W = "Metformin 1000 mg bid", "Warfarin 3 mg 1 tab od"
REV5 = {}
for pid, text, exp, freq in B_ROWS:
    REV5[pid] = (text, UNP if exp[1] == "unparsed_token" else PER, freq, M)
PARTNER = {"K9": "Alendronate 70 mg weekly", "K10": "Alendronate 70 mg weekly", "K16": "Perindopril 4 mg od",
           "K17": "Perphenazine 4 mg tid"}
for pid, text, v, u, q, freq in K_ROWS:
    REV5[pid] = (text, ["resolved", None, v, u, q], freq, PARTNER.get(pid, "Metformin 500 mg bid"))
A10 = {"I1", "SL1", "DT1", "D1", "QF1", "M1", "M6", "PU1", "N6", "B1", "B6", "B12", "B16"}

FINDINGS = {
    "BQ5-1_en_daily_1x2": ("Metformin 1000 mg daily 1x2", M),
    "BQ5-2_en_qd_1x2": ("Metformin 1000 mg qd 1x2", M),
    "BQ5-3_en_1x2_every_day": ("Metformin 1000 mg 1x2 every day", M),
    "BQ5-4_en_once_daily_1x2": ("Metformin 1000 mg once daily 1x2", M),
    "BQ5-5_th_thukwan_1x2": ("เมทฟอร์มิน 1000 มก. ทุกวัน 1x2", M),
    "BQ5-6_th_1x2_lang_ahan_thukwan": ("เมทฟอร์มิน 1000 มก. 1x2 หลังอาหาร ทุกวัน", M),
    "BQ5-7_th_wanlakrang_1x2": ("เมทฟอร์มิน 1000 มก. วันละครั้ง 1x2", M),
    "BQ5-8_en_daily_1x3": ("Metformin 1000 mg daily 1x3", "Metformin 1000 mg tid"),
    "BQ5b-1_en_1x1_bid": ("Metformin 1000 mg 1x1 bid", M),
    "BQ5b-2_th_1x1_chao_yen": ("เมทฟอร์มิน 1000 มก. 1x1 เช้า เย็น", M),
    "BQ5b-3_th_1x1_wanla2": ("เมทฟอร์มิน 1000 มก. 1x1 วันละ 2 ครั้ง", M),
    "BQ7-1_th_warfarin_wanla_1_tab_chao_yen": ("วาร์ฟาริน 3 มก. วันละ 1 เม็ด เช้า เย็น", "Warfarin 3 mg 1 tab bid"),
    "BQ7-2_th_metformin_wanla_1_tab_wanla_2": ("เมทฟอร์มิน 500 มก. วันละ 1 เม็ด วันละ 2 ครั้ง", "Metformin 500 mg 1 tab bid"),
    "BQ7-3_th_warfarin_wanla_half_chao_yen": ("วาร์ฟาริน 3 มก. วันละครึ่งเม็ด เช้า เย็น", "Warfarin 3 mg ½ tab bid"),
    "BQ7-4_th_metformin_wanla_1_tab_1x2": ("เมทฟอร์มิน 500 มก. วันละ 1 เม็ด 1x2", "Metformin 500 mg 1 tab bid"),
    "BN-1_en_nightly_bid": ("Metformin 1000 mg nightly bid", M),
    "CTRL_th_warfarin_1_tab_thukwan_chao_yen": ("วาร์ฟาริน 3 มก. 1 เม็ด ทุกวัน เช้า เย็น", "Warfarin 3 mg 1 tab bid"),
    "CTRL_en_daily_1_tab_bid": ("Metformin 1000 mg daily 1 tab bid", M),
    "CTRL_th_thukwan_1_tab_wanla2": ("เมทฟอร์มิน 1000 มก. ทุกวัน 1 เม็ด วันละ 2 ครั้ง", M),
    "CTRL_th_wanla1_chao_yen_B21": ("เมทฟอร์มิน 1000 มก. วันละครั้ง เช้า เย็น", M),
    "CTRL_1x2_no_daily": ("เมทฟอร์มิน 500 มก. 1x2 หลังอาหาร", "Metformin 500 mg 1 tab bid"),
}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--api", default="http://127.0.0.1:8105"); ap.add_argument("--out")
    a = ap.parse_args()
    rn = r1.Runner(a.api)
    base_run = rn.run({"home_list": ["Amlodipine 5 mg od"], "new_order": ["Amlodipine 5 mg od"]})
    base_unv = (base_run.get("unchecked_by_reason") or {}).get("unverifiable", 0)
    rows = []
    for pid, (text, exp, freq, partner) in {**REV3_PROBES, **REV4, **REV5}.items():
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
        he = r1.entry(r, "home_list")
        fnd[k] = {"run_id": r["run_id"], "home": home, "order": order, "home_extraction": r1.ex(he),
                  "home_freq": he["frequency_code"], "home_name_read": he.get("drug_name_raw"),
                  "order_extraction": r1.ex(r1.entry(r, "new_order")), "order_freq": r1.entry(r, "new_order")["frequency_code"],
                  "issues": sorted((i["type"], i.get("field") or "") for i in r["issues"]), "missing_dose": len(mf),
                  "dose_mismatch": len(dm), "silent_no_dose_issue": not mf and not dm}
    versions = {k: base_run.get(k) for k in base_run if k.endswith("version")}
    nurse = base.Client(a.api).login("nurse1")
    s, _ = nurse.call("POST", "/api/pharma/reconcile", {"snapshot": r1.snap("s5r4r3chk-nurse", {"home_list": ["Amlodipine 5 mg od"]}),
                                                         "mode": "rules_only"})
    by = lambda pre: [x for x in rows if x["id"].startswith(pre)]  # noqa: E731
    out = {"part_a": {"n": len(rows), "pass": sum(x["pass"] for x in rows),
                      "rev5_B": f"{sum(x['pass'] for x in rows if x['id'] in {p for p, *_ in B_ROWS})}/24",
                      "rev5_K9_K19": f"{sum(x['pass'] for x in rows if x['id'] in {p for p, *_ in K_ROWS})}/11",
                      "a10": f"{sum(bool(x['a10']) for x in rows if x['a10'] is not None)}/{len(A10)}",
                      "failed": [x for x in rows if not x["pass"]], "rows": rows},
           "part_b_findings": fnd, "part_c": {"run_versions": versions, "nurse_reconcile_status": s}}
    print(json.dumps({"part_a": f"{out['part_a']['pass']}/{out['part_a']['n']}", "B": out["part_a"]["rev5_B"],
                      "K": out["part_a"]["rev5_K9_K19"], "a10": out["part_a"]["a10"],
                      "failed": [(x["id"], x["extraction"], x["freq"]) for x in out["part_a"]["failed"]],
                      "findings": {k: (v["home_extraction"], v["home_freq"], v["issues"], "SILENT" if v["silent_no_dose_issue"] else "")
                                   for k, v in fnd.items()}, "part_c": out["part_c"]}, ensure_ascii=False, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
