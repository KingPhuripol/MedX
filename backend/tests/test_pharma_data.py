"""S5 data, harness and config tests (A05-A07, A14, A15, A18)."""

import json
import re
from datetime import datetime

from collections import Counter
from functools import lru_cache

from app.pharma.eval.inject import (
    DETECTION_FORMS,
    SURFACE_FORMS,
    build_cases,
    build_surface_cases,
    load_patients,
    log_lines,
    surface_log_lines,
)
from app.pharma.eval.run_eval import THRESHOLDS, bootstrap_stats, evaluate
from app.pharma.mock_rules import parse_entry
from app.pharma.fixtures.build import build_all, dumps, fixtures_file_sha256, manifest, frozen_split_sha256
from app.pharma.formulary import DATA_DIR, load_formulary
from app.pharma.models import ISSUE_TYPES

from .conftest import REPO_ROOT

PHARMA_DIR = REPO_ROOT / "backend" / "app" / "pharma"
ORIGINAL_TEST_REFS = [f"s5-p{n:02d}" for n in range(3, 31, 3)]  # the 10 s5 v1 test patients
MANIFEST = PHARMA_DIR / "fixtures" / "test_manifest.json"


V2_TEST_REFS = [f"s5-p{n:02d}" for n in range(3, 97, 3)]  # manifest v2 test split (32 refs)
V2_SHA256 = "313e44b314097bf8980d353b3d28f739223fb848c5fe8f9cabdf9b307771dad9"
BILINGUAL_FORMS = ("SF-NXM", "SF-FRAC", "SF-VAR", "SF-LIQ", "SF-MULTI", "SF-FREQ")


@lru_cache(maxsize=1)
def _cases() -> tuple[dict, ...]:
    return tuple(build_cases(load_patients()))


@lru_cache(maxsize=1)
def _surface_cases() -> tuple[dict, ...]:
    return tuple(build_surface_cases(load_patients()))

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
    assert stored["generator_version"].startswith("s5-fixtures-3.")
    assert len(patients) >= 90
    splits = [p["split"] for p in patients]
    assert splits.count("dev") >= 60 and splits.count("test") >= 30
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert frozen["generator_version"] == stored["generator_version"]
    assert frozen["sha256"] == frozen_split_sha256(patients) == manifest(patients)["sha256"]
    assert frozen["fixtures_file_sha256"] == fixtures_file_sha256()
    assert frozen == manifest(patients)
    assert frozen["patient_refs"] == [p["patient_ref"] for p in patients if p["split"] == "test"]
    for p in patients:
        snap = p["snapshot"]
        assert p["data_class"] == snap["data_class"] == "synthetic"
        assert [s["source_type"] for s in snap["sources"]] == ["home_list", "patient_reported", "new_order"]
        for item in snap["sources"] + snap["allergies"]:
            assert item["available_at_time"] and item["provenance"] and item["version"]
            assert datetime.fromisoformat(item["available_at_time"]) <= datetime.fromisoformat(snap["as_of"])
        for s in snap["sources"]:
            assert len(p["gold"][s["source_type"]]) == len(s["entries"]) >= 1
    for scope, disc_min, thai_min in (("all", 15, 30), ("test", 5, 10)):
        picked = [p for p in patients if scope == "all" or p["split"] == "test"]
        assert sum(p["meta"]["documented_discontinuation"] for p in picked) >= disc_min, scope
        assert sum(p["meta"]["uses_thai_mentions"] for p in picked) >= thai_min, scope
    demo = json.loads((PHARMA_DIR / "fixtures" / "demo.json").read_text(encoding="utf-8"))
    assert all(c["snapshot"]["data_class"] == "synthetic" for c in demo["cases"])


def test_fixture_split_disjoint():
    patients = load_patients()
    refs = [p["patient_ref"] for p in patients]
    assert len(set(refs)) == len(refs)  # each patient appears once, so in exactly one split
    by_split = {s: {p["patient_ref"] for p in patients if p["split"] == s} for s in ("dev", "test")}
    assert not by_split["dev"] & by_split["test"] and by_split["dev"] | by_split["test"] == set(refs)
    for p in patients:  # every item of a patient carries that patient's ref only
        snap = p["snapshot"]
        assert snap["patient_ref"] == p["patient_ref"]
        for item in snap["sources"] + snap["allergies"]:
            assert item["evidence_ref"].startswith(p["patient_ref"] + "/")
    split_of = dict(zip(refs, (p["split"] for p in patients)))
    for case in _cases():  # split assigned by patient before injection
        assert case["split"] == split_of[case["patient_ref"]] and case["snapshot"]["patient_ref"] == case["patient_ref"]


