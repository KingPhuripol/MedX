"""S8-A08..A11: patient-level cluster bootstrap."""

from __future__ import annotations

import time
from collections import Counter

import numpy as np

from eval.bootstrap import RatioStat, cluster_bootstrap, paired_cluster_bootstrap, row_bootstrap
from eval.metrics import Undefined


def _patients(n_patients: int, rows_each: int, values: np.ndarray):
    ids = [f"P{i:03d}" for i in range(n_patients) for _ in range(rows_each)]
    return ids, np.repeat(values, rows_each).astype(float)


def mean_stat(v):
    return lambda idx: float(v[idx].mean()) if idx.size else Undefined("empty")


# ---------------------------------------------------------------- A08


def test_bootstrap_keeps_whole_patients():
    sizes = [1, 2, 3, 4, 5] * 6
    ids = [f"P{i:02d}" for i, s in enumerate(sizes) for _ in range(s)]
    size_of = dict(zip([f"P{i:02d}" for i in range(len(sizes))], sizes))
    arr = np.array(ids)
    seen = []

    def stat(idx):
        c = Counter(arr[idx].tolist())
        seen.append(c)
        return float(len(idx))

    res = cluster_bootstrap(ids, stat, n_boot=200, seed=1)
    assert len(seen) == 201  # point estimate + 200 resamples
    for c in seen[1:]:
        # every drawn patient contributes all its rows, multiplicity preserved
        assert all(n % size_of[p] == 0 for p, n in c.items())
        assert sum(n // size_of[p] for p, n in c.items()) == len(sizes)
    assert any(max(n // size_of[p] for p, n in c.items()) > 1 for c in seen[1:])
    assert res.n_patients == 30 and res.n_decision_points == sum(sizes)


def test_cluster_wider_than_row():
    r = np.random.Generator(np.random.PCG64(7))
    per_patient = (r.random(50) < 0.5).astype(float)
    ids, v = _patients(50, 10, per_patient)  # 10 identical rows per patient
    stat = RatioStat(v, np.ones_like(v))
    c = cluster_bootstrap(ids, stat, n_boot=2000, seed=3)
    w = row_bootstrap(len(v), stat, n_boot=2000, seed=3)
    ratio = (c.ci_high - c.ci_low) / (w.ci_high - w.ci_low)
    assert ratio >= 2.0, ratio
    assert 2.5 < ratio < 4.0  # expected about sqrt(10) = 3.16
    # generic callable path and vectorized ratio path agree on the same draws
    g = cluster_bootstrap(ids, mean_stat(v), n_boot=2000, seed=3)
    assert abs(g.ci_low - c.ci_low) <= 1e-12 and abs(g.ci_high - c.ci_high) <= 1e-12


def test_cluster_equals_row_when_singletons():
    r = np.random.Generator(np.random.PCG64(11))
    v = (r.random(60) < 0.7).astype(float)
    ids = [f"P{i:03d}" for i in range(60)]
    for stat in (RatioStat(v, np.ones_like(v)), mean_stat(v)):
        c = cluster_bootstrap(ids, stat, n_boot=1000, seed=5)
        w = row_bootstrap(60, stat, n_boot=1000, seed=5)
        assert (c.point, c.ci_low, c.ci_high) == (w.point, w.ci_low, w.ci_high)


# ---------------------------------------------------------------- A09


def test_bootstrap_coverage_simulation():
    """200 patients, cluster sizes 1-5, p_i ~ Beta(2,2), rows ~ Bernoulli(p_i): true accuracy 0.5."""
    t0 = time.perf_counter()
    master = np.random.Generator(np.random.PCG64(20260926))
    n_sims, n_boot, n_pat = 1000, 1000, 200
    cover_cluster = cover_row = 0
    for s in range(n_sims):
        sizes = master.integers(1, 6, n_pat)
        p = master.beta(2, 2, n_pat)
        y = (master.random(sizes.sum()) < np.repeat(p, sizes)).astype(float)
        ids = np.repeat(np.arange(n_pat), sizes)
        stat = RatioStat(y, np.ones_like(y))
        c = cluster_bootstrap(ids, stat, n_boot=n_boot, seed=s)
        w = row_bootstrap(y.size, stat, n_boot=n_boot, seed=s)
        cover_cluster += c.ci_low <= 0.5 <= c.ci_high
        cover_row += w.ci_low <= 0.5 <= w.ci_high
    elapsed = time.perf_counter() - t0
    cc, rc = cover_cluster / n_sims, cover_row / n_sims
    print(f"\ncoverage: cluster={cc:.3f} row={rc:.3f} (row not gated) in {elapsed:.1f}s")
    assert 0.93 <= cc <= 0.97, cc
    assert elapsed <= 120


# ---------------------------------------------------------------- A10


def test_paired_self_zero():
    r = np.random.Generator(np.random.PCG64(2))
    v = (r.random(90) < 0.6).astype(float)
    ids = [f"P{i % 30:02d}" for i in range(90)]
    for stat in (RatioStat(v, np.ones_like(v)), mean_stat(v)):
        d = paired_cluster_bootstrap(ids, stat, ids, stat, n_boot=500, seed=9)
        assert (d.point, d.ci_low, d.ci_high) == (0.0, 0.0, 0.0)
        assert d.n_degenerate == 0


def test_paired_shift():
    r = np.random.Generator(np.random.PCG64(4))
    delta = 1.25
    lat = r.uniform(1, 5, 120)
    ids = [f"P{i % 40:02d}" for i in range(120)]
    first = np.zeros(120)
    first[:40] = 1.0  # one "first row" per patient -> per-patient sum, then mean over patients
    sys_rows = np.array([p for p in ids])
    seen_a, seen_b = [], []

    def arm(values, seen):
        def stat(idx):
            seen.append(sys_rows[idx].tolist())
            return float(values[idx].sum() / first[idx].sum())
        return stat

    # comparator's per-patient total is shifted by +delta (spread over that patient's rows)
    per_row_shift = delta / 3.0
    d = paired_cluster_bootstrap(ids, arm(lat + per_row_shift, seen_a), ids, arm(lat, seen_b), n_boot=400, seed=8)
    assert abs(d.point - delta) <= 1e-9
    assert d.ci_low <= delta <= d.ci_high
    assert d.ci_high - d.ci_low <= 1e-9  # a constant per-patient shift gives a degenerate-width CI
    assert seen_a == seen_b  # same patient draws for both arms
    # vectorized ratio path gives the same answer
    d2 = paired_cluster_bootstrap(ids, RatioStat(lat + per_row_shift, first), ids, RatioStat(lat, first),
                                  n_boot=400, seed=8)
    assert d2.ci_low <= delta + 1e-9 and d2.ci_high >= delta - 1e-9


# ---------------------------------------------------------------- A11


def test_degenerate_resamples_flagged():
    # 40 patients, only one answered row -> most resamples have zero answered rows (denominator 0).
    ids = [f"P{i:02d}" for i in range(40)]
    num = np.zeros(40)
    den = np.zeros(40)
    num[0] = den[0] = 1.0
    res = cluster_bootstrap(ids, RatioStat(num, den), n_boot=1000, seed=0)
    assert res.n_degenerate > 10 and res.unstable
    assert res.ci_low is not None and not np.isnan(res.ci_low) and not np.isnan(res.ci_high)
    # Generic callable: Undefined / NaN are counted, never propagated.
    v = np.arange(40, dtype=float)
    res = cluster_bootstrap(ids, lambda idx: Undefined("x") if 0 not in idx else float(v[idx].mean()),
                            n_boot=500, seed=0)
    assert res.n_degenerate > 5 and res.unstable
    assert not any(np.isnan(x) for x in (res.ci_low, res.ci_high))
    # Stable when < 1% degenerate.
    ok = cluster_bootstrap(ids, RatioStat(np.ones(40), np.ones(40)), n_boot=500, seed=0)
    assert ok.n_degenerate == 0 and not ok.unstable
    # Undefined point -> null + reason, no CI.
    u = cluster_bootstrap(ids, RatioStat(np.zeros(40), np.zeros(40), "coverage is 0"), n_boot=100, seed=0)
    assert u.point is None and u.ci_low is None and u.reason == "coverage is 0"
