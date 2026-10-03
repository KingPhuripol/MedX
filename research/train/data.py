"""Synthetic dataset and the collator that enforces modality dropout / report-substitution provenance.

Proposal 3.3: stage 3 randomly drops modalities and creates samples in which an image is replaced by
the text report of the same image, *only* for tasks whose label does not come from that report.
Proposal 3.4: a report is never an input when it is the label source. The rule is enforced here, in
the collator (`decide_modalities` + `ReportLeakageError`), not by convention.

Slice s9r: references are compared by canonical (dataset, study) identity, not by string, so
`MIMIC-CXR/s50414267` and `mimic-cxr:files/p10/p10000032/s50414267.txt` are the same report. If either
reference cannot be canonicalized, substitution fails closed (treated as forbidden) and is counted.
"""

from __future__ import annotations

import random
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import torch

DATA_CLASS = "synthetic"
IMAGE, REPORT, DROPPED = "image", "report", "dropped"


class ReportLeakageError(RuntimeError):
    """A report that is the sample's label source was about to be used as model input."""


class SourceIdError(ValueError):
    """A report or label-source reference cannot be parsed or names an unknown dataset."""


STRUCTURED = "structured"
REPORT_DATASETS = {"mimic-cxr", "ct-rate", "synthetic"}
# Keys are lower-case with '-', '_', '.' and spaces removed. MIMIC-CXR-JPG reuses the MIMIC-CXR reports.
DATASET_ALIASES = {
    "mimiccxr": "mimic-cxr", "mimiccxrjpg": "mimic-cxr",
    "ctrate": "ct-rate",
    "synthetic": "synthetic",
    "structured": STRUCTURED,
}
# ASCII digits only ([0-9], never `\d`): `\d` also matches Thai, Arabic-Indic, Devanagari ... digits,
# which NFKC does not fold, so the same study written in two scripts would get two ids (s9r F2).
# canonical_source_id folds every Unicode decimal digit to ASCII first; anything left fails closed.
_CT_RATE_STUDY = re.compile(r"(train|valid)_([0-9]+)_([a-z]+)(?:_[0-9]+)?", re.ASCII)  # split_patient_scan[_recon]
_NUMERIC_STUDY = re.compile(r"s?([0-9]+)", re.ASCII)


def _fold_digits(text: str) -> str:
    """Every Unicode decimal digit (category Nd, e.g. Thai '๕', Arabic-Indic '٥', Devanagari '५') -> ASCII."""
    return "".join(str(unicodedata.decimal(c)) if not c.isascii() and c.isdecimal() else c for c in text)


def _number(digits: str) -> str:
    """Leading zeros do not make a different study: '050414267' == '50414267'."""
    return str(int(digits))


def _study_id(dataset: str, stem: str) -> str | None:
    """Dataset-specific study identity; None if the stem is not a valid id for that dataset."""
    if dataset == "mimic-cxr":
        m = _NUMERIC_STUDY.fullmatch(stem)
        return _number(m.group(1)) if m else None
    if dataset == "ct-rate":  # every reconstruction of a scan shares the scan's report
        m = _CT_RATE_STUDY.fullmatch(stem)
        return f"{m.group(1)}_{_number(m.group(2))}_{m.group(3)}" if m else None
    if dataset == "synthetic":
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", stem, re.ASCII):
            return None
        m = _NUMERIC_STUDY.fullmatch(stem)
        return _number(m.group(1)) if m else stem
    return stem or None  # structured


_SUFFIXES = (".nii.gz", ".nii", ".txt")


def _dataset_alias(name: str) -> str | None:
    return DATASET_ALIASES.get(re.sub(r"[-_.\s]", "", name))


