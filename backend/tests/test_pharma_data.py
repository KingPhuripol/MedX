"""S5 data, harness and config tests (A05-A07, A14, A15, A18)."""

import json
import re
from datetime import datetime

from app.pharma.eval.inject import build_cases, load_patients, log_lines
from app.pharma.eval.run_eval import THRESHOLDS, evaluate
from app.pharma.fixtures.build import build_all, dumps, manifest, frozen_split_sha256
from app.pharma.formulary import DATA_DIR, load_formulary
from app.pharma.models import ISSUE_TYPES

from .conftest import REPO_ROOT

PHARMA_DIR = REPO_ROOT / "backend" / "app" / "pharma"
ATC_RE = re.compile(r"^[A-Z]\d\d[A-Z]{2}\d\d$")
TMT_RE = re.compile(r"^\d{6,7}$")  # TMTID (numeric concept id); rxcui values are exempt below
NLM_ATTRIBUTION = (
    "This product uses publicly available data from the U.S. National Library of Medicine (NLM), "
    "National Institutes of Health, Department of Health and Human Services; NLM is not responsible "
    "for the product and does not endorse or recommend this or any other product."
)
LICENCE_URLS = (
    "https://www.nlm.nih.gov/research/umls/rxnorm/docs/termsofservice.html",
    "https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html",
    "https://lhncbc.nlm.nih.gov/RxNav/TermsofService.html",
    "https://lhncbc.nlm.nih.gov/RxNav/applications/RxClassIntro.html",
    "https://www.nlm.nih.gov/research/umls/sourcereleasedocs/current/MED-RT/index.html",
    "https://www.whocc.no/copyright_disclaimer/",
    "https://this.or.th/service/tmt/download/",
    "https://this.or.th/service/tmt/",
)


def _strings(obj, key=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v, key)
    elif isinstance(obj, str):
        yield key, obj


