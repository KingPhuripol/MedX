"""Generate the synthetic toy fixtures for slice s8 (deterministic; committed outputs).

Synthetic data only - no real, MIMIC, CT-RATE or hospital records. Research prototype - not for clinical use.

    .venv/bin/python -m eval.examples.make_toy
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SEED = 20260926
N_PATIENTS = 40
FINDINGS = ["atelectasis", "cardiomegaly", "consolidation", "edema", "effusion"]
TESTS = ["cbc", "bmp", "troponin", "ecg", "cxr", "lactate", "blood_culture", "urinalysis", "ct_head", "lipase"]
CLASSES = ["normal", "abnormal", "indeterminate"]
DEPARTMENTS = ["emergency_medicine", "internal_medicine", "surgery", "cardiology", "neurology", "orthopedics",
               "obstetrics_gynecology"]
ISSUES = ["duplicate", "dose_mismatch", "allergy_conflict"]
VOICE_FIELDS = {
    "chief_complaint": ["chest pain", "shortness of breath", "abdominal pain", "headache", "fever"],
    "onset": ["today", "yesterday", "3 days ago", "1 week ago"],
    "pain_score": ["2", "4", "6", "8"],
    "allergies": ["none", "penicillin", "sulfa", "ibuprofen"],
    "current_medications": ["none", "metformin", "amlodipine", "atorvastatin"],
}
ITEMS = {
    "model_cxr": "Model, by modality", "model_ct_seg": "Model, by modality", "care_pathway": "Case Graph",
    "provider_swap": "Provider swap", "voice_intake": "Voice Agent", "department": "Department suggestion",
    "pharma": "Pharma Agent", "abstention": "Abstention", "replay": "Replay / Regenerate",
}


def r3(x: float) -> float:
    return round(float(x), 3)


def rec(pid: str, dp: str, task: str, **kw) -> dict:
    return {"patient_id": pid, "decision_point_id": dp, "task": task, **kw}


def generate() -> tuple[list[dict], list[dict], list[str]]:
    rng = np.random.Generator(np.random.PCG64(SEED))
    pids = [f"SYN-P{i:03d}" for i in range(1, N_PATIENTS + 1)]
    sys_rows: list[dict] = []
    cmp_rows: list[dict] = []

    def add(pid, dp, task, common, system, comparators):
        sys_rows.append(rec(pid, dp, task, **common, **system))
        for name, fields in comparators.items():
            cmp_rows.append(rec(pid, dp, task, comparator=name, **common, **fields))

    for n, pid in enumerate(pids):
        n_dp = int(rng.integers(1, 4))
        dps = [f"T{j + 1}" for j in range(n_dp)]

        # Model, by modality: CXR findings (multilabel) - one study per patient.
        truth = [f for f in FINDINGS if rng.random() < 0.3]

        def scores(a_pos, b_pos, a_neg, b_neg):
            return {f: r3(rng.beta(a_pos, b_pos) if f in truth else rng.beta(a_neg, b_neg)) for f in FINDINGS}

        s_sys, s_base = scores(5, 2, 2, 5), scores(3, 2.5, 2.5, 3)
        add(pid, "CXR1", "model_cxr", {"y_true": truth},
            {"y_score": s_sys, "y_pred": [f for f in FINDINGS if s_sys[f] >= 0.5]},
            {"base_model_before_finetune": {"y_score": s_base, "y_pred": [f for f in FINDINGS if s_base[f] >= 0.5]}})

        # Model, by modality: CT segmentation (Dice) - first 20 patients, one case each.
        if n < 20:
            gold = np.zeros((3, 4, 4), dtype=int)
            if n != 0:  # patient 1: empty gold and empty prediction (declared empty_empty value applies)
                z, y, x = (int(v) for v in rng.integers(0, 2, size=3))
                gold[z:z + 2, y:y + 2 + int(rng.integers(0, 2)), x:x + 3] = 1

            def noisy(p_flip):
                if n == 0:
                    return gold.tolist()
                flip = rng.random(gold.shape) < p_flip
                return np.where(flip, 1 - gold, gold).tolist()

            add(pid, "CT1", "model_ct_seg", {"mask_true": gold.tolist()}, {"mask_pred": noisy(0.08)},
                {"base_model_before_finetune": {"mask_pred": noisy(0.2)}})

        # Department suggestion - first decision point.
        dept = DEPARTMENTS[int(rng.integers(0, len(DEPARTMENTS)))]
        others = [d for d in DEPARTMENTS if d != dept]
        rng.shuffle(others)
        pos = int(rng.choice([0, 0, 0, 1, 2, 4]))
        ranked = others[:pos] + [dept] + others[pos:]
        sys_rows.append(rec(pid, "T1", "department", y_true=dept, ranked=ranked))

        # Voice Agent - first 30 patients, one interview each.
        if n < 30:
            gold_f = {k: v[int(rng.integers(0, len(v)))] for k, v in VOICE_FIELDS.items()}

            def extract(p_ok):
                out = {}
                for k, v in gold_f.items():
                    u = rng.random()
                    if u < p_ok:
                        out[k] = v.upper() if rng.random() < 0.2 else v  # normalization makes case irrelevant
                    elif u < p_ok + (1 - p_ok) / 2:
                        out[k] = VOICE_FIELDS[k][(VOICE_FIELDS[k].index(v) + 1) % len(VOICE_FIELDS[k])]
                return out

            add(pid, "V1", "voice_intake", {"gold_fields": gold_f},
                {"extracted_fields": extract(0.85), "response_latency_s": r3(rng.uniform(0.8, 2.5)),
                 "total_time_s": r3(rng.uniform(120, 400))},
                {"form_filling": {"extracted_fields": extract(0.92), "response_latency_s": r3(rng.uniform(4, 15)),
                                  "total_time_s": r3(rng.uniform(200, 600))}})

        # Pharma Agent - recall on synthetic error injection (P001-P020), precision on the
        # pharmacist-reviewed sample (P021-P035).
        if n < 35:
            population = "synthetic_error_injection" if n < 20 else "pharmacist_review"

            def issues(k):
                return [{"type": ISSUES[int(rng.integers(0, 3))], "id": f"{pid}-i{j}"} for j in range(k)]

            if population == "synthetic_error_injection":
                injected = issues(int(rng.integers(1, 4)))

                def detect(p_det):
                    fl = [i for i in injected if rng.random() < p_det]
                    if rng.random() < 0.2:
                        fl.append({"type": ISSUES[int(rng.integers(0, 3))], "id": f"{pid}-fp"})
                    return fl

                add(pid, "M1", "pharma", {"population": population, "gold": injected},
                    {"flagged": detect(0.85)}, {"rules_only": {"flagged": detect(0.65)}})
            else:
                def review(p_conf):
                    fl = issues(int(rng.integers(1, 4)))
                    return {"flagged": fl, "gold": [i for i in fl if rng.random() < p_conf]}

                s, c = review(0.8), review(0.7)
                sys_rows.append(rec(pid, "M1", "pharma", population=population, **s))
                cmp_rows.append(rec(pid, "M1", "pharma", comparator="rules_only", population=population, **c))

        # Replay / Regenerate - first 30 patients, one graph each.
        if n < 30:
            n_nodes = int(rng.integers(4, 9))
            orig = {f"node{j}": f"{int(rng.integers(0, 2**32)):08x}" for j in range(n_nodes)}
            rep = dict(orig)
            if n == 7:  # one non-deterministic node, reported honestly
                rep["node1"] = "ffffffff"
            add(pid, "G1", "replay", {"original_hashes": orig, "n_nodes_full": n_nodes},
                {"replay_hashes": rep, "n_recomputed": int(rng.integers(1, 4))},
                {"full_graph_recompute": {"replay_hashes": dict(orig), "n_recomputed": n_nodes}})

        for dp in dps:
            # Case Graph - suggested next tests vs tests later ordered.
            ordered = list(rng.choice(TESTS, size=int(rng.integers(1, 4)), replace=False))

            def suggest(p_hit):
                keep = [t for t in ordered if rng.random() < p_hit]
                rest = [t for t in TESTS if t not in keep]
                rng.shuffle(rest)
                s = keep + rest[: 4 - len(keep)] if len(keep) < 4 else keep[:4]
                rng.shuffle(s)
                return [str(t) for t in s]

            add(pid, dp, "care_pathway", {"ordered": [str(t) for t in ordered]},
                {"suggested": suggest(0.65), "n_calls": int(rng.integers(3, 7)), "latency_s": r3(rng.uniform(2, 8))},
                {"single_prompt_no_graph": {"suggested": suggest(0.45), "n_calls": 1,
                                            "latency_s": r3(rng.uniform(3, 10))}})

            # Provider swap - same task via different providers.
            y = CLASSES[int(rng.choice(3, p=[0.5, 0.35, 0.15]))]

            def answer(p_ok):
                return y if rng.random() < p_ok else CLASSES[(CLASSES.index(y) + 1 + int(rng.integers(0, 2))) % 3]

            add(pid, dp, "provider_swap", {"y_true": y},
                {"y_pred": answer(0.82), "latency_s": r3(rng.uniform(1, 6)), "cost": r3(rng.uniform(0.01, 0.03))},
                {"external_model": {"y_pred": answer(0.85), "latency_s": r3(rng.uniform(2, 12)),
                                    "cost": r3(rng.uniform(0.05, 0.12))},
                 "classifier": {"y_pred": answer(0.7), "latency_s": r3(rng.uniform(0.05, 0.3)), "cost": 0.0}})

            # Abstention - system may abstain (y_pred null); comparator always answers.
            ya = CLASSES[int(rng.integers(0, 3))]
            yp = None if rng.random() < 0.2 else (ya if rng.random() < 0.88 else CLASSES[(CLASSES.index(ya) + 1) % 3])
            ca = ya if rng.random() < 0.76 else CLASSES[(CLASSES.index(ya) + 2) % 3]
            add(pid, dp, "abstention", {"y_true": ya}, {"y_pred": yp}, {"always_answer": {"y_pred": ca}})

    return sys_rows, cmp_rows, pids


def metric(mid, task, name, params=None, primary=False):
    return {"id": mid, "item": ITEMS[task], "task": task, "name": name, "params": params or {}, "primary": primary}


def manifest(pids: list[str]) -> dict:
    ms = [
        metric("cxr_macro_f1", "model_cxr", "multilabel_macro_f1", {"labels": FINDINGS}, True),
        metric("cxr_auroc", "model_cxr", "auroc", {"mode": "multilabel", "labels": FINDINGS}),
        metric("ct_dice", "model_ct_seg", "dice", {"empty_empty": 1.0}, True),
        metric("cp_hit3", "care_pathway", "hit_at_k", {"k": 3}, True),
        metric("cp_f1", "care_pathway", "set_prf", {"component": "f1"}),
        metric("cp_calls", "care_pathway", "calls_per_patient"),
        metric("cp_latency", "care_pathway", "latency_per_patient"),
        metric("ps_accuracy", "provider_swap", "accuracy", {}, True),
        metric("ps_macro_f1", "provider_swap", "macro_f1", {"labels": CLASSES}),
        metric("ps_latency_p90", "provider_swap", "latency_summary", {"component": "p90"}),
        metric("ps_cost", "provider_swap", "cost_per_patient"),
        metric("voice_f1", "voice_intake", "field_prf", {"component": "f1"}, True),
        metric("voice_cc_recall", "voice_intake", "field_prf", {"component": "recall", "field": "chief_complaint"}),
        metric("voice_resp_median", "voice_intake", "response_latency", {"component": "median"}),
        metric("voice_total_mean", "voice_intake", "total_time", {"component": "mean"}),
        metric("dept_top1", "department", "topk_accuracy", {"k": 1}, True),
        metric("dept_top3", "department", "topk_accuracy", {"k": 3}),
    ]
    for t in ISSUES:
        ms.append(metric(f"pharma_{t}_precision", "pharma", "per_issue_type_pr",
                         {"issue_type": t, "component": "precision"}, t == "allergy_conflict"))
        ms.append(metric(f"pharma_{t}_recall", "pharma", "per_issue_type_pr",
                         {"issue_type": t, "component": "recall"}, t == "allergy_conflict"))
    ms.append(metric("pharma_duplicate_f1", "pharma", "per_issue_type_pr", {"issue_type": "duplicate", "component": "f1"}))
    ms += [
        metric("abst_coverage", "abstention", "coverage"),
        metric("abst_selective_accuracy", "abstention", "selective_accuracy", {}, True),
        metric("replay_graph", "replay", "replay_determinism", {"component": "graph_fraction"}, True),
        metric("replay_node", "replay", "replay_determinism", {"component": "node_fraction"}),
        metric("regen_ratio", "replay", "recomputed_nodes", {"component": "ratio"}),
        metric("regen_median", "replay", "recomputed_nodes", {"component": "median_recomputed"}),
    ]
    return {
        "$comment": "Toy synthetic manifest for slice s8. Research prototype - not for clinical use.",
        "manifest_version": "1.0",
        "evaluation_id": "s8-toy-test-0001",
        "slice": "s8",
        "dataset": {"name": "s8-toy-synthetic", "version": "0.1.0", "data_class": "synthetic"},
        "split": "test",
        "split_version": "toy-split-v1",
        "split_patient_list": pids,
        "task_patient_lists": {
            "model_ct_seg": pids[:20],
            "voice_intake": pids[:30],
            "replay": pids[:30],
            "pharma:synthetic_error_injection": pids[:20],
            "pharma:pharmacist_review": pids[20:35],
        },
        "metrics": ms,
        "comparators": [
            {"name": "base_model_before_finetune", "description": "Base model before fine-tuning",
             "tasks": ["model_cxr", "model_ct_seg"]},
            {"name": "single_prompt_no_graph", "description": "Same model, whole snapshot in one prompt, no graph",
             "tasks": ["care_pathway"]},
            {"name": "external_model", "description": "External model (synthetic data only)",
             "tasks": ["provider_swap"]},
            {"name": "classifier", "description": "Classifier provider", "tasks": ["provider_swap"]},
            {"name": "form_filling", "description": "Nurse form filling", "tasks": ["voice_intake"]},
            {"name": "rules_only", "description": "Rule-based checks only", "tasks": ["pharma"]},
            {"name": "always_answer", "description": "System that answers every case", "tasks": ["abstention"]},
            {"name": "full_graph_recompute", "description": "Recompute the whole graph", "tasks": ["replay"]},
        ],
        "thresholds": [
            {"metric": "cp_hit3", "op": ">=", "value": 0.5, "rule": "ci_lower"},
            {"metric": "dept_top3", "op": ">=", "value": 0.8, "rule": "point"},
            {"metric": "abst_selective_accuracy", "op": ">=", "value": 0.8, "rule": "ci_lower"},
            {"metric": "ps_latency_p90", "op": "<=", "value": 10.0, "rule": "ci_upper"},
            {"metric": "replay_graph", "op": ">=", "value": 0.95, "rule": "point"},
        ],
        "bootstrap": {"n_boot": 2000, "seed": SEED, "ci_level": 0.95, "method": "percentile"},
        "expert_review": {"done": False, "n_reviewers": 0},
    }


def _jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows)


def main() -> None:
    sys_rows, cmp_rows, pids = generate()
    (HERE / "toy_predictions.jsonl").write_text(_jsonl(sys_rows), encoding="utf-8")
    (HERE / "toy_comparator.jsonl").write_text(_jsonl(cmp_rows), encoding="utf-8")
    (HERE / "toy_manifest_test.json").write_text(json.dumps(manifest(pids), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(sys_rows)} system rows, {len(cmp_rows)} comparator rows, {len(pids)} patients")


if __name__ == "__main__":
    main()
