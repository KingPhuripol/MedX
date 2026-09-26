"""Table 3.2 metrics (slice s8). Research prototype - not for clinical use.

Pure functions: arrays or records in, floats (or dicts of floats) out.

Conventions
- Metrics are computed on the pooled rows of the evaluated patients, never as an
  average of per-patient scores, unless the metric name says "per patient".
- An undefined value is returned as ``Undefined(reason)``; it is never coerced to 0 or 1.
  (Exception, declared by the spec: per-label F1 inside macro-F1 uses zero_division=0
  exactly as scikit-learn does.)
- A missing prediction (``None``) raises ``MissingPredictionError`` unless the metric is
  abstention-aware (``coverage``, ``selective_accuracy``), where it counts as abstain.
- NaN and +/-inf (Python or numpy floats, anywhere in any input) raise ``NonFiniteValueError``.
  A NaN is never treated as missing, abstain or negative (s8r).
"""

from __future__ import annotations

import functools
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = [
    "Undefined",
    "MissingPredictionError",
    "NonFiniteValueError",
    "check_finite",
    "is_undefined",
    "accuracy",
    "macro_f1",
    "multilabel_macro_f1",
    "auroc",
    "dice_case",
    "dice",
    "dice_summary",
    "hit_at_k",
    "set_prf",
    "calls_per_patient",
    "latency_per_patient",
    "cost_per_patient",
    "latency_summary",
    "response_latency",
    "total_time",
    "normalize_field_value",
    "field_prf",
    "topk_accuracy",
    "per_issue_type_pr",
    "coverage",
    "selective_accuracy",
    "replay_determinism",
    "recomputed_nodes",
]


@dataclass(frozen=True)
class Undefined:
    """A metric value that is mathematically undefined. Serialized as ``null`` + ``reason``."""

    reason: str


class MissingPredictionError(ValueError):
    """A prediction is missing. Missing predictions are never dropped or treated as negative."""


class NonFiniteValueError(ValueError):
    """A NaN or +/-inf value was found in an input. Corrupt values never become numbers or abstentions."""


def check_finite(obj: Any, what: str = "input") -> None:
    """Raise ``NonFiniteValueError`` if ``obj`` contains a NaN or +/-inf anywhere (recursively)."""
    if obj is None or isinstance(obj, (str, bytes, bool, int, Undefined)):
        return
    if isinstance(obj, (float, np.floating, complex, np.complexfloating)):
        if not np.isfinite(obj):
            raise NonFiniteValueError(f"{what}: non-finite value {obj!r}; NaN/inf is an error, never missing or 0")
        return
    if isinstance(obj, np.ndarray):
        if obj.dtype.kind in "fc":
            if not np.isfinite(obj).all():
                raise NonFiniteValueError(f"{what}: array contains NaN/inf; NaN/inf is an error, never missing or 0")
            return
        if obj.dtype.kind != "O":
            return
        for v in obj.ravel():
            check_finite(v, what)
        return
    if isinstance(obj, Mapping):
        for v in obj.values():
            check_finite(v, what)
        return
    if isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            check_finite(v, what)


