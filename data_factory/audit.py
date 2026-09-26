"""Dataset audits for ``make audit``: schema, gold separation, identifier scan, manifest hashes, snapshot times."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .generate import TEMPLATES, dumps, tree_sha256, validate_item

GOLD_KEYS = ("target_department", "red_flags", "rule_id", "required_fields", "medication_issues",
             "expected_action", "injection_id", "issue_type", "department_evaluable", "department_reason",
             "NOT_EVALUABLE")
TIME_FIELDS = ("event_time", "observed_at", "available_at_time")
IDENTIFIER_PATTERNS = {
    "thai_national_id": r"(?<!\d)\d{13}(?!\d)|(?<!\d)\d-\d{4}-\d{5}-\d{2}-\d(?!\d)",
    "phone": r"(?<![\d.])0[2-9]\d{7,8}(?![\d.])|(?<!\d)0\d{1,2}-\d{3}-\d{3,4}(?!\d)|\+66",
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "honorific_name": r"นางสาว|นาย|นาง|น\.ส\.|ด\.ช\.|ด\.ญ\.",
    "address": r"บ้านเลขที่|หมู่ที่|ซอย|ถนน|ตำบล|อำเภอ|จังหวัด|แขวง|เขต",
    "postcode": r"(?<![\d./-])[1-9]\d{4}(?![\d./-])",
    "hn_an": r"\b(?:HN|AN)\s*[:#.]?\s*\d+",
}
PLANTED_POSITIVES = {
    "thai_national_id": ["1234567890123", "1-2345-67890-12-3"],
    "phone": ["0812345678", "02-123-4567", "+66 81 234 5678"],
    "email": ["someone@example.org"],
    "honorific_name": ["นายสมมุติ", "นางสาวสมมุติ", "น.ส.สมมุติ", "ด.ช.สมมุติ"],
    "address": ["บ้านเลขที่ 1", "ซอยสมมุติ", "จังหวัดสมมุติ"],
    "postcode": ["รหัส 10330"],
    "hn_an": ["HN 123456", "AN:7890"],
}
_COMPILED = {k: re.compile(v) for k, v in IDENTIFIER_PATTERNS.items()}


def scan_text(text: str) -> list[tuple[str, str]]:
    return [(k, m.group(0)) for k, rx in _COMPILED.items() for m in rx.finditer(text)]


def identifier_self_test() -> dict[str, bool]:
    return {k: all(any(c == k for c, _ in scan_text(s)) for s in samples) for k, samples in PLANTED_POSITIVES.items()}


def identifier_scan(roots: list[Path]) -> list[str]:
    hits = []
    for root in roots:
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix in {".json", ".jsonl", ".md"} and p.name != "manifest.json":
                for cls, s in scan_text(p.read_text(encoding="utf-8")):
                    hits.append(f"{p}: {cls} {s!r}")
    return hits


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def schema_check(ds: Path) -> tuple[list[str], int]:
    errors, n = [], 0
    for p in sorted((ds / "inputs").rglob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for it in doc["items"]:
            n += 1
            try:
                validate_item(it)
                if any(not (it.get(f) or "").endswith("+07:00") for f in TIME_FIELDS):
                    raise ValueError("times must be tz-aware ISO-8601 +07:00")
            except Exception as exc:  # noqa: BLE001 - report every failure
                errors.append(f"{p}: {it.get('item_id')}: {exc}")
    return errors, n


def gold_separation(ds: Path) -> list[str]:
    names = [c["display_th"] for c in json.loads((TEMPLATES / "departments.json").read_text("utf-8"))["codes"]]
    errors = []
    for p in sorted((ds / "inputs").rglob("*")):
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        for tok in (*GOLD_KEYS, *names, "gold/"):
            if tok in text:
                errors.append(f"{p}: contains {tok!r}")
        if p.suffix == ".json":
            errors += [f"{p}: gold key {k!r}" for k in _keys(json.loads(text)) if k in GOLD_KEYS]
    return errors


def manifest_check(ds: Path) -> list[str]:
    manifest = json.loads((ds / "manifest.json").read_text(encoding="utf-8"))
    errors = []
    for rel, sha in manifest["files"].items():
        p = ds / rel
        if not p.is_file():
            errors.append(f"missing file {rel}")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            errors.append(f"sha256 mismatch {rel}")
    listed = set(manifest["files"])
    for p in sorted(ds.rglob("*")):
        rel = p.relative_to(ds).as_posix()
        if p.is_file() and rel not in listed and rel != "manifest.json" and not rel.endswith("audit_report.json"):
            errors.append(f"unlisted file {rel}")
    tree = tree_sha256(manifest["files"], manifest.get("model_inputs_glob"), manifest.get("audit_only_globs"))
    if tree != manifest["tree_sha256"]:
        errors.append("tree_sha256 mismatch")
    return errors


def snapshot_items_after_T(ds: Path) -> list[str]:
    """Every item in every model-input snapshot must have event/observed/available time <= the snapshot's T."""
    errors = []
    for p in sorted((ds / "inputs").glob("*/*/snapshot_T*.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        T = datetime.fromisoformat(s["as_of"])
        for it in s["items"]:
            late = [f for f in TIME_FIELDS if datetime.fromisoformat(it[f]) > T]
            if late:
                errors.append(f"{p}: {it['item_id']} {','.join(late)} > {s['as_of']}")
    return errors


def run_audit(ds: Path, write_report: bool = True) -> dict:
    ds = Path(ds)
    schema_errors, n_items = schema_check(ds)
    self_test = identifier_self_test()
    steps = {
        "schema": schema_errors,
        "gold_separation": gold_separation(ds),
        "identifier_scan": identifier_scan([ds / "inputs", ds / "gold", TEMPLATES]),
        "identifier_self_test": [k for k, ok in self_test.items() if not ok],
        "manifest": manifest_check(ds),
        "snapshot_items_after_T": snapshot_items_after_T(ds),
    }
    report = {"status": "PASS" if not any(steps.values()) else "FAIL", "items_validated": n_items,
              "steps": {k: ("PASS" if not v else f"FAIL ({len(v)})") for k, v in steps.items()},
              "errors": [e for v in steps.values() for e in v]}
    if write_report:
        (ds / "factory_audit_report.json").write_bytes(dumps(report))
    return report
