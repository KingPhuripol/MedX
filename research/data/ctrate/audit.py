"""Data audit for a CT-RATE build: schema, gold separation, identifiers, manifest hashes, times, overlap,
missing != negative. Read-only; writes nothing."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .types import LABEL_VALUES, AbnormalityLabels, CTVolume, RadiologyReport

TIME_FIELDS = ("event_time", "observed_at", "available_at_time")
FORBIDDEN_INPUT_KEYS = {"labels", "values", "label_source", "report", "findings", "impressions", "Findings_EN",
                        "Impressions_EN", "labels_status", "report_ref"}
IDENTIFIER_PATTERNS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "national_id": r"(?<!\d)\d{13}(?!\d)",
    "phone": r"(?<![\d.])0[2-9]\d{7,8}(?![\d.])|(?<!\d)0\d{1,2}-\d{3}-\d{3,4}(?!\d)|\+\d{2} ?\d{2,3} ?\d{3} ?\d{4}",
    "hn_an": r"\b(?:HN|AN)\s*[:#.]?\s*\d+",
    "thai_honorific": r"นางสาว|นาย|นาง",
}
_COMPILED = {k: re.compile(v) for k, v in IDENTIFIER_PATTERNS.items()}


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


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _step_schema(ds: Path) -> list[str]:
    errs = []
    for p in sorted((ds / "inputs").rglob("*.json")):
        for it in _load(p)["items"]:
            try:
                CTVolume.model_validate(it)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{p.relative_to(ds)}: {it.get('item_id')}: {str(exc).splitlines()[0]}")
    for p in sorted((ds / "label_sources").glob("*/*.json")):
        rep = _load(p)["report"]
        if rep != "missing":
            try:
                RadiologyReport.model_validate(rep)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{p.relative_to(ds)}: {str(exc).splitlines()[0]}")
    for p in sorted((ds / "gold").glob("*/*.json")):
        g = _load(p)
        if g["labels"] is not None:
            try:
                AbnormalityLabels.model_validate(g["labels"])
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{p.relative_to(ds)}: {str(exc).splitlines()[0]}")
    return errs


def _step_gold_separation(ds: Path, label_columns: list[str]) -> list[str]:
    report_texts = set()
    for p in sorted((ds / "label_sources").glob("*/*.json")):
        rep = _load(p)["report"]
        if rep != "missing":
            report_texts |= {s for s in (rep["findings"], rep["impressions"]) if len(s) >= 20}
    banned = FORBIDDEN_INPUT_KEYS | set(label_columns)
    errs = []
    for p in sorted((ds / "inputs").rglob("*")):
        if not p.is_file():
            if "gold" in p.name.lower() or "label" in p.name.lower():
                errs.append(f"gold/label directory under inputs: {p.relative_to(ds)}")
            continue
        text = p.read_text(encoding="utf-8")
        if p.suffix != ".json":
            errs.append(f"non-json file under inputs: {p.relative_to(ds)}")
            continue
        errs += [f"{p.relative_to(ds)}: forbidden key {k!r}" for k in sorted(set(_keys(json.loads(text))) & banned)]
        errs += [f"{p.relative_to(ds)}: report text present" for t in report_texts if t in text][:1]
    return errs


def _step_identifiers(ds: Path) -> list[str]:
    errs = []
    for p in sorted((ds / "inputs").rglob("*.json")):
        text = p.read_text(encoding="utf-8")
        errs += [f"{p.relative_to(ds)}: {cls}" for cls, rx in _COMPILED.items() if rx.search(text)]
    return errs


def _step_manifest(ds: Path, manifest: dict) -> list[str]:
    errs = []
    for rel, sha in manifest["files"].items():
        p = ds / rel
        if not p.is_file():
            errs.append(f"missing file {rel}")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            errs.append(f"sha256 mismatch {rel}")
    listed = set(manifest["files"])
    for p in sorted(ds.rglob("*")):
        rel = p.relative_to(ds).as_posix()
        if p.is_file() and rel not in listed and rel not in ("manifest.json", "audit_report.json"):
            errs.append(f"unlisted file {rel}")
    tree = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in sorted(manifest["files"].items())).encode()).hexdigest()
    if tree != manifest["tree_sha256"]:
        errs.append("tree_sha256 mismatch")
    return errs


def _step_times(ds: Path) -> list[str]:
    errs = []
    for p in sorted((ds / "inputs").glob("*/*/snapshot_T*.json")):
        s = _load(p)
        T = datetime.fromisoformat(s["as_of"])
        for it in s["items"]:
            late = [f for f in TIME_FIELDS if datetime.fromisoformat(it[f]) > T]
            if late:
                errs.append(f"{p.relative_to(ds)}: {it['item_id']} {','.join(late)} > {s['as_of']}")
    return errs


def _step_overlap(ds: Path) -> list[str]:
    splits = _load(ds / "splits.json")
    seen: dict[str, set[str]] = {}
    errs = []
    for sub in ("inputs", "label_sources", "gold"):
        for p in sorted((ds / sub).glob("*/*")):
            split = p.parent.name
            pref = _load(p / "journey.json" if p.is_dir() else p)["patient_ref"]
            seen.setdefault(pref, set()).add(split)
            if splits.get(pref) != split:
                errs.append(f"{sub}/{split}/{p.name}: patient {pref} assigned {splits.get(pref)} in splits.json")
            official = "test" if pref.startswith("valid_") else "trainlike"
            if (official == "test") != (split == "test"):
                errs.append(f"{sub}/{split}/{p.name}: official split of {pref} contradicts {split}")
    errs += [f"patient {p} in several splits {sorted(s)}" for p, s in sorted(seen.items()) if len(s) > 1]
    return errs


def _step_missing(ds: Path, manifest: dict) -> list[str]:
    errs = []
    cols = manifest["label_columns"]
    blank: dict[str, int] = {}
    for p in sorted((ds / "gold").glob("*/*.json")):
        g, split = _load(p), p.parent.name
        if g["labels_status"] == "missing":
            if g["labels"] is not None:
                errs.append(f"{p.name}: status missing but a label item is present")
            continue
        vals = g["labels"]["values"]
        if sorted(vals) != sorted(cols):
            errs.append(f"{p.name}: label columns differ from manifest")
        for c, v in vals.items():
            if v not in LABEL_VALUES:
                errs.append(f"{p.name}: column {c!r} has value {v!r} (not 1/0/missing)")
        blank[split] = blank.get(split, 0) + sum(v == "missing" for v in vals.values())
    for split, n in manifest["counts"]["blank_label_cells"].items():
        if (ds / "gold" / split).is_dir() and blank.get(split, 0) != n:
            errs.append(f"{split}: {n} blank label cells in the source but {blank.get(split, 0)} 'missing' in gold")
    return errs


def run_audit(ds: Path | str) -> dict:
    ds = Path(ds)
    manifest = _load(ds / "manifest.json")
    steps = {
        "schema": _step_schema(ds),
        "gold_separation": _step_gold_separation(ds, manifest["label_columns"]),
        "identifier_scan": _step_identifiers(ds),
        "manifest_hashes": _step_manifest(ds, manifest),
        "snapshot_items_after_T": _step_times(ds),
        "patient_overlap": _step_overlap(ds),
        "missing_not_negative": _step_missing(ds, manifest),
    }
    return {"status": "PASS" if not any(steps.values()) else "FAIL",
            "steps": {k: ("PASS" if not v else f"FAIL ({len(v)})") for k, v in steps.items()},
            "errors": [e for v in steps.values() for e in v]}