def canonical_source_id(ref: Any) -> tuple[str, str]:
    """(dataset, study_id) of a report / label-source reference. Raises SourceIdError if unparseable.

    Order: NFKC + casefold, Unicode decimal digits -> ASCII, trim, drop `file://`, `\\` -> `/`, collapse `//`, dataset from a `name:`
    prefix or a path directory (alias table), directories and `.txt` stripped, study-id normalized
    (`s50414267` == `50414267` == `s050414267`; ids match ASCII [0-9] only, so no `\\d` Unicode gap).
    Two different datasets named in one reference is unparseable.
    """
    if not isinstance(ref, str):
        raise SourceIdError(f"reference {ref!r} is not a string")
    text = _fold_digits(unicodedata.normalize("NFKC", ref).casefold()).strip()
    if text.startswith("file://"):
        text = text[len("file://"):]
    text = re.sub(r"/{2,}", "/", text.replace("\\", "/"))
    datasets: set[str] = set()
    if (m := re.match(r"^([^/:]{2,}):(.*)$", text)) is not None:  # `dataset:rest` (a 1-letter prefix is a drive)
        prefix, text = m.group(1), m.group(2)
        if (alias := _dataset_alias(prefix)) is None:
            raise SourceIdError(f"unknown dataset {prefix!r} in {ref!r}")
        datasets.add(alias)
        if alias == STRUCTURED:
            return STRUCTURED, _require(_study_id(STRUCTURED, text.strip("/").strip()), ref)
    parts = [p for p in text.split("/") if p]
    if not parts:
        raise SourceIdError(f"no study id in {ref!r}")
    datasets |= {a for p in parts[:-1] if (a := _dataset_alias(p)) is not None}
    if len(datasets) != 1:
        raise SourceIdError(f"reference {ref!r} names {'no known dataset' if not datasets else sorted(datasets)}")
    dataset = datasets.pop()
    if dataset == STRUCTURED:
        raise SourceIdError(f"structured source must be written `structured:<field>`: {ref!r}")
    stem = parts[-1]
    for suffix in _SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return dataset, _require(_study_id(dataset, stem), ref)


def _require(study: str | None, ref: Any) -> str:
    if not study:
        raise SourceIdError(f"cannot parse a study id from {ref!r}")
    return study


ALLOWED, SAME_SOURCE, UNVERIFIABLE = "allowed", "same_source", "unverifiable"
SAME_PATIENT = "same_patient"  # CT-RATE only: another scan of the label source's patient


def report_provenance(report_ref: Any, label_source: Any) -> str:
    """May this report replace its image as input? ALLOWED, SAME_SOURCE (it is the label), SAME_PATIENT (CT-RATE:
    another scan of the same patient as the label source) or UNVERIFIABLE.

    Fail closed: an unparseable/unknown report or label reference is UNVERIFIABLE (substitution forbidden).
    A structured, non-report label (`structured:service`) cannot be a report, so it never blocks.
    """
    try:
        report = canonical_source_id(report_ref)
        label = canonical_source_id(label_source)
    except SourceIdError:
        return UNVERIFIABLE
    if report[0] not in REPORT_DATASETS:
        return UNVERIFIABLE
    if label[0] == STRUCTURED:
        return ALLOWED
    if report == label:
        return SAME_SOURCE
    if report[0] == "ct-rate" and label[0] == "ct-rate" and report[1].rsplit("_", 1)[0] == label[1].rsplit("_", 1)[0]:
        return SAME_PATIENT  # `<split>_<pid>_<scan>`: same `<split>_<pid>`, different scan (proposal 3.4)
    return ALLOWED


@dataclass(frozen=True)
class ModalityPolicy:
    dropout_p: dict[str, float] = field(default_factory=dict)  # per-modality image dropout probability
    report_substitution: bool = False  # replace a dropped image by its own report when provenance allows


def decide_modalities(sample: dict[str, Any], policy: ModalityPolicy, rng: random.Random,
                      events: Counter | None = None) -> dict[str, str]:
    """Per modality: IMAGE (kept), REPORT (image replaced by its report) or DROPPED.

    - dropout fires with probability p[m];
    - a dropped image becomes its report only if substitution is enabled, the report exists and the
      report is NOT the sample's label source by canonical (dataset, study) identity;
    - if either reference cannot be canonicalized, substitution fails closed (counted in
      `events["fail_closed"]`); a blocked label-source report is counted in `events["blocked_label_source"]`;
    - a required modality is never left with neither image nor report: if substitution is not
      allowed, the dropout is vetoed and the image is kept.
    """
    decisions: dict[str, str] = {}
    for modality in sorted(sample["images"]):
        info = sample["images"][modality]
        if rng.random() >= policy.dropout_p.get(modality, 0.0):
            decisions[modality] = IMAGE
            continue
        report_ref = info.get("report_ref")
        can_substitute = False
        if policy.report_substitution and report_ref is not None and info.get("report_ids") is not None:
            verdict = report_provenance(report_ref, sample.get("label_source"))
            can_substitute = verdict == ALLOWED
            if events is not None and not can_substitute:
                events["fail_closed" if verdict == UNVERIFIABLE else
                       "blocked_same_patient" if verdict == SAME_PATIENT else "blocked_label_source"] += 1
        if can_substitute:
            decisions[modality] = REPORT
        elif modality in sample["required_modalities"]:
            decisions[modality] = IMAGE
        else:
            decisions[modality] = DROPPED
    return decisions


