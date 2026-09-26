"""Patient-level cluster bootstrap (slice s8). Research prototype - not for clinical use.

Patient IDs are resampled with replacement; every drawn patient contributes all of its
decision points (multiplicity preserved). The metric is recomputed on each resample and a
percentile CI is taken over the non-degenerate resamples.

A statistic is either
- a callable ``stat(row_idx: np.ndarray) -> float | Undefined`` evaluated on the concatenated
  row indices of the drawn patients, or
- a ``RatioStat(num, den)``: ``sum(num[idx]) / sum(den[idx])``, evaluated in vectorized form
  (same patient draws, same estimand; used for accuracy-like and per-patient-mean metrics).

Draws come from ``numpy.random.Generator(PCG64(seed))`` as one ``(n_boot, n_patients)`` matrix,
so the single-arm, paired and row-level variants are reproducible and comparable.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, field
from typing import Any, Union

import numpy as np

from .metrics import Undefined

UNSTABLE_FRACTION = 0.01
METHODS = ("percentile",)


@dataclass(frozen=True)
class RatioStat:
    num: np.ndarray
    den: np.ndarray
    reason: str = "denominator is 0"

    def __call__(self, idx: np.ndarray) -> float | Undefined:
        d = float(self.den[idx].sum())
        return Undefined(self.reason) if d == 0 else float(self.num[idx].sum()) / d


Stat = Union[RatioStat, Callable[[np.ndarray], Any]]


@dataclass
class BootResult:
    point: float | None
    ci_low: float | None
    ci_high: float | None
    ci_level: float
    n_boot: int
    seed: int
    method: str
    n_degenerate: int | None
    unstable: bool
    n_patients: int
    n_decision_points: int
    reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "point": self.point,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "ci_level": self.ci_level,
            "n_boot": self.n_boot,
            "seed": self.seed,
            "method": self.method,
            "n_degenerate": self.n_degenerate,
            "unstable": self.unstable,
            "n_patients": self.n_patients,
            "n_decision_points": self.n_decision_points,
            "reason": self.reason,
        }
        d.update(self.extra)
        return d


class _Clusters:
    """Cluster codes in order of first appearance, and each cluster's row indices."""

    def __init__(self, cluster_ids: Sequence[Hashable], order: dict[Hashable, int] | None = None):
        ids = list(cluster_ids)
        if order is None:
            order = {}
            for c in ids:
                order.setdefault(c, len(order))
        else:
            unknown = {c for c in ids if c not in order}
            if unknown or len(set(ids)) != len(order):
                raise ValueError("paired bootstrap: both arms must contain exactly the same patients")
        self.order = order
        self.codes = np.fromiter((order[c] for c in ids), dtype=np.int64, count=len(ids))
        self.n = len(order)
        sort = np.argsort(self.codes, kind="stable")
        counts = np.bincount(self.codes, minlength=self.n)
        self.groups = np.split(sort, np.cumsum(counts)[:-1]) if self.n else []


def _draws(n_clusters: int, n_boot: int, seed: int) -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(seed))
    return rng.integers(0, n_clusters, size=(n_boot, n_clusters))


def _value(v: Any) -> float:
    if isinstance(v, Undefined) or v is None:
        return float("nan")
    v = float(v)
    return v if np.isfinite(v) else float("nan")


def _evaluate(stat: Stat, cl: _Clusters, draws: np.ndarray) -> np.ndarray:
    """Statistic on every resample; NaN marks a degenerate resample."""
    if isinstance(stat, RatioStat):
        cnum = np.bincount(cl.codes, weights=stat.num.astype(float), minlength=cl.n)
        cden = np.bincount(cl.codes, weights=stat.den.astype(float), minlength=cl.n)
        num, den = cnum[draws].sum(axis=1), cden[draws].sum(axis=1)
        out = np.full(draws.shape[0], np.nan)
        ok = den != 0
        out[ok] = num[ok] / den[ok]
        return out
    return np.array([_value(stat(np.concatenate([cl.groups[j] for j in d]))) for d in draws], dtype=float)


