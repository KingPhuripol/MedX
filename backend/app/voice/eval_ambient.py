"""System evaluation of ambient intake (slice v2a) on the 15 synthetic ambient fixtures (mock rules, gateway).

Run: ``make eval-voice-ambient`` -> ``slices/v2a/eval/ambient_intake_eval.json``. Reuses the S3 scorer
(field_counts, prf, 2,000-resample dialogue-level bootstrap, seed 0). NOT clinical performance: mock rules,
hand-converted synthetic text dialogues, no audio or ASR, n=15.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..config import Settings
from ..db import create_schema, make_engine
from ..deps import CurrentUser
from ..gateway import build_provider
from ..roles import Role
from .db import create_voice_schema, voice_turns
from .eval import FIXTURE_DIR, N_BOOT, REPO_ROOT, SEED, _percentile, bootstrap_ci, field_counts, final_predictions, prf
from .mock_rules import EXTRACTOR_VERSION
from .models import ASK_ORDER, FACT_FIELDS
from .service import VoiceContext
from .simulate import SimRun, simulate_ambient

AMBIENT_DIR = FIXTURE_DIR / "ambient"
OUT_PATH = REPO_ROOT / "slices" / "v2a" / "eval" / "ambient_intake_eval.json"
LABEL = "system evaluation — mock rules, synthetic ambient text dialogues (no audio/ASR), not clinical performance"
GATED_FIELDS = ("chief_complaint", "onset_duration", "severity", "allergy_status", "allergens", "current_medications")
SOURCE_FILES = ("mock_rules.py", "policy.py", "service.py", "simulate.py", "eval.py", "eval_ambient.py", "models.py",
                "intent_th.py", "utterances_th.py")


def load_fixtures() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(AMBIENT_DIR.glob("th_ambient_*.json"))]


def inputs_sha256() -> str:
    h = hashlib.sha256()
    for p in sorted(AMBIENT_DIR.glob("th_ambient_*.json")):
        h.update(p.read_bytes())
    for name in SOURCE_FILES:
        h.update((Path(__file__).parent / name).read_bytes())
    return h.hexdigest()


def expected_final(fx: dict) -> dict[str, Any]:
    """Gold final action: handoff on attention; complete iff gold covers every ASK_ORDER field; else prompt the
    first gold-missing field."""
    if fx["gold_nurse_attention"]:
        return {"kind": "handoff", "field": None}
    covered = {g["field"] for g in fx["gold_facts"]}
    missing = [f for f in ASK_ORDER if f not in covered]
    return {"kind": "prompt_nurse", "field": missing[0]} if missing else {"kind": "complete", "field": None}


def _micro(rows: list[dict], fields: tuple[str, ...]) -> dict:
    per = [tuple(sum(r["counts"][f][i] for f in fields) for i in range(3)) for r in rows]
    tot = tuple(sum(x[i] for x in per) for i in range(3))
    return prf(*tot) | {"ci95": bootstrap_ci(per)}


def _summarise(rows: list[dict]) -> dict:
    out: dict[str, Any] = {}
    for field in FACT_FIELDS:
        per = [r["counts"][field] for r in rows]
        out[field] = prf(*(sum(x[i] for x in per) for i in range(3))) | {"ci95": bootstrap_ci(per)}
    out["micro_gated"] = _micro(rows, GATED_FIELDS)
    out["micro_overall"] = _micro(rows, FACT_FIELDS)
    return out


def _classifier(rows: list[dict]) -> dict:
    q = [t for r in rows for t in r["turns"] if t["gold"]]
    answers = [t for r in rows for t in r["turns"] if not t["gold"]]
    correct = sum(1 for t in q if t["pred"] == t["gold"])
    confusion: dict[str, dict[str, int]] = {}
    for t in q + answers:
        row = confusion.setdefault(t["gold"] or "answer", {})
        row[t["pred"] or "none"] = row.get(t["pred"] or "none", 0) + 1
    return {
        "n_question_turns": len(q), "correct_field": correct,
        "wrong_field": sum(1 for t in q if t["pred"] and t["pred"] != t["gold"]),
        "missed": sum(1 for t in q if not t["pred"]),
        "correct_field_rate": round(correct / len(q), 4) if q else "n/a",
        "n_answer_turns": len(answers), "answer_turns_flagged": sum(1 for t in answers if t["pred"]),
        "confusion": confusion,
    }


def run_eval() -> dict:
    fixtures = load_fixtures()
    with tempfile.TemporaryDirectory() as tmp:
        engine = make_engine(f"sqlite:///{Path(tmp) / 'eval.db'}")
        create_schema(engine)
        create_voice_schema(engine)
        ctx = VoiceContext(engine=engine, provider=build_provider("mock", Settings()),
                           actor=CurrentUser(id=0, username="eval-nurse", role=Role.NURSE), request_id="eval-ambient")
        runs: list[SimRun] = [simulate_ambient(ctx, fx) for fx in fixtures]
        with engine.connect() as conn:
            stored = {r.turn_id: r for r in conn.execute(select(voice_turns))}
        engine.dispose()

    rows, latencies = [], []
    allergy_false_none = attention_on_questions = 0
    for fx, run in zip(fixtures, runs):
        gold = {g["field"]: g for g in fx["gold_facts"]}
        pred = final_predictions(run)
        final = run.decisions[-1]["action"]
        exp = expected_final(fx)
        turns = [{"turn_id": ftid, "gold": fx["gold_question_turns"].get(ftid), "pred": stored[sid].field}
                 for ftid, sid in run.turn_map.items()]
        attention_on_questions += sum(1 for ftid, sid in run.turn_map.items()
                                      if stored[sid].field and stored[sid].nurse_attention)
        rows.append({
            "dialogue_id": fx["dialogue_id"], "heldout": "heldout" in fx["scenario_tags"],
            "counts": {f: field_counts(gold.get(f), pred.get(f), f) for f in FACT_FIELDS},
            "handoff_reason": run.finish["handoff_reason"], "missing_fields": run.finish["missing_fields"],
            "final_action": {"kind": final["kind"], "field": final["field"]}, "expected_final": exp,
            "final_match": final["kind"] == exp["kind"] and final["field"] == exp["field"], "turns": turns,
        })
        latencies += run.latencies_ms
        g, p = gold.get("allergy_status"), pred.get("allergy_status")
        gold_none = bool(g and g["state"] == "KNOWN" and g["value"] == "none")
        if p and p["state"] == "KNOWN" and p["value"] == "none" and not gold_none:
            allergy_false_none += 1

    lat = sorted(latencies)
    split_rows = {"dev": [r for r in rows if not r["heldout"]], "heldout": [r for r in rows if r["heldout"]]}
    return {
        "label": LABEL,
        "slice": "v2a",
        "mode": "ambient",
        "provider": "mock",
        "extractor": EXTRACTOR_VERSION,
        "inputs_sha256": inputs_sha256(),
        "n_dialogues": len(rows),
        "bootstrap": {"resamples": N_BOOT, "seed": SEED, "unit": "dialogue (patient)", "method": "percentile"},
        "gated_fields": list(GATED_FIELDS),
        "splits": {k: _summarise(v) for k, v in split_rows.items()},
        "allergy_false_none": allergy_false_none,
        "classifier": {k: _classifier(v) for k, v in split_rows.items()},
        "final_action": {k: {"n": len(v), "matched": sum(r["final_match"] for r in v)} for k, v in split_rows.items()},
        "attention_on_question_turns": attention_on_questions,
        "latency_ms": {
            "n_turns": len(lat),
            "p50": round(_percentile(lat, 0.50), 3),
            "p95": round(_percentile(lat, 0.95), 3),
            "scope": "per-turn processing, mock provider in process, local",
        },
        "per_dialogue": [
            {k: r[k] for k in ("dialogue_id", "heldout", "handoff_reason", "missing_fields", "final_action",
                               "expected_final", "final_match")}
            | {"counts": {f: list(c) for f, c in r["counts"].items()},
               "question_turns": {t["turn_id"]: {"gold": t["gold"], "pred": t["pred"]} for t in r["turns"]
                                  if t["gold"] or t["pred"]}}
            for r in rows
        ],
        "notes": "Fixtures, classifier and rules share one author. The held-out question wordings were committed "
                 "before intent_th.py existed, but by the same author, so the held-out split is not independent "
                 "evidence. Held-out results were not used to change rules. Text only: no audio, no ASR errors, "
                 "no diarization errors beyond the unknown speaker. A nurse statement (not a question) is extracted "
                 "like a patient statement; v2d nurse review is the control. With n=15 the CIs are wide by design.",
    }


def main() -> None:
    result = run_eval()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{LABEL}\nwrote {OUT_PATH.relative_to(REPO_ROOT)}")
    for split, block in result["splits"].items():
        g, o = block["micro_gated"], block["micro_overall"]
        c, fa = result["classifier"][split], result["final_action"][split]
        print(f"  {split:8s} gated F1={g['f1']} CI={g['ci95']['f1']} overall F1={o['f1']} "
              f"classifier {c['correct_field']}/{c['n_question_turns']} answers_flagged={c['answer_turns_flagged']} "
              f"final {fa['matched']}/{fa['n']}")
    print(f"  allergy_false_none={result['allergy_false_none']}  latency p50={result['latency_ms']['p50']}ms "
          f"p95={result['latency_ms']['p95']}ms  n_turns={result['latency_ms']['n_turns']}")


if __name__ == "__main__":
    sys.exit(main())
