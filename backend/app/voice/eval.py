"""System evaluation of the Voice Agent on the 15 synthetic Thai fixtures (mock rules via the gateway).

Run: ``make eval-voice`` -> ``slices/s3/eval/voice_intake_eval.json``.
Field-level micro P/R/F1 with a 95% percentile bootstrap CI (2,000 dialogue-level resamples, seed 0),
dev vs held-out breakdown, per-turn latency p50/p95 and the allergy-safety count (S3-A02).
NOT clinical performance: mock rules, hand-written synthetic dialogues, n=15.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
import tempfile
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db import create_schema, make_engine
from ..deps import CurrentUser
from ..gateway import build_provider
from ..roles import Role
from .db import create_voice_schema
from .mock_rules import EXTRACTOR_VERSION
from .models import FACT_FIELDS, LIST_FIELDS
from .service import VoiceContext
from .simulate import SimRun, simulate

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "voice" / "fixtures"
OUT_PATH = REPO_ROOT / "slices" / "s3" / "eval" / "voice_intake_eval.json"
LABEL = "system evaluation — mock rules, synthetic dialogues, not clinical performance"
N_BOOT = 2000
SEED = 0
SOURCE_FILES = ("mock_rules.py", "policy.py", "service.py", "simulate.py", "eval.py", "models.py")

# Local Thai/English alias table used only for set matching of list items.
ALIASES = {
    "พารา": "paracetamol", "พาราเซตามอล": "paracetamol", "paracetamol": "paracetamol",
    "เมทฟอร์มิน": "metformin", "ไอบูโพรเฟน": "ibuprofen", "แอสไพริน": "aspirin",
    "เพนิซิลลิน": "penicillin", "เพนนิซิลิน": "penicillin", "อะม็อกซีซิลลิน": "amoxicillin",
    "อะม็อกซี่": "amoxicillin", "ซัลฟา": "sulfa", "แอมโลดิปีน": "amlodipine", "โลซาร์แทน": "losartan",
    "ความดันโลหิตสูง": "ความดันสูง",
}


def load_fixtures() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURE_DIR.glob("th_intake_*.json"))]


def inputs_sha256() -> str:
    h = hashlib.sha256()
    for p in sorted(FIXTURE_DIR.glob("th_intake_*.json")):
        h.update(p.read_bytes())
    for name in SOURCE_FILES:
        h.update((Path(__file__).parent / name).read_bytes())
    return h.hexdigest()


def _norm_item(item: str) -> str:
    key = item.strip().casefold()
    return ALIASES.get(key, key)


def _norm_scalar(value: Any) -> str:
    return str(value).strip().casefold()


def _as_set(state: str, value: Any, items: Any) -> set[str]:
    if state != "KNOWN":
        return {f"<{state}>"}
    seq = items if items is not None else value
    return {_norm_item(i) for i in seq} or {"none"}


def field_counts(gold: dict | None, pred: dict | None, field: str) -> tuple[int, int, int]:
    """(TP, FP, FN) for one field in one dialogue. MISSING prediction = no prediction."""
    if field in LIST_FIELDS:
        g = _as_set(gold["state"], gold.get("value"), gold.get("items")) if gold else set()
        p = _as_set(pred["state"], pred.get("value"), None) if pred else set()
        return len(g & p), len(p - g), len(g - p)
    if gold and pred:
        same = gold["state"] == pred["state"] and (
            gold["state"] != "KNOWN" or _norm_scalar(gold["value"]) == _norm_scalar(pred["value"])
        )
        return (1, 0, 0) if same else (0, 1, 1)
    if pred:
        return 0, 1, 0
    if gold:
        return 0, 0, 1
    return 0, 0, 0


def prf(tp: int, fp: int, fn: int) -> dict[str, Any]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = None if p is None or r is None else (2 * p * r / (p + r) if p + r > 0 else 0.0)
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(p, 4) if p is not None else "n/a",
        "recall": round(r, 4) if r is not None else "n/a",
        "f1": round(f1, 4) if f1 is not None else "n/a",
    }


def _percentile(sorted_vals: list[float], q: float) -> float:
    idx = min(len(sorted_vals) - 1, max(0, math.ceil(q * len(sorted_vals)) - 1))
    return sorted_vals[idx]


def bootstrap_ci(per_dialogue: list[tuple[int, int, int]], rng_seed: int = SEED, n_boot: int = N_BOOT) -> dict:
    rng = random.Random(rng_seed)
    n = len(per_dialogue)
    stats: dict[str, list[float]] = {"precision": [], "recall": [], "f1": []}
    for _ in range(n_boot):
        sample = [per_dialogue[rng.randrange(n)] for _ in range(n)]
        tp, fp, fn = (sum(x[i] for x in sample) for i in range(3))
        m = prf(tp, fp, fn)
        for k in stats:
            if m[k] != "n/a":
                stats[k].append(float(m[k]))
    out = {}
    for k, vals in stats.items():
        vals.sort()
        out[k] = [round(_percentile(vals, 0.025), 4), round(_percentile(vals, 0.975), 4)] if vals else "n/a"
    return out


def final_predictions(run: SimRun) -> dict[str, dict]:
    return {f["field"]: f for f in run.finish["facts"]}


def _summarise(rows: list[dict], fields: tuple[str, ...]) -> dict:
    out: dict[str, Any] = {}
    for field in fields:
        per = [r["counts"][field] for r in rows]
        tot = tuple(sum(x[i] for x in per) for i in range(3))
        out[field] = prf(*tot) | {"ci95": bootstrap_ci(per)}
    per_all = [tuple(sum(r["counts"][f][i] for f in fields) for i in range(3)) for r in rows]
    tot_all = tuple(sum(x[i] for x in per_all) for i in range(3))
    out["micro_overall"] = prf(*tot_all) | {"ci95": bootstrap_ci(per_all)}
    return out


def run_eval() -> dict:
    fixtures = load_fixtures()
    with tempfile.TemporaryDirectory() as tmp:
        engine = make_engine(f"sqlite:///{Path(tmp) / 'eval.db'}")
        create_schema(engine)
        create_voice_schema(engine)
        provider = build_provider("mock", Settings())
        actor = CurrentUser(id=0, username="eval-nurse", role=Role.NURSE)
        ctx = VoiceContext(engine=engine, provider=provider, actor=actor, request_id="eval-voice")
        runs = [simulate(ctx, fx) for fx in fixtures]
        engine.dispose()

    rows = []
    latencies: list[float] = []
    allergy_false_none = 0
    for fx, run in zip(fixtures, runs):
        gold = {g["field"]: g for g in fx["gold_facts"]}
        pred = final_predictions(run)
        counts = {f: field_counts(gold.get(f), pred.get(f), f) for f in FACT_FIELDS}
        rows.append({"dialogue_id": fx["dialogue_id"], "heldout": "heldout" in fx["scenario_tags"], "counts": counts,
                     "handoff_reason": run.finish["handoff_reason"], "missing_fields": run.finish["missing_fields"]})
        latencies += run.latencies_ms
        g, p = gold.get("allergy_status"), pred.get("allergy_status")
        gold_none = bool(g and g["state"] == "KNOWN" and g["value"] == "none")
        if p and p["state"] == "KNOWN" and p["value"] == "none" and not gold_none:
            allergy_false_none += 1

    lat = sorted(latencies)
    return {
        "label": LABEL,
        "slice": "s3",
        "provider": "mock",
        "extractor": EXTRACTOR_VERSION,
        "inputs_sha256": inputs_sha256(),
        "n_dialogues": len(rows),
        "bootstrap": {"resamples": N_BOOT, "seed": SEED, "unit": "dialogue (patient)", "method": "percentile"},
        "fields": _summarise(rows, FACT_FIELDS),
        "splits": {
            "dev": _summarise([r for r in rows if not r["heldout"]], FACT_FIELDS),
            "heldout": _summarise([r for r in rows if r["heldout"]], FACT_FIELDS),
        },
        "allergy_false_none": allergy_false_none,
        "latency_ms": {
            "n_turns": len(lat),
            "p50": round(_percentile(lat, 0.50), 3),
            "p95": round(_percentile(lat, 0.95), 3),
            "scope": "per-turn processing, mock provider in process",
        },
        "per_dialogue": [
            {"dialogue_id": r["dialogue_id"], "heldout": r["heldout"], "handoff_reason": r["handoff_reason"],
             "missing_fields": r["missing_fields"],
             "counts": {f: list(c) for f, c in r["counts"].items()}}
            for r in rows
        ],
        "notes": "Fixtures and rules share one author; the held-out split was committed before the rules "
                 "but is not independent evidence. With n=15 the CIs are wide by design. "
                 "allergy_false_none counts these 15 dialogues only and is not a general safety property; "
                 "hedge/question/non-answer/exception phrasing is covered by the phrase regressions in "
                 "backend/tests/voice/test_negative_safety.py and by the service allergy guard.",
    }


def main() -> None:
    result = run_eval()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    f = result["fields"]
    print(f"{LABEL}\nwrote {OUT_PATH.relative_to(REPO_ROOT)}")
    for name in (*FACT_FIELDS, "micro_overall"):
        print(f"  {name:22s} P={f[name]['precision']} R={f[name]['recall']} F1={f[name]['f1']} CI={f[name]['ci95']['f1']}")
    print(f"  allergy_false_none={result['allergy_false_none']}  latency p50={result['latency_ms']['p50']}ms "
          f"p95={result['latency_ms']['p95']}ms")


if __name__ == "__main__":
    sys.exit(main())
