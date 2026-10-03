"""Tiny SYNTHETIC tree mimicking the CT-RATE layout. Nothing here is copied from CT-RATE; placeholder bytes only."""

from __future__ import annotations

import csv
from pathlib import Path

LABELS = ["Cardiomegaly", "Pleural effusion", "Lung nodule"]
TRAIN_PIDS = list(range(1, 11))
VALID_PIDS = [3, 7, 9, 21]  # 3, 7, 9 share a pid with a train patient
# scans per patient: default one scan "a" with one reconstruction
SCANS = {("train", 2): {"a": 1, "b": 1}, ("train", 3): {"a": 3}, ("train", 10): {"a": 1, "b": 1},
         ("valid", 21): {"a": 1, "b": 1}}
NO_REPORT_SCAN = "train_5_a"
NO_LABELS_SCAN = "train_6_a"
BLANK_LABEL = ("train_4_a", "Lung nodule")
NO_CHEST = ["train_10_b_1.nii.gz"]
HEADERS = {"metadata": ["VolumeName", "RescaleSlope", "RescaleIntercept", "XYSpacing", "ZSpacing"]}


def scans_of(split: str, pid: int) -> dict[str, int]:
    return SCANS.get((split, pid), {"a": 1})


def volume_names() -> list[str]:
    return [f"{s}_{p}_{sc}_{r}.nii.gz" for s, pids in (("train", TRAIN_PIDS), ("valid", VALID_PIDS)) for p in pids
            for sc, n in scans_of(s, p).items() for r in range(1, n + 1)]


def _write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


def write_rows(path: Path, header: list[str], rows: list[list[str]]) -> None:
    _write(path, header, rows)


def make_fixture(root: Path) -> Path:
    for split, pids, ms, rp, lb in (("train", TRAIN_PIDS, "train_metadata.csv", "train_reports.csv",
                                     "train_predicted_labels.csv"),
                                    ("valid", VALID_PIDS, "validation_metadata.csv", "validation_reports.csv",
                                     "valid_predicted_labels.csv")):
        meta, reps, labs = [], [], []
        for p in pids:
            for sc, n in scans_of(split, p).items():
                scan = f"{split}_{p}_{sc}"
                for r in range(1, n + 1):
                    name = f"{scan}_{r}.nii.gz"
                    vol = root / "dataset" / split / f"{split}_{p}" / scan / name
                    vol.parent.mkdir(parents=True, exist_ok=True)
                    vol.write_bytes(b"SYNTHETIC-PLACEHOLDER-NOT-NIFTI")
                    meta.append([name, "1.0", "-1024.0", "[0.8, 0.8]", "1.5"])
                    if scan != NO_REPORT_SCAN:
                        reps.append([name, f"SYNTHETIC REPORT findings for {scan}: synthetic text only.",
                                     f"SYNTHETIC REPORT impression for {scan}: synthetic text only."])
                    if scan != NO_LABELS_SCAN:
                        vals = [str((p + len(sc) + i) % 2) for i in range(len(LABELS))]
                        if scan == BLANK_LABEL[0]:
                            vals[LABELS.index(BLANK_LABEL[1])] = ""
                        labs.append([name, *vals])
        _write(root / "dataset/metadata" / ms, HEADERS["metadata"], meta)
        _write(root / "dataset/radiology_text_reports" / rp, ["VolumeName", "Findings_EN", "Impressions_EN"], reps)
        _write(root / "dataset/multi_abnormality_labels" / lb, ["VolumeName", *LABELS], labs)
    nc = root / "dataset/metadata"
    (nc / "no_chest_train.txt").write_text("".join(n + "\n" for n in NO_CHEST), encoding="utf-8")
    (nc / "no_chest_valid.txt").write_text("", encoding="utf-8")
    return root
