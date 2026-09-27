"""S5R3 (Pharma Agent v1.3): one closed dose grammar; anything it does not consume is unverifiable."""

import ast
import collections
import hashlib
import json
import re
from pathlib import Path

import pytest

from app.pharma.fixtures import get_fixture
from app.pharma.eval.inject import load_patients
from app.pharma.formulary import load_formulary
from app.pharma.mock_rules import DOSE_GRAMMAR, DOSE_GRAMMAR_VERSION, MOCK_RULES_VERSION, normalise, parse_entry, read_dose
from app.pharma.models import UnverifiableReason
from app.pharma.phrasing import TEMPLATE_VERSION, UNVERIFIABLE_WORDS, phrase_input, template_text, validate_text
from app.pharma.pipeline import PIPELINE_VERSION

from .conftest import REPO_ROOT
from .pharma_dose_fuzz import ADVERSARIAL, entry_tuple, generate, harness
from .pharma_dose_reference import reference_parse
from .pharma_helpers import of_type, run, snapshot

PHARMA_DIR = REPO_ROOT / "backend" / "app" / "pharma"
RESULTS = REPO_ROOT / "slices" / "s5" / "eval" / "results.json"
REASONS = ("variable_regimen", "liquid_volume", "multiple_strengths", "range", "ambiguous_quantity", "unparsed_token")


def _dose(text: str) -> tuple:
    e = parse_entry(text)
    return e["dose_status"], e["dose_unverifiable_reason"], e["dose_value"], e["dose_unit"], e["quantity"]


# ---------------------------------------------------------------- A03 one closed table


def test_grammar_table_closed():
    assert set(DOSE_GRAMMAR) == {"S1", "S2", "S3", "L1", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "F1", "F2", "F3"}


DELETED = ("DOSE_RE", "QTY_RE", "_QTY_NUM", "_MIXED_RE", "_STRAY_NUM_BEFORE_RE", "_QTY_WORD_RE", "TIMES_RE")


def test_no_piecewise_dose_regex():
    hits = [(p.name, name) for p in PHARMA_DIR.rglob("*.py") for name in DELETED
            if re.search(rf"(?<![\w]){name}(?![\w])", p.read_text(encoding="utf-8"))]
    assert hits == []


# ---------------------------------------------------------------- A04 probes F1-F7 (+P1-P4)

PROBES = {
    "F1": ("Warfarin 3 mg 1 1/2 tab od", ("resolved", None, 3.0, "mg", 1.5), "q24h"),
    "F2": ("เมทฟอร์มิน 500 มก. ครั้งละ2เม็ด วันละ2ครั้ง", ("resolved", None, 500.0, "mg", 2.0), "q12h"),
    "F3a": ("Warfarin 3 mg 1-1/2 tab od", ("resolved", None, 3.0, "mg", 1.5), "q24h"),
    "F3b": ("Warfarin 3 mg 1 and 1/2 tab od", ("resolved", None, 3.0, "mg", 1.5), "q24h"),
    "F4a": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง วันละ 1 ครั้ง", ("resolved", None, 3.0, "mg", 1.5), "q24h"),
    "F4b": ("วาร์ฟาริน 3 มก. 2เม็ดครึ่ง วันละ 1 ครั้ง", ("resolved", None, 3.0, "mg", 2.5), "q24h"),
    "F5a": ("วาร์ฟาริน 3 มก. 1-2 เม็ด วันละ 1 ครั้ง", ("unverifiable", "range", None, None, None), None),
    "F5b": ("Paracetamol 500 mg 1-2 tabs q4-6h prn", ("unverifiable", "range", None, None, None), None),
    "F6a": ("Warfarin 3 mg ½x1", ("resolved", None, 3.0, "mg", 0.5), "q24h"),
    "F6b": ("Warfarin 3 mg 1/2x2", ("resolved", None, 3.0, "mg", 0.5), "q12h"),
    "F7": ("Warfarin 3 mg 1/2 od", ("unverifiable", "unparsed_token", None, None, None), None),
    "P1": ("Warfarin 3 mg 3 od", ("unverifiable", "unparsed_token", None, None, None), None),
    "P2": ("Warfarin 3 mg 2 tabs x 2", ("unverifiable", "unparsed_token", None, None, None), None),
    "P3": ("Aspirin 81 mg 1x1 หลังอาหารเช้า 1", ("unverifiable", "unparsed_token", None, None, None), None),
    "P4": ("Paracetamol 500 mg 1 tab or 2 tabs prn", ("unverifiable", "range", None, None, None), None),
}


