"""B4: the scan's own report is never model input; canonical identity, existing collator."""

from __future__ import annotations

import random
from collections import Counter

import pytest
import torch

import research.train.data as D
from research.data.ctrate.build import TASKS, guard_sample
from research.data.ctrate.loader import load_tree
from research.train.data import (Collator, ModalityPolicy, ReportLeakageError, canonical_source_id, decide_modalities,
                                 report_provenance)


@pytest.fixture
def parts(ctrate_raw):
    r = load_tree(ctrate_raw)
    rep = {x.scan_ref: x for x in r.reports}
    lab = {x.scan_ref: x for x in r.labels}
    return r, rep, lab


def test_refs_canonicalize_to_the_scan(parts):
    r, rep, lab = parts
    recs = [v for v in r.volumes if v.scan_ref == "train_3_a"]
    assert len(recs) == 3
    ids = {canonical_source_id(v.volume_ref) for v in recs} | {canonical_source_id(rep["train_3_a"].report_ref)}
    assert ids == {("ct-rate", "train_3_a")}
    assert report_provenance(rep["train_3_a"].report_ref, lab["train_3_a"].label_source) == "same_source"
    assert canonical_source_id(recs[0].volume_ref) != canonical_source_id(rep["train_2_a"].report_ref)


@pytest.mark.parametrize("task", TASKS)
def test_own_report_is_blocked_and_counted_for_every_task(parts, task):
    r, rep, lab = parts
    v = next(v for v in r.volumes if v.scan_ref == "train_3_a" and v.reconstruction == 2)
    s = guard_sample(v.volume_ref, rep["train_3_a"].report_ref, lab["train_3_a"].label_source, task=task)
    ev = Counter()
    d = decide_modalities(s, ModalityPolicy({"ct": 1.0}, report_substitution=True), random.Random(0), ev)
    assert d["ct"] == D.DROPPED and ev["blocked_label_source"] == 1 and not ev["fail_closed"]


def test_other_scan_report_is_allowed(parts):
    r, rep, lab = parts
    v = next(v for v in r.volumes if v.scan_ref == "train_3_a")
    s = guard_sample(v.volume_ref, rep["train_2_a"].report_ref, lab["train_3_a"].label_source)
    ev = Counter()
    d = decide_modalities(s, ModalityPolicy({"ct": 1.0}, report_substitution=True), random.Random(0), ev)
    assert d["ct"] == D.REPORT and not ev


def _collator_sample(guard):
    return guard | {"data_class": "synthetic", "volume": torch.zeros(1, 2, 2, 2), "prompt_ids": [1], "target_ids": [2]}


def test_collator_raises_if_own_report_gets_substituted(parts, monkeypatch):
    r, rep, lab = parts
    v = r.volumes[0]
    s = _collator_sample(guard_sample(v.volume_ref, rep[v.scan_ref].report_ref, lab[v.scan_ref].label_source))
    monkeypatch.setattr(D, "decide_modalities", lambda *a, **k: {"ct": D.REPORT})  # adversarial: bypass the policy
    with pytest.raises(ReportLeakageError):
        Collator(ModalityPolicy({"ct": 1.0}, True), seq_len=8)([s], random.Random(0))


def test_collator_normal_path_blocks_and_counts(parts):
    r, rep, lab = parts
    v = r.volumes[0]
    s = _collator_sample(guard_sample(v.volume_ref, rep[v.scan_ref].report_ref, lab[v.scan_ref].label_source))
    c = Collator(ModalityPolicy({"ct": 1.0}, True), seq_len=8)
    c([s], random.Random(0))
    assert c.events["blocked_label_source"] == 1
