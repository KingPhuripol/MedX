"""Header-driven, fail-loud parser for the CT-RATE CSV/TXT files. Never drops a row silently."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .types import (ANCHOR, LABEL_ORIGIN, OFFSETS, PINNED_REVISION, SOURCE, AbnormalityLabels, CTVolume, RadiologyReport,
                    provenance, report_ref_for, version_string, volume_ref_for)

# ASCII only, no normalization: zero-padded or non-ASCII digits are rejected, never folded.
VOLUME_NAME = re.compile(r"(train|valid)_([1-9][0-9]*)_([a-z]+)_([1-9][0-9]*)\.nii\.gz", re.ASCII)
SPLITS = {
    "train": {"metadata": "dataset/metadata/train_metadata.csv",
              "reports": "dataset/radiology_text_reports/train_reports.csv",
              "labels": "dataset/multi_abnormality_labels/train_predicted_labels.csv",
              "no_chest": "dataset/metadata/no_chest_train.txt"},
    "valid": {"metadata": "dataset/metadata/validation_metadata.csv",
              "reports": "dataset/radiology_text_reports/validation_reports.csv",
              "labels": "dataset/multi_abnormality_labels/valid_predicted_labels.csv",
              "no_chest": "dataset/metadata/no_chest_valid.txt"},
}
NO_CHEST_REASON = "provider_no_chest"


@dataclass(frozen=True)
class RowError:
    file: str
    row: int
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.file}:row={self.row}: {self.code}: {self.detail}"


class CTRateLoadError(ValueError):
    """Malformed CT-RATE input. ``errors`` lists every offending row."""

    def __init__(self, errors: list[RowError]):
        self.errors = list(errors)
        super().__init__(f"CT-RATE load failed with {len(errors)} error(s):\n" + "\n".join(map(str, errors)))


@dataclass
class LoadResult:
    revision: str
    volumes: list[CTVolume]
    reports: list[RadiologyReport]
    labels: list[AbnormalityLabels]
    exclusions: list[dict]
    label_columns: list[str]
    row_counts: dict[str, int]
    missing_report_scans: list[str] = field(default_factory=list)
    missing_label_scans: list[str] = field(default_factory=list)
    blank_label_cells: dict[str, int] = field(default_factory=dict)  # by official split


def _t(offset_key: str) -> datetime:
    return ANCHOR + OFFSETS[offset_key]


def _read_table(root: Path, rel: str, split: str, required: tuple[str, ...], errors: list[RowError]):
    """-> (header, [(row_no, name, groups, row)]). Row numbers are 1-based data rows."""
    path = root / rel
    if not path.is_file():
        errors.append(RowError(rel, 0, "missing_file", "required file not found"))
        return [], []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        bad = False
        for need in required:
            if need not in header:
                errors.append(RowError(rel, 0, "missing_column", need))
                bad = True
        if len(set(header)) != len(header):
            errors.append(RowError(rel, 0, "duplicate_column", "header has repeated names"))
            bad = True
        if bad:
            return header, []
        out, seen = [], set()
        for n, row in enumerate(reader, start=1):
            if None in row or any(v is None for v in row.values()):
                errors.append(RowError(rel, n, "ragged_row", "wrong number of fields"))
                continue
            name = row["VolumeName"]
            m = VOLUME_NAME.fullmatch(name)
            if not m:
                errors.append(RowError(rel, n, "bad_volume_name", repr(name)))
            elif m.group(1) != split:
                errors.append(RowError(rel, n, "split_mismatch", f"{name!r} in a {split} file"))
            elif name in seen:
                errors.append(RowError(rel, n, "duplicate_volume_name", name))
            else:
                seen.add(name)
                out.append((n, name, m.groups(), row))
    return header, out


def _read_no_chest(root: Path, rel: str, split: str, errors: list[RowError]) -> list[tuple[int, str]]:
    path = root / rel
    if not path.is_file():  # listed in manifest expected_files: required. An empty file means zero exclusions.
        errors.append(RowError(rel, 0, "missing_file", "required file not found"))
        return []
    out, seen = [], set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        m = VOLUME_NAME.fullmatch(line)
        if not m:
            errors.append(RowError(rel, n, "bad_volume_name", repr(line)))
        elif m.group(1) != split:
            errors.append(RowError(rel, n, "split_mismatch", f"{line!r} in a {split} file"))
        elif line in seen:
            errors.append(RowError(rel, n, "duplicate_volume_name", line))
        else:
            seen.add(line)
            out.append((n, line))
    return out


def load_tree(root: Path | str, revision: str = PINNED_REVISION) -> LoadResult:
    root = Path(root)
    errors: list[RowError] = []
    version = version_string(revision)
    volumes: list[CTVolume] = []
    exclusions: list[dict] = []
    reports_by_scan: dict[str, list] = defaultdict(list)  # scan -> [(rel,row_no,name,(findings,impr,extra))]
    labels_by_scan: dict[str, list] = defaultdict(list)  # scan -> [(rel,row_no,name,values)]
    label_header: list[str] | None = None
    row_counts = {"metadata": 0, "reports": 0, "labels": 0, "no_chest": 0}
    blank_cells = {s: 0 for s in SPLITS}
    meta_rows: dict[str, tuple] = {}  # all metadata names (incl. excluded)

    for split, rels in SPLITS.items():
        _, meta = _read_table(root, rels["metadata"], split, ("VolumeName",), errors)
        row_counts["metadata"] += len(meta)
        names = {n for _, n, _, _ in meta}
        no_chest = _read_no_chest(root, rels["no_chest"], split, errors)
        row_counts["no_chest"] += len(no_chest)
        for n, name in no_chest:
            if name not in names:
                errors.append(RowError(rels["no_chest"], n, "orphan_row", f"{name} has no metadata row"))
        excluded = {name for _, name in no_chest}

        for n, name, (_, pid, scan, rec), row in meta:
            meta_rows[name] = (split, pid, scan, rec)
            if name in excluded:
                exclusions.append({"volume_name": name, "reason": NO_CHEST_REASON, "table": "metadata"})
                continue
            scan_ref = f"{split}_{pid}_{scan}"
            volumes.append(CTVolume(
                item_id=f"ctv:{name}", encounter_ref=scan_ref, observed_at=_t("volume"),
                data_type="ct_volume", patient_ref=f"{split}_{pid}", event_time=_t("volume"),
                available_at_time=_t("volume"), source=SOURCE, provenance=provenance(rels["metadata"], n, revision),
                version=version, split=split, volume_ref=volume_ref_for(name), scan_ref=scan_ref,
                reconstruction=int(rec), metadata={k: v for k, v in row.items() if k != "VolumeName"}))

        _, reps = _read_table(root, rels["reports"], split, ("VolumeName", "Findings_EN", "Impressions_EN"), errors)
        row_counts["reports"] += len(reps)
        for n, name, (_, pid, scan, _r), row in reps:
            if name not in names:
                errors.append(RowError(rels["reports"], n, "orphan_row", f"{name} has no metadata row"))
            elif name in excluded:
                exclusions.append({"volume_name": name, "reason": NO_CHEST_REASON, "table": "reports"})
            else:
                extra = {k: v for k, v in row.items() if k not in ("VolumeName", "Findings_EN", "Impressions_EN")}
                reports_by_scan[f"{split}_{pid}_{scan}"].append(
                    (rels["reports"], n, name, (row["Findings_EN"], row["Impressions_EN"], tuple(sorted(extra.items())))))

        header, labs = _read_table(root, rels["labels"], split, ("VolumeName",), errors)
        cols = [h for h in header if h != "VolumeName"]
        if label_header is None:
            label_header = cols
        elif cols != label_header:
            errors.append(RowError(rels["labels"], 0, "label_header_mismatch", "label columns differ between splits"))
        row_counts["labels"] += len(labs)
        for n, name, (_, pid, scan, _r), row in labs:
            if name not in names:
                errors.append(RowError(rels["labels"], n, "orphan_row", f"{name} has no metadata row"))
                continue
            if name in excluded:
                exclusions.append({"volume_name": name, "reason": NO_CHEST_REASON, "table": "labels"})
                continue
            vals, ok = {}, True
            for c in cols:
                v = row[c]
                if v == "":
                    vals[c] = "missing"
                elif v in ("0", "1"):
                    vals[c] = v
                else:
                    errors.append(RowError(rels["labels"], n, "bad_label_value", f"column {c!r} value {v!r}"))
                    ok = False
            if ok:
                labels_by_scan[f"{split}_{pid}_{scan}"].append((rels["labels"], n, name, tuple(vals.items())))

    # Group by scan; reconstructions of one scan must agree and be all-present or all-absent.
    recs_by_scan: dict[str, list[CTVolume]] = defaultdict(list)
    for v in volumes:
        recs_by_scan[v.scan_ref].append(v)
    reports, labels = [], []
    missing_reports, missing_labels = [], []
    for scan_ref, vols in recs_by_scan.items():
        vnames = sorted(v.volume_ref.split(":", 1)[1] for v in vols)
        first = vols[0]
        for kind, table in (("report", reports_by_scan), ("labels", labels_by_scan)):
            rows = table.get(scan_ref, [])
            if not rows:
                (missing_reports if kind == "report" else missing_labels).append(scan_ref)
                continue
            payloads = {r[3] for r in rows}
            have = sorted(r[2] for r in rows)
            if len(payloads) > 1:
                errors += [RowError(r[0], r[1], "reconstruction_conflict",
                                    f"{kind} differs across reconstructions of {scan_ref}") for r in rows]
                continue
            if have != vnames:
                errors += [RowError(r[0], r[1], "reconstruction_conflict",
                                    f"{kind} present for only some reconstructions of {scan_ref}") for r in rows]
                continue
            r0 = rows[0]
            common = dict(item_id=f"{'rpt' if kind == 'report' else 'lab'}:{scan_ref}", encounter_ref=scan_ref,
                          patient_ref=first.patient_ref, source=SOURCE, version=version, event_time=_t("volume"),
                          scan_ref=scan_ref, volume_names=tuple(vnames),
                          provenance=provenance(r0[0], r0[1], revision))
            if kind == "report":
                f, i, extra = r0[3]
                reports.append(RadiologyReport(
                    **common, observed_at=_t("report"), available_at_time=_t("report"),
                    report_ref=report_ref_for(scan_ref), findings=f, impressions=i, extra=dict(extra)))
            else:
                vals = dict(r0[3])
                labels.append(AbnormalityLabels(
                    **common, observed_at=_t("labels"), available_at_time=_t("labels"),
                    label_source=report_ref_for(scan_ref), values=vals,
                    label_origin=LABEL_ORIGIN))
                blank_cells[first.split] += sum(v == "missing" for v in vals.values())

    if errors:
        raise CTRateLoadError(errors)
    return LoadResult(revision=revision, volumes=volumes, reports=reports, labels=labels, exclusions=exclusions,
                      label_columns=label_header or [], row_counts=row_counts,
                      missing_report_scans=sorted(missing_reports), missing_label_scans=sorted(missing_labels),
                      blank_label_cells=blank_cells)
