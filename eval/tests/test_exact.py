"""E1-A05: pure-Python Wilson and Clopper-Pearson intervals match scipy (slice e1, S4 reviewer condition C3).

scipy is used here as the reference only; ``eval/exact.py`` itself never imports it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from scipy.stats import binomtest

from eval.exact import betainc, clopper_pearson, wilson

EXACT = Path(__file__).resolve().parents[1] / "exact.py"

PAIRS = sorted({(0, 1), (1, 1), (0, 2), (1, 2), (2, 2), (0, 3), (3, 3), (1, 3)}
               | {(x, n) for n in (4, 5, 8, 10, 13, 24, 26, 40, 52, 56, 80, 97, 193, 400, 1000)
                  for x in sorted({0, 1, 2, n // 3, n // 2, n - 2, n - 1, n}) if 0 <= x <= n})


def test_exact_intervals_match_scipy():
    assert len(PAIRS) >= 50
    assert any(x == 0 for x, _ in PAIRS) and any(x == n for x, n in PAIRS) and any(n == 1 for _, n in PAIRS)
    for x, n in PAIRS:
        ref_w = binomtest(x, n).proportion_ci(confidence_level=0.95, method="wilson")
        ref_cp = binomtest(x, n).proportion_ci(confidence_level=0.95, method="exact")
        w, cp = wilson(x, n), clopper_pearson(x, n)
        assert abs(w[0] - ref_w.low) <= 1e-9 and abs(w[1] - ref_w.high) <= 1e-9, (x, n, w, ref_w)
        assert abs(cp[0] - ref_cp.low) <= 1e-9 and abs(cp[1] - ref_cp.high) <= 1e-9, (x, n, cp, ref_cp)
        for lo, hi in (w, cp):
            assert 0.0 <= lo <= x / n <= hi <= 1.0


def test_exact_other_levels_and_edges():
    for x, n in ((0, 5), (3, 7), (7, 7)):
        for cl in (0.8, 0.9, 0.99):
            ref = binomtest(x, n).proportion_ci(confidence_level=cl, method="exact")
            got = clopper_pearson(x, n, cl)
            assert abs(got[0] - ref.low) <= 1e-9 and abs(got[1] - ref.high) <= 1e-9
    assert clopper_pearson(0, 4)[0] == 0.0 and clopper_pearson(4, 4)[1] == 1.0
    assert wilson(0, 4)[0] == 0.0 and wilson(4, 4)[1] == 1.0
    assert betainc(2.0, 3.0, 0.0) == 0.0 and betainc(2.0, 3.0, 1.0) == 1.0
    for bad in ((-1, 3), (4, 3), (0, 0), (1.5, 3), (True, 3)):
        with pytest.raises(ValueError):
            wilson(*bad)
        with pytest.raises(ValueError):
            clopper_pearson(*bad)


def test_exact_has_no_scipy_or_sklearn():
    mods = set()
    for node in ast.walk(ast.parse(EXACT.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods <= {"__future__", "math", "statistics"}, mods
