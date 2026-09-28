"""e2e-tester (s5r5 checker, 7382c7c). LIVE API on 127.0.0.1:8105 as pharmacist1 (rules_only), synthetic data only.

New rev-5-round findings end to end (s5r5_probes.py): each home-list entry is paired with a formulary order whose
per-dose amount differs from the daily-total reading. 'silent' = neither dose_mismatch nor missing_field(dose).
Controls: the same content written with P4 DAILY words (rev 5 -> per_unit_amount -> missing_field(dose)).
Also: versions on the run record; nurse denied.
Run: .venv/bin/python tests/e2e/s5r5_live_e2e.py [--api URL] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import s5_independent_e2e as base  # noqa: E402
import s5r3_live_e2e as r1  # noqa: E402

M = "Metformin 1000 mg bid"
FINDINGS = {
    "BE-1_en_every_morning_bid": ("Metformin 1000 mg every morning bid", M),
    "BE-3_en_every_night_bid": ("Metformin 1000 mg every night bid", M),
    "BE-4_en_2tabs_every_morning_q12h": ("Metformin 500 mg 2 tabs every morning q12h", "Metformin 500 mg 1 tab bid"),
    "BE-5_th_thukchao_wanla2": ("เมทฟอร์มิน 1000 มก. ทุกเช้า วันละ 2 ครั้ง", M),
    "BE-6_th_thukyen_wanla2": ("เมทฟอร์มิน 1000 มก. ทุกเย็น วันละ 2 ครั้ง", M),
    "BE-8_th_thukchao_1x2": ("เมทฟอร์มิน 1000 มก. ทุกเช้า 1x2", M),
    "NR-1_name_region_od_bid": ("Metformin od 1000 mg bid", M),
    "NR-3_name_region_thukwan": ("เมทฟอร์มิน ทุกวัน 1000 มก. วันละ 2 ครั้ง", M),
    "CTRL_en_daily_in_the_morning_bid": ("Metformin 1000 mg daily in the morning bid", M),
    "CTRL_th_thukwan_chao_wanla2": ("เมทฟอร์มิน 1000 มก. ทุกวัน ตอนเช้า วันละ 2 ครั้ง", M),
    "CTRL_en_nightly_alone": ("Metformin 1000 mg nightly", "Metformin 1000 mg od"),
}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--api", default="http://127.0.0.1:8105"); ap.add_argument("--out")
    a = ap.parse_args()
    rn = r1.Runner(a.api)
    base_run = rn.run({"home_list": ["Amlodipine 5 mg od"], "new_order": ["Amlodipine 5 mg od"]})
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
    s, _ = nurse.call("POST", "/api/pharma/reconcile", {"snapshot": r1.snap("s5r5chk-nurse", {"home_list": ["Amlodipine 5 mg od"]}),
                                                         "mode": "rules_only"})
    out = {"findings": fnd, "run_versions": versions, "nurse_reconcile_status": s}
    for k, v in fnd.items():
        print(f"{k:36} {v['home_extraction']} freq={v['home_freq']} issues={v['issues']} {'SILENT' if v['silent_no_dose_issue'] else ''}")
    print(versions, "nurse", s)
    if a.out:
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
