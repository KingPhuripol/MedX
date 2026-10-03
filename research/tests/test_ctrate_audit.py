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
    rep = run_audit(ds)
    assert rep["status"] == "PASS", rep["errors"]
    assert set(rep["steps"]) == {"schema", "gold_separation", "identifier_scan", "manifest_hashes",
                                 "snapshot_items_after_T", "patient_overlap", "missing_not_negative"}
    assert set(rep["steps"].values()) == {"PASS"}
    assert main(["audit", str(ds)]) == 0
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
