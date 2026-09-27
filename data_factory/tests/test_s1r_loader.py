"""Slice i2 (C6, I2-A02): the S1r loader maps every snapshot item into casegraph.data losslessly."""

import json

import pytest

from casegraph.data import Evidence
from casegraph.sources import s1r


def test_s1r_snapshot_loads_lossless(dataset):
    n_snap = n_items = 0
    for split in s1r.SPLITS:
        paths = s1r.snapshot_paths(dataset.root, split)
        for path, snap in zip(paths, s1r.load_split(dataset.root, split), strict=True):
            raw = json.loads(path.read_text(encoding="utf-8"))
            assert snap.T.isoformat() == raw["as_of"] and snap.patient_ref == raw["patient_ref"]
            assert len(snap.items) == len(raw["items"])
            for item, source in zip(snap.items, raw["items"], strict=True):
                assert isinstance(item, Evidence) and item.data_class == dataset.manifest["data_class"]
                assert s1r.roundtrip(item) == {**source, "data_class": "synthetic"}  # only data_class added
                n_items += 1
            n_snap += 1
    assert n_snap == 400 and n_items > 2000


def test_s1r_loader_reads_only_snapshots_and_needs_manifest_data_class(dataset, tmp_path):
    paths = [p for split in s1r.SPLITS for p in s1r.snapshot_paths(dataset.root, split)]
    assert paths and all(s1r.SNAPSHOT_NAME.match(p.name) for p in paths)
    (tmp_path / "manifest.json").write_text(json.dumps({"seed": 1}), encoding="utf-8")
    with pytest.raises(s1r.S1rLoadError, match="data_class"):
        s1r.manifest_data_class(tmp_path)


def test_s1r_loader_refuses_future_item(dataset):
    path = s1r.snapshot_paths(dataset.root, "train")[0]
    doc = json.loads(path.read_text(encoding="utf-8"))
    late = dict(doc["items"][-1], item_id="PLANTED-FUTURE", available_at_time="2099-01-01T00:00:00+07:00")
    with pytest.raises(s1r.S1rLoadError, match="after T"):
        s1r.parse_snapshot({**doc, "items": [*doc["items"], late]}, "synthetic", "train", "T1")
