"""Slices e1r (scope 4) and e1r2 (E1R2-A06): instrumented replay of dev SYNE-0196 through the S3 service.

Dev split only; test-split cases are analysed from stored outputs only. The replay runs in-process on an
in-memory SQLite engine and writes nothing under eval/results or eval/ledger (checked). It lives outside eval/
because it imports product code (app.*), which eval/ modules outside eval/adapters may not.

Re-scoped in slice v2a (SPEC D-V2A-1). The frozen constant eval.posthoc.e1_findings.INSTRUMENTED_REPLAY_SYNE0196
records the pre-fix DEF-E1R-001 behaviour. Its live-replay equality was last verified at the pre-v2a base commit
eed8366 (test_replay_constant_recomputed). After the DEF-E1R-001 (a)+(b) fix that equality can never hold again,
so this file now checks (1) that the frozen constant still equals the committed POSTHOC_FINDINGS.json trace and
(2) the fixed behaviour on the same dev case. The frozen artifacts are unchanged. Research prototype.
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


def test_frozen_constant_matches_committed_trace():
    """E1R2-A06 (kept): the hand-transcribed constant equals the committed trace and is provenance-labelled."""
    assert set(F.INSTRUMENTED_REPLAY_SYNE0196) >= set(NOT_RECOMPUTED)
    assert "hand-transcribed" in F.INSTRUMENTED_REPLAY_SYNE0196["provenance"]
    assert "test_replay_constant_recomputed" in F.INSTRUMENTED_REPLAY_SYNE0196["provenance"]
    committed = json.loads((REPO / "eval/results/e1" / F.OUT_JSON).read_text("utf-8"))
    trace = next(s for s in committed["sections"] if s["id"] == "C-E1-1")["data"]["syne0196_trace"]
    assert trace["instrumented_replay"] == F.INSTRUMENTED_REPLAY_SYNE0196


def test_replay_after_def_e1r_001_fix(ds):
    """v2a (DEF-E1R-001 a+b): the same dev replay no longer attributes the allergy answer to the chief complaint."""
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
                "select field, state, value_json, span_turn_ids_json, supersedes_fact_id from voice_facts order by id"))]
    finally:
        engine.dispose()

    index = {t["turn_id"]: i for i, t in enumerate(x for x in turns if x["speaker"] != "agent")}
    # The ask/handoff policy is unchanged.
    assert [t["utterance_id"] for t in turns if t["speaker"] == "agent"] == [
        "ask.chief_complaint", "reask.chief_complaint", "handoff.nurse_attention_phrase"]
    frozen = F.INSTRUMENTED_REPLAY_SYNE0196["chief_complaint_facts"]
    cc = [(index[json.loads(f["span_turn_ids_json"])[0]], json.loads(f["value_json"]), f["supersedes_fact_id"])
          for f in facts if f["field"] == "chief_complaint"]
    # (b) only the turn-1 CC is written; the later joint_pain CC of the frozen trace is gone and nothing supersedes.
    assert cc == [(frozen[0]["turn_index"], frozen[0]["value"], None)]
    assert res["facts"]["chief_complaint"]["value"] == "fatigue"
    assert res["facts"]["chief_complaint"]["span_turn_indexes"] == [1]
    # (a) the nurse's drug-reaction question sets the window; the answer is an allergy, not a CC or a medicine.
    drug_q = next(t for t in turns if t["speaker"] == "nurse" and "ยา" in t["text"] and t["field"] == "allergy_status")
    answer = next(t for t in turns if t["seq"] == drug_q["seq"] + 1)
    assert res["facts"]["allergy_status"]["value"] == "present"
    assert res["facts"]["allergy_status"]["span_turn_indexes"] == [index[answer["turn_id"]]]
    assert all(answer["turn_id"] not in json.loads(f["span_turn_ids_json"])
               for f in facts if f["field"] in ("chief_complaint", "current_medications"))
    assert res["handoff_reason"] == "nurse_attention_phrase"
    assert _tree(*guarded) == before
