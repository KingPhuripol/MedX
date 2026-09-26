"""Synthetic dataset and the collator that enforces modality dropout / report-substitution provenance.

Proposal 3.3: stage 3 randomly drops modalities and creates samples in which an image is replaced by
the text report of the same image, *only* for tasks whose label does not come from that report.
Proposal 3.4: a report is never an input when it is the label source. The rule is enforced here, in
the collator (`decide_modalities` + `ReportLeakageError`), not by convention.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import torch

DATA_CLASS = "synthetic"
IMAGE, REPORT, DROPPED = "image", "report", "dropped"


class ReportLeakageError(RuntimeError):
    """A report that is the sample's label source was about to be used as model input."""


@dataclass(frozen=True)
class ModalityPolicy:
    dropout_p: dict[str, float] = field(default_factory=dict)  # per-modality image dropout probability
    report_substitution: bool = False  # replace a dropped image by its own report when provenance allows


def decide_modalities(sample: dict[str, Any], policy: ModalityPolicy, rng: random.Random) -> dict[str, str]:
    """Per modality: IMAGE (kept), REPORT (image replaced by its report) or DROPPED.

    - dropout fires with probability p[m];
    - a dropped image becomes its report only if substitution is enabled, the report exists and the
      report is NOT the sample's label source;
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
        can_substitute = (
            policy.report_substitution and report_ref is not None and info.get("report_ids") is not None
            and sample["label_source"] != report_ref
        )
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
            m: {"ref": f"{m}-{i:05d}", "report_ref": f"{m}-{i:05d}-report", "report_ids": tok(self.report_len)}
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

    def __call__(self, samples: list[dict[str, Any]], rng: random.Random) -> dict[str, Any]:
        ids, labels, masks, image_mask, decisions = [], [], [], [], []
        for s in samples:
            if s.get("data_class") != DATA_CLASS:
                raise ValueError("the dry-run collator accepts only synthetic samples")
            d = decide_modalities(s, self.policy, rng)
            context = list(s["prompt_ids"])
            for modality, choice in d.items():
                if choice == REPORT:
                    info = s["images"][modality]
                    if info["report_ref"] == s["label_source"]:  # defence in depth: never feed the label
                        raise ReportLeakageError(f"{s['sample_id']}: {info['report_ref']} is the label source")
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