class SyntheticCaseDataset:
    """Deterministic synthetic (CT volume, report, target) samples. `data_class = synthetic`, no real data."""

    data_class = DATA_CLASS

    def __init__(self, n: int, volume_shape: tuple[int, int, int], vocab_size: int, seed: int,
                 prompt_len: int = 4, report_len: int = 6, target_len: int = 6,
                 modalities: tuple[str, ...] = ("ct",), report_is_label_every: int = 2):
        self.n, self.volume_shape, self.vocab_size, self.seed = n, tuple(volume_shape), vocab_size, seed
        self.prompt_len, self.report_len, self.target_len = prompt_len, report_len, target_len
        self.modalities, self.report_is_label_every = modalities, report_is_label_every

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, i: int) -> dict[str, Any]:
        if not 0 <= i < self.n:
            raise IndexError(i)
        g = torch.Generator().manual_seed(self.seed * 1_000_003 + i)
        tok = lambda k: torch.randint(3, self.vocab_size, (k,), generator=g).tolist()  # noqa: E731
        images = {
            m: {"ref": f"synthetic:{m}-{i:05d}", "report_ref": f"synthetic:{m}-{i:05d}-report",
                "report_ids": tok(self.report_len)}
            for m in self.modalities
        }
        first = self.modalities[0]
        # Every k-th sample is a findings task whose label comes from the first modality's own report.
        label_source = images[first]["report_ref"] if i % self.report_is_label_every == 0 else "structured:service"
        return {
            "sample_id": f"syn-{i:05d}",
            "data_class": DATA_CLASS,
            "volume": torch.randn((1, *self.volume_shape), generator=g),
            "images": images,
            "label_source": label_source,
            "required_modalities": [],
            "prompt_ids": tok(self.prompt_len),
            "target_ids": tok(self.target_len),
        }


class Collator:
    """Builds a batch: CT volume + image mask, prompt (+ substituted reports) + target, loss on target only."""

    def __init__(self, policy: ModalityPolicy, seq_len: int, pad_id: int = 0, volume_modality: str = "ct"):
        self.policy, self.seq_len, self.pad_id, self.volume_modality = policy, seq_len, pad_id, volume_modality
        self.events: Counter = Counter()  # fail_closed / blocked_label_source substitution events

    def __call__(self, samples: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
        ids, labels, masks, image_mask, decisions = [], [], [], [], []
        for s in samples:
            if s.get("data_class") != DATA_CLASS:
                raise ValueError("the dry-run collator accepts only synthetic samples")
            d = decide_modalities(s, self.policy, rng, self.events)
            context = list(s["prompt_ids"])
            for modality, choice in d.items():
                if choice == REPORT:
                    info = s["images"][modality]
                    verdict = report_provenance(info.get("report_ref"), s.get("label_source"))
                    if verdict != ALLOWED:  # defence in depth: never feed the label (canonical identity, fail closed)
                        raise ReportLeakageError(f"{s['sample_id']}: report {info.get('report_ref')!r} vs label "
                                                 f"{s.get('label_source')!r}: {verdict}")
                    context += info["report_ids"]
            seq = (context + list(s["target_ids"]))[: self.seq_len]
            lab = ([-100] * len(context) + list(s["target_ids"]))[: self.seq_len]
            pad = self.seq_len - len(seq)
            ids.append(seq + [self.pad_id] * pad)
            labels.append(lab + [-100] * pad)
            masks.append([1] * len(seq) + [0] * pad)
            image_mask.append(d.get(self.volume_modality, DROPPED) == IMAGE)
            decisions.append(d)
        return {
            "volumes": torch.stack([s["volume"] for s in samples]),
            "image_mask": torch.tensor(image_mask),
            "input_ids": torch.tensor(ids),
            "attention_mask": torch.tensor(masks),
            "labels": torch.tensor(labels),
            "decisions": decisions,
        }
