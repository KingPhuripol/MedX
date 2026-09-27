"""Slice s6 additions to the harness: ``selective_hit_at_k`` and ``exact_binomial_ci`` (S6-A11)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import binomtest

from eval import metrics as M
from eval.bootstrap import RatioStat, cluster_bootstrap
from eval.metrics import NonFiniteValueError
from eval.metrics import Undefined, exact_binomial_ci, selective_hit_at_k
from eval.registry import ABSTENTION_AWARE, METRICS, REGISTRY, prepare
from eval.runner import exact_interval

# (suggested, ordered, k, hand-computed selective hit@k)
TOY = [
    # 4 rows, 1 abstain; answered: hit (b in top2), miss (x,y), hit (a) -> 2/3
    ([["a", "b"], None, ["x", "y", "z"], ["a"]], [["b"], ["q"], ["z"], ["a", "c"]], 2, 2 / 3),
    # all answered; k=1: hit, miss, miss -> 1/3
    ([["a", "b"], ["b", "a"], ["c"]], [["a"], ["a"], ["d"]], 1, 1 / 3),
    # 2 abstain out of 3; answered row misses -> 0/1
    ([None, None, ["a", "b", "c", "d"]], [["a"], ["a"], ["d"]], 3, 0.0),
]


@pytest.mark.parametrize("suggested,ordered,k,expected", TOY)
def test_selective_hit_at_k_hand(suggested, ordered, k, expected):
    assert selective_hit_at_k(suggested, ordered, k) == expected
    rows = [{"patient_id": f"p{i}", "decision_point_id": "T1", "task": "t", "suggested": s, "ordered": o}
            for i, (s, o) in enumerate(zip(suggested, ordered))]
    prep = prepare("selective_hit_at_k", rows, {"k": k})
    assert prep.stat(np.arange(len(rows))) == expected


def test_abstained_rows_never_answered():
    # The abstained row's gold would be a hit for any suggestion; it must not enter the answered set.
    rows = [{"patient_id": "p1", "decision_point_id": "T1", "task": "t", "suggested": None, "ordered": ["a"]},
            {"patient_id": "p2", "decision_point_id": "T1", "task": "t", "suggested": ["b"], "ordered": ["c"]}]
    prep = prepare("selective_hit_at_k", rows, {"k": 3})
    assert isinstance(prep.stat, RatioStat) and prep.stat.den.tolist() == [0.0, 1.0]
    assert prep.stat(np.arange(2)) == 0.0
    assert isinstance(selective_hit_at_k([None], [["a"]], 3), Undefined)
    # An abstained row may carry no gold at all (runner-imputed missing patient).
    imputed = {"patient_id": "p3", "decision_point_id": "__missing__", "task": "t", "suggested": None,
               "imputed_missing": True}
    assert prepare("selective_hit_at_k", [*rows, imputed], {"k": 3}).stat(np.arange(3)) == 0.0


def test_selective_hit_registered_as_extension():
    assert "selective_hit_at_k" in ABSTENTION_AWARE and "selective_hit_at_k" in METRICS
    assert "selective_hit_at_k" not in REGISTRY  # the s8 registry of 20 is unchanged


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_selective_hit_rejects_nonfinite(bad):
    with pytest.raises(NonFiniteValueError):
        selective_hit_at_k([["a", bad]], [["a"]], 1)
    with pytest.raises(NonFiniteValueError):
        prepare("selective_hit_at_k", [{"patient_id": "p", "decision_point_id": "T1", "task": "t",
                                        "suggested": ["a", bad], "ordered": ["a"]}], {"k": 1})


CP_CASES = [(0, 1), (1, 1), (0, 10), (10, 10), (3, 10), (1, 36), (35, 36), (17, 36), (0, 72), (72, 72),
            (50, 179), (1, 2), (99, 100), (5, 400)]


@pytest.mark.parametrize("x,n", CP_CASES)
@pytest.mark.parametrize("level", [0.95, 0.9])
def test_exact_ci_matches_scipy(x, n, level):
    lo, hi = exact_binomial_ci(x, n, level)
    ref = binomtest(x, n).proportion_ci(confidence_level=level, method="exact")
    assert math.isclose(lo, ref.low, abs_tol=1e-9) and math.isclose(hi, ref.high, abs_tol=1e-9)


def test_exact_ci_edge_inputs():
    assert isinstance(exact_binomial_ci(0, 0), Undefined)
    for bad in [(-1, 3), (4, 3), (1.5, 3), (True, 3)]:
        with pytest.raises(ValueError):
            exact_binomial_ci(*bad)
    with pytest.raises(ValueError):
        exact_binomial_ci(1, 3, 1.0)
    assert M.exact_binomial_ci is exact_binomial_ci


def _spec(**params):
    return {"id": "m", "params": params}


def test_exact_interval_zero_width_trigger():
    # 4 patients, every answered decision point is a hit -> bootstrap CI is [1, 1] (zero width).
    ids = ["p1", "p1", "p2", "p3", "p4"]
    stat = RatioStat(np.array([1, 0, 1, 1, 1], float), np.array([1, 0, 1, 1, 1], float))
    res = cluster_bootstrap(ids, stat, n_boot=200, seed=1).to_dict()
    assert res["ci_low"] == res["ci_high"] == 1.0
    ex = exact_interval(_spec(exact_ci="patient_all_success"), stat, ids, res, 0.95)
    assert ex["x"] == 4 and ex["n"] == 4 and ex["method"] == "clopper_pearson"
    assert ex["trigger"] == "bootstrap CI has zero width"
    assert math.isclose(ex["ci_low"], 0.025 ** 0.25) and ex["ci_high"] == 1.0
    # Not declared -> not computed; non-degenerate CI -> not computed.
    assert exact_interval(_spec(), stat, ids, res, 0.95) is None
    stat2 = RatioStat(np.array([1, 0, 1, 0, 1], float), np.ones(5))
    res2 = cluster_bootstrap(ids, stat2, n_boot=200, seed=1).to_dict()
    assert res2["ci_low"] < res2["ci_high"] and not res2["unstable"]
    assert exact_interval(_spec(exact_ci="patient_all_success"), stat2, ids, res2, 0.95) is None


def test_exact_interval_patient_all_success_is_conservative():
    # p1 has one hit and one miss -> p1 fails as a patient; p2 abstained everywhere -> not eligible.
    ids = ["p1", "p1", "p2", "p3"]
    stat = RatioStat(np.array([1, 0, 0, 1], float), np.array([1, 1, 0, 1], float))
    res = {"point": 2 / 3, "ci_low": 0.5, "ci_high": 0.5, "unstable": False}
    ex = exact_interval(_spec(exact_ci="patient_all_success"), stat, ids, res, 0.95)
    assert (ex["x"], ex["n"]) == (1, 2)