def test_original_test_refs_kept():
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(ORIGINAL_TEST_REFS) == 10
    assert set(ORIGINAL_TEST_REFS) <= set(frozen["patient_refs"])
    split_of = {p["patient_ref"]: p["split"] for p in load_patients()}
    assert all(split_of[r] == "test" for r in ORIGINAL_TEST_REFS)


def test_clean_fixtures_fully_specified():
    for p in load_patients():
        for source in p["snapshot"]["sources"]:
            for entry, gold in zip(source["entries"], p["gold"][source["source_type"]]):
                assert gold["dose_value"] is not None and gold["dose_unit"] and gold["frequency_code"], (p["patient_ref"], gold)
                assert (gold["dose_status"], gold["frequency_status"]) == ("resolved", "recognised"), gold
                parsed = parse_entry(entry["text"])
                assert parsed["dose_value"] is not None and parsed["dose_unit"] and parsed["frequency_code"], entry
                assert (parsed["dose_status"], parsed["frequency_status"]) == ("resolved", "recognised"), entry
                assert parsed["quantity"] == gold["quantity"], entry


def test_quantity_form_clean_patients():
    """v3: >= 10 test (>= 30 all) clean patients carry an entry in a quantity form whose dose per administration
    equals the other sources' dose written another way."""
    patients = load_patients()
    for scope, minimum in (("test", 10), ("all", 30)):
        picked = [p for p in patients if p["meta"]["quantity_form"] and (scope == "all" or p["split"] == "test")]
        assert len(picked) >= minimum, scope
    for p in patients:
        qf = p["meta"]["quantity_form"]
        if not qf:
            continue
        g = p["gold"][qf["source_type"]][qf["entry_index"]]
        assert g["quantity"] in (0.5, 2.0)
        per_admin = g["dose_value"] * g["quantity"]
        others = [o for st, gl in p["gold"].items() for o in gl if o["product"] == g["product"] and o is not g]
        assert others and all(o["dose_value"] * (o["quantity"] or 1) == per_admin and o["quantity"] in (None, 1.0) for o in others)


def test_injection_counts():
    cases = _cases()
    for scope, per_type in (("test", 30), ("all", 90)):
        picked = [c for c in cases if scope == "all" or c["split"] == "test"]
        counts = Counter(c["type"] for c in picked)
        assert set(counts) == set(ISSUE_TYPES) and len(ISSUE_TYPES) == 9 and "missing_field" in ISSUE_TYPES
        assert min(counts.values()) >= per_type, (scope, counts)
    mf = [c for c in cases if c["type"] == "missing_field" and c["split"] == "test"]
    fields, sources = Counter(c["field"] for c in mf), Counter(c["source"] for c in mf)
    assert fields["dose"] >= 10 and fields["frequency"] >= 10, fields
    assert all(sources[s] >= 5 for s in ("home_list", "patient_reported", "new_order")), sources
    # every test patient is injectable for all 9 types
    test_refs = {p["patient_ref"] for p in load_patients() if p["split"] == "test"}
    injected = Counter(c["patient_ref"] for c in cases if c["split"] == "test")
    assert set(injected) == test_refs and set(injected.values()) == {9}


def _entry_changes(before: list, after: list) -> int:
    key = lambda e: json.dumps(e, sort_keys=True, ensure_ascii=False)  # noqa: E731
    b, a = Counter(map(key, before)), Counter(map(key, after))
    return max(sum((b - a).values()), sum((a - b).values()))


def test_injection_one_per_patient_type():
    cases = _cases()
    pairs = Counter((c["patient_ref"], c["type"]) for c in cases)
    assert max(pairs.values()) == 1
    clean = {p["patient_ref"]: p["snapshot"] for p in load_patients()}
    for c in cases:
        snap, orig = c["snapshot"], clean[c["patient_ref"]]
        assert [s["source_type"] for s in snap["sources"]] == [s["source_type"] for s in orig["sources"]]
        changes = sum(_entry_changes(o["entries"], s["entries"]) for o, s in zip(orig["sources"], snap["sources"]))
        changes += _entry_changes(orig["allergies"], snap["allergies"])
        assert changes == 1, c["case_id"]  # exactly one injected discrepancy per case
        assert {k: v for k, v in snap.items() if k not in ("sources", "allergies")} == {
            k: v for k, v in orig.items() if k not in ("sources", "allergies")}