@pytest.mark.parametrize("probe", list(PROBES))
def test_probe_f1_f7(probe):
    text, expected, freq = PROBES[probe]
    assert _dose(text) == expected
    if freq:
        assert parse_entry(text)["frequency_code"] == freq


# ---------------------------------------------------------------- A05 every production reads exactly

R = "resolved"
POSITIVE = {  # id: (text, (status, reason, value, unit, quantity), frequency_code or ..., production that must fire)
    "S1-en": ("Warfarin 3 mg od", (R, None, 3.0, "mg", None), "q24h", "S1"),
    "S1-en-joined": ("Warfarin 3mg od", (R, None, 3.0, "mg", None), "q24h", "S1"),
    "S1-th": ("เมทฟอร์มิน 500 มก. วันละ 2 ครั้ง", (R, None, 500.0, "mg", None), "q12h", "S1"),
    "S1-ml": ("Lactulose 15 ml od", (R, None, 15.0, "ml", None), "q24h", "S1"),
    "S1-units": ("Lantus 10 units hs", (R, None, 10.0, "unit", None), "q24h", "S1"),
    "S2-en": ("Augmentin 875/125 mg bid", ("not_stated", None, None, None, None), "q12h", "S2"),
    "S2-th": ("ออกเมนติน 500/125 มก. วันละ 2 ครั้ง", ("not_stated", None, None, None, None), "q12h", "S2"),
    "S3-en": ("Warfarin 3 mg + 1 mg od", ("unverifiable", "multiple_strengths", None, None, None), "q24h", "S3"),
    "S3-en-and": ("Warfarin 3 mg and 2 mg od", ("unverifiable", "multiple_strengths", None, None, None), "q24h", "S3"),
    "S3-th": ("วาร์ฟาริน 3 มก. และ 2 มก. วันละ 1 ครั้ง", ("unverifiable", "multiple_strengths", None, None, None), "q24h", "S3"),
    "L1-en": ("Paracetamol syrup 250 mg/5 ml 10 ml q6h prn", ("unverifiable", "liquid_volume", None, None, None), "q6h", "L1"),
    "L1-th": ("พาราเซตามอล น้ำเชื่อม 120 มก./5 มล. 5 มล. ทุก 6 ชั่วโมง", ("unverifiable", "liquid_volume", None, None, None),
              "q6h", "L1"),
    "Q1-en": ("Warfarin 3 mg 2 tabs od", (R, None, 3.0, "mg", 2.0), "q24h", "Q1"),
    "Q1-en-joined": ("Warfarin 3 mg 2tabs od", (R, None, 3.0, "mg", 2.0), "q24h", "Q1"),
    "Q1-th-decimal": ("วาร์ฟาริน 1 มก. 1.5 เม็ด วันละ 1 ครั้ง", (R, None, 1.0, "mg", 1.5), "q24h", "Q1"),
    "Q1-th-cap": ("โอเมพราโซล 20 มก. 3 แคปซูล วันละ 1 ครั้ง", (R, None, 20.0, "mg", 3.0), "q24h", "Q1"),
    "Q2-en": ("Warfarin 3 mg 1/2 tab od", (R, None, 3.0, "mg", 0.5), "q24h", "Q2"),
    "Q2-en-quarter": ("Warfarin 4 mg 3/4 tab od", (R, None, 4.0, "mg", 0.75), "q24h", "Q2"),
    "Q2-th": ("วาร์ฟาริน 3 มก. ½ เม็ด วันละ 1 ครั้ง", (R, None, 3.0, "mg", 0.5), "q24h", "Q2"),
    "Q3-en-space": ("Warfarin 3 mg 1 1/2 tab od", (R, None, 3.0, "mg", 1.5), "q24h", "Q3"),
    "Q3-en-hyphen": ("Warfarin 3 mg 1-1/2 tab od", (R, None, 3.0, "mg", 1.5), "q24h", "Q3"),
    "Q3-en-and": ("Warfarin 3 mg 1 and 1/2 tab od", (R, None, 3.0, "mg", 1.5), "q24h", "Q3"),
    "Q3-en-ufrac": ("Warfarin 3 mg 1½ tab od", (R, None, 3.0, "mg", 1.5), "q24h", "Q3"),
    "Q3-th": ("วาร์ฟาริน 3 มก. 1และ1/2 เม็ด วันละ 1 ครั้ง", (R, None, 3.0, "mg", 1.5), "q24h", "Q3"),
    "Q4-th-half": ("วาร์ฟาริน 3 มก. ครึ่งเม็ด วันละ 1 ครั้ง", (R, None, 3.0, "mg", 0.5), "q24h", "Q4"),
    "Q4-th-n-and-half": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง วันละ 1 ครั้ง", (R, None, 3.0, "mg", 1.5), "q24h", "Q4"),
    "Q4-th-joined": ("วาร์ฟาริน 3 มก. 2เม็ดครึ่ง วันละ 1 ครั้ง", (R, None, 3.0, "mg", 2.5), "q24h", "Q4"),
    "Q5-en": ("Metformin 500 mg 2x2", (R, None, 500.0, "mg", 2.0), "q12h", "Q5"),
    "Q5-th": ("แอสไพริน 81 มก. 1x1 หลังอาหารเช้า", (R, None, 81.0, "mg", 1.0), "q24h", "Q5"),
    "Q5-ufrac": ("Warfarin 3 mg ½x1", (R, None, 3.0, "mg", 0.5), "q24h", "Q5"),
    "Q5-slash": ("Warfarin 3 mg 1/2x2", (R, None, 3.0, "mg", 0.5), "q12h", "Q5"),
    "Q6-th": ("เมทฟอร์มิน 500 มก. ครั้งละ2เม็ด วันละ2ครั้ง", (R, None, 500.0, "mg", 2.0), "q12h", "Q6"),
    "Q6-th-half": ("วาร์ฟาริน 3 มก. ครั้งละ ครึ่งเม็ด", (R, None, 3.0, "mg", 0.5), None, "Q6"),
    "Q7-th": ("วาร์ฟาริน 3 มก. วันละ 1 เม็ด", (R, None, 3.0, "mg", 1.0), "q24h", "Q7"),
    "Q7-th-half": ("วาร์ฟาริน 3 มก. วันละครึ่งเม็ด", (R, None, 3.0, "mg", 0.5), None, "Q7"),
    "F1-en": ("Metformin 500 mg q6h", (R, None, 500.0, "mg", None), "q6h", "F1"),
    "F1-en-every": ("Metformin 500 mg every 8 hours", (R, None, 500.0, "mg", None), "q8h", "F1"),
    "F1-en-unmapped": ("Paracetamol 500 mg q4h", (R, None, 500.0, "mg", None), None, "F1"),
    "F1-th": ("พาราเซตามอล 500 มก. ทุก 6 ชั่วโมง", (R, None, 500.0, "mg", None), "q6h", "F1"),
    "F2-en": ("Metformin 500 mg twice daily", (R, None, 500.0, "mg", None), "q12h", "F2"),
    "F2-en-four": ("Metformin 500 mg four times daily", (R, None, 500.0, "mg", None), "q6h", "F2"),
    "F2-en-week": ("Omeprazole 20 mg 3 times a week", (R, None, 20.0, "mg", None), None, "F2"),
    "F3-th": ("เมทฟอร์มิน 500 มก. วันละ 3 ครั้ง", (R, None, 500.0, "mg", None), "q8h", "F3"),
    "F3-th-once": ("เมทฟอร์มิน 500 มก. วันละครั้ง", (R, None, 500.0, "mg", None), "q24h", "F3"),
    "F3-th-week": ("เมทฟอร์มิน 500 มก. สัปดาห์ละ 1 ครั้ง", (R, None, 500.0, "mg", None), None, "F3"),
    # required extras
    "joined-strength-and-quantity": ("3mg 2tabs od", (R, None, 3.0, "mg", 2.0), "q24h", "Q1"),
    "equal-quantities": ("Metformin 500 mg 1 tab 1x2", (R, None, 500.0, "mg", 1.0), "q12h", "Q5"),
    "equal-strengths": ("Warfarin 3 mg 3 mg od", (R, None, 3.0, "mg", None), "q24h", "S1"),
}


