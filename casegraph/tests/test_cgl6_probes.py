"""cg-l6 (CONDITIONS L6d): refactored cg-t123 probes run in `make test`. Synthetic, offline, mock gateways."""
from __future__ import annotations

import importlib.util
from pathlib import Path

E2E = Path(__file__).resolve().parents[2] / "tests" / "e2e"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_l6", E2E / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_allergy_probe_reference(tmp_path):
    out = _load("cgt123_allergy_probe").run_probe(tmp_path)
    assert (out["combos"], out["bad"], out["gap_combos"]) == (80, [], 71)
    assert out["pass"] is True


def test_h1_probe_reference(tmp_path):
    from casegraph import reader_text

    real = reader_text.read_clinical_text
    out = _load("cgt123_h1_probe").run_probe(tmp_path)
    assert (out["combos"], out["bad"]) == (16, []) and out["pass"] is True
    assert reader_text.read_clinical_text is real  # patch never leaks
