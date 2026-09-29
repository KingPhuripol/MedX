"""S8-A01..A07: metrics vs scikit-learn reference and hand-computed examples."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import (
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
    top_k_accuracy_score,
)
from sklearn.preprocessing import MultiLabelBinarizer

from eval import metrics as M
from eval.metrics import MissingPredictionError, Undefined
from eval.registry import prepare

TOL = 1e-9


def rng(seed: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


# ---------------------------------------------------------------- A01


def test_macro_f1_matches_sklearn():
    labels = ["a", "b", "c", "d"]
    for seed in range(25):
        r = rng(seed)
        n = int(r.integers(5, 60))
        yt = list(r.choice(labels, n))
        yp = list(r.choice(labels, n))
        ref = f1_score(yt, yp, labels=labels, average="macro", zero_division=0)
        assert abs(M.macro_f1(yt, yp, labels) - ref) <= TOL
    # Edge cases: declared label absent from y_true; label never predicted; undeclared prediction.
    yt, yp = ["a", "a", "b", "b"], ["a", "b", "b", "b"]
    for case_true, case_pred in [(yt, yp), (["a", "b", "b"], ["a", "a", "a"]), (["a", "b"], ["x", "b"])]:
        ref = f1_score(case_true, case_pred, labels=labels, average="macro", zero_division=0)
        assert abs(M.macro_f1(case_true, case_pred, labels) - ref) <= TOL
    # Multilabel (report-derived findings).
    mlb = MultiLabelBinarizer(classes=labels)
    for seed in range(25):
        r = rng(100 + seed)
        n = int(r.integers(5, 40))
        yt = [[lab for lab in labels if r.random() < 0.35] for _ in range(n)]
        yp = [[lab for lab in labels if r.random() < 0.35] for _ in range(n)]
        yt[0] = [lab for lab in yt[0] if lab != "d"]  # keep the edge case "d" sometimes absent
        ref = f1_score(mlb.fit_transform(yt), mlb.fit_transform(yp), average="macro", zero_division=0)
        assert abs(M.multilabel_macro_f1(yt, yp, labels) - ref) <= TOL
    ref = f1_score(mlb.fit_transform([["a"], ["a"]]), mlb.fit_transform([["a"], []]), average="macro", zero_division=0)
    assert abs(M.multilabel_macro_f1([["a"], ["a"]], [["a"], []], labels) - ref) <= TOL


# ---------------------------------------------------------------- A02


def test_auroc_matches_sklearn():
    labels = ["x", "y", "z"]
    for seed in range(25):
        r = rng(200 + seed)
        n = int(r.integers(10, 80))
        # Binary with ties (scores rounded to 1 decimal).
        y = r.integers(0, 2, n)
        y[0], y[1] = 0, 1
        s = np.round(r.random(n), 1)
        assert abs(M.auroc(list(y), list(s)) - roc_auc_score(y, s)) <= TOL
        # Multiclass OvR macro.
        yc = list(r.choice(labels, n))
        yc[:3] = labels
        P = np.round(r.random((n, 3)), 1) + 0.01
        P = P / P.sum(axis=1, keepdims=True)
        ref = roc_auc_score(yc, P, multi_class="ovr", average="macro", labels=labels)
        assert abs(M.auroc(yc, P.tolist(), mode="multiclass", labels=labels) - ref) <= TOL
        dicts = [dict(zip(labels, row)) for row in P.tolist()]
        assert abs(M.auroc(yc, dicts, mode="multiclass", labels=labels) - ref) <= TOL
        # Multilabel macro.
        Y = r.integers(0, 2, (n, 3))
        Y[0], Y[1] = 0, 1
        S = np.round(r.random((n, 3)), 1)
        sets = [[labels[j] for j in range(3) if Y[i, j]] for i in range(n)]
        ref = roc_auc_score(Y, S, average="macro")
        assert abs(M.auroc(sets, S.tolist(), mode="multilabel", labels=labels) - ref) <= TOL


def test_auroc_single_class_null():
    v = M.auroc([1, 1, 1], [0.2, 0.5, 0.9])
    assert isinstance(v, Undefined) and "one class" in v.reason
    v = M.auroc(["x", "x"], [[0.5, 0.5], [0.4, 0.6]], mode="multiclass", labels=["x", "y"])
    assert isinstance(v, Undefined) and "'x'" in v.reason  # 'x' is all-positive in one-vs-rest
    v = M.auroc([["x"], ["x"]], [[0.5, 0.5], [0.4, 0.6]], mode="multilabel", labels=["x", "y"])
    assert isinstance(v, Undefined)


# ---------------------------------------------------------------- A03


def test_dice_hand_example():
    a = [[1, 1, 0], [0, 1, 0]]
    b = [[1, 0, 0], [0, 1, 1]]
    assert M.dice_case(a, b) == 2 * 2 / (3 + 3)  # |A∩B|=2, |A|=3, |B|=3 -> 0.6666...
    a3 = np.zeros((2, 2, 2), int)
    b3 = np.zeros((2, 2, 2), int)
    a3[0, 0, 0] = a3[1, 1, 1] = a3[1, 0, 1] = 1
    b3[1, 1, 1] = 1
    assert M.dice_case(a3, b3) == 2 * 1 / (3 + 1)  # 0.5
    assert M.dice([a, a3], [b, b3]) == (2 / 3 + 0.5) / 2


def test_dice_matches_f1_flat():
    for seed in range(25):
        r = rng(300 + seed)
        a = r.random((4, 5, 6)) < 0.3
        b = r.random((4, 5, 6)) < 0.3
        ref = f1_score(a.ravel(), b.ravel(), zero_division=0)
        assert abs(M.dice_case(a, b) - ref) <= TOL
        inter = (a & b).sum()
        assert abs(M.dice_case(a, b) - 2 * inter / (a.sum() + b.sum())) <= TOL


def test_dice_empty_empty():
    z = np.zeros((3, 3), int)
    assert M.dice_case(z, z) == 1.0
    assert M.dice_case(z, z, empty_empty=0.0) == 0.0
    s = M.dice_summary([z, [[1, 0, 0]] * 3], [z, [[1, 0, 0]] * 3], empty_empty=1.0)
    assert s["n_empty_empty"] == 1 and s["empty_empty_value"] == 1.0 and s["value"] == 1.0
    prep = prepare("dice", [{"patient_id": "p", "decision_point_id": "d", "mask_true": z.tolist(),
                             "mask_pred": z.tolist()}], {"empty_empty": 1.0})
    assert prep.details == {"empty_empty_value": 1.0, "n_empty_empty": 1}


# ---------------------------------------------------------------- A04


def test_topk_matches_sklearn():
    labels = sorted(["ed", "med", "surg", "card", "neuro"])  # sklearn requires ordered labels
    for seed in range(25):
        r = rng(400 + seed)
        n = int(r.integers(5, 50))
        yt = list(r.choice(labels, n))
        ranked = [list(r.permutation(labels)) for _ in range(n)]
        scores = np.array([[len(labels) - rk.index(lab) for lab in labels] for rk in ranked], float)
        for k in (1, 3):
            ref = top_k_accuracy_score(yt, scores, k=k, labels=labels)
            assert abs(M.topk_accuracy(yt, ranked, k) - ref) <= TOL


# ---------------------------------------------------------------- A05


def test_field_prf():
    gold = [
        {"cc": "Chest pain", "onset": "today", "allergy": "none"},
        {"cc": "fever", "onset": "2 days", "allergy": None},
    ]
    extracted = [
        {"cc": " chest  PAIN ", "onset": "yesterday"},  # cc match (normalized), onset wrong, allergy missed
        {"cc": "fever", "allergy": "penicillin"},  # cc match, onset missed, allergy spurious
    ]
    out = M.field_prf(gold, extracted)
    # tp=2 (cc x2); fp: onset wrong (1) + allergy spurious (1) = 2; fn: onset wrong, allergy missed, onset missed = 3
    assert out["micro"]["tp"] == 2 and out["micro"]["fp"] == 2 and out["micro"]["fn"] == 3
    assert out["micro"]["precision"] == 2 / 4 and out["micro"]["recall"] == 2 / 5
    assert out["micro"]["f1"] == 4 / 9
    assert out["per_field"]["cc"]["precision"] == 1.0 and out["per_field"]["cc"]["recall"] == 1.0
    assert out["per_field"]["onset"]["precision"] == 0.0 and out["per_field"]["onset"]["recall"] == 0.0

    # Reference: each (field, normalized value) pair is a label; sklearn micro over a field's pairs.
    for seed in range(20):
        r = rng(500 + seed)
        fields = ["cc", "onset", "pain"]
        vals = ["a", "b", "c"]
        n = int(r.integers(3, 20))
        g = [{f: str(r.choice(vals)) for f in fields if r.random() < 0.8} for _ in range(n)]
        e = [{f: str(r.choice(vals)) for f in fields if r.random() < 0.8} for _ in range(n)]
        pairs = sorted({f"{f}={v}" for d in g + e for f, v in d.items()})
        mlb = MultiLabelBinarizer(classes=pairs)
        Yt = mlb.fit_transform([[f"{f}={v}" for f, v in d.items()] for d in g])
        Yp = mlb.fit_transform([[f"{f}={v}" for f, v in d.items()] for d in e])
        out = M.field_prf(g, e, fields)
        p, rc, f1, _ = precision_recall_fscore_support(Yt, Yp, average="micro", zero_division=0)
        assert abs(out["micro"]["precision"] - p) <= TOL and abs(out["micro"]["recall"] - rc) <= TOL
        assert abs(out["micro"]["f1"] - f1) <= TOL
        for f in fields:
            idx = [i for i, pr in enumerate(pairs) if pr.startswith(f + "=")]
            if not idx:
                continue
            p, rc, f1, _ = precision_recall_fscore_support(Yt, Yp, labels=idx, average="micro", zero_division=0)
            pf = out["per_field"][f]
            for mine, ref in ((pf["precision"], p), (pf["recall"], rc), (pf["f1"], f1)):
                if isinstance(mine, Undefined):
                    continue  # zero denominator: null by design (sklearn would coerce to 0)
                assert abs(mine - ref) <= TOL


def _iss(t, i):
    return {"type": t, "id": i}


def test_pharma_per_issue_pr():
    recall_rows = [
        {"gold": [_iss("dup", 1), _iss("dose", 2)], "flagged": [_iss("dup", 1)]},
        {"gold": [_iss("dose", 3), _iss("allergy", 4)], "flagged": [_iss("dose", 3), _iss("allergy", 4), _iss("dup", 9)]},
    ]
    precision_rows = [
        {"flagged": [_iss("dup", 5), _iss("dup", 6), _iss("dose", 7)], "gold": [_iss("dup", 5), _iss("dose", 7)]},
        {"flagged": [_iss("allergy", 8)], "gold": []},
    ]
    out = M.per_issue_type_pr(recall_rows, precision_rows, ["dup", "dose", "allergy"])
    assert out["dup"]["recall"] == 1.0 and out["dup"]["precision"] == 0.5
    assert out["dose"]["recall"] == 0.5 and out["dose"]["precision"] == 1.0
    assert out["allergy"]["recall"] == 1.0 and out["allergy"]["precision"] == 0.0
    for t in out.values():
        assert t["recall_source"] == "synthetic_error_injection" and t["precision_source"] == "pharmacist_review"
        assert isinstance(t["f1"], Undefined) and "different populations" in t["f1"].reason

    # sklearn reference on binary item-level vectors, per type and population.
    def ref(rows, t):
        items = sorted({i["id"] for r in rows for i in r["gold"] + r["flagged"] if i["type"] == t})
        g = {i["id"] for r in rows for i in r["gold"] if i["type"] == t}
        f = {i["id"] for r in rows for i in r["flagged"] if i["type"] == t}
        return precision_recall_fscore_support([x in g for x in items], [x in f for x in items], average="binary",
                                               zero_division=0)

    for t in ("dup", "dose", "allergy"):
        assert abs(out[t]["recall"] - ref(recall_rows, t)[1]) <= TOL
        assert abs(out[t]["precision"] - ref(precision_rows, t)[0]) <= TOL
    # Same source -> F1 reported.
    same = M.per_issue_type_pr(recall_rows, recall_rows, ["dup"], "pop", "pop")
    p, r, f1, _ = ref(recall_rows, "dup")
    assert abs(same["dup"]["f1"] - f1) <= TOL

    # Runner adapter reports the source tag per component.
    rows = [{"patient_id": "a", "decision_point_id": "1", "population": "synthetic_error_injection", **recall_rows[0]},
            {"patient_id": "b", "decision_point_id": "1", "population": "pharmacist_review", **precision_rows[0]}]
    assert prepare("per_issue_type_pr", rows, {"issue_type": "dup", "component": "recall"}).details["source"] == \
        "synthetic_error_injection"
    pr = prepare("per_issue_type_pr", rows, {"issue_type": "dup", "component": "precision"})
    assert pr.details["source"] == "pharmacist_review" and pr.stat(np.arange(2)) == 0.5


def test_undefined_is_null():
    assert isinstance(M.set_prf([[]], [["cbc"]])["precision"], Undefined)
    out = M.field_prf([{"a": None}], [{}], ["a"])
    assert all(isinstance(out["micro"][k], Undefined) for k in ("precision", "recall", "f1"))
    pr = M.per_issue_type_pr([], [], ["dup"])
    assert isinstance(pr["dup"]["precision"], Undefined) and isinstance(pr["dup"]["recall"], Undefined)
    assert isinstance(M.selective_accuracy(["a"], [None]), Undefined)
    assert isinstance(M.auroc([0, 0], [0.1, 0.2]), Undefined)
    assert isinstance(M.latency_summary([])["p90"], Undefined)
    assert isinstance(M.accuracy([], []), Undefined)


# ---------------------------------------------------------------- A06


def test_abstention_hand():
    y_true = ["a", "b", "c", "a", "b"]
    y_pred = ["a", None, "c", "b", None]
    assert M.coverage(y_pred) == 3 / 5
    assert M.selective_accuracy(y_true, y_pred) == 2 / 3
    assert M.coverage(["a"] * 5) == 1.0  # always-answer comparator
    assert M.coverage([None, None]) == 0.0
    assert isinstance(M.selective_accuracy(["a", "b"], [None, None]), Undefined)


def test_latency_cost_hand():
    v = [1.0, 2.0, 3.0, 4.0, 10.0]
    s = M.latency_summary(v)
    assert s["mean"] == 4.0 and s["median"] == 3.0
    assert abs(s["p90"] - (4.0 + 0.6 * (10.0 - 4.0))) <= TOL  # linear interpolation at rank 3.6 -> 7.6
    assert s["p90"] == float(np.percentile(v, 90, method="linear"))
    assert M.response_latency(v) == s and M.total_time(v) == s
    pids = ["p1", "p1", "p2", "p3", "p3", "p3"]
    cost = [0.1, 0.2, 0.3, 0.0, 0.1, 0.2]
    assert abs(M.cost_per_patient(pids, cost) - (0.3 + 0.3 + 0.3) / 3) <= TOL
    assert M.calls_per_patient(pids, [1, 2, 3, 1, 1, 1]) == (3 + 3 + 3) / 3
    assert M.latency_per_patient(["a", "b"], [2.0, 4.0]) == 3.0
    # Runner adapter (patient-level ratio) equals the pure function.
    rows = [{"patient_id": p, "decision_point_id": str(i), "cost": c} for i, (p, c) in enumerate(zip(pids, cost))]
    assert abs(prepare("cost_per_patient", rows, {}).stat(np.arange(6)) - 0.3) <= TOL
    lat = [{"patient_id": "p", "decision_point_id": str(i), "latency_s": x} for i, x in enumerate(v)]
    assert prepare("latency_summary", lat, {"component": "p90"}).stat(np.arange(5)) == s["p90"]


def test_replay_metrics_hand():
    orig = [{"n1": "a", "n2": "b"}, {"n1": "c", "n2": "d", "n3": "e"}, {"n1": "f"}]
    rep = [{"n1": "a", "n2": "b"}, {"n1": "c", "n2": "X", "n3": "e"}, {"n1": "f", "n9": "g"}]
    out = M.replay_determinism(orig, rep)
    assert out["graph_fraction"] == 1 / 3  # graph 3 has an extra node -> not identical
    assert out["node_fraction"] == 5 / 6
    rc = M.recomputed_nodes([1, 2, 6], [4, 6, 6])
    assert rc["mean_recomputed"] == 3.0 and rc["median_recomputed"] == 2.0
    assert rc["mean_full"] == 16 / 3 and rc["median_full"] == 6.0 and rc["ratio"] == 9 / 16
    assert M.hit_at_k([["a", "b", "c", "d"], ["x", "y", "z", "b"]], [["c"], ["b"]], 3) == 0.5
    sp = M.set_prf([["a", "b"], ["c"]], [["a"], ["c", "d"]])
    assert sp["precision"] == 2 / 3 and sp["recall"] == 2 / 3 and sp["f1"] == 4 / 6


# ---------------------------------------------------------------- A07


def test_missing_prediction_policy():
    cases = [
        lambda: M.accuracy(["a", "b"], ["a", None]),
        lambda: M.macro_f1(["a", "b"], ["a", None], ["a", "b"]),
        lambda: M.multilabel_macro_f1([["a"]], [None], ["a"]),
        lambda: M.auroc([0, 1], [0.3, None]),
        lambda: M.auroc(["x", "y"], [{"x": 0.2, "y": 0.8}, {"x": 0.5}], mode="multiclass", labels=["x", "y"]),
        lambda: M.dice([[1]], [None]),
        lambda: M.hit_at_k([None], [["a"]], 3),
        lambda: M.set_prf([None], [["a"]]),
        lambda: M.cost_per_patient(["p"], [None]),
        lambda: M.latency_summary([1.0, None]),
        lambda: M.field_prf([{"a": "x"}], [None]),
        lambda: M.topk_accuracy(["a"], [None], 1),
        lambda: M.per_issue_type_pr([{"gold": [], "flagged": None}], [], ["dup"]),
        lambda: M.replay_determinism([{"n": "a"}], [None]),
        lambda: M.recomputed_nodes([None], [3]),
    ]
    for c in cases:
        with pytest.raises(MissingPredictionError):
            c()
    # Registry adapters: absent key raises for non-abstention metrics...
    row = {"patient_id": "p", "decision_point_id": "d", "y_true": "a"}
    for name, params in [("accuracy", {}), ("macro_f1", {"labels": ["a"]}), ("topk_accuracy", {"k": 1})]:
        with pytest.raises(MissingPredictionError):
            prepare(name, [row], params)
    # ... and counts as abstain for abstention-aware metrics (never dropped: denominator keeps it).
    rows = [row, {**row, "decision_point_id": "e", "y_pred": "a"}, {**row, "decision_point_id": "f", "y_pred": None}]
    assert prepare("coverage", rows, {}).stat(np.arange(3)) == 1 / 3
    assert prepare("selective_accuracy", rows, {}).stat(np.arange(3)) == 1.0
    assert M.coverage([None, "a", None]) == 1 / 3