@pytest.mark.parametrize("case", list(POSITIVE))
def test_grammar_positive(case):
    text, expected, freq, pid = POSITIVE[case]
    assert _dose(text) == expected
    assert parse_entry(text)["frequency_code"] == freq
    assert pid in {m.pid for m in read_dose(normalise(text)).matches}


def test_grammar_positive_covers_every_production():
    per = collections.Counter(pid for *_, pid in POSITIVE.values())
    assert set(per) == set(DOSE_GRAMMAR) and min(per.values()) >= 2


# ---------------------------------------------------------------- A06 anything else is unverifiable, visibly

NEGATIVE = {
    "Warfarin 3 mg ⅓ tab od": "unparsed_token",
    "Warfarin 3 mg .5 tab od": "unparsed_token",
    "Warfarin 3 mg 3/2 tab od": "unparsed_token",
    "วาร์ฟาริน 3 มก. ๑ เม็ด": "unparsed_token",
    "Warfarin 3 mg half tab od": "unparsed_token",
    "Paracetamol 1,000 mg q6h": "unparsed_token",
    "Paracetamol 500 mg 30 tabs": "unparsed_token",  # QV > 10
    "Metformin 500 mg x2": "unparsed_token",
    "Metformin 500 mg 2x5": "unparsed_token",
    "Warfarin 3 mg 2 x1 tab": "unparsed_token",
    "Warfarin 3 mg tab od": "unparsed_token",
    "Paracetamol 500-1000 mg q6h": "range",
    "Paracetamol 500 mg 1 ถึง 2 เม็ด": "range",
    "Paracetamol 500 mg 1 หรือ 2 เม็ด": "range",
    "Warfarin 3 mg 1–2 tabs": "range",  # en dash
    "Warfarin 3 mg 1~2 tabs": "range",
    "เมทฟอร์มิน 500 มก. วันละ 2 เม็ด": "ambiguous_quantity",  # Q7 > 1: a daily total
    "Metformin 500 mg 2 tabs 1x2": "ambiguous_quantity",
    "Warfarin 3 mg 0 tab od": "unparsed_token",
}


