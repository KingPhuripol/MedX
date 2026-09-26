"""Record -> statistic adapters for the runner (slice s8). Research prototype - not for clinical use.

Each metric name maps to ``prepare(rows, params) -> Prepared``. ``Prepared.stat`` is evaluated
on row indices (so the patient-level bootstrap can recompute it), and reuses the per-row
helpers from ``eval.metrics`` so point estimates equal the pure functions.

Scored-record fields (one JSONL row per decision point; gold label + system output):

| metric | gold fields | prediction fields |
|---|---|---|
| accuracy, macro_f1 | y_true | y_pred |
| multilabel_macro_f1 | y_true (list) | y_pred (list) |
| auroc | y_true | y_score (float, or dict label->score) |
| dice | mask_true | mask_pred |
| hit_at_k, set_prf | ordered | suggested |
| calls_per_patient / latency_per_patient / cost_per_patient | - | n_calls / latency_s / cost |
| latency_summary / response_latency / total_time | - | latency_s / response_latency_s / total_time_s |
| field_prf | gold_fields | extracted_fields |
| topk_accuracy | y_true | ranked |
| per_issue_type_pr | population, gold | flagged |
| coverage, selective_accuracy (abstention-aware) | y_true | y_pred (null or absent = abstain) |

NaN / +-inf anywhere in a row or in params raises ``NonFiniteValueError`` (s8r); NaN is never abstain.
Rows imputed by the runner for a listed-but-missing patient (``imputed_missing: true``, ``y_pred: null``)
carry no gold label: they are abstentions and never enter the answered set.
| replay_determinism | original_hashes | replay_hashes |
| recomputed_nodes | n_nodes_full | n_recomputed |
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import metrics as M
from .bootstrap import RatioStat, Stat
from .metrics import MissingPredictionError, Undefined, check_finite

Row = Mapping[str, Any]


@dataclass
class Prepared:
    stat: Stat
    details: dict[str, Any] = field(default_factory=dict)


def _where(row: Row) -> str:
    return f"patient {row.get('patient_id')!r} decision point {row.get('decision_point_id')!r}"


def pred(rows: Sequence[Row], key: str, metric: str) -> list[Any]:
    out = []
    for r in rows:
        if r.get(key) is None:
            raise MissingPredictionError(
                f"{metric}: {_where(r)} has no prediction {key!r}; missing predictions are never dropped "
                "or treated as negative"
            )
        out.append(r[key])
    return out


def gold(rows: Sequence[Row], key: str, metric: str) -> list[Any]:
    out = []
    for r in rows:
        if key not in r or r[key] is None:
            raise ValueError(f"{metric}: {_where(r)} has no gold field {key!r}")
        out.append(r[key])
    return out


def _ones(n: int) -> np.ndarray:
    return np.ones(n, dtype=float)


def _first_row_of_patient(rows: Sequence[Row]) -> np.ndarray:
    seen: set[Any] = set()
    out = np.zeros(len(rows), dtype=float)
    for i, r in enumerate(rows):
        if r["patient_id"] not in seen:
            seen.add(r["patient_id"])
            out[i] = 1.0
    return out


def _component(params: Mapping[str, Any], allowed: Sequence[str], default: str | None = None) -> str:
    c = params.get("component", default)
    if c not in allowed:
        raise ValueError(f"component must be one of {list(allowed)}, got {c!r}")
    return c


# ---------------------------------------------------------------- adapters


def _accuracy(rows, params):
    t, p = gold(rows, "y_true", "accuracy"), pred(rows, "y_pred", "accuracy")
    return Prepared(RatioStat(np.array([a == b for a, b in zip(t, p)], float), _ones(len(rows)), "no decision points"))


def _macro_f1(rows, params):
    labels = list(params["labels"])
    t = M._codes(gold(rows, "y_true", "macro_f1"), labels)
    p = M._codes(pred(rows, "y_pred", "macro_f1"), labels)
    return Prepared(lambda idx: M._macro_f1_codes(t[idx], p[idx], len(labels)), {"labels": labels})


def _multilabel_macro_f1(rows, params):
    labels = list(params["labels"])
    T = M._indicator(gold(rows, "y_true", "multilabel_macro_f1"), labels, "y_true")
    P = M._indicator(pred(rows, "y_pred", "multilabel_macro_f1"), labels, "y_pred")
    return Prepared(lambda idx: M._ml_f1(T[idx], P[idx]), {"labels": labels})


def _auroc(rows, params):
    mode = params.get("mode", "binary")
    y_true = gold(rows, "y_true", "auroc")
    y_score = pred(rows, "y_score", "auroc")
    if mode == "binary":
        pos = params.get("pos_label", 1)
        y = np.array([v == pos for v in y_true], dtype=bool)
        s = np.asarray(y_score, dtype=float)
        return Prepared(lambda idx: M._binary_auc(y[idx], s[idx]), {"mode": mode, "pos_label": pos})
    labels = list(params["labels"])
    S = M._score_matrix(y_score, labels)
    if mode == "multiclass":
        Y = M._codes(y_true, labels)[:, None] == np.arange(len(labels))[None, :]
    elif mode == "multilabel":
        Y = M._indicator(y_true, labels, "y_true")
    else:
        raise ValueError(f"auroc: unknown mode {mode!r}")
    return Prepared(lambda idx: M._macro_auc(Y[idx], S[idx], labels), {"mode": mode, "labels": labels})


def _dice(rows, params):
    ee = float(params.get("empty_empty", 1.0))
    summ = M.dice_summary(gold(rows, "mask_true", "dice"), pred(rows, "mask_pred", "dice"), ee)
    return Prepared(
        RatioStat(np.asarray(summ["per_case"], float), _ones(len(rows)), "no cases"),
        {"empty_empty_value": ee, "n_empty_empty": summ["n_empty_empty"]},
    )


def _hit_at_k(rows, params):
    k = int(params["k"])
    s, o = pred(rows, "suggested", "hit_at_k"), gold(rows, "ordered", "hit_at_k")
    hits = np.array([M._hit(a, b, k) for a, b in zip(s, o)], float)
    return Prepared(RatioStat(hits, _ones(len(rows)), "no decision points"), {"k": k})


def _set_prf(rows, params):
    comp = _component(params, ("precision", "recall", "f1"))
    s, o = pred(rows, "suggested", "set_prf"), gold(rows, "ordered", "set_prf")
    c = np.array([M._set_counts(a, b) for a, b in zip(s, o)], float).reshape(len(rows), 3)
    tp, ns, no = c[:, 0], c[:, 1], c[:, 2]
    num, den = {"precision": (tp, ns), "recall": (tp, no), "f1": (2 * tp, ns + no)}[comp]
    return Prepared(RatioStat(num, den, f"{comp} denominator is 0"), {"component": comp})


def _per_patient(key: str, metric: str):
    def prep(rows, params):
        v = np.asarray(pred(rows, key, metric), dtype=float)
        return Prepared(RatioStat(v, _first_row_of_patient(rows), "no patients"), {"field": key})

    return prep


def _latency(default_field: str, metric: str):
    def prep(rows, params):
        fld = params.get("field", default_field)
        stat = _component(params, ("mean", "median", "p90"), params.get("stat", "mean"))
        v = np.asarray(pred(rows, fld, metric), dtype=float)
        details = {"field": fld, "component": stat, "percentile_method": "linear"}
        if stat == "mean":
            return Prepared(RatioStat(v, _ones(len(rows)), "no measurements"), details)
        q = 50.0 if stat == "median" else 90.0

        def pct(idx):
            return Undefined("no measurements") if idx.size == 0 else float(np.percentile(v[idx], q, method="linear"))

        return Prepared(pct, details)

    return prep


def _field_prf(rows, params):
    comp = _component(params, ("precision", "recall", "f1"))
    g = gold(rows, "gold_fields", "field_prf")
    e = pred(rows, "extracted_fields", "field_prf")
    fields = params.get("fields") or sorted({k for d in g + e for k in d})
    only = params.get("field")
    use = [only] if only else list(fields)
    c = np.zeros((len(rows), 3))
    for i, (a, b) in enumerate(zip(g, e)):
        for f, cnt in M._field_counts(a, b, use).items():
            c[i] += cnt
    tp, fp, fn = c[:, 0], c[:, 1], c[:, 2]
    num, den = {"precision": (tp, tp + fp), "recall": (tp, tp + fn), "f1": (2 * tp, 2 * tp + fp + fn)}[comp]
    return Prepared(
        RatioStat(num, den, f"{comp} denominator is 0"),
        {"component": comp, "scope": f"field:{only}" if only else "micro", "fields": list(fields),
         "normalization": "casefold + strip + collapse whitespace"},
    )


def _topk(rows, params):
    k = int(params["k"])
    t, r = gold(rows, "y_true", "topk_accuracy"), pred(rows, "ranked", "topk_accuracy")
    return Prepared(RatioStat(np.array([a in list(b)[:k] for a, b in zip(t, r)], float), _ones(len(rows)),
                              "no decision points"), {"k": k})


def _pharma(rows, params):
    t = params["issue_type"]
    comp = _component(params, ("precision", "recall", "f1"))
    rpop = params.get("recall_population", "synthetic_error_injection")
    ppop = params.get("precision_population", "pharmacist_review")
    pops = gold(rows, "population", "per_issue_type_pr")
    bad = sorted({p for p in pops if p not in (rpop, ppop)})
    if bad:
        raise ValueError(f"per_issue_type_pr: undeclared population(s) {bad}; rows are never silently dropped")
    g, f = gold(rows, "gold", "per_issue_type_pr"), pred(rows, "flagged", "per_issue_type_pr")
    tp = np.zeros(len(rows))
    ng = np.zeros(len(rows))
    nf = np.zeros(len(rows))
    for i, (a, b) in enumerate(zip(g, f)):
        ka, kb = M._issue_keys(a, t), M._issue_keys(b, t)
        tp[i], ng[i], nf[i] = len(ka & kb), len(ka), len(kb)
    in_r = np.array([p == rpop for p in pops], float)
    in_p = np.array([p == ppop for p in pops], float)
    details = {"issue_type": t, "component": comp}
    if comp == "recall":
        details["source"] = rpop
        return Prepared(RatioStat(tp * in_r, ng * in_r, f"no {t} issues in the {rpop} population"), details)
    if comp == "precision":
        details["source"] = ppop
        return Prepared(RatioStat(tp * in_p, nf * in_p, f"no {t} issues flagged in the {ppop} population"), details)
    if rpop != ppop:
        details["source"] = f"{ppop} (precision) / {rpop} (recall)"
        reason = f"precision ({ppop}) and recall ({rpop}) come from different populations; F1 is not reported"
        return Prepared(lambda idx: Undefined(reason), details)
    details["source"] = rpop
    return Prepared(RatioStat(2 * tp * in_r, (ng + nf) * in_r, "F1 denominator is 0"), details)


def _answered(rows) -> np.ndarray:
    return np.array([r.get("y_pred") is not None for r in rows], float)


def _coverage(rows, params):
    return Prepared(RatioStat(_answered(rows), _ones(len(rows)), "no decision points"),
                    {"abstain": "y_pred null or absent"})


def _selective_accuracy(rows, params):
    # Gold is required on every row except runner-imputed abstentions (which are never answered).
    for r in rows:
        if r.get("imputed_missing") and r.get("y_pred") is not None:
            raise ValueError(f"selective_accuracy: {_where(r)} is imputed as missing but has a prediction")
    gold([r for r in rows if not r.get("imputed_missing")], "y_true", "selective_accuracy")
    ans = _answered(rows)
    correct = np.array([r.get("y_pred") is not None and r["y_pred"] == r["y_true"] for r in rows], float)
    return Prepared(RatioStat(correct, ans, "coverage is 0; selective accuracy is undefined"),
                    {"abstain": "y_pred null or absent"})


def _replay(rows, params):
    comp = _component(params, ("graph_fraction", "node_fraction"))
    o = gold(rows, "original_hashes", "replay_determinism")
    r = pred(rows, "replay_hashes", "replay_determinism")
    c = np.array([M._replay_counts(a, b) for a, b in zip(o, r)], float).reshape(len(rows), 3)
    if comp == "graph_fraction":
        return Prepared(RatioStat(c[:, 0], _ones(len(rows)), "no graphs"), {"component": comp})
    return Prepared(RatioStat(c[:, 1], c[:, 2], "no nodes"), {"component": comp})


def _recomputed(rows, params):
    comp = _component(params, ("mean_recomputed", "median_recomputed", "mean_full", "median_full", "ratio"))
    r = np.asarray(pred(rows, "n_recomputed", "recomputed_nodes"), float)
    f = np.asarray(gold(rows, "n_nodes_full", "recomputed_nodes"), float)
    d = {"component": comp}
    if comp == "mean_recomputed":
        return Prepared(RatioStat(r, _ones(len(rows)), "no regenerations"), d)
    if comp == "mean_full":
        return Prepared(RatioStat(f, _ones(len(rows)), "no regenerations"), d)
    if comp == "ratio":
        return Prepared(RatioStat(r, f, "full-graph node count is 0"), d)
    v = r if comp == "median_recomputed" else f
    return Prepared(lambda idx: Undefined("no regenerations") if idx.size == 0 else float(np.median(v[idx])), d)


def _finite_guard(name: str, fn: Callable[[Sequence[Row], Mapping[str, Any]], Prepared]):
    def adapter(rows: Sequence[Row], params: Mapping[str, Any]) -> Prepared:
        check_finite(params, f"{name} params")
        for r in rows:
            check_finite(r, f"{name}: {_where(r)}")
        return fn(rows, params)

    adapter.__name__ = adapter.__qualname__ = f"{name}_adapter"
    return adapter


_ADAPTERS: dict[str, Callable[[Sequence[Row], Mapping[str, Any]], Prepared]] = {
    "accuracy": _accuracy,
    "macro_f1": _macro_f1,
    "multilabel_macro_f1": _multilabel_macro_f1,
    "auroc": _auroc,
    "dice": _dice,
    "hit_at_k": _hit_at_k,
    "set_prf": _set_prf,
    "calls_per_patient": _per_patient("n_calls", "calls_per_patient"),
    "latency_per_patient": _per_patient("latency_s", "latency_per_patient"),
    "cost_per_patient": _per_patient("cost", "cost_per_patient"),
    "latency_summary": _latency("latency_s", "latency_summary"),
    "response_latency": _latency("response_latency_s", "response_latency"),
    "total_time": _latency("total_time_s", "total_time"),
    "field_prf": _field_prf,
    "topk_accuracy": _topk,
    "per_issue_type_pr": _pharma,
    "coverage": _coverage,
    "selective_accuracy": _selective_accuracy,
    "replay_determinism": _replay,
    "recomputed_nodes": _recomputed,
}

REGISTRY: dict[str, Callable[[Sequence[Row], Mapping[str, Any]], Prepared]] = {
    k: _finite_guard(k, v) for k, v in _ADAPTERS.items()
}

ABSTENTION_AWARE = frozenset({"coverage", "selective_accuracy"})


def prepare(name: str, rows: Sequence[Row], params: Mapping[str, Any]) -> Prepared:
    if name not in REGISTRY:
        raise ValueError(f"unknown metric {name!r}")
    return REGISTRY[name](rows, params or {})


def population_for(name: str, params: Mapping[str, Any]) -> tuple[str | None, set[str]]:
    """(population the metric is computed on, all declared populations) for population-specific metrics.

    Pharma precision and recall come from different populations; each is bootstrapped over its own
    patients so ``n_patients`` / ``n_decision_points`` are the true denominators.
    """
    if name != "per_issue_type_pr":
        return None, set()
    rpop = params.get("recall_population", "synthetic_error_injection")
    ppop = params.get("precision_population", "pharmacist_review")
    comp = params.get("component")
    pop = {"recall": rpop, "precision": ppop}.get(comp, rpop if rpop == ppop else None)
    return pop, {rpop, ppop}