def _finite_args(fn):
    """Decorator: every positional and keyword argument of a public metric is checked for NaN/inf."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        for i, a in enumerate(args):
            check_finite(a, f"{fn.__name__} argument {i}")
        for k, a in kwargs.items():
            check_finite(a, f"{fn.__name__} argument {k!r}")
        return fn(*args, **kwargs)

    return wrapper


def is_undefined(value: Any) -> bool:
    return isinstance(value, Undefined)


def _is_missing(v: Any) -> bool:
    """Missing means ``None`` (or an absent field) only. NaN is rejected earlier, never missing."""
    return v is None


def _require(values: Sequence[Any], what: str) -> None:
    for i, v in enumerate(values):
        if _is_missing(v):
            raise MissingPredictionError(
                f"{what}: missing value at index {i}; missing predictions are never dropped or treated as negative"
            )


def _same_len(a: Sequence[Any], b: Sequence[Any], what: str) -> None:
    if len(a) != len(b):
        raise ValueError(f"{what}: length mismatch ({len(a)} vs {len(b)})")


def _ratio(num: float, den: float, reason: str) -> float | Undefined:
    return Undefined(reason) if den == 0 else float(num) / float(den)


# ---------------------------------------------------------------- classification


@_finite_args
def accuracy(y_true: Sequence[Hashable], y_pred: Sequence[Hashable]) -> float | Undefined:
    _same_len(y_true, y_pred, "accuracy")
    _require(y_true, "accuracy y_true")
    _require(y_pred, "accuracy y_pred")
    if not y_true:
        return Undefined("no decision points")
    return float(np.mean([t == p for t, p in zip(y_true, y_pred)]))


def _codes(values: Sequence[Hashable], labels: Sequence[Hashable]) -> np.ndarray:
    index = {lab: i for i, lab in enumerate(labels)}
    return np.fromiter((index.get(v, -1) for v in values), dtype=np.int64, count=len(values))


def _macro_f1_codes(t: np.ndarray, p: np.ndarray, n_labels: int) -> float | Undefined:
    """Per-label F1 = 2TP / (|pred| + |true|), zero_division=0, then unweighted mean."""
    if t.size == 0:
        return Undefined("no decision points")
    vt, vp = t >= 0, p >= 0
    tp = np.bincount(t[(t == p) & vt], minlength=n_labels)
    denom = np.bincount(t[vt], minlength=n_labels) + np.bincount(p[vp], minlength=n_labels)
    f1 = np.where(denom > 0, 2.0 * tp / np.maximum(denom, 1), 0.0)
    return float(f1.mean())


@_finite_args
def macro_f1(y_true: Sequence[Hashable], y_pred: Sequence[Hashable], labels: Sequence[Hashable]) -> float | Undefined:
    """Macro-F1 over the declared ``labels`` (zero_division=0, as sklearn ``f1_score(average="macro")``)."""
    labels = list(labels)
    if not labels:
        raise ValueError("macro_f1: labels must be declared")
    _same_len(y_true, y_pred, "macro_f1")
    _require(y_true, "macro_f1 y_true")
    _require(y_pred, "macro_f1 y_pred")
    return _macro_f1_codes(_codes(y_true, labels), _codes(y_pred, labels), len(labels))


def _indicator(sets: Sequence[Iterable[Hashable] | None], labels: Sequence[Hashable], what: str) -> np.ndarray:
    _require(sets, what)
    index = {lab: i for i, lab in enumerate(labels)}
    out = np.zeros((len(sets), len(labels)), dtype=bool)
    for r, s in enumerate(sets):
        for v in s:
            j = index.get(v)
            if j is not None:
                out[r, j] = True
    return out


def _ml_f1(T: np.ndarray, P: np.ndarray) -> float | Undefined:
    if T.shape[0] == 0:
        return Undefined("no decision points")
    tp = (T & P).sum(axis=0)
    denom = T.sum(axis=0) + P.sum(axis=0)
    f1 = np.where(denom > 0, 2.0 * tp / np.maximum(denom, 1), 0.0)
    return float(f1.mean())


@_finite_args
def multilabel_macro_f1(
    y_true: Sequence[Iterable[Hashable]], y_pred: Sequence[Iterable[Hashable]], labels: Sequence[Hashable]
) -> float | Undefined:
    """Macro-F1 for report-derived finding labels (sets of labels per decision point)."""
    labels = list(labels)
    if not labels:
        raise ValueError("multilabel_macro_f1: labels must be declared")
    _same_len(y_true, y_pred, "multilabel_macro_f1")
    return _ml_f1(_indicator(y_true, labels, "y_true"), _indicator(y_pred, labels, "y_pred"))


def _avg_ranks(s: np.ndarray) -> np.ndarray:
    _, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    ends = np.cumsum(cnt).astype(float)
    return (ends - (cnt - 1) / 2.0)[inv.reshape(-1)]


def _binary_auc(y: np.ndarray, s: np.ndarray) -> float | Undefined:
    n_pos = int(y.sum())
    n_neg = int(y.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        return Undefined("only one class present in y_true; AUROC is undefined")
    ranks = _avg_ranks(s)
    return float((ranks[y].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _macro_auc(Y: np.ndarray, S: np.ndarray, labels: Sequence[Hashable]) -> float | Undefined:
    vals = []
    for j, lab in enumerate(labels):
        v = _binary_auc(Y[:, j], S[:, j])
        if isinstance(v, Undefined):
            return Undefined(f"AUROC undefined for label {lab!r}: {v.reason}")
        vals.append(v)
    return float(np.mean(vals))


def _score_matrix(y_score: Sequence[Any], labels: Sequence[Hashable]) -> np.ndarray:
    _require(y_score, "auroc y_score")
    rows = []
    for i, r in enumerate(y_score):
        if isinstance(r, Mapping):
            missing = [lab for lab in labels if _is_missing(r.get(lab))]
            if missing:
                raise MissingPredictionError(f"auroc y_score: row {i} has no score for {missing!r}")
            rows.append([float(r[lab]) for lab in labels])
        else:
            vals = [float(x) for x in r]
            if len(vals) != len(labels) or any(np.isnan(vals)):
                raise MissingPredictionError(f"auroc y_score: row {i} does not have {len(labels)} finite scores")
            rows.append(vals)
    return np.asarray(rows, dtype=float).reshape(len(rows), len(labels))


@_finite_args
def auroc(
    y_true: Sequence[Any],
    y_score: Sequence[Any],
    mode: str = "binary",
    labels: Sequence[Hashable] | None = None,
    pos_label: Hashable = 1,
) -> float | Undefined:
    """AUROC with average ranks for ties (Mann-Whitney).

    - ``binary``: ``y_true`` labels, positive = ``pos_label``; ``y_score`` floats.
    - ``multiclass``: one-vs-rest macro; ``y_true`` labels; ``y_score`` rows aligned with ``labels``
      (list) or dicts label -> score.
    - ``multilabel``: macro over labels; ``y_true`` sets of labels; ``y_score`` as multiclass.
    A single-class input returns ``Undefined`` (never 0.5).
    """
    _same_len(y_true, y_score, "auroc")
    if len(y_true) == 0:
        return Undefined("no decision points")
    if mode == "binary":
        _require(y_true, "auroc y_true")
        _require(y_score, "auroc y_score")
        y = np.fromiter((t == pos_label for t in y_true), dtype=bool, count=len(y_true))
        return _binary_auc(y, np.asarray(y_score, dtype=float))
    if not labels:
        raise ValueError(f"auroc({mode}): labels must be declared")
    labels = list(labels)
    S = _score_matrix(y_score, labels)
    if mode == "multiclass":
        _require(y_true, "auroc y_true")
        codes = _codes(y_true, labels)
        Y = codes[:, None] == np.arange(len(labels))[None, :]
    elif mode == "multilabel":
        Y = _indicator(y_true, labels, "auroc y_true")
    else:
        raise ValueError(f"auroc: unknown mode {mode!r}")
    return _macro_auc(Y, S, labels)


# ---------------------------------------------------------------- segmentation


@_finite_args
def dice_case(mask_true: Any, mask_pred: Any, empty_empty: float = 1.0) -> float:
    """Dice = 2|A∩B| / (|A|+|B|). Both masks empty -> the declared ``empty_empty`` value."""
    if mask_pred is None:
        raise MissingPredictionError("dice: missing predicted mask")
    a = np.asarray(mask_true, dtype=bool)
    b = np.asarray(mask_pred, dtype=bool)
    if a.shape != b.shape:
        raise ValueError(f"dice: shape mismatch {a.shape} vs {b.shape}")
    s = int(a.sum()) + int(b.sum())
    if s == 0:
        return float(empty_empty)
    return 2.0 * int((a & b).sum()) / s


@_finite_args
def dice_summary(masks_true: Sequence[Any], masks_pred: Sequence[Any], empty_empty: float = 1.0) -> dict[str, Any]:
    _same_len(masks_true, masks_pred, "dice")
    per_case = [dice_case(t, p, empty_empty) for t, p in zip(masks_true, masks_pred)]
    n_ee = sum(
        1 for t, p in zip(masks_true, masks_pred) if not np.asarray(t, bool).any() and not np.asarray(p, bool).any()
    )
    return {
        "value": float(np.mean(per_case)) if per_case else Undefined("no cases"),
        "per_case": per_case,
        "n_cases": len(per_case),
        "n_empty_empty": n_ee,
        "empty_empty_value": float(empty_empty),
    }


@_finite_args
def dice(masks_true: Sequence[Any], masks_pred: Sequence[Any], empty_empty: float = 1.0) -> float | Undefined:
    """Dice per case, then averaged over cases."""
    return dice_summary(masks_true, masks_pred, empty_empty)["value"]


# ---------------------------------------------------------------- Case Graph


def _hit(suggested: Sequence[Hashable], ordered: Iterable[Hashable], k: int) -> bool:
    ordered = set(ordered)
    if not ordered:
        raise ValueError(
            "hit_at_k: a decision point has no later-ordered tests; hit@k is undefined there. "
            "Exclude such decision points in the predeclared cohort definition, not here."
        )
    return bool(set(list(suggested)[:k]) & ordered)


@_finite_args
def hit_at_k(suggested: Sequence[Sequence[Hashable]], ordered: Sequence[Iterable[Hashable]], k: int) -> float | Undefined:
    """Fraction of decision points where any of the top-k suggested tests was later ordered."""
    _same_len(suggested, ordered, "hit_at_k")
    _require(suggested, "hit_at_k suggested")
    _require(ordered, "hit_at_k ordered")
    if not suggested:
        return Undefined("no decision points")
    return float(np.mean([_hit(s, o, k) for s, o in zip(suggested, ordered)]))


def _set_counts(suggested: Iterable[Hashable], ordered: Iterable[Hashable]) -> tuple[int, int, int]:
    s, o = set(suggested), set(ordered)
    return len(s & o), len(s), len(o)


@_finite_args
def set_prf(suggested: Sequence[Iterable[Hashable]], ordered: Sequence[Iterable[Hashable]]) -> dict[str, Any]:
    """Pooled (micro) precision/recall/F1 of suggested vs later-ordered tests."""
    _same_len(suggested, ordered, "set_prf")
    _require(suggested, "set_prf suggested")
    _require(ordered, "set_prf ordered")
    tp = ns = no = 0
    for s, o in zip(suggested, ordered):
        a, b, c = _set_counts(s, o)
        tp, ns, no = tp + a, ns + b, no + c
    return {
        "precision": _ratio(tp, ns, "no tests suggested (precision denominator is 0)"),
        "recall": _ratio(tp, no, "no tests ordered (recall denominator is 0)"),
        "f1": _ratio(2 * tp, ns + no, "no tests suggested or ordered (F1 denominator is 0)"),
    }


def _per_patient_mean(patient_ids: Sequence[Hashable], values: Sequence[float], what: str) -> float | Undefined:
    _same_len(patient_ids, values, what)
    _require(values, what)
    totals: dict[Hashable, float] = {}
    for pid, v in zip(patient_ids, values):
        totals[pid] = totals.get(pid, 0.0) + float(v)
    if not totals:
        return Undefined("no patients")
    return float(sum(totals.values()) / len(totals))


@_finite_args
def calls_per_patient(patient_ids: Sequence[Hashable], n_calls: Sequence[float]) -> float | Undefined:
    """Model calls summed over each patient's decision points, then mean over patients."""
    return _per_patient_mean(patient_ids, n_calls, "calls_per_patient")