@pytest.mark.parametrize("text", list(NEGATIVE))
def test_grammar_negative(text):
    assert _dose(text) == ("unverifiable", NEGATIVE[text], None, None, None)


PARTNER = {"warfarin": "Warfarin 3 mg od", "acetaminophen": "Paracetamol 500 mg q6h", "metformin": "Metformin 500 mg bid"}


@pytest.mark.parametrize("reason", ["range", "unparsed_token", "ambiguous_quantity"])
def test_negative_raises_missing_dose(reason):
    cases = [t for t, r in NEGATIVE.items() if r == reason]
    assert cases
    for text in cases:
        clean = run(snapshot(home=["Amlodipine 5 mg od"], orders=["Amlodipine 5 mg od"]))
        [ingredient] = load_formulary().resolve_name(parse_entry(text)["drug_name_raw"])
        result = run(snapshot(home=[text], orders=[PARTNER[ingredient]]))
        dose_issues = [i for i in of_type(result, "missing_field") if i["field"] == "dose"]
        assert len(dose_issues) == 1, text
        [mf] = dose_issues
        assert (mf["detail"]["field_status"], mf["detail"]["unverifiable_reason"]) == ("unverifiable", reason), text
        assert mf["conflicting_sources"][0]["raw_span"] == text
        assert of_type(result, "dose_mismatch") == [], text
        assert result["unchecked_by_reason"]["unverifiable"] - clean["unchecked_by_reason"]["unverifiable"] == 1, text