def _ci(vals: np.ndarray, ci_level: float) -> tuple[float | None, float | None, int]:
    ok = vals[~np.isnan(vals)]
    n_deg = int(vals.size - ok.size)
    if ok.size == 0:
        return None, None, n_deg
    a = (1.0 - ci_level) / 2.0
    lo, hi = np.percentile(ok, [100.0 * a, 100.0 * (1.0 - a)], method="linear")
    return float(lo), float(hi), n_deg


def _check(n_boot: int, ci_level: float, method: str) -> None:
    if method not in METHODS:
        raise ValueError(f"bootstrap method {method!r} not supported; use one of {METHODS}")
    if not (0.0 < ci_level < 1.0):
        raise ValueError("ci_level must be in (0, 1)")
    if n_boot < 1:
        raise ValueError("n_boot must be >= 1")


def _result(point: Any, vals: np.ndarray | None, cl: _Clusters, n_rows: int, n_boot: int, seed: int,
            ci_level: float, method: str) -> BootResult:
    common = dict(ci_level=ci_level, n_boot=n_boot, seed=seed, method=method, n_patients=cl.n,
                  n_decision_points=n_rows)
    if isinstance(point, Undefined) or vals is None:
        reason = point.reason if isinstance(point, Undefined) else "undefined"
        return BootResult(None, None, None, n_degenerate=None, unstable=False, reason=reason, **common)
    lo, hi, n_deg = _ci(vals, ci_level)
    unstable = n_deg > UNSTABLE_FRACTION * n_boot
    reason = None if lo is not None else "all bootstrap resamples were degenerate"
    return BootResult(float(point), lo, hi, n_degenerate=n_deg, unstable=unstable, reason=reason, **common)


def cluster_bootstrap(
    cluster_ids: Sequence[Hashable],
    stat: Stat,
    *,
    n_boot: int = 2000,
    seed: int = 0,
    ci_level: float = 0.95,
    method: str = "percentile",
) -> BootResult:
    """Patient-level (cluster) bootstrap CI of ``stat``; ``cluster_ids[i]`` is row i's patient."""
    _check(n_boot, ci_level, method)
    cl = _Clusters(cluster_ids)
    n_rows = len(cl.codes)
    point = stat(np.arange(n_rows)) if n_rows else Undefined("no decision points")
    if isinstance(point, Undefined):
        return _result(point, None, cl, n_rows, n_boot, seed, ci_level, method)
    vals = _evaluate(stat, cl, _draws(cl.n, n_boot, seed))
    return _result(point, vals, cl, n_rows, n_boot, seed, ci_level, method)


def row_bootstrap(n_rows: int, stat: Stat, **kw: Any) -> BootResult:
    """Row-level bootstrap (each decision point its own cluster). For contrast only; not for reporting."""
    return cluster_bootstrap(range(n_rows), stat, **kw)


def paired_cluster_bootstrap(
    cluster_ids_a: Sequence[Hashable],
    stat_a: Stat,
    cluster_ids_b: Sequence[Hashable],
    stat_b: Stat,
    *,
    n_boot: int = 2000,
    seed: int = 0,
    ci_level: float = 0.95,
    method: str = "percentile",
) -> BootResult:
    """CI of ``stat_a - stat_b`` with the same patient draw applied to both arms."""
    _check(n_boot, ci_level, method)
    ca = _Clusters(cluster_ids_a)
    cb = _Clusters(cluster_ids_b, order=ca.order)
    pa = stat_a(np.arange(len(ca.codes))) if len(ca.codes) else Undefined("no decision points")
    pb = stat_b(np.arange(len(cb.codes))) if len(cb.codes) else Undefined("no decision points")
    if isinstance(pa, Undefined) or isinstance(pb, Undefined):
        u = pa if isinstance(pa, Undefined) else pb
        arm = "system" if isinstance(pa, Undefined) else "comparator"
        return _result(Undefined(f"{arm} metric undefined: {u.reason}"), None, ca, len(ca.codes), n_boot, seed,
                       ci_level, method)
    draws = _draws(ca.n, n_boot, seed)
    diff = _evaluate(stat_a, ca, draws) - _evaluate(stat_b, cb, draws)
    return _result(float(pa) - float(pb), diff, ca, len(ca.codes), n_boot, seed, ci_level, method)
