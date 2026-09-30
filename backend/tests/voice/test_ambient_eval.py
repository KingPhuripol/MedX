"""V2A-A01/A02/A03/A04/A09/A16: ambient eval thresholds and guided eval counts unchanged."""

import json
import subprocess

from app.voice import eval as guided_eval
from app.voice import eval_ambient

from ..conftest import REPO_ROOT

# slices/s3/eval/voice_intake_eval.json at the pre-v2a base (eed8366): (tp, fp, fn) per field.
BASE_COMMIT = "eed8366"
BASE_COUNTS = {
    "dev": {"chief_complaint": (10, 0, 0), "onset_duration": (10, 0, 0), "severity": (8, 1, 0),
            "allergy_status": (8, 0, 0), "allergens": (2, 0, 0), "current_medications": (11, 0, 0),
            "relevant_history": (8, 0, 0), "micro_overall": (57, 1, 0)},
    "heldout": {"chief_complaint": (5, 0, 0), "onset_duration": (5, 0, 0), "severity": (4, 0, 0),
                "allergy_status": (4, 0, 0), "allergens": (2, 0, 0), "current_medications": (5, 0, 0),
                "relevant_history": (5, 0, 0), "micro_overall": (30, 0, 0)},
}


def _fresh_or_rerun(module) -> dict:
    path = module.OUT_PATH
    committed = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    fresh = committed is not None and committed.get("inputs_sha256") == module.inputs_sha256()
    return committed if fresh else module.run_eval()


def _counts(block: dict) -> dict:
    return {k: (v["tp"], v["fp"], v["fn"]) for k, v in block.items()}


def test_ambient_eval_thresholds():
    r = _fresh_or_rerun(eval_ambient)
    assert r["label"] == ("system evaluation — mock rules, synthetic ambient text dialogues (no audio/ASR), "
                          "not clinical performance")
    assert r["n_dialogues"] == 15
    assert r["bootstrap"] == {"resamples": 2000, "seed": 0, "unit": "dialogue (patient)", "method": "percentile"}
    for split in ("dev", "heldout"):
        assert {"micro_gated", "micro_overall", "relevant_history"} <= set(r["splits"][split])
    assert r["splits"]["dev"]["micro_gated"]["f1"] >= 0.90  # A02
    assert r["splits"]["heldout"]["micro_gated"]["f1"] >= 0.80
    assert r["allergy_false_none"] == 0  # A03
    dev = r["classifier"]["dev"]  # A04
    assert dev["correct_field"] == dev["n_question_turns"] > 0
    assert dev["flagged_answer_turns"] == []  # rev-3 A04: field-less gold (SPEC section 5) is not an answer
    assert dev["fieldless_question_turns"] == [
        {"ref": "th_ambient_07:t14", "question": True, "question_field": None, "n_facts": 0}]
    assert {"flagged_answer_turns", "fieldless_question_turns"} <= set(r["classifier"]["heldout"])  # A16, reported
    assert r["classifier"]["heldout"]["correct_field_rate"] >= 0.80
    assert r["final_action"]["dev"]["matched"] == 10 and r["final_action"]["heldout"]["matched"] >= 4  # A05
    assert isinstance(r["attention_on_question_turns"], int)
    lat = r["latency_ms"]  # A09
    assert lat["n_turns"] >= 150 and lat["p50"] <= lat["p95"] <= 500


def test_guided_eval_counts_unchanged():
    r = _fresh_or_rerun(guided_eval)
    for split, expected in BASE_COUNTS.items():
        assert _counts(r["splits"][split]) == expected, split
    assert r["allergy_false_none"] == 0
    base = subprocess.run(["git", "-C", str(REPO_ROOT), "show", f"{BASE_COMMIT}:slices/s3/eval/voice_intake_eval.json"],
                          capture_output=True, text=True)
    if base.returncode == 0:  # cross-check against the committed pre-v2a file when the commit is reachable
        old = json.loads(base.stdout)
        for split in BASE_COUNTS:
            assert _counts(old["splits"][split]) == BASE_COUNTS[split]
        assert old["per_dialogue"] == r["per_dialogue"]