def test_injection_reproducible():
    patients = load_patients()
    a, b = build_cases(patients), build_cases(patients)
    assert log_lines(a).encode() == log_lines(b).encode()
    lines = [json.loads(line) for line in log_lines(a).splitlines()]
    assert len(lines) == len(a) == len(patients) * len(ISSUE_TYPES)
    base = {"case_id", "patient_ref", "split", "type", "source", "before", "after", "expected"}
    for line in lines:
        mf = line["type"] == "missing_field"
        assert set(line) == base | ({"field"} if mf else set())
        assert set(line["expected"]) == {"type", "ingredients", "sources"} | ({"field"} if mf else set())
        assert line["expected"]["type"] == line["type"]
        if mf:
            assert line["field"] == line["expected"]["field"] in ("dose", "frequency")
    assert {line["split"] for line in lines} == {"dev", "test"}
    committed = REPO_ROOT / "slices" / "s5" / "eval" / "injection_log.jsonl"
    assert committed.read_text(encoding="utf-8") == log_lines(a)


def test_extraction_null_preserved():
    """S5R-A08: mock extraction yields null for 100% of blanked missing_field fields (0 fabricated)."""
    keys = {"dose": ("dose_value", "dose_unit"), "frequency": ("frequency_code",)}
    mf = [c for c in _cases() if c["type"] == "missing_field"]
    assert len(mf) >= 90
    for c in mf:
        parsed = parse_entry(c["after"])
        assert all(parsed[k] is None for k in keys[c["field"]]), (c["case_id"], c["after"], parsed)
        other = keys["frequency" if c["field"] == "dose" else "dose"]
        assert all(parsed[k] is not None for k in other), c["case_id"]  # only the blanked field is missing


def test_bootstrap_resamples_patients():
    # Patient A: both cases detected; patient B: both missed. If cases were resampled independently the two
    # types' recalls would diverge in some resample; with patient resampling they are always equal.
    per_patient = {
        "A": {"clean_alerts": 0, "cases": [
            {"type": "dose_mismatch", "matched": 1, "extras": 0, "predicted": {}},
            {"type": "missing_field", "matched": 1, "extras": 0, "predicted": {}}]},
        "B": {"clean_alerts": 1, "cases": [
            {"type": "dose_mismatch", "matched": 0, "extras": 1, "predicted": {}},
            {"type": "missing_field", "matched": 0, "extras": 1, "predicted": {}}]},
    }
    stats = bootstrap_stats(per_patient, ["A", "B"], seed=1)
    assert len(stats) == 1000
    for s in stats:
        assert s["rec:dose_mismatch"] == s["rec:missing_field"]
        assert s["clean"] == s["extras"] == round(1 - s["rec:missing_field"], 4)
    assert {s["rec:missing_field"] for s in stats} == {0.0, 0.5, 1.0}
    assert bootstrap_stats(per_patient, ["A", "B"], seed=1) == stats  # fixed seed


