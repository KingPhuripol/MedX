"""B2: typed parsing with full coverage; every malformation fails loudly naming the row."""

from __future__ import annotations

import pytest

from research.data.ctrate.loader import CTRateLoadError, load_tree
from research.data.ctrate.types import ANCHOR, AbnormalityLabels, CTVolume, RadiologyReport

from . import ctrate_fixture as fx

META_T = "dataset/metadata/train_metadata.csv"
REP_T = "dataset/radiology_text_reports/train_reports.csv"
LAB_T = "dataset/multi_abnormality_labels/train_predicted_labels.csv"
REP_V = "dataset/radiology_text_reports/validation_reports.csv"


def _mutate(root, rel, fn):
    header, rows = fx.read_rows(root / rel)
    fx.write_rows(root / rel, header, fn(header, rows))


def test_full_coverage_and_accounting(ctrate_raw):
    r = load_tree(ctrate_raw)
    n_vol = len(fx.volume_names())
    # rows in = evidence + recorded exclusions, per table: 0 silent drops
    assert r.row_counts["metadata"] == n_vol == len(r.volumes) + sum(e["table"] == "metadata" for e in r.exclusions)
    n_rep_rows = sum(len(x.volume_names) for x in r.reports) + sum(e["table"] == "reports" for e in r.exclusions)
    assert r.row_counts["reports"] == n_rep_rows
    n_lab_rows = sum(len(x.volume_names) for x in r.labels) + sum(e["table"] == "labels" for e in r.exclusions)
    assert r.row_counts["labels"] == n_lab_rows
    for it in [*r.volumes, *r.reports, *r.labels]:
        assert it.available_at_time and it.source == "ct-rate"
        assert it.provenance.startswith("hf://datasets/ibrahimhamamci/CT-RATE@deeca4d8") and "#row=" in it.provenance
        assert it.version.startswith("ct-rate@deeca4d8") and it.time_basis == "synthetic_anchor"
    assert {type(x) for x in [*r.volumes, *r.reports, *r.labels]} == {CTVolume, RadiologyReport, AbnormalityLabels}


def test_time_ordering_volume_before_report_before_labels(ctrate_raw):
    r = load_tree(ctrate_raw)
    v, rep, lab = r.volumes[0], r.reports[0], r.labels[0]
    assert v.available_at_time == v.event_time == v.observed_at == ANCHOR
    assert v.available_at_time < rep.available_at_time < lab.available_at_time


def test_reconstructions_collapse_to_one_scan_report(ctrate_raw):
    r = load_tree(ctrate_raw)
    rep = next(x for x in r.reports if x.scan_ref == "train_3_a")
    assert len(rep.volume_names) == 3
    assert len([v for v in r.volumes if v.scan_ref == "train_3_a"]) == 3


def test_blank_is_missing_and_zero_is_negative(ctrate_raw):
    r = load_tree(ctrate_raw)
    lab = next(x for x in r.labels if x.scan_ref == fx.BLANK_LABEL[0])
    assert lab.values[fx.BLANK_LABEL[1]] == "missing"
    assert "0" in {v for x in r.labels for v in x.values.values()}
    assert r.blank_label_cells["train"] == 1


def test_missing_report_and_labels_kept_and_no_chest_excluded(ctrate_raw):
    r = load_tree(ctrate_raw)
    assert fx.NO_REPORT_SCAN in r.missing_report_scans and fx.NO_REPORT_SCAN in {v.scan_ref for v in r.volumes}
    assert fx.NO_LABELS_SCAN in r.missing_label_scans
    ex = [e for e in r.exclusions if e["table"] == "metadata"]
    assert [(e["volume_name"], e["reason"]) for e in ex] == [("train_10_b_1.nii.gz", "provider_no_chest")]
    assert "train_10_b_1.nii.gz" not in {v.volume_ref.split(":")[1] for v in r.volumes}
    assert "train_10_b" not in {x.scan_ref for x in [*r.reports, *r.labels]}


def _name(i):
    return lambda h, rows: [[f"train_{i}_a_1.nii.gz", *rows[0][1:]]] + rows[1:]


def _dup(h, rows):
    return rows + [list(rows[0])]


def _bad_label(h, rows):
    rows[0][1] = "2"
    return rows


