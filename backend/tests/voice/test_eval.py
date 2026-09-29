"""S3-A01 / S3-A02 / S3-A19: evaluation thresholds and report completeness."""

import json

from app.voice import eval as voice_eval
from app.voice.models import FACT_FIELDS

THRESHOLD_FIELDS = ("chief_complaint", "onset_duration", "allergy_status")


def _check_block(block: dict) -> None:
    for name in (*FACT_FIELDS, "micro_overall"):
        m = block[name]
        assert {"tp", "fp", "fn", "precision", "recall", "f1", "ci95"} <= set(m), name
        assert set(m["ci95"]) == {"precision", "recall", "f1"}, name


def test_eval_thresholds():
    path = voice_eval.OUT_PATH
    committed = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    fresh = committed is not None and committed.get("inputs_sha256") == voice_eval.inputs_sha256()
    result = committed if fresh else voice_eval.run_eval()  # stale or missing -> run in process

    assert result["label"] == "system evaluation — mock rules, synthetic dialogues, not clinical performance"
    assert result["n_dialogues"] == 15
    assert result["bootstrap"] == {"resamples": 2000, "seed": 0, "unit": "dialogue (patient)", "method": "percentile"}
    _check_block(result["fields"])
    _check_block(result["splits"]["dev"])
    _check_block(result["splits"]["heldout"])
    for field in THRESHOLD_FIELDS:
        f1 = result["fields"][field]["f1"]
        assert f1 != "n/a" and f1 >= 0.80, (field, f1)
    assert result["allergy_false_none"] == 0
    lat = result["latency_ms"]
    assert lat["n_turns"] > 60 and lat["p50"] <= lat["p95"] <= 500


def test_prf_na_and_bootstrap_deterministic():
    assert voice_eval.prf(0, 0, 0)["f1"] == "n/a"
    assert voice_eval.prf(0, 2, 0) == {"tp": 0, "fp": 2, "fn": 0, "precision": 0.0, "recall": "n/a", "f1": "n/a"}
    per = [(1, 0, 0), (0, 1, 1), (1, 0, 0), (1, 0, 0)]
    assert voice_eval.bootstrap_ci(per) == voice_eval.bootstrap_ci(per)
    assert voice_eval.field_counts(None, {"state": "KNOWN", "value": "none"}, "allergy_status") == (0, 1, 0)
    assert voice_eval.field_counts({"state": "KNOWN", "value": None, "items": []}, None, "current_medications") == (0, 0, 1)
    gold = {"state": "KNOWN", "value": None, "items": ["พารา", "metformin"]}
    pred = {"state": "KNOWN", "value": ["Paracetamol", "metformin"]}
    assert voice_eval.field_counts(gold, pred, "current_medications") == (2, 0, 0)
