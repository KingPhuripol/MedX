"""e2e-tester (s5r4 checker): S5R4-A11/A12/A13. Run the builder's fuzz harness (s5r3 §F, seed 5303) on HEAD and on
older parsers loaded from `git show <rev>:backend/app/pharma/mock_rules.py`; report strata, closure and misreads.
Run from repo root: .venv/bin/python tests/e2e/s5r4_fuzz_old_parsers.py [--out FILE]
"""
import argparse, collections, importlib.util, json, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from tests.pharma_dose_fuzz import entry_tuple, generate, harness, REV3_CLASSES  # noqa: E402
from tests.pharma_dose_reference import reference_parse  # noqa: E402


def load(rev):
    src = subprocess.run(["git", "show", f"{rev}:backend/app/pharma/mock_rules.py"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout
    p = Path(tempfile.mkdtemp()) / f"mock_rules_{rev}.py"
    p.write_text(src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"mock_rules_{rev}", p)
    m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)
    return m


ap = argparse.ArgumentParser(); ap.add_argument("--out"); a = ap.parse_args()
t0 = time.perf_counter(); phrases = generate(); tgen = time.perf_counter() - t0
refs = [reference_parse(p.text) for p in phrases]
n = len(phrases)
cls_counts = collections.Counter(c for p in phrases for c in p.adversarial)
prod_counts = collections.Counter(c for p in phrases for c in p.productions)
qlang = collections.Counter(p.quantity_lang for p in phrases)
out = {"n_phrases": n, "gen_seconds": round(tgen, 2),
       "ref_resolved_frac": sum(r[0] == "resolved" for r in refs) / n,
       "ref_unverifiable_frac": sum(r[0] == "unverifiable" for r in refs) / n,
       "quantity_lang_frac": {k: v / n for k, v in qlang.items()},
       "min_class_count": min(cls_counts.values()), "rev3_class_counts": {c: cls_counts[c] for c in REV3_CLASSES},
       "classes_below_20": [c for c, v in cls_counts.items() if v < 20],
       "productions_below_20": [c for c, v in prod_counts.items() if v < 20], "production_counts": dict(prod_counts)}
for rev in ("1c1f476", "29d8b20", "e6a354f", "HEAD"):
    if rev == "HEAD":
        from app.pharma.mock_rules import parse_entry
    else:
        parse_entry = load(rev).parse_entry
    t0 = time.perf_counter(); rep = harness(entry_tuple(parse_entry), phrases); dt = time.perf_counter() - t0
    out[rev] = {"seconds": round(dt, 2), "safety_misreads": len(rep.safety), "status_reason_disagreements": len(rep.status),
                "reference_check_failures": len(rep.reference), "resolved_over_ten": len(rep.over_ten),
                "closure_violations": len(rep.closure), "closure_trigger_counts": dict(rep.closure_counts),
                "misread_classes": dict(rep.safety_classes), "examples": rep.safety[:3]}
    print(rev, {k: v for k, v in out[rev].items() if k not in ("examples", "misread_classes")})
print({k: v for k, v in out.items() if not isinstance(v, dict) or k in ("rev3_class_counts", "quantity_lang_frac")})
print("e6a354f rev3 misreads:", {c: out["e6a354f"]["misread_classes"].get(c, 0) for c in REV3_CLASSES})
print("29d8b20:", {c: out["29d8b20"]["misread_classes"].get(c, 0) for c in ("th_half_time", "per_unit", "qv_over")})
if a.out: Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
