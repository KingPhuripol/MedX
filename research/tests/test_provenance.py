"""S9R-A10..A12: report substitution is blocked by canonical (dataset, study) identity, fails closed on
unparseable/unknown references, and still happens for genuinely distinct sources."""

from __future__ import annotations

import random
from collections import Counter

import pytest
import torch

from research.train import data as D
from research.train.data import (DROPPED, IMAGE, REPORT, Collator, ModalityPolicy, ReportLeakageError, canonical_source_id,
                                 decide_modalities)

REPORT_REF = "mimic-cxr:files/p10/p10000032/s50414267.txt"
CT_REPORT_REF = "ct-rate:train_1_a"
DRAWS = 1000
POLICY = ModalityPolicy(dropout_p={"cxr": 1.0}, report_substitution=True)

# (report_ref, label_source): both name the same (dataset, study).
IDENTITY_VARIANTS = {
    "case": (REPORT_REF, "MIMIC-CXR:FILES/P10/P10000032/S50414267.TXT"),
    "whitespace": (REPORT_REF, "  \tmimic-cxr:s50414267 \n"),
    "nfkc_fullwidth": (REPORT_REF, "ｍｉｍｉｃ－ｃｘｒ：ｓ５０４１４２６７"),
    "relative_path": (REPORT_REF, "mimic-cxr/files/p10/p10000032/s50414267.txt"),
    "absolute_path": (REPORT_REF, "/data/physionet/mimic-cxr/2.0.0/files/p10/p10000032/s50414267.txt"),
    "file_uri": (REPORT_REF, "file:///data/physionet/mimic-cxr/2.0.0/files/p10/p10000032/s50414267.txt"),
    "backslash_path": (REPORT_REF, "C:\\data\\mimic-cxr\\files\\p10\\p10000032\\s50414267.txt"),
    "duplicate_slashes": (REPORT_REF, "mimic-cxr//files///p10/p10000032//s50414267.txt"),
    "txt_suffix": ("mimic-cxr:s50414267", "mimic-cxr:s50414267.txt"),
    "s_prefix": ("mimic-cxr:s50414267", "mimic-cxr:50414267"),
    "alias_MIMIC_CXR": (REPORT_REF, "MIMIC_CXR:s50414267"),
    "alias_mimiccxr": (REPORT_REF, "mimiccxr/s50414267"),
    "mimic_cxr_jpg": (REPORT_REF, "mimic-cxr-jpg:files/p10/p10000032/s50414267.txt"),
    "spec_example": ("MIMIC-CXR/s50414267", REPORT_REF),
    "alias_CT_RATE": (CT_REPORT_REF, "CT_RATE:train_1_a"),
    "alias_ctrate": (CT_REPORT_REF, "ctrate/train_1_a.txt"),
    "ct_rate_reconstruction": (CT_REPORT_REF, "CT-RATE:train_1_a_2.nii.gz"),
}


def _sample(report_ref, label_source, required=()):
    return {
        "sample_id": "variant", "data_class": D.DATA_CLASS, "volume": torch.zeros(1, 4, 8, 8),
        "images": {"cxr": {"ref": "cxr-image", "report_ref": report_ref, "report_ids": [5, 6, 7]}},
        "label_source": label_source, "required_modalities": list(required), "prompt_ids": [3, 4], "target_ids": [8, 9],
    }


def _count(sample, policy=POLICY, seed=0, events=None):
    rng = random.Random(seed)
    return Counter(decide_modalities(sample, policy, rng, events)["cxr"] for _ in range(DRAWS))


@pytest.mark.parametrize("variant", list(IDENTITY_VARIANTS))
def test_no_substitution_under_identity_variants(variant):
    report_ref, label = IDENTITY_VARIANTS[variant]
    assert canonical_source_id(report_ref) == canonical_source_id(label)  # really the same identity, not fail-closed
    events = Counter()
    counts = _count(_sample(report_ref, label), events=events)
    assert counts[REPORT] == 0 and counts[DROPPED] == DRAWS
    assert events["blocked_label_source"] == DRAWS and events["fail_closed"] == 0


def test_identity_variant_count():
    assert len(IDENTITY_VARIANTS) >= 12


@pytest.mark.parametrize("variant", list(IDENTITY_VARIANTS))
def test_collator_defence_uses_canonical_id(variant, monkeypatch):
    report_ref, label = IDENTITY_VARIANTS[variant]
    monkeypatch.setattr(D, "decide_modalities", lambda s, p, r, e=None: {"cxr": REPORT})  # force a substitution
    collator = Collator(POLICY, seq_len=16, volume_modality="cxr")
    with pytest.raises(ReportLeakageError):
        collator([_sample(report_ref, label)], random.Random(0))


UNPARSEABLE = {
    "label_unparseable": (REPORT_REF, "files/p10/p10000032/s50414267.txt"),  # no dataset
    "label_unknown_dataset": (REPORT_REF, "padchest:50414267"),
    "label_not_string": (REPORT_REF, None),
    "label_bad_study": (REPORT_REF, "mimic-cxr:report-final"),
    "report_unknown_dataset": ("chexpert:s50414267", "structured:service"),
    "report_unparseable": ("???", "mimic-cxr:s50414268"),
    "two_datasets": ("mimic-cxr/ct-rate/s50414267", "structured:service"),
}


def test_unparseable_source_fails_closed(monkeypatch):
    for name, (report_ref, label) in UNPARSEABLE.items():
        events = Counter()
        counts = _count(_sample(report_ref, label), events=events)
        assert counts[REPORT] == 0, name
        assert events["fail_closed"] == DRAWS, (name, events)
        required = _count(_sample(report_ref, label, required=["cxr"]))
        assert required[IMAGE] == DRAWS, name  # a required modality keeps its image (100%)
    # The collator counts the events, and its defence check refuses a forced substitution.
    collator = Collator(POLICY, seq_len=16, volume_modality="cxr")
    collator([_sample(*UNPARSEABLE["label_unknown_dataset"])], random.Random(0))
    assert collator.events["fail_closed"] > 0
    monkeypatch.setattr(D, "decide_modalities", lambda s, p, r, e=None: {"cxr": REPORT})
    for report_ref, label in UNPARSEABLE.values():
        with pytest.raises(ReportLeakageError):
            collator([_sample(report_ref, label)], random.Random(0))


DISTINCT = {
    "other_study": (REPORT_REF, "mimic-cxr:files/p10/p10000032/s53189527.txt"),  # same patient, different study
    "other_dataset": ("mimic-cxr:s50414267", "synthetic:50414267"),  # same numeric id, different dataset
    "structured": (REPORT_REF, "structured:service"),
}


@pytest.mark.parametrize("case", list(DISTINCT))
def test_substitution_allowed_for_distinct_source(case):
    report_ref, label = DISTINCT[case]
    events = Counter()
    counts = _count(_sample(report_ref, label), events=events)
    assert counts[REPORT] > 0 and counts[REPORT] == DRAWS
    assert sum(events.values()) == 0
    out = Collator(POLICY, seq_len=16, volume_modality="cxr")([_sample(report_ref, label)], random.Random(0))
    assert out["decisions"][0]["cxr"] == REPORT