def test_eval_thresholds(tmp_path):
    r = evaluate(tmp_path)
    assert (tmp_path / "results.json").exists() and (tmp_path / "injection_log.jsonl").exists()
    assert "System Evaluation" in r["label"] and r["data_class"] == "synthetic"
    assert set(r["recall"]) == set(ISSUE_TYPES) and len(ISSUE_TYPES) == 9
    assert r["seeds"]["resamples"] == 1000 and r["seeds"]["resampling_unit"] == "patient"
    for scope, min_cases in (("test", 30), ("all", 90)):
        for t in ISSUE_TYPES:
            rec = r["recall"][t][scope]
            assert rec["cases"] >= min_cases, (scope, t, rec)
            assert rec["recall"] >= THRESHOLDS["recall_min_per_type"], (scope, t, rec)
            lo, hi = rec["ci95"]
            assert lo is not None and lo <= rec["recall"] <= hi
            elo, ehi = rec["ci95_exact"]
            assert 0 <= elo <= rec["recall"] <= ehi <= 1
            if rec["detected"] == rec["cases"]:
                assert elo < 1.0  # not degenerate, unlike the bootstrap interval at 100%
            assert r["precision"][t][scope]["precision"] is not None
        clean = r["clean_false_alerts"][scope]
        extra = r["extra_issues_per_injected_case"][scope]
        assert clean["mean_per_list"] <= THRESHOLDS["clean_false_alerts_max"], (scope, r["alert_breakdown"]["clean_lists"][scope])
        assert extra["mean_per_case"] <= THRESHOLDS["extra_issues_per_case_max"], (scope, r["alert_breakdown"]["injected_case_extras"][scope])
        assert clean["ci95"][0] is not None and extra["ci95"][0] is not None
        assert r["extraction"][scope]["overall_accuracy"] >= THRESHOLDS["extraction_accuracy_min"]
        assert r["extraction"][scope]["fabricated_values"] == 0
        for mode in ("rules_only", "rules_plus_model"):
            assert r["modes"][mode][scope]["recall"]["missing_field"]["recall"] is not None
    assert r["extraction_null_preserved"]["fabricated"] == []
    assert r["mode_equality"]["fraction"] == 1.0
    assert r["issue_sources_complete"]["violations"] == 0
    raw = (tmp_path / "results.json").read_text(encoding="utf-8")
    assert "informational_mean_excluding_missing_field" not in raw
    for scope in ("test", "all"):
        minimum = THRESHOLDS["min_surface_cases_per_form"][scope]
        for form in SURFACE_FORMS:
            rec = r["surface_forms"][form][scope]
            floor = THRESHOLDS["surface_equiv_no_dose_issue_min" if form == "SF-EQUIV" else "surface_recall_min_per_form"]
            assert rec["cases"] >= minimum and rec["recall"] >= floor, (scope, form, rec)
            assert rec["ci95"][0] is not None and 0 <= rec["ci95_exact"][0] <= rec["recall"] <= rec["ci95_exact"][1] <= 1
        extra = r["surface_extra_issues_per_case"][scope]
        assert extra["mean_per_case"] <= THRESHOLDS["surface_extra_issues_per_case_max"], (scope, extra)
        for field in ("quantity", "dose_status", "frequency_status"):
            assert r["extraction"][scope]["field_accuracy"][field] >= THRESHOLDS["extraction_accuracy_min"]
    assert r["versions"]["mock_rules"] == "s5-mock-rules-2.2.0" and r["versions"]["template"] == "template-1.3.0"
    assert r["versions"]["dose_grammar"] == "s5-dose-grammar-1.2.0" and r["versions"]["pipeline"] == "s5-pipeline-2.4.0"
    assert r["versions"]["rules"] == "s5-rules-2.1.0" and r["versions"]["extract_task"] == "pharma.extract.v2"
    assert r["versions"]["rule_versions"]["dose_mismatch"] == "1.2.0"
    assert r["versions"]["rule_versions"]["missing_field"] == "2.1.0"
    committed = json.loads((REPO_ROOT / "slices" / "s5" / "eval" / "results.json").read_text(encoding="utf-8"))
    assert committed == json.loads(raw), "re-run make pharma-eval"
    assert (tmp_path / "injection_log_surface.jsonl").read_text(encoding="utf-8") == (
        REPO_ROOT / "slices" / "s5" / "eval" / "injection_log_surface.jsonl").read_text(encoding="utf-8")


def test_eval_summary_leads_with_exact():
    r = json.loads((REPO_ROOT / "slices" / "s5" / "eval" / "results.json").read_text(encoding="utf-8"))
    assert "System Evaluation" in r["label"] and "not clinical performance" in r["label"]
    recall_lines = [line for line in r["summary"] if " recall " in line]
    assert len(recall_lines) == 2 * (len(ISSUE_TYPES) + len(SURFACE_FORMS))
    for line in recall_lines:
        assert "Clopper–Pearson 95%" in line and "bootstrap" in line
        assert line.index("Clopper–Pearson") < line.index("bootstrap") and line.index("(") < line.index("Clopper–Pearson")


def test_results_manifest_matches():
    results = json.loads((REPO_ROOT / "slices" / "s5" / "eval" / "results.json").read_text(encoding="utf-8"))
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert results["test_manifest"] == {k: frozen[k] for k in (
        "manifest_version", "sha256", "generator_version", "fixtures_file_sha256", "surface_suite")}
    assert frozen["manifest_version"] == 3
    assert frozen["sha256"] == frozen_split_sha256(load_patients())
    assert frozen["fixtures_file_sha256"] == fixtures_file_sha256()