@_finite_args
def latency_per_patient(patient_ids: Sequence[Hashable], latency_s: Sequence[float]) -> float | Undefined:
    """Latency summed over each patient's decision points, then mean over patients."""
    return _per_patient_mean(patient_ids, latency_s, "latency_per_patient")


@_finite_args
def cost_per_patient(patient_ids: Sequence[Hashable], costs: Sequence[float]) -> float | Undefined:
    """Cost summed over the patient's decision points, then mean over patients."""
    return _per_patient_mean(patient_ids, costs, "cost_per_patient")


@_finite_args
def latency_summary(values: Sequence[float]) -> dict[str, Any]:
    """Mean, median and p90 (numpy ``method="linear"``). Timeouts must be recorded, not dropped."""
    _require(values, "latency")
    if len(values) == 0:
        u = Undefined("no measurements")
        return {"mean": u, "median": u, "p90": u}
    v = np.asarray(values, dtype=float)
    return {
        "mean": float(v.mean()),
        "median": float(np.percentile(v, 50, method="linear")),
        "p90": float(np.percentile(v, 90, method="linear")),
    }


@_finite_args
def response_latency(values: Sequence[float]) -> dict[str, Any]:
    """Voice Agent response latency (seconds) summary."""
    return latency_summary(values)


@_finite_args
def total_time(values: Sequence[float]) -> dict[str, Any]:
    """Voice Agent total interaction time (seconds) summary."""
    return latency_summary(values)


