"""Typed CT-RATE evidence (subclasses of casegraph.types.EvidenceItem) and the time convention.

Convention ``ctrate_synthetic_anchor_v1``: CT-RATE has no clinical timestamps, so a sentinel anchor
A = 2000-01-01T00:00:00+00:00 is used (``time_basis="synthetic_anchor"``, never a real clinical time).
volume: event=observed=available=A; report: event A, available A+1d; labels: event A, available A+2d.
The reader decision time is T_read = A, so only volumes are model input.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import AwareDatetime

from casegraph.types import EvidenceItem

PINNED_REVISION = "deeca4d89e9f978d4d1bccd88a55071ddbb146bb"
HF_REPO = "ibrahimhamamci/CT-RATE"
TIME_CONVENTION = "ctrate_synthetic_anchor_v1"
ANCHOR = datetime(2000, 1, 1, tzinfo=timezone.utc)
OFFSETS = {"volume": timedelta(0), "report": timedelta(days=1), "labels": timedelta(days=2)}
T_READ = ANCHOR
LOADER_VERSION = "ctrate-loader/1"
SOURCE = "ct-rate"
LABEL_VALUES = ("1", "0", "missing")


def version_string(revision: str = PINNED_REVISION) -> str:
    return f"ct-rate@{revision};{LOADER_VERSION}"


def provenance(path: str, row: int, revision: str = PINNED_REVISION) -> str:
    return f"hf://datasets/{HF_REPO}@{revision}/{path}#row={row}"


class CTRateItem(EvidenceItem):
    item_id: str
    encounter_ref: str
    observed_at: AwareDatetime
    time_basis: Literal["synthetic_anchor"] = "synthetic_anchor"

    def to_json(self) -> dict:
        d = self.model_dump(mode="json")
        for k in ("event_time", "observed_at", "available_at_time"):
            d[k] = getattr(self, k).isoformat()
        return d


class CTVolume(CTRateItem):
    data_type: Literal["ct_volume"] = "ct_volume"
    role: Literal["input"] = "input"
    split: Literal["train", "valid"]  # official provider split
    volume_ref: str
    scan_ref: str
    reconstruction: int
    metadata: dict[str, str]


class RadiologyReport(CTRateItem):
    data_type: Literal["radiology_report"] = "radiology_report"
    role: Literal["label_source"] = "label_source"
    scan_ref: str
    report_ref: str
    volume_names: tuple[str, ...]
    findings: str
    impressions: str
    extra: dict[str, str]


class AbnormalityLabels(CTRateItem):
    data_type: Literal["abnormality_labels"] = "abnormality_labels"
    role: Literal["label"] = "label"
    scan_ref: str
    label_source: str
    volume_names: tuple[str, ...]
    values: dict[str, Literal["1", "0", "missing"]]


def report_ref_for(scan_ref: str) -> str:
    """Reference that research.train.data.canonical_source_id maps to the scan (all reconstructions)."""
    return f"ct-rate:{scan_ref}"


def volume_ref_for(volume_name: str) -> str:
    return f"ct-rate:{volume_name}"
