"""Slices e1r (scope 4) and e1r2 (E1R2-A06): instrumented replay of dev SYNE-0196 through the unchanged S3 service.

Dev split only; test-split cases are analysed from stored outputs only. The replay runs in-process on an
in-memory SQLite engine and writes nothing under eval/results or eval/ledger (checked). It lives outside eval/
because it imports product code (app.*), which eval/ modules outside eval/adapters may not. It fails unless it
observes exactly what eval.posthoc.e1_findings.INSTRUMENTED_REPLAY_SYNE0196 and the committed
POSTHOC_FINDINGS.json trace state. Research prototype.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from eval.adapters import inputs, voice
from eval.posthoc import e1_findings as F

REPO = Path(__file__).resolve().parents[2]


def _tree(*roots: Path) -> dict[str, str]:
    return {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for r in roots for p in sorted(r.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def ds(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("s1r") / "v1"
    env = {**os.environ, "PYTHONPATH": f"{REPO}{os.pathsep}{REPO / 'backend'}"}
    subprocess.run([sys.executable, "-m", "data_factory", "generate", "--seed", "20260926", "--out", str(out)],
                   check=True, cwd=REPO, env=env, capture_output=True)
    frozen = F._manifest_hashes(json.loads((REPO / "eval/manifests/e1/e1-voice-dev-v1.json").read_text("utf-8")))
    F.load_gold(out, frozen["dataset_tree_sha256"])  # raises unless the E1 data projection is the frozen one
    return out


NOT_RECOMPUTED = ("verified_by", "provenance")  # labels about the constant, not replay observations


def test_replay_constant_recomputed(ds):
    """E1R2-A06: recompute every key of the hand-transcribed INSTRUMENTED_REPLAY_SYNE0196 from the replay."""
    split, cid = F.TRACE_CASE
    guarded = (REPO / "eval" / "results", REPO / "eval" / "ledger")
    before = _tree(*guarded)
    case = inputs.load_case(ds, split, cid)
    ctx, engine = voice.make_context()
    try:
        res = voice.replay(ctx, case)
        with engine.begin() as c:
            turns = [dict(r._mapping) for r in c.execute(text(
                "select turn_id, seq, speaker, field, utterance_id, text from voice_turns order by seq"))]
            facts = [dict(r._mapping) for r in c.execute(text(
                "select fact_id, field, state, value_json, value_text, span_turn_ids_json, supersedes_fact_id "
                "from voice_facts order by id"))]
    finally:
        engine.dispose()

    index: dict[str, int] = {}  # recorded (non-agent) turn id -> transcript turn index
    agent_turns, last_asked, last_idx, current = [], {}, None, None
    for t in turns:
        if t["speaker"] == "agent":
            agent_turns.append({"after_turn_index": last_idx, "utterance_id": t["utterance_id"],
                                "field": t["field"]})
            current = t["field"] or current
            continue
        last_idx = len(index)
        index[t["turn_id"]] = last_idx
        if t["speaker"] == "patient":
            last_asked[str(last_idx)] = current
    superseded = {f["supersedes_fact_id"] for f in facts if f["supersedes_fact_id"]}
    cc = [{"turn_index": index[json.loads(f["span_turn_ids_json"])[0]], "state": f["state"],
           "value": json.loads(f["value_json"]), "value_text": f["value_text"],
           "superseded": f["fact_id"] in superseded} for f in facts if f["field"] == "chief_complaint"]
    turn1 = next(t["text"] for t in turns if index.get(t["turn_id"]) == 1)
    gold = json.loads((ds / "gold" / split / f"{cid}.json").read_text("utf-8"))
    gold_cc = next(d for d in gold["decision_times"] if d["decision_point"] == "T1")["required_fields"][
        "chief_complaint"]["th_text"]
    stored = next(json.loads(x) for x in (REPO / "eval/results/e1/dev/system_outputs.jsonl").read_text(
        "utf-8").splitlines() if json.loads(x)["case_id"] == cid)["voice"]

    observed = {
        "agent_turns": agent_turns,
        "last_asked_field_at_patient_turns": last_asked,
        "chief_complaint_facts": cc,
        "turn_1_contains_gold_cc_text": gold_cc in turn1,
        "final_facts_equal_stored": res == stored,
    }
    assert [a["utterance_id"] for a in agent_turns] == [
        "ask.chief_complaint", "reask.chief_complaint", "handoff.nurse_attention_phrase"]
    assert [(f["turn_index"], f["value"], f["superseded"]) for f in cc] == [
        (1, "fatigue", True), (9, "joint_pain", False)]
    assert observed["final_facts_equal_stored"] is True
    assert set(F.INSTRUMENTED_REPLAY_SYNE0196) >= set(NOT_RECOMPUTED)
    expected = {k: v for k, v in F.INSTRUMENTED_REPLAY_SYNE0196.items() if k not in NOT_RECOMPUTED}
    assert set(observed) == set(expected)
    for k in expected:
        assert observed[k] == expected[k], k
    assert "hand-transcribed" in F.INSTRUMENTED_REPLAY_SYNE0196["provenance"]
    assert "test_replay_constant_recomputed" in F.INSTRUMENTED_REPLAY_SYNE0196["provenance"]
    committed = json.loads((REPO / "eval/results/e1" / F.OUT_JSON).read_text("utf-8"))
    trace = next(s for s in committed["sections"] if s["id"] == "C-E1-1")["data"]["syne0196_trace"]
    assert trace["instrumented_replay"] == F.INSTRUMENTED_REPLAY_SYNE0196
    assert _tree(*guarded) == before