# ---------------------------------------------------------------- Voice Agent fields


@_finite_args
def normalize_field_value(v: Any) -> str | None:
    """Casefold, strip and collapse whitespace. ``None``/empty -> no value."""
    if v is None:
        return None
    s = " ".join(str(v).split()).casefold()
    return s or None


def _field_counts(gold: Mapping[str, Any], extracted: Mapping[str, Any], fields: Iterable[str]) -> dict[str, list[int]]:
    """Per field [tp, fp, fn]. A wrong value counts as one FP and one FN."""
    out = {}
    for f in fields:
        g, e = normalize_field_value(gold.get(f)), normalize_field_value(extracted.get(f))
        tp = int(g is not None and e is not None and g == e)
        fp = int(e is not None and not tp)
        fn = int(g is not None and not tp)
        out[f] = [tp, fp, fn]
    return out


def _prf(tp: int, fp: int, fn: int) -> dict[str, Any]:
    return {
        "precision": _ratio(tp, tp + fp, "no values extracted (precision denominator is 0)"),
        "recall": _ratio(tp, tp + fn, "no gold values (recall denominator is 0)"),
        "f1": _ratio(2 * tp, 2 * tp + fp + fn, "no gold or extracted values (F1 denominator is 0)"),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


@_finite_args
def field_prf(
    gold_fields: Sequence[Mapping[str, Any]],
    extracted_fields: Sequence[Mapping[str, Any] | None],
    fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Exact match on normalized value per field; micro-averaged and per field."""
    _same_len(gold_fields, extracted_fields, "field_prf")
    _require(extracted_fields, "field_prf extracted_fields")
    if fields is None:
        fields = sorted({k for d in list(gold_fields) + list(extracted_fields) for k in d})
    totals = {f: [0, 0, 0] for f in fields}
    for g, e in zip(gold_fields, extracted_fields):
        for f, c in _field_counts(g, e, fields).items():
            totals[f] = [a + b for a, b in zip(totals[f], c)]
    micro = [sum(c[i] for c in totals.values()) for i in range(3)]
    return {"micro": _prf(*micro), "per_field": {f: _prf(*c) for f, c in totals.items()}}


# ---------------------------------------------------------------- Department suggestion


@_finite_args
def topk_accuracy(y_true: Sequence[Hashable], ranked: Sequence[Sequence[Hashable]], k: int) -> float | Undefined:
    """Fraction of decision points whose true department is in the top-k ranked suggestions."""
    _same_len(y_true, ranked, "topk_accuracy")
    _require(y_true, "topk_accuracy y_true")
    _require(ranked, "topk_accuracy ranked")
    if not y_true:
        return Undefined("no decision points")
    return float(np.mean([t in list(r)[:k] for t, r in zip(y_true, ranked)]))


# ---------------------------------------------------------------- Pharma Agent


def _issue_keys(issues: Iterable[Mapping[str, Any]], issue_type: str) -> set[Any]:
    return {i["id"] for i in issues if i["type"] == issue_type}


@_finite_args
def per_issue_type_pr(
    recall_rows: Sequence[Mapping[str, Any]],
    precision_rows: Sequence[Mapping[str, Any]],
    issue_types: Sequence[str],
    recall_source: str = "synthetic_error_injection",
    precision_source: str = "pharmacist_review",
) -> dict[str, dict[str, Any]]:
    """Precision and recall per issue type, each on its own population.

    Rows are ``{"gold": [{"type", "id"}...], "flagged": [{"type", "id"}...]}``.
    Recall = |gold ∩ flagged| / |gold| on ``recall_rows`` (e.g. synthetic error injection).
    Precision = |gold ∩ flagged| / |flagged| on ``precision_rows`` where ``gold`` is the set of flagged
    issues the pharmacist confirmed. F1 is only reported when both come from the same source.
    """
    for what, rows in (("recall_rows", recall_rows), ("precision_rows", precision_rows)):
        for i, r in enumerate(rows):
            if r.get("flagged") is None:
                raise MissingPredictionError(f"per_issue_type_pr {what}[{i}]: missing flagged issues")
            if r.get("gold") is None:
                raise ValueError(f"per_issue_type_pr {what}[{i}]: missing gold issues")
    out: dict[str, dict[str, Any]] = {}
    for t in issue_types:
        rtp = rden = ptp = pden = 0
        for r in recall_rows:
            g, f = _issue_keys(r["gold"], t), _issue_keys(r["flagged"], t)
            rtp, rden = rtp + len(g & f), rden + len(g)
        for r in precision_rows:
            g, f = _issue_keys(r["gold"], t), _issue_keys(r["flagged"], t)
            ptp, pden = ptp + len(g & f), pden + len(f)
        p = _ratio(ptp, pden, f"no {t} issues flagged in the {precision_source} population")
        rec = _ratio(rtp, rden, f"no {t} issues in the {recall_source} population")
        if recall_source != precision_source:
            f1: float | Undefined = Undefined(
                f"precision ({precision_source}) and recall ({recall_source}) come from different populations; "
                "F1 is not reported"
            )
        elif isinstance(p, Undefined) or isinstance(rec, Undefined):
            f1 = Undefined("precision or recall undefined")
        else:
            f1 = 0.0 if p + rec == 0 else 2 * p * rec / (p + rec)
        out[t] = {
            "precision": p,
            "precision_source": precision_source,
            "precision_n_flagged": pden,
            "recall": rec,
            "recall_source": recall_source,
            "recall_n_gold": rden,
            "f1": f1,
        }
    return out


# ---------------------------------------------------------------- Abstention


@_finite_args
def coverage(y_pred: Sequence[Any]) -> float | Undefined:
    """Fraction of decision points answered. ``None`` (missing) counts as abstain."""
    if len(y_pred) == 0:
        return Undefined("no decision points")
    return float(np.mean([not _is_missing(p) for p in y_pred]))


@_finite_args
def selective_accuracy(y_true: Sequence[Hashable], y_pred: Sequence[Any]) -> float | Undefined:
    """Accuracy on answered decision points. Coverage 0 -> Undefined."""
    _same_len(y_true, y_pred, "selective_accuracy")
    _require(y_true, "selective_accuracy y_true")
    answered = [(t, p) for t, p in zip(y_true, y_pred) if not _is_missing(p)]
    if not answered:
        return Undefined("coverage is 0; selective accuracy is undefined")
    return float(np.mean([t == p for t, p in answered]))


# ---------------------------------------------------------------- Replay / Regenerate


def _replay_counts(original: Mapping[str, str], replay: Mapping[str, str] | None) -> tuple[bool, int, int]:
    if replay is None:
        raise MissingPredictionError("replay_determinism: missing replay hashes")
    identical = sum(1 for n, h in original.items() if replay.get(n) == h)
    deterministic = set(original) == set(replay) and identical == len(original)
    return deterministic, identical, len(original)


@_finite_args
def replay_determinism(
    original_hashes: Sequence[Mapping[str, str]], replay_hashes: Sequence[Mapping[str, str] | None]
) -> dict[str, Any]:
    """Fraction of graphs whose no-cache replay node-output hashes are all identical, plus node-level fraction."""
    _same_len(original_hashes, replay_hashes, "replay_determinism")
    g = ident = total = 0
    for o, r in zip(original_hashes, replay_hashes):
        d, i, n = _replay_counts(o, r)
        g, ident, total = g + int(d), ident + i, total + n
    return {
        "graph_fraction": _ratio(g, len(original_hashes), "no graphs"),
        "node_fraction": _ratio(ident, total, "no nodes"),
        "n_graphs": len(original_hashes),
        "n_nodes": total,
    }


@_finite_args
def recomputed_nodes(n_recomputed: Sequence[float], n_nodes_full: Sequence[float]) -> dict[str, Any]:
    """Recomputed nodes on Regenerate vs a full-graph node count."""
    _same_len(n_recomputed, n_nodes_full, "recomputed_nodes")
    _require(n_recomputed, "recomputed_nodes n_recomputed")
    _require(n_nodes_full, "recomputed_nodes n_nodes_full")
    if not n_recomputed:
        u = Undefined("no regenerations")
        return {k: u for k in ("mean_recomputed", "median_recomputed", "mean_full", "median_full", "ratio")}
    r = np.asarray(n_recomputed, dtype=float)
    f = np.asarray(n_nodes_full, dtype=float)
    return {
        "mean_recomputed": float(r.mean()),
        "median_recomputed": float(np.median(r)),
        "mean_full": float(f.mean()),
        "median_full": float(np.median(f)),
        "ratio": _ratio(r.sum(), f.sum(), "full-graph node count is 0"),
    }
