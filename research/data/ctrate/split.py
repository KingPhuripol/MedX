"""Patient-level split. Assignment takes patient keys only, before any scan/reconstruction expansion."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable

from .loader import LoadResult

DEFAULT_SEED = 20260926
DEV_FRACTION = 0.10
_KEY = re.compile(r"(train|valid)_([1-9][0-9]*)", re.ASCII)
METHOD = ("official valid -> test (sealed); official train -> train/dev; dev = the round(dev_fraction*N) train "
          "patients with the lowest sha256(f'{seed}:{patient_key}') (ties by key)")


class SealedTestError(PermissionError):
    """Test-split gold was requested without purpose='final_eval'."""


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def assign_patients(patient_keys: Iterable[str], seed: int = DEFAULT_SEED,
                    dev_fraction: float = DEV_FRACTION) -> dict[str, str]:
    """patient_key -> 'train' | 'dev' | 'test'. `train_7` and `valid_7` are different patients."""
    keys = sorted(set(patient_keys))
    for k in keys:
        if not _KEY.fullmatch(k):
            raise ValueError(f"not a patient key: {k!r}")
    train = [k for k in keys if k.startswith("train_")]
    ranked = sorted(train, key=lambda k: (sha256_hex(f"{seed}:{k}"), k))
    dev = set(ranked[: round(dev_fraction * len(train))])
    return {k: ("test" if k.startswith("valid_") else "dev" if k in dev else "train") for k in keys}


def split_manifest(result: LoadResult, assignment: dict[str, str], seed: int = DEFAULT_SEED,
                   dev_fraction: float = DEV_FRACTION) -> dict:
    per: dict[str, dict] = {s: {"patients": set(), "scans": set(), "volumes": 0} for s in ("train", "dev", "test")}
    for v in result.volumes:
        p = per[assignment[v.patient_ref]]
        p["patients"].add(v.patient_ref)
        p["scans"].add(v.scan_ref)
        p["volumes"] += 1
    reasons: dict[str, int] = defaultdict(int)
    names = []
    for e in result.exclusions:
        if e["table"] == "metadata":
            reasons[e["reason"]] += 1
            names.append(e["volume_name"])
    body = {
        "policy": {"unit": "patient", "seed": seed, "dev_fraction": dev_fraction, "method": METHOD,
                   "patient_key": "<official_split>_<int pid>"},
        "revision": result.revision,
        "splits": {s: {"patients": len(d["patients"]), "scans": len(d["scans"]), "volumes": d["volumes"],
                       "patient_keys_sha256": sha256_hex("\n".join(sorted(d["patients"])))}
                   for s, d in per.items()},
        "exclusions": {"by_reason": dict(sorted(reasons.items())),
                       "volume_names_sha256": sha256_hex("\n".join(sorted(names)))},
    }
    return body | {"manifest_sha256": sha256_hex(canonical_json(body))}


def gold_labels(result: LoadResult, assignment: dict[str, str], split: str, purpose: str | None = None):
    """Label items of one split. Test gold is sealed: only purpose='final_eval' unseals it."""
    if split == "test" and purpose != "final_eval":
        raise SealedTestError("test labels are sealed; pass purpose='final_eval' (final evaluation only)")
    return [lab for lab in result.labels if assignment[lab.patient_ref] == split]


def sealed_report_sources(result: LoadResult, assignment: dict[str, str], split: str, purpose: str | None = None):
    """Reports are the label source of their cases, so test reports are sealed with test labels."""
    if split == "test" and purpose != "final_eval":
        raise SealedTestError("test report/label sources are sealed; pass purpose='final_eval'")
    return [r for r in result.reports if assignment[r.patient_ref] == split]
