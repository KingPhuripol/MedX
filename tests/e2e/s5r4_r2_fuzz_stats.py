"""e2e-tester (s5r4 rev-4 checker): recount S5R4-A11/A12 fuzz statistics independently of the pytest assertions."""
import collections, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.pharma.mock_rules import parse_entry, DOSE_GRAMMAR  # noqa: E402
from tests.pharma_dose_fuzz import generate, harness, entry_tuple, ADVERSARIAL  # noqa: E402
from tests.pharma_dose_reference import reference_parse  # noqa: E402

t0 = time.time()
ph = generate()
n = len(ph)
st = collections.Counter(reference_parse(p.text)[0] for p in ph)
prods = collections.Counter(pid for p in ph for pid in p.productions)
adv = collections.Counter(c for p in ph for c in p.adversarial)
langs = collections.Counter(p.quantity_lang for p in ph)
rep = harness(entry_tuple(parse_entry), ph)
agree = sum(tuple(entry_tuple(parse_entry)(p.text)[:5]) == tuple(reference_parse(p.text)) for p in ph)
out = {"n": n, "status": dict(st), "resolved_frac": st["resolved"] / n, "unverifiable_frac": st["unverifiable"] / n,
       "productions": dict(prods), "missing_productions": sorted(set(DOSE_GRAMMAR) - set(prods)),
       "adversarial": dict(adv), "missing_classes": sorted(set(ADVERSARIAL) - set(adv)),
       "min_class": min(adv.values()), "min_prod": min(prods.values()),
       "lang": {k: v / n for k, v in langs.items()}, "safety": len(rep.safety), "status_disagree": len(rep.status),
       "reference_fail": len(rep.reference), "over_ten": len(rep.over_ten), "closure": len(rep.closure),
       "closure_counts": dict(rep.closure_counts), "canonical": len(rep.canonical),
       "impl_ref_agreement": f"{agree}/{n}", "seconds": round(time.time() - t0, 2)}
print(json.dumps(out, indent=1, ensure_ascii=False))