def test_manifest_v3_same_split():
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert frozen["patient_refs"] == V2_TEST_REFS and len(V2_TEST_REFS) == 32
    assert frozen["supersedes"]["sha256"] == V2_SHA256 and frozen["supersedes"]["manifest_version"] == 2
    split_of = {p["patient_ref"]: p["split"] for p in load_patients()}
    assert [r for r, s in split_of.items() if s == "test"] == V2_TEST_REFS  # 0 split changes
    assert len(split_of) == 96 and set(split_of.values()) == {"dev", "test"}
    assert frozen["surface_suite"] == {"seed": 11, "generator_version": "s5-surface-forms-1.0.0"}


def test_surface_form_counts():
    cases = _surface_cases()
    assert len(SURFACE_FORMS) == 9 and "SF-EQUIV" not in DETECTION_FORMS
    for form in SURFACE_FORMS:
        test = [c for c in cases if c["form"] == form and c["split"] == "test"]
        assert len(test) >= 10 and len([c for c in cases if c["form"] == form]) >= 30, form
        if form in BILINGUAL_FORMS:
            langs = Counter(c["lang"] for c in test)
            assert langs["en"] >= 3 and langs["th"] >= 3, (form, langs)
    assert {c["lang"] for c in cases if c["form"] == "SF-TABS"} == {"en"}
    assert {c["lang"] for c in cases if c["form"] == "SF-MED"} == {"th"}


def test_surface_form_one_per_patient_form():
    cases = _surface_cases()
    assert max(Counter((c["patient_ref"], c["form"]) for c in cases).values()) == 1
    clean = {p["patient_ref"]: p["snapshot"] for p in load_patients()}
    for c in cases:
        snap, orig = c["snapshot"], clean[c["patient_ref"]]
        changes = sum(_entry_changes(o["entries"], s["entries"]) for o, s in zip(orig["sources"], snap["sources"]))
        assert changes == 1 and snap["allergies"] == orig["allergies"], c["case_id"]  # exactly one injected change
        assert c["before"] != c["after"] and c["expected"]["sources"] == [c["source"]]


def test_surface_form_reproducible():
    patients = load_patients()
    a = surface_log_lines(build_surface_cases(patients))
    assert a.encode() == surface_log_lines(build_surface_cases(patients)).encode()
    lines = [json.loads(line) for line in a.splitlines()]
    base = {"case_id", "patient_ref", "split", "type", "source", "before", "after", "expected", "form", "lang"}
    assert all(set(line) == base and line["lang"] in ("en", "th") for line in lines)
    committed = REPO_ROOT / "slices" / "s5" / "eval" / "injection_log_surface.jsonl"
    assert committed.read_text(encoding="utf-8") == a


def test_decisions_recorded():
    decisions = (REPO_ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    entry = decisions[decisions.index("## 2026-09-27 — S5 Pharma evaluation definitions"):]
    for text in (
        "(1) A notice that a source does not state dose or frequency counts as an alert.",
        "an incomplete source is its own labelled discrepancy type `missing_field`",
        "The pipeline still never treats a missing value as agreement.",
        "(2) The S5 fixture set grows to at least 90 patients (at least 30 in the frozen test split)",
        "**Approved by:** project owner (chat, 2026-09-27).",
        "thresholds unchanged (false alerts per clean list <= 0.10, recall per type >= 0.95)",
    ):
        assert text in entry, text
    open_entry = decisions[decisions.index("## 2026-09-26 — OPEN: do `missing_field` notices"):decisions.index("## 2026-09-27")]
    assert "**Resolved:** 2026-09-27 by the project owner" in open_entry


def test_makefile_port_defaults():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^API_PORT \?= 8000$", makefile, re.MULTILINE)
    assert re.search(r"^WEB_PORT \?= 3000$", makefile, re.MULTILINE)
    assert "API_ORIGIN=" in makefile
    assert "--port $(API_PORT)" in makefile and "--host 127.0.0.1" in makefile
    pw = (REPO_ROOT / "web" / "playwright.config.ts").read_text(encoding="utf-8")
    assert "process.env" in pw and "baseURL" in pw