def test_formulary_licence_and_coverage():
    raw = json.loads((DATA_DIR / "formulary.json").read_text(encoding="utf-8"))
    meta = raw["metadata"]
    assert meta["attribution"] == NLM_ATTRIBUTION
    assert meta["verified_on"] and meta["field_sources"]["ingredients.rxcui"]
    assert {"ingredients.name", "ingredients.rxcui", "classes.name", "products.aliases"} <= set(meta["field_sources"])
    for path in (DATA_DIR / "formulary.json", DATA_DIR / "cross_reactivity.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in _strings(data):
            assert not ATC_RE.match(value.strip()), f"ATC-like code in {path.name}: {value}"
            if key != "rxcui":
                assert not TMT_RE.match(value.strip()), f"TMT-like id in {path.name}: {value}"
    ingredients = raw["ingredients"]
    assert len(ingredients) >= 40
    for ing in ingredients.values():
        assert re.fullmatch(r"\d+", ing["rxcui"]) and ing["verified_on"] and ing["tmt_id"] is None
    assert sum(c["duplication_relevant"] for c in raw["classes"].values()) >= 12
    assert sum(len(p["ingredients"]) > 1 for p in raw["products"]) >= 3
    thai = [a for p in raw["products"] for a in p["aliases"] if a["kind"] in ("th_brand", "th_script")]
    assert len(thai) >= 15 and all(a["alias_source"] for a in thai)
    classes_needed = {"dhp_ccb", "acei", "arb", "statin", "biguanide", "ppi", "nsaid", "penicillin",
                      "cephalosporin", "sulfonamide_antibacterial", "vka", "factor_xa"}
    assert classes_needed <= set(raw["classes"])
    form = load_formulary()
    assert form.version == meta["formulary_version"]
    decisions = (REPO_ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    section = decisions[decisions.index("Formulary licence"):]
    assert re.search(r"2026-09-26", decisions)
    for url in LICENCE_URLS:
        assert url in section, url
    page = (REPO_ROOT / "web" / "lib" / "pharma.ts").read_text(encoding="utf-8")
    assert NLM_ATTRIBUTION in page


def test_fixtures_valid():
    stored = json.loads((PHARMA_DIR / "fixtures" / "patients.json").read_text(encoding="utf-8"))
    patients = stored["patients"]
    assert (PHARMA_DIR / "fixtures" / "patients.json").read_text(encoding="utf-8") == dumps(
        {"generator_version": stored["generator_version"], "seed": stored["seed"], "patients": build_all()}
    ), "patients.json is not reproducible from the generator"
    assert len(patients) >= 30
    splits = [p["split"] for p in patients]
    assert splits.count("dev") >= 20 and splits.count("test") >= 10
    assert len({p["patient_ref"] for p in patients}) == len(patients)  # one split per patient
    frozen = json.loads((PHARMA_DIR / "fixtures" / "test_manifest.json").read_text(encoding="utf-8"))
    assert frozen["sha256"] == frozen_split_sha256(patients) == manifest(patients)["sha256"]
    assert frozen["patient_refs"] == [p["patient_ref"] for p in patients if p["split"] == "test"]
    for p in patients:
        snap = p["snapshot"]
        assert p["data_class"] == snap["data_class"] == "synthetic"
        assert {s["source_type"] for s in snap["sources"]} >= {"home_list", "new_order"}
        for item in snap["sources"] + snap["allergies"]:
            assert item["available_at_time"] and item["provenance"] and item["version"]
            assert datetime.fromisoformat(item["available_at_time"]) <= datetime.fromisoformat(snap["as_of"])
        for s in snap["sources"]:
            assert len(p["gold"][s["source_type"]]) == len(s["entries"])
    assert sum(p["meta"]["documented_discontinuation"] for p in patients) >= 5
    assert sum(p["meta"]["uses_thai_mentions"] for p in patients) >= 10
    assert sum(len(p["snapshot"]["sources"]) == 3 for p in patients) >= 25
    demo = json.loads((PHARMA_DIR / "fixtures" / "demo.json").read_text(encoding="utf-8"))
    assert all(c["snapshot"]["data_class"] == "synthetic" for c in demo["cases"])


def test_injection_reproducible():
    patients = load_patients()
    a, b = build_cases(patients), build_cases(patients)
    assert log_lines(a).encode() == log_lines(b).encode()
    lines = [json.loads(line) for line in log_lines(a).splitlines()]
    assert len(lines) == len(a) == len(patients) * len(ISSUE_TYPES)
    for t in ISSUE_TYPES:
        assert sum(line["type"] == t for line in lines) >= 30
    for line in lines:
        assert set(line) == {"case_id", "patient_ref", "split", "type", "source", "before", "after", "expected"}
        assert set(line["expected"]) == {"type", "ingredients", "sources"} and line["expected"]["type"] == line["type"]
    assert {line["split"] for line in lines} == {"dev", "test"}
    committed = REPO_ROOT / "slices" / "s5" / "eval" / "injection_log.jsonl"
    assert committed.read_text(encoding="utf-8") == log_lines(a)


def test_eval_thresholds(tmp_path):
    r = evaluate(tmp_path)
    assert (tmp_path / "results.json").exists() and (tmp_path / "injection_log.jsonl").exists()
    for scope in ("test", "all"):
        for t in ISSUE_TYPES:
            rec = r["recall"][t][scope]
            assert rec["recall"] >= THRESHOLDS["recall_min_per_type"], (scope, t, rec)
            assert rec["ci95"][0] is not None
            assert r["precision"][t][scope]["precision"] is not None
            if scope == "all":
                assert rec["cases"] >= THRESHOLDS["min_cases_per_type"]
        assert r["clean_false_alerts"][scope]["mean_per_list"] <= THRESHOLDS["clean_false_alerts_max"]
        assert r["extra_issues_per_injected_case"][scope]["mean_per_case"] <= THRESHOLDS["extra_issues_per_case_max"]
        assert r["extraction"][scope]["overall_accuracy"] >= THRESHOLDS["extraction_accuracy_min"]
        assert r["extraction"][scope]["fabricated_values"] == 0
        for mode in ("rules_only", "rules_plus_model"):
            assert r["modes"][mode][scope]["recall"]["omission"]["recall"] is not None
    assert r["mode_equality"]["fraction"] == 1.0
    assert r["issue_sources_complete"]["violations"] == 0
    committed = json.loads((REPO_ROOT / "slices" / "s5" / "eval" / "results.json").read_text(encoding="utf-8"))
    assert committed == json.loads((tmp_path / "results.json").read_text(encoding="utf-8")), "re-run make pharma-eval"


def test_makefile_port_defaults():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^API_PORT \?= 8000$", makefile, re.MULTILINE)
    assert re.search(r"^WEB_PORT \?= 3000$", makefile, re.MULTILINE)
    assert "API_ORIGIN=" in makefile
    assert "--port $(API_PORT)" in makefile and "--host 127.0.0.1" in makefile
    pw = (REPO_ROOT / "web" / "playwright.config.ts").read_text(encoding="utf-8")
    assert "process.env" in pw and "baseURL" in pw
