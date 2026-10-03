"""B6: data audit PASS, missing != negative, planted-failure cases."""

from __future__ import annotations

import json

from research.data.ctrate.__main__ import main
from research.data.ctrate.audit import run_audit
from research.data.ctrate.build import build

from . import ctrate_fixture as fx


def _b(raw, tmp, **kw):
    ds = tmp / "b"
    build(raw, ds, unseal_test=True, **kw)
    return ds


def test_audit_pass_all_steps_and_cli_exit_code(ctrate_raw, tmp_path, capsys):
    ds = _b(ctrate_raw, tmp_path)
    rep = run_audit(ds, raw=ctrate_raw)
    assert rep["status"] == "PASS", rep["errors"]
    assert set(rep["steps"]) == {"schema", "gold_separation", "identifier_scan", "manifest_hashes",
                                 "snapshot_items_after_T", "patient_overlap", "missing_not_negative"}
    assert set(rep["steps"].values()) == {"PASS"}
    assert main(["audit", str(ds), "--raw", str(ctrate_raw)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_missing_is_serialized_as_missing_never_zero(ctrate_raw, tmp_path):
    ds = _b(ctrate_raw, tmp_path)
    gold = json.loads((ds / "gold/train" / f"{fx.BLANK_LABEL[0]}.json").read_text())
    assert gold["labels"]["values"][fx.BLANK_LABEL[1]] == "missing"
    no_labels = json.loads((ds / "gold/train" / f"{fx.NO_LABELS_SCAN}.json").read_text())
    assert no_labels["labels_status"] == "missing" and no_labels["labels"] is None
    no_report = json.loads((ds / "label_sources/train" / f"{fx.NO_REPORT_SCAN}.json").read_text())
    assert no_report["report"] == "missing"
    m = json.loads((ds / "manifest.json").read_text())
    assert m["counts"]["exclusions_by_reason"] == {"provider_no_chest": 1}
    assert m["counts"]["blank_label_cells"]["train"] == 1 and m["counts"]["missing_report_cases"]["train"] == 1


def test_audit_fails_if_blank_turned_into_zero(ctrate_raw, tmp_path):
    ds = _b(ctrate_raw, tmp_path)
    p = ds / "gold/train" / f"{fx.BLANK_LABEL[0]}.json"
    g = json.loads(p.read_text())
    g["labels"]["values"][fx.BLANK_LABEL[1]] = "0"
    p.write_text(json.dumps(g))
    rep = run_audit(ds)
    assert rep["status"] == "FAIL" and rep["steps"]["missing_not_negative"].startswith("FAIL")
    assert main(["audit", str(ds)]) == 1


def test_planted_report_text_under_inputs_fails(ctrate_raw, tmp_path):
    ds = _b(ctrate_raw, tmp_path)
    case = next((ds / "inputs/train").iterdir())
    rep = json.loads((ds / "label_sources/train" / f"{case.name}.json").read_text())["report"]
    text = rep["findings"] if rep != "missing" else "SYNTHETIC REPORT findings for planted: synthetic text only."
    p = case / "snapshot_T0.json"
    d = json.loads(p.read_text())
    d["items"][0]["metadata"]["note"] = text
    p.write_text(json.dumps(d))
    r = run_audit(ds)
    assert r["status"] == "FAIL" and r["steps"]["gold_separation"].startswith("FAIL")


def test_planted_label_column_under_inputs_fails(ctrate_raw, tmp_path):
    ds = _b(ctrate_raw, tmp_path)
    p = next((ds / "inputs/train").iterdir()) / "journey.json"
    d = json.loads(p.read_text())
    d["items"][0]["metadata"][fx.LABELS[0]] = "1"
    p.write_text(json.dumps(d))
    r = run_audit(ds)
    assert r["steps"]["gold_separation"].startswith("FAIL")


def test_planted_identifier_and_patient_overlap_fail(ctrate_raw, tmp_path):
    ds = _b(ctrate_raw, tmp_path)
    p = next((ds / "inputs/train").iterdir()) / "journey.json"
    d = json.loads(p.read_text())
    d["items"][0]["metadata"]["contact"] = "someone@example.org"
    p.write_text(json.dumps(d))
    assert run_audit(ds)["steps"]["identifier_scan"].startswith("FAIL")
    ds2 = tmp_path / "c"
    build(ctrate_raw, ds2, unseal_test=True)
    sp = json.loads((ds2 / "splits.json").read_text())
    sp["train_7"] = "test"  # contradicts official split + case dir
    (ds2 / "splits.json").write_text(json.dumps(sp))
    assert run_audit(ds2)["steps"]["patient_overlap"].startswith("FAIL")


LAB_T = "dataset/multi_abnormality_labels/train_predicted_labels.csv"


def _planted(monkeypatch, fn):
    """Corrupt the loader's view of the label CSV (derived counts stay self-consistent)."""
    import research.data.ctrate.loader as L
    orig = L._read_table

    def patched(root, rel, split, required, errors):
        header, out = orig(root, rel, split, required, errors)
        return header, ([(n, name, g, fn(dict(row))) for n, name, g, row in out] if "predicted_labels" in rel else out)

    monkeypatch.setattr(L, "_read_table", patched)


def test_planted_pipeline_bug_blank_to_zero_fails(ctrate_raw, tmp_path, monkeypatch, capsys):
    _planted(monkeypatch, lambda row: {k: ("0" if v == "" else v) for k, v in row.items()})
    ds = _b(ctrate_raw, tmp_path)
    m = json.loads((ds / "manifest.json").read_text())
    assert sum(m["counts"]["blank_label_cells"].values()) == 0  # the pipeline's own counts are self-consistent
    assert run_audit(ds)["steps"]["missing_not_negative"] == "NOT_RUN"  # ...so only the raw re-read can catch it
    rep = run_audit(ds, raw=ctrate_raw)
    assert rep["status"] == "FAIL" and rep["steps"]["missing_not_negative"].startswith("FAIL")
    assert any(fx.BLANK_LABEL[0] in e for e in rep["errors"])
    assert main(["audit", str(ds), "--raw", str(ctrate_raw)]) == 1


def test_planted_pipeline_bug_zero_to_missing_fails(ctrate_raw, tmp_path, monkeypatch):
    _planted(monkeypatch, lambda row: {k: ("" if v == "0" else v) for k, v in row.items()})
    ds = _b(ctrate_raw, tmp_path)
    rep = run_audit(ds, raw=ctrate_raw)
    assert rep["status"] == "FAIL" and rep["steps"]["missing_not_negative"].startswith("FAIL")


def test_missing_audit_does_not_use_loader(ctrate_raw, tmp_path, monkeypatch):
    ds = _b(ctrate_raw, tmp_path)
    import research.data.ctrate.loader as L

    def boom(*a, **k):
        raise AssertionError("audit must not call the loader")

    monkeypatch.setattr(L, "load_tree", boom)
    monkeypatch.setattr(L, "_read_table", boom)
    monkeypatch.setattr(L, "_read_no_chest", boom)
    import research.data.ctrate.audit as A
    assert not hasattr(A, "load_tree") and "loader" not in "".join(
        ln for ln in open(A.__file__, encoding="utf-8") if ln.startswith(("import", "from")))
    assert run_audit(ds, raw=ctrate_raw)["status"] == "PASS"


def test_audit_without_raw_is_not_pass(ctrate_raw, tmp_path, capsys):
    ds = _b(ctrate_raw, tmp_path)
    rep = run_audit(ds)
    assert rep["status"] != "PASS" and rep["steps"]["missing_not_negative"] == "NOT_RUN"
    assert main(["audit", str(ds)]) != 0


def test_raw_audit_flags_gold_without_raw_row_and_unsealed_raw_without_gold(ctrate_raw, tmp_path):
    ds = _b(ctrate_raw, tmp_path)
    raw2 = tmp_path / "raw2"
    import shutil
    shutil.copytree(ctrate_raw, raw2)
    h, rows = fx.read_rows(raw2 / LAB_T)
    fx.write_rows(raw2 / LAB_T, h, [r for r in rows if not r[0].startswith("train_2_a")])
    assert any("train_2_a" in e for e in run_audit(ds, raw=raw2)["errors"])
    raw3 = tmp_path / "raw3"
    shutil.copytree(ctrate_raw, raw3)
    h, rows = fx.read_rows(raw3 / LAB_T)
    fx.write_rows(raw3 / LAB_T, h, rows + [["train_1_z_1.nii.gz", *rows[0][1:]]])
    assert any("train_1_z" in e for e in run_audit(ds, raw=raw3)["errors"])


def test_raw_audit_skips_no_chest_rows(ctrate_raw, tmp_path):
    ds = _b(ctrate_raw, tmp_path)
    h, rows = fx.read_rows(ctrate_raw / LAB_T)
    assert any(r[0] == "train_10_b_1.nii.gz" for r in rows)  # raw label row exists for the excluded volume
    assert run_audit(ds, raw=ctrate_raw)["status"] == "PASS"


def test_label_origin_tamper_fails_schema(ctrate_raw, tmp_path):
    for mode in ("remove", "change"):
        ds = tmp_path / mode
        build(ctrate_raw, ds, unseal_test=True)
        p = next(q for q in sorted((ds / "gold/train").glob("*.json")) if json.loads(q.read_text())["labels"])
        g = json.loads(p.read_text())
        assert g["labels"]["label_origin"] == "provider_text_classifier_prediction_from_report"
        if mode == "remove":
            del g["labels"]["label_origin"]
        else:
            g["labels"]["label_origin"] = "radiologist_ground_truth"
        p.write_text(json.dumps(g))
        assert run_audit(ds, raw=ctrate_raw)["steps"]["schema"].startswith("FAIL")


def test_manifest_names_label_metric(ctrate_raw, tmp_path):
    m = json.loads((_b(ctrate_raw, tmp_path) / "manifest.json").read_text())
    assert m["label_origin"] == "provider_text_classifier_prediction_from_report"
    assert m["label_metric_name"] == "agreement with report-derived labels"
