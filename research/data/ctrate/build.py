"""Build a versioned, immutable output tree in the layout scripts/temporal_leakage_audit.py --dataset reads."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from .loader import LoadResult, load_tree
from .split import DEFAULT_SEED, DEV_FRACTION, assign_patients, gold_labels, sealed_report_sources, split_manifest
from .types import ANCHOR, PINNED_REVISION, T_READ, TIME_CONVENTION

TASKS = ("abnormality_labels", "report_generation", "image_text_alignment")


def dumps(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def guard_sample(volume_ref: str, report_ref: str, label_source: str, *, task: str = "abnormality_labels") -> dict:
    """Sample dict in the shape research.train.data.decide_modalities expects. For every CT-RATE task the
    label source is the scan's own report, so that report may never replace the image as input (proposal 3.4)."""
    if task not in TASKS:
        raise ValueError(f"unknown CT-RATE task {task!r}")
    return {"sample_id": f"{task}:{volume_ref}", "task": task, "required_modalities": [],
            "images": {"ct": {"ref": volume_ref, "report_ref": report_ref, "report_ids": [1]}},
            "label_source": label_source}


def build(raw: Path | str, out: Path | str, *, seed: int = DEFAULT_SEED, dev_fraction: float = DEV_FRACTION,
          unseal_test: bool = False, revision: str = PINNED_REVISION) -> dict:
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} is not empty; builds are versioned, never overwritten in place")
    res: LoadResult = load_tree(raw, revision)
    assignment = assign_patients((v.patient_ref for v in res.volumes), seed, dev_fraction)
    sm = split_manifest(res, assignment, seed, dev_fraction)
    files: dict[str, str] = {}

    def put(rel: str, obj) -> None:
        data = dumps(obj)
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        files[rel] = hashlib.sha256(data).hexdigest()

    put("splits.json", assignment)
    put("split_manifest.json", sm)
    cases: dict[str, list] = defaultdict(list)
    for v in sorted(res.volumes, key=lambda x: x.volume_ref):
        cases[v.scan_ref].append(v)
    reports = {r.scan_ref: r for r in res.reports}
    labels = {x.scan_ref: x for x in res.labels}
    t0 = T_READ.isoformat()
    n_cases: dict[str, int] = defaultdict(int)
    n_missing = {"report": defaultdict(int), "labels": defaultdict(int)}
    blank: dict[str, int] = defaultdict(int)
    for split in ("train", "dev", "test"):
        sealed = split == "test" and not unseal_test
        if sealed:
            continue  # inputs, label sources and gold of the test split are all withheld until unsealed
        purpose = "final_eval" if split == "test" else None
        ok_reports = {r.scan_ref for r in sealed_report_sources(res, assignment, split, purpose)}
        ok_labels = {x.scan_ref: x for x in gold_labels(res, assignment, split, purpose)}
        for scan_ref in sorted(s for s, vs in cases.items() if assignment[vs[0].patient_ref] == split):
            vs = cases[scan_ref]
            pref = vs[0].patient_ref
            items = [v.to_json() for v in vs]
            put(f"inputs/{split}/{scan_ref}/journey.json",
                {"case_id": scan_ref, "split": split, "patient_ref": pref, "decision_times": [t0], "items": items,
                 "time_convention": TIME_CONVENTION})
            put(f"inputs/{split}/{scan_ref}/snapshot_T0.json",
                {"patient_ref": pref, "as_of": t0, "items": [i for i in items]})
            rep = reports[scan_ref].to_json() if scan_ref in ok_reports else "missing"
            put(f"label_sources/{split}/{scan_ref}.json", {"case_id": scan_ref, "patient_ref": pref, "report": rep})
            lab = ok_labels.get(scan_ref)
            put(f"gold/{split}/{scan_ref}.json",
                {"case_id": scan_ref, "patient_ref": pref, "decision_times": [{"T": t0}],
                 "labels_status": "present" if lab else "missing", "labels": lab.to_json() if lab else None})
            n_cases[split] += 1
            n_missing["report"][split] += rep == "missing"
            n_missing["labels"][split] += lab is None
            blank[split] += sum(x == "missing" for x in lab.values.values()) if lab else 0
    manifest = {
        "schema": "ctrate-build/1", "build_id": out.name, "revision": revision, "seed": seed,
        "dev_fraction": dev_fraction, "time_convention": TIME_CONVENTION, "anchor": ANCHOR.isoformat(),
        "label_columns": res.label_columns, "unsealed_test": bool(unseal_test),
        "split_manifest_sha256": sm["manifest_sha256"], "tasks": list(TASKS),
        "counts": {"cases": dict(n_cases), "missing_report_cases": dict(n_missing["report"]),
                   "missing_label_cases": dict(n_missing["labels"]), "blank_label_cells": dict(blank),
                   "exclusions_by_reason": sm["exclusions"]["by_reason"]},
        "files": dict(sorted(files.items())),
    }
    manifest["tree_sha256"] = hashlib.sha256(
        "".join(f"{k}:{v}\n" for k, v in sorted(files.items())).encode()).hexdigest()
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_bytes(dumps(manifest))
    return manifest
