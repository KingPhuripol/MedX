"""Exact binomial intervals: Wilson score and Clopper-Pearson (slice e1, S4 reviewer condition C3).

Pure Python (stdlib ``math`` and ``statistics`` only; no scipy at runtime). Both are two-sided and
match ``scipy.stats.binomtest(x, n).proportion_ci(method="wilson" | "exact")``:

- Wilson (Newcombe 1998, method 3, no continuity correction); lower bound 0 when x = 0, upper 1 when x = n.
- Clopper-Pearson: lower = I^-1(alpha/2; x, n-x+1), upper = I^-1(1-alpha/2; x+1, n-x), where I is the
  regularized incomplete beta function (0 when x = 0, 1 when x = n).

Both assume n independent Bernoulli trials. Decision points of one patient are not independent, so these
intervals ignore patient clustering; reports show them next to the patient-level bootstrap with n_patients.
Research prototype - not for clinical use.
"""

from __future__ import annotations

import math
from statistics import NormalDist

__all__ = ["wilson", "clopper_pearson", "betainc", "check_counts"]

_EPS = 1e-300
_TOL = 3e-16


def check_counts(x: int, n: int, confidence: float = 0.95) -> None:
    if isinstance(x, bool) or isinstance(n, bool) or int(x) != x or int(n) != n:
        raise ValueError(f"x and n must be integers, got x={x!r}, n={n!r}")
    if n < 1 or x < 0 or x > n:
        raise ValueError(f"need 0 <= x <= n and n >= 1, got x={x}, n={n}")
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence must be in (0, 1)")


def wilson(x: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Two-sided Wilson score interval for x successes in n trials."""
    check_counts(x, n, confidence)
    z = NormalDist().inv_cdf(0.5 + 0.5 * confidence)
    p = x / n
    q = 1.0 - p
    denom = 2.0 * (n + z * z)
    center = (2.0 * n * p + z * z) / denom
    delta = z / denom * math.sqrt(4.0 * n * p * q + z * z)
    lo = 0.0 if x == 0 else max(0.0, center - delta)
    hi = 1.0 if x == n else min(1.0, center + delta)
    return lo, hi


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _EPS else _EPS)
    h = d
    for m in range(1, 10000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _EPS else _EPS)
        c = 1.0 + aa / c
        c = c if abs(c) > _EPS else _EPS
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _EPS else _EPS)
        c = 1.0 + aa / c
        c = c if abs(c) > _EPS else _EPS
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _TOL:
            return h
    raise ArithmeticError("incomplete beta continued fraction did not converge")


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b) for a, b > 0 and 0 <= x <= 1."""
    if a <= 0 or b <= 0:
        raise ValueError("a and b must be > 0")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _betainc_inv(a: float, b: float, target: float) -> float:
    """x in [0, 1] with I_x(a, b) = target, by bisection (I is increasing in x)."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if mid in (lo, hi):
            break
        if betainc(a, b, mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def clopper_pearson(x: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Two-sided Clopper-Pearson ("exact") interval for x successes in n trials."""
    check_counts(x, n, confidence)
    alpha = (1.0 - confidence) / 2.0
    lo = 0.0 if x == 0 else _betainc_inv(float(x), float(n - x + 1), alpha)
    hi = 1.0 if x == n else _betainc_inv(float(x + 1), float(n - x), 1.0 - alpha)
    return min(max(lo, 0.0), 1.0), min(max(hi, 0.0), 1.0)
