"""Comparators (slice e1): always-answer fallback and the S1r lexical shortcut. Research prototype.

- Always-answer: S4 ``baseline.rank`` on the same gateway inputs with no abstain gate (computed in
  ``triage.py``); an empty ranking falls back to the train-split majority E code, from train gold only.
- Lexical shortcut (S1r scope 4a semantics): V = every substring of length 1-30 of each T1 patient turn (NFC),
  plus whitespace tokens and every S1r registry lexicon term. ``s`` predicts positive when it occurs in any
  patient turn. s* maximises F1 for "any text red flag at T1" on the train split only; ties go to the shorter
  substring, then lexicographic order. The fixed rule ``contains("ทันที")`` is also reported.
  This module does not import ``data_factory.generate``; the lexicon is read from the registry JSON.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from . import gold as G
from . import mapping
from .inputs import load_split, patient_turn_texts

TAMTEE = "ทันที"
MAX_LEN = 30
REGISTRY_RED_FLAGS = Path(__file__).resolve().parents[2] / "data_factory" / "templates" / "red_flags.json"


def registry_lexicon(path: Path = REGISTRY_RED_FLAGS) -> list[str]:
    terms: set[str] = set()

    def walk(c: Any) -> None:
        if isinstance(c, dict):
            if c.get("kind") == "transcript":
                for group in c["all_of"]:
                    terms.update(mapping.nfc(x) for x in group)
            for v in c.values():
                walk(v)
        elif isinstance(c, list):
            for v in c:
                walk(v)

    for rule in json.loads(Path(path).read_text(encoding="utf-8")):
        walk(rule["criterion"])
    return sorted(terms)


def _f1(pred: set[str], pos: set[str]) -> tuple[float, float, float]:
    tp = len(pred & pos)
    if not tp:
        return 0.0, 0.0, 0.0
    p, r = tp / len(pred), tp / len(pos)
    return 2 * p * r / (p + r), p, r


def text_positive_t1(g: dict[str, Any]) -> bool:
    t1 = next(d for d in g["decision_times"] if d["decision_point"] == "T1")
    return any(f["rule_id"] in mapping.TEXT_RULES_S1R for f in t1["red_flags"])


def select_shortcut(dataset: Path) -> dict[str, Any]:
    """Choose s* on the train split only (inputs: train T1 snapshots; labels: train gold)."""
    turns = {c.case_id: patient_turn_texts(c.snapshots["T1"]) for c in load_split(dataset, "train")}
    occ: dict[str, set[str]] = {}
    for cid, ts in turns.items():
        for s in {x[i:j] for x in ts for i in range(len(x)) for j in range(i + 1, min(i + MAX_LEN, len(x)) + 1)}:
            occ.setdefault(s, set()).add(cid)
    extra = {w for ts in turns.values() for x in ts for w in x.split()} | set(registry_lexicon())
    for w in sorted(extra - set(occ)):
        occ[w] = {cid for cid, ts in turns.items() if any(w in x for x in ts)}
    gold = G.load_split_gold(dataset, "train")
    pos = {cid for cid, g in gold.items() if text_positive_t1(g)}
    if set(gold) != set(turns):
        raise ValueError("train inputs and train gold cover different cases")
    best = min(occ, key=lambda s: (-_f1(occ[s], pos)[0], len(s), s))
    f1, p, r = _f1(occ[best], pos)
    tf1, tp_, tr = _f1(occ.get(TAMTEE, set()), pos)
    return {
        "s_star": best,
        "train": {"f1": f1, "precision": p, "recall": r, "support": len(occ[best]), "n_positive": len(pos),
                  "n_cases": len(turns), "n_candidates": len(occ)},
        "tamtee_train": {"f1": tf1, "precision": tp_, "recall": tr, "support": len(occ.get(TAMTEE, set()))},
        "rule": "V = substrings (1-30 chars) of T1 patient turns + whitespace tokens + registry lexicon; "
                "max F1 on train for any text red flag at T1; ties: shorter, then lexicographic",
    }


def occurs(s: str, snap: dict[str, Any]) -> bool:
    return any(s in x for x in patient_turn_texts(snap))


def train_majority_e(dataset: Path) -> dict[str, Any]:
    """Train-split majority E code over department-population DPs (train gold only)."""
    c: Counter[str] = Counter()
    for g in G.load_split_gold(dataset, "train").values():
        for d in g["decision_times"]:
            e, _ = mapping.gold_department(d["target_department"], d["department_evaluable"])
            if e is not None:
                c[e] += 1
    code = min(c, key=lambda k: (-c[k], k))
    return {"code": code, "counts": dict(sorted(c.items())), "rule": "most frequent E code among train DPs "
            "with department_evaluable and a mappable gold; ties -> lexicographic"}


def always_answer(ranking_s4: list[str], fallback_e: str) -> list[str]:
    e = mapping.s4_to_e(ranking_s4)
    return e if e else [fallback_e]