# ---------------------------------------------------------------- A03 trace: resolved consumes every numeric-ish token


def _pinned() -> dict:
    return json.loads((Path(__file__).parent / "data" / "s5r3_frequency_1c1f476.json").read_text(encoding="utf-8"))


def test_resolved_consumes_all_numeric_tokens():
    texts = list(_pinned()["entries"]) + [t for t, *_ in POSITIVE.values()] + [p.text for p in generate(n=600)]
    resolved = 0
    for text in texts:
        trace = read_dose(normalise(text))
        if trace.dose_status == "resolved":
            resolved += 1
            assert trace.unconsumed_numeric == [], text
    assert resolved >= 500


# ---------------------------------------------------------------- A07 fuzz against the independent reference


def test_dose_fuzz_vs_reference():
    phrases = generate()
    assert len(phrases) >= 2000
    ref_status = collections.Counter(reference_parse(p.text)[0] for p in phrases)
    assert ref_status["resolved"] >= 0.25 * len(phrases) and ref_status["unverifiable"] >= 0.25 * len(phrases), ref_status
    productions = collections.Counter(pid for p in phrases for pid in p.productions)
    assert set(productions) == set(DOSE_GRAMMAR) and min(productions.values()) >= 20, productions
    adversarial = collections.Counter(c for p in phrases for c in p.adversarial)
    assert set(adversarial) == set(ADVERSARIAL) and min(adversarial.values()) >= 20, adversarial
    langs = collections.Counter(p.quantity_lang for p in phrases)
    assert langs["en"] >= 0.3 * len(phrases) and langs["th"] >= 0.3 * len(phrases), langs
    assert sum(p.single_quantity is not None for p in phrases) >= 200

    report = harness(entry_tuple(parse_entry), phrases)
    assert report.safety == [], "\n".join(report.safety[:20])  # 1. safety: 0 misreads
    assert report.status == [], "\n".join(report.status[:20])  # 2. 100% dose_status agreement
    assert report.reference == [], "\n".join(report.reference[:20])  # 3. reference == generator's built value


def _piecewise_stub(text: str):
    """The pre-s5r3 failure mode: read pieces, ignore the rest. Drops a mixed number's whole part and reads the
    upper end of a range."""
    s = text.lower()
    strength = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|units?|มก\.?)", s)
    if not strength:
        return "not_stated", None, None, None
    qty = re.search(r"(\d+/\d+|\d+(?:\.\d+)?)\s*(?:tabs?|tablets?|caps?|เม็ด|แคปซูล)", s)
    unit = {"มก": "mg", "มก.": "mg", "units": "unit"}.get(strength.group(2), strength.group(2))
    quantity = None
    if qty:
        num, _, den = qty.group(1).partition("/")
        quantity = float(num) / float(den) if den and float(den) else float(num)
    return "resolved", float(strength.group(1)), unit, quantity


def test_fuzz_catches_piecewise_stub():
    report = harness(_piecewise_stub, generate())
    assert len(report.safety) >= 1
    assert any("1 1/2 tab" in line or "1-1/2 tab" in line for line in report.safety)  # whole part dropped
    assert any("1-2 tabs" in line or "1 to 2 tabs" in line for line in report.safety)  # upper end of a range


