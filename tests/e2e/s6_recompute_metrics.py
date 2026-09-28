"""s6 checker: recompute Table 3.2 point estimates from committed predictions/comparators and gold (independent)."""
import json, sys
from collections import Counter
from pathlib import Path
DS = Path(sys.argv[1]); EV = Path(sys.argv[2])
def rows(p): return [json.loads(l) for l in open(p)]
gold = {}
for g in (DS / "gold").glob("*/*.json"):
    d = json.loads(g.read_text())
    for r in d["decision_times"]:
        gold[f"{d['case_id']}:{r['decision_point']}"] = (d["split"], d["patient_ref"], r["care"])
cnt = Counter(c for s, p, care in gold.values() if s == "train" and care["evaluable"] for c in care["next_info"])
prior = [c for c, _ in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
out = {"train_prior_top3": prior}
for sp in ("dev", "test"):
    P = rows(EV / f"predictions_{sp}.jsonl"); C = rows(EV / f"comparator_{sp}.jsonl")
    by = lambda rs, t: [r for r in rs if r["task"] == t]
    cov = by(P, "care_coverage")
    # gold alignment
    mism = 0
    for r in cov:
        s, pid, care = gold[r["decision_point_id"]]
        mism += (s != sp) or (pid != r["patient_id"]) or (r["y_true"] != care["expected_action"])
    ev_rows = [k for k, (s, p, c) in gold.items() if s == sp and c["evaluable"]]
    ni = by(P, "care_next_info")
    mism += sorted(r["decision_point_id"] for r in ni) != sorted(ev_rows)
    mism += sum(sorted(r["ordered"]) != sorted(gold[r["decision_point_id"]][2]["next_info"]) for r in ni)
    hit = lambda s, o: bool(set(s[:3]) & set(o))
    ans = [r for r in ni if r["suggested"] is not None]
    sel = sum(hit(r["suggested"], r["ordered"]) for r in ans) / len(ans)
    aa = [r for r in C if r["comparator"] == "always_answer"]
    aao = [r for r in C if r["comparator"] == "always_answer_on_answered" and r["suggested"] is not None]
    tp = [r for r in C if r["comparator"] == "train_prior" and r["suggested"] is not None]
    tp_ok = all(r["suggested"] == prior for r in tp)
    px = by(P, "care_ordered_proxy"); pxa = [r for r in px if r["suggested"] is not None]
    mism += sum(sorted(r["ordered"]) != sorted(gold[r["decision_point_id"]][2]["ordered_after_T"]) for r in px)
    pw = by(P, "care_pathway"); pwa = [r for r in pw if r["y_pred"] is not None]
    mism += sum(r["y_true"] != gold[r["decision_point_id"]][2]["pathway"] for r in pw)
    out[sp] = {
        "gold_mismatches": mism,
        "coverage": f"{sum(r['y_pred'] is not None for r in cov)}/{len(cov)}",
        "coverage_point": sum(r['y_pred'] is not None for r in cov) / len(cov),
        "n_patients": len({r['patient_id'] for r in cov}),
        "evaluable_rows": len(ni), "answered_evaluable": len(ans),
        "selective_hit3": sel,
        "always_answer_hit3_all_evaluable": sum(hit(r["suggested"], r["ordered"]) for r in aa) / len(aa), "n_aa": len(aa),
        "always_answer_on_answered": sum(hit(r["suggested"], r["ordered"]) for r in aao) / len(aao), "n_aao": len(aao),
        "train_prior_hit3": sum(hit(r["suggested"], r["ordered"]) for r in tp) / len(tp), "train_prior_is_static_top3": tp_ok,
        "proxy_hit3": f"{sum(hit(r['suggested'], r['ordered']) for r in pxa)}/{len(pxa)}",
        "pathway_top1": f"{sum(r['y_pred'] == r['y_true'] for r in pwa)}/{len(pwa)}",
        "abstained_evaluable": len(ni) - len(ans),
    }
print(json.dumps(out, indent=1))
