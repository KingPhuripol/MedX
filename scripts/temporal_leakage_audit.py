#!/usr/bin/env python3
"""Temporal leakage and patient-split audit (slice s1). Stdlib only. Exit 0 only on PASS.

  --dataset DIR              audit a generated dataset (writes DIR/audit_report.json)
  <journey.json> --as-of T   legacy mode: flag items with available_at_time > T
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

GOLD_KEYS = {"target_department", "red_flags", "rule_id", "required_fields", "medication_issues",
             "expected_action", "injection_id", "issue_type", "department_evaluable", "department_reason"}


def _t(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        raise ValueError(f"naive datetime {ts!r}")
    return dt


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def audit_dataset(ds: Path) -> dict:
    errors: list[str] = []
    splits = _load(ds / "splits.json")
    seen: dict[str, set[str]] = {}
    n_pairs = n_pass = n_cases = 0
    inputs = ds / "inputs"
    for p in sorted(inputs.rglob("*")):
        rel = p.relative_to(inputs).parts
        if p.is_dir() and "gold" in p.name.lower():
            errors.append(f"gold directory under inputs: {p}")
        if p.is_file() and (len(rel) != 3 or not (p.name == "journey.json" or
                                                   (p.name.startswith("snapshot_") and p.suffix == ".json"))):
            errors.append(f"unexpected file under inputs: {p}")
        if p.is_file() and p.suffix == ".json" and GOLD_KEYS & set(_keys(_load(p))):
            errors.append(f"gold key in input file {p}: {sorted(GOLD_KEYS & set(_keys(_load(p))))}")
    for split_dir in sorted(x for x in inputs.iterdir() if x.is_dir()):
        for case_dir in sorted(x for x in split_dir.iterdir() if x.is_dir()):
            n_cases += 1
            split, case_id = split_dir.name, case_dir.name
            j = _load(case_dir / "journey.json")
            pref = j["patient_ref"]
            seen.setdefault(pref, set()).add(split)
            if splits.get(pref) != split:
                errors.append(f"{case_id}: patient {pref} in dir split {split} but splits.json says {splits.get(pref)}")
            if j.get("split") != split or j["case_id"] != case_id:
                errors.append(f"{case_id}: journey split/case_id disagree with directory")
            for it in j["items"]:
                if it["patient_ref"] != pref:
                    errors.append(f"{case_id}: item {it['item_id']} patient_ref {it['patient_ref']} != {pref}")
                if it.get("encounter_ref") != case_id:
                    errors.append(f"{case_id}: item {it['item_id']} encounter_ref mismatch")
                if not (_t(it["event_time"]) <= _t(it["observed_at"]) <= _t(it["available_at_time"])):
                    errors.append(f"{case_id}: item {it['item_id']} violates event<=observed<=available")
            snaps = sorted(case_dir.glob("snapshot_*.json"))
            snap_ts = []
            for sp in snaps:
                s = _load(sp)
                T = _t(s["as_of"])
                snap_ts.append(s["as_of"])
                n_pairs += 1
                bad = [it["item_id"] for it in s["items"] if _t(it["available_at_time"]) > T]
                expected = [it for it in j["items"] if _t(it["available_at_time"]) <= T]
                ok = not bad and s["items"] == expected and s["patient_ref"] == pref
                if bad:
                    errors.append(f"{case_id}@{s['as_of']}: future items in snapshot {bad}")
                if s["items"] != expected:
                    errors.append(f"{case_id}@{s['as_of']}: snapshot != filter(journey, T)")
                if s["patient_ref"] != pref:
                    errors.append(f"{case_id}@{s['as_of']}: snapshot patient_ref mismatch")
                n_pass += ok
            if sorted(snap_ts, key=_t) != j["decision_times"]:
                errors.append(f"{case_id}: snapshot Ts {snap_ts} != journey decision_times")
            gp = ds / "gold" / split / f"{case_id}.json"
            if not gp.is_file():
                errors.append(f"{case_id}: gold file missing in split {split}")
            else:
                g = _load(gp)
                gts = [r["T"] for r in g["decision_times"]]
                if sorted(gts) != sorted(snap_ts) or g["patient_ref"] != pref:
                    errors.append(f"{case_id}: gold Ts {gts} != snapshot Ts {snap_ts}")
    for gp in sorted((ds / "gold").glob("*/*.json")):
        g = _load(gp)
        seen.setdefault(g["patient_ref"], set()).add(gp.parent.name)
    multi = sorted(p for p, s in seen.items() if len(s) > 1)
    if multi:
        errors.append(f"patients in more than one split: {multi}")
    return {"mode": "dataset", "dataset": str(ds), "status": "PASS" if not errors else "FAIL", "cases": n_cases,
            "case_x_T": n_pairs, "case_x_T_pass": n_pass, "patients_multi_split": multi, "errors": errors}


def audit_legacy(path: Path, as_of: str) -> dict:
    doc = _load(path)
    items = doc.get("items", doc.get("events", []))
    T = _t(as_of)
    eligible, future = [], []
    for it in items:
        iid = it.get("item_id", it.get("event_id"))
        (future if _t(it["available_at_time"]) > T else eligible).append(iid)
    return {"mode": "legacy", "file": str(path), "as_of": as_of, "status": "PASS" if not future else "FAIL",
            "eligible_item_ids": eligible, "future_item_ids": future,
            "errors": [f"item {i} available after {as_of}" for i in future]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", type=Path)
    ap.add_argument("--as-of")
    ap.add_argument("--dataset", type=Path)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)
    if args.dataset:
        report = audit_dataset(args.dataset)
        out = args.report or args.dataset / "audit_report.json"
    elif args.target and args.as_of:
        report = audit_legacy(args.target, args.as_of)
        out = args.report
    else:
        ap.error("use --dataset DIR or <journey.json> --as-of ISO")
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8")
    summary = {k: v for k, v in report.items() if k not in ("errors", "eligible_item_ids")}
    print(json.dumps(summary | {"errors": report["errors"][:20]}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