def test_reference_independent():
    path = Path(__file__).parent / "pharma_dose_reference.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any(m == "app" or m.startswith("app.") or m == "re" for m in imported), imported
    impl = ast.parse((PHARMA_DIR / "mock_rules.py").read_text(encoding="utf-8"))
    patterns = set()
    for node in ast.walk(impl):  # every literal passed to re.compile / re.search / ...
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and getattr(node.func.value, "id", "") == "re":
            for arg in node.args[:1]:
                for c in ast.walk(arg):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str) and len(c.value) >= 4:
                        patterns.add(c.value)
    ref_literals = {c.value for c in ast.walk(tree) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    assert patterns and not patterns & ref_literals


# ---------------------------------------------------------------- A09 frozen data untouched

FROZEN = {
    "backend/app/pharma/fixtures/patients.json": "22979820a842432e5faf63e63490a6e8ea24cb973704c3c29a88d0dda80d0521",
    "backend/app/pharma/fixtures/test_manifest.json": "b91d9d67dc8c0d94ba73e9891b880e1c6313510c44d036044df8a05ccdd789c1",
    "slices/s5/eval/injection_log.jsonl": "468a28980ba66b4bc80e1f54d66b8bc6943bc8d72eb3ab2a2c47be84edbc0299",
    "slices/s5/eval/injection_log_surface.jsonl": "b948a7481756906bedc46531663f7aa2812732522123b67fffb9629f5ca541d7",
}


def test_frozen_artifacts_unchanged():
    for rel, digest in FROZEN.items():
        assert hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest() == digest, rel
    manifest = json.loads((REPO_ROOT / "backend/app/pharma/fixtures/test_manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3


# ---------------------------------------------------------------- A10 evaluation unchanged except versions/notes

# sha256 of results.json at 1c1f476 without "versions" and "notes" (json.dumps sort_keys, ensure_ascii=False).
RESULTS_BODY_1C1F476 = "3e59e382ef684a58bacfc37d7cc5b7814c4afa7cddf25dbc18540cadac9b2410"


def test_results_unchanged_except_versions():
    # test_eval_thresholds proves the committed file equals a fresh run; this pins it to the 1c1f476 body.
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    body = {k: v for k, v in results.items() if k not in ("versions", "notes")}
    assert hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest() == RESULTS_BODY_1C1F476
    assert results["label"].startswith("System Evaluation")
    v = results["versions"]
    assert (v["mock_rules"], v["dose_grammar"], v["template"], v["pipeline"]) == (
        MOCK_RULES_VERSION, DOSE_GRAMMAR_VERSION, TEMPLATE_VERSION, PIPELINE_VERSION)
    assert v["rules"] == "s5-rules-2.1.0" and v["extract_task"] == "pharma.extract.v2"


# ---------------------------------------------------------------- A11 clean fixtures use only grammar forms


def test_clean_fixtures_grammar_only():
    patients = load_patients()
    assert len(patients) == 96
    entries = 0
    for p in patients:
        for source in p["snapshot"]["sources"]:
            for entry, gold in zip(source["entries"], p["gold"][source["source_type"]], strict=True):
                trace = read_dose(normalise(entry["text"]))
                assert trace.dose_status == "resolved" and trace.unconsumed_numeric == [], entry["text"]
                assert trace.quantity == gold["quantity"], entry["text"]
                entries += 1
    assert entries > 0


def test_surface_after_strings_expected():
    rows = [json.loads(line) for line in FROZEN_SURFACE.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 864
    for r in rows:
        e = parse_entry(r["after"])
        exp = r["expected"]
        if exp.get("field") == "dose":
            assert (e["dose_status"], e["dose_unverifiable_reason"]) == (exp["field_status"], exp.get("unverifiable_reason")), r
        else:
            assert (e["dose_status"], e["dose_unverifiable_reason"]) == ("resolved", None), r
            if exp.get("field") == "frequency":
                assert e["frequency_status"] == exp["field_status"], r


FROZEN_SURFACE = REPO_ROOT / "slices" / "s5" / "eval" / "injection_log_surface.jsonl"


# ---------------------------------------------------------------- A12 frequency unchanged


def test_frequency_unchanged():
    pinned = _pinned()
    assert pinned["source_commit"] == "1c1f476" and len(pinned["entries"]) >= 1500
    changed = {t: (parse_entry(t)["frequency_code"], parse_entry(t)["frequency_status"]) for t in pinned["entries"]}
    changed = {t: v for t, v in changed.items() if list(v) != pinned["entries"][t]}
    assert changed == {}
    # the one allowed change (§4): Q5 with a fractional N now yields the code of M, as an integer N does
    assert parse_entry("Warfarin 3 mg ½x1")["frequency_code"] == "q24h"
    assert parse_entry("Warfarin 3 mg 1/2x2")["frequency_code"] == "q12h"


# ---------------------------------------------------------------- A13 new reasons labelled end to end


def test_reason_labels_complete():
    assert UnverifiableReason.__args__ == REASONS
    assert set(UNVERIFIABLE_WORDS) == set(REASONS)
    assert UNVERIFIABLE_WORDS["range"] == "a range or alternative between two amounts"
    assert UNVERIFIABLE_WORDS["unparsed_token"] == "a dose form this checker does not read"
    ts = (REPO_ROOT / "web" / "lib" / "pharma.ts").read_text(encoding="utf-8")
    block = ts.split("export const UNVERIFIABLE_REASONS")[1].split("};")[0]
    for reason in REASONS:
        assert f'  {reason}: "{UNVERIFIABLE_WORDS[reason]}",' in block, reason


@pytest.mark.parametrize("reason", ["range", "unparsed_token"])
def test_templates_pass_validation(reason):
    text = next(t for t, r in NEGATIVE.items() if r == reason)
    for snap in (snapshot(home=["Warfarin 3 mg od"], orders=[text]), snapshot(orders=[text])):
        issues = [i for i in run(snap, mode="rules_only")["issues"] if i["type"] == "missing_field" and i["field"] == "dose"]
        assert issues, text
        for issue in issues:
            item = phrase_input(issue)
            rendered = template_text(item)
            assert validate_text(rendered, item) is None, rendered
            assert f"could not be verified ({UNVERIFIABLE_WORDS[reason]})" in rendered


# ---------------------------------------------------------------- A14 versions and truthful wording


def test_versions_recorded():
    assert (MOCK_RULES_VERSION, DOSE_GRAMMAR_VERSION, TEMPLATE_VERSION, PIPELINE_VERSION) == (
        "s5-mock-rules-2.0.0", "s5-dose-grammar-1.0.0", "template-1.2.0", "s5-pipeline-2.2.0")
    r = run(get_fixture("demo-quantity"))
    assert (r["extract_mock_version"], r["dose_grammar_version"], r["template_version"], r["pipeline_version"]) == (
        MOCK_RULES_VERSION, DOSE_GRAMMAR_VERSION, TEMPLATE_VERSION, PIPELINE_VERSION)


OVERCLAIM = re.compile(r"all doses|every dose|may be misread", re.IGNORECASE)


def test_results_notes_grammar():
    note = json.loads(RESULTS.read_text(encoding="utf-8"))["notes"][0]
    ts = (REPO_ROOT / "web" / "lib" / "pharma.ts").read_text(encoding="utf-8")
    scope = ts.split("export const SCOPE_READING =")[1].split(";\n")[0]
    for text in (note, scope):
        assert "fixed, listed grammar" in text and "could not be verified" in text, text
        assert "2 tabs" in text and "still read as 2 tablets per dose" in text, text  # residual risk kept
        assert not OVERCLAIM.search(text), text