def _orphan(h, rows):
    return rows + [["train_99_a_1.nii.gz", *rows[0][1:]]]


def _conflict(h, rows):
    i = next(i for i, r in enumerate(rows) if r[0] == "train_3_a_2.nii.gz")
    rows[i][1] = "SYNTHETIC REPORT changed"
    return rows


def _valid_in_train(h, rows):
    return rows + [["valid_3_a_1.nii.gz", *rows[0][1:]]]


def _zero_pad(h, rows):
    rows[0][0] = "train_01_a_1.nii.gz"
    return rows


def _thai(h, rows):
    rows[0][0] = "train_๑_a_1.nii.gz"
    return rows


@pytest.mark.parametrize("rel,fn,code", [
    (META_T, _zero_pad, "bad_volume_name"),
    (META_T, _thai, "bad_volume_name"),
    (REP_T, _valid_in_train, "split_mismatch"),
    (META_T, _dup, "duplicate_volume_name"),
    (LAB_T, _bad_label, "bad_label_value"),
    (LAB_T, _orphan, "orphan_row"),
    (REP_T, _conflict, "reconstruction_conflict"),
])
def test_malformed_input_fails_loudly_naming_the_row(ctrate_raw, rel, fn, code):
    _mutate(ctrate_raw, rel, fn)
    with pytest.raises(CTRateLoadError) as ei:
        load_tree(ctrate_raw)
    hits = [e for e in ei.value.errors if e.code == code]
    assert hits, [str(e) for e in ei.value.errors]
    assert hits[0].file in str(hits[0]) and hits[0].row >= 0 and f"row={hits[0].row}" in str(ei.value)


def test_missing_required_column_fails(ctrate_raw):
    _mutate(ctrate_raw, REP_V, lambda h, rows: rows)
    p = ctrate_raw / REP_V
    h, rows = fx.read_rows(p)
    fx.write_rows(p, ["VolumeName", "Findings_EN"], [r[:2] for r in rows])
    with pytest.raises(CTRateLoadError) as ei:
        load_tree(ctrate_raw)
    assert any(e.code == "missing_column" and e.detail == "Impressions_EN" for e in ei.value.errors)


def test_partial_reconstruction_report_is_a_conflict(ctrate_raw):
    _mutate(ctrate_raw, REP_T, lambda h, rows: [r for r in rows if r[0] != "train_3_a_3.nii.gz"])
    with pytest.raises(CTRateLoadError) as ei:
        load_tree(ctrate_raw)
    assert any(e.code == "reconstruction_conflict" for e in ei.value.errors)


@pytest.mark.parametrize("split", ["train", "valid"])
def test_missing_no_chest_file_fails_loudly(ctrate_raw, split, tmp_path):
    rel = f"dataset/metadata/no_chest_{split}.txt"
    (ctrate_raw / rel).unlink()
    with pytest.raises(CTRateLoadError) as ei:
        load_tree(ctrate_raw)
    assert [e.file for e in ei.value.errors if e.code == "missing_file"] == [rel]
    from research.data.ctrate.build import build
    out = tmp_path / "out"
    with pytest.raises(CTRateLoadError):
        build(ctrate_raw, out)
    assert not out.exists() or not any(out.iterdir())


def test_empty_no_chest_file_means_zero_exclusions(ctrate_raw):
    (ctrate_raw / "dataset/metadata/no_chest_train.txt").write_text("", encoding="utf-8")
    r = load_tree(ctrate_raw)
    assert r.exclusions == [] and r.row_counts["no_chest"] == 0
    assert "train_10_b" in {v.scan_ref for v in r.volumes}


def test_label_origin_required(ctrate_raw):
    r = load_tree(ctrate_raw)
    lab = r.labels[0]
    assert lab.label_origin == "provider_text_classifier_prediction_from_report"
    d = lab.model_dump()
    d.pop("label_origin")
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        AbnormalityLabels(**d)
    with pytest.raises(Exception):  # noqa: B017
        AbnormalityLabels(**(d | {"label_origin": "radiologist_ground_truth"}))
    from research.data.ctrate.types import LABEL_METRIC_NAME
    assert LABEL_METRIC_NAME == "agreement with report-derived labels"
