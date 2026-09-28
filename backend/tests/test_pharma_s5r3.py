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
from app.pharma.mock_rules import (DOSE_GRAMMAR, DOSE_GRAMMAR_VERSION, MOCK_RULES_VERSION, is_invisible, is_slash_like,
                                   normalise, parse_entry, read_dose)
from app.pharma.models import UnverifiableReason
from app.pharma.phrasing import TEMPLATE_VERSION, UNVERIFIABLE_WORDS, phrase_input, template_text, validate_text
from app.pharma.pipeline import PIPELINE_VERSION

from .conftest import REPO_ROOT
from .pharma_dose_fuzz import ADVERSARIAL, INVISIBLE_POINTS, entry_tuple, generate, harness
from .pharma_dose_reference import reference_parse
from .pharma_helpers import of_type, run, snapshot

PHARMA_DIR = REPO_ROOT / "backend" / "app" / "pharma"
RESULTS = REPO_ROOT / "slices" / "s5" / "eval" / "results.json"
REASONS = ("variable_regimen", "liquid_volume", "multiple_strengths", "range", "ambiguous_quantity", "unparsed_token",
           "per_unit_amount")


def _dose(text: str) -> tuple:
    e = parse_entry(text)
    return e["dose_status"], e["dose_unverifiable_reason"], e["dose_value"], e["dose_unit"], e["quantity"]


# ---------------------------------------------------------------- A03 one closed table


def test_grammar_table_closed():
    # s5r4 amendment (S5R4-A03): C1 joins the table.
    assert set(DOSE_GRAMMAR) == {"S1", "S2", "S3", "L1", "R1", "D1", "C1", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7",
                                 "T1", "F1", "F2", "F3"}


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


# ---------------------------------------------------------------- A15-A18 rev 2 probe suites

U = ("unverifiable",)
AMB = ("unverifiable", "ambiguous_quantity", None, None, None)
H_PROBES = {  # A15: Thai half-hour is a time, never a half tablet
    "H1": ("วาร์ฟาริน 3 มก. 1 เม็ด ก่อนอาหารครึ่งชั่วโมง", ("resolved", None, 3.0, "mg", 1.0)),
    "H2": ("วาร์ฟาริน 3 มก. 1 เม็ด ก่อนอาหาร ครึ่ง ชั่วโมง", ("resolved", None, 3.0, "mg", 1.0)),
    "H3": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่งชั่วโมงก่อนอาหาร", AMB),
    "H4": ("วาร์ฟาริน 3 มก. 1 เม็ด ครึ่งชั่วโมงก่อนอาหาร", AMB),
    "H5": ("วาร์ฟาริน 3 มก. 1 เม็ด ครึ่ง ชม. ก่อนอาหาร", AMB),
    "H6": ("วาร์ฟาริน 3 มก. ครั้งละ 1 เม็ดครึ่งชั่วโมงก่อนอาหาร", AMB),
    "H7": ("วาร์ฟาริน 3 มก. วันละ 1 เม็ด ครึ่งชม ก่อนอาหาร", AMB),
    "H8": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่งนาที", AMB),
    "H9": ("วาร์ฟาริน 3 มก. ครึ่งเม็ด ครึ่งชั่วโมงก่อนอาหาร", ("resolved", None, 3.0, "mg", 0.5)),
    "H10": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ครึ่งชั่วโมงก่อนอาหาร", ("resolved", None, 3.0, "mg", 1.5)),
    "H11": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ก่อนนอน", ("resolved", None, 3.0, "mg", 1.5)),
    "H12": ("วาร์ฟาริน 3 มก. 1 เม็ด ครึ่ง ก่อนนอน", ("resolved", None, 3.0, "mg", 1.5)),
    "H13": ("วาร์ฟาริน 3 มก. 1 เม็ด ก่อนอาหารครึ่ง hr", ("resolved", None, 3.0, "mg", 1.0)),
}
PER = ("unverifiable", "per_unit_amount", None, None, None)
U_PROBES = {  # A16: per-unit amounts are unverifiable; (text, expected, frequency_code)
    "U1": ("Metformin 1000 mg/day", PER, None),
    "U2": ("เมทฟอร์มิน 1000 มก./วัน", PER, None),
    "U3": ("เมทฟอร์มิน 1000 มก.ต่อวัน", PER, None),
    "U4": ("เมทฟอร์มิน 1000 มก. ต่อ วัน", PER, None),
    "U5": ("Gentamicin 5 mg/kg q24h", PER, "q24h"),
    "U6": ("Enoxaparin 1 mg / kg bid", PER, "q12h"),
    "U7": ("Metformin 500 mg per day", PER, None),
    "U8": ("Metformin 500 mg 2 tabs/day", PER, None),
    "U9": ("เมทฟอร์มิน 500 มก. 2 เม็ด/วัน", PER, None),
    "U10": ("Metformin 500-1000 mg/day", PER, None),
    "U11": ("Paracetamol syrup 250 mg/5 ml 10 ml prn", ("unverifiable", "liquid_volume", None, None, None), "prn"),
    "U12": ("Metformin 500 mg 2 times per day", ("resolved", None, 500.0, "mg", None), "q12h"),
}
UNPARSED = ("unverifiable", "unparsed_token", None, None, None)
V_PROBES = {  # A17: QV <= 10 on every quantity production
    "V1": ("Warfarin 3 mg 30 1/2 tabs", UNPARSED),
    "V2": ("Warfarin 3 mg 30 ½ tab", UNPARSED),
    "V3": ("Warfarin 3 mg 10 1/2 tab", UNPARSED),
    "V4": ("วาร์ฟาริน 3 มก. 12 เม็ดครึ่ง", UNPARSED),
    "V5": ("Warfarin 3 mg 9 1/2 tab", ("resolved", None, 3.0, "mg", 9.5)),
    "V6": ("Warfarin 3 mg 12x2", UNPARSED),
}
W_PROBES = {  # A18: undotted มก/มล are units only as a word
    "W1": ("วาร์ฟาริน 3 มก 1 เม็ด", ("resolved", None, 3.0, "mg", 1.0)),
    "W2": ("Paracetamol syrup 120 มก/5 มล 5 มล", ("unverifiable", "liquid_volume", None, None, None)),
    "W3": ("แอมลอดิปีน 5 มก. 1 เม็ด วันละครั้ง", ("resolved", None, 5.0, "mg", 1.0)),
    "W4": ("Warfarin 3 mg 1 tab เริ่ม 5 มกราคม", UNPARSED),
    "W5": ("ยา 5 มลพิษ 1 เม็ด", UNPARSED),
}


def _check_probe(text: str, expected: tuple) -> None:
    assert _dose(text) == expected, text
    status, reason, *dose = expected
    assert reference_parse(text) == (status, *dose, reason), text  # the independent reference agrees
    assert expected[4] is None or expected[4] <= 10


@pytest.mark.parametrize("probe", list(H_PROBES))
def test_probe_half_hour(probe):
    _check_probe(*H_PROBES[probe])


@pytest.mark.parametrize("probe", list(U_PROBES))
def test_probe_per_unit(probe):
    text, expected, freq = U_PROBES[probe]
    _check_probe(text, expected)
    assert parse_entry(text)["frequency_code"] == freq


@pytest.mark.parametrize("probe", list(V_PROBES))
def test_probe_qv_bound(probe):
    _check_probe(*V_PROBES[probe])


@pytest.mark.parametrize("probe", list(W_PROBES))
def test_probe_undotted_unit(probe):
    _check_probe(*W_PROBES[probe])


def _half_spacings(text: str) -> set[str]:
    """Every variant with 0 or 1 space on each side of every "ครึ่ง" (before it, and before the TW or QW after it)."""
    parts = text.split("ครึ่ง")
    parts = [parts[0].rstrip(" ")] + [p.strip(" ") for p in parts[1:-1]] + [parts[-1].lstrip(" ")]
    variants = {""}
    for k, part in enumerate(parts):
        if k == 0:
            variants = {part}
            continue
        after_prev = [""] if k == len(parts) - 1 and not part else ["", " "]
        variants = {v + b + "ครึ่ง" + a + part for v in variants for b in ("", " ") for a in after_prev}
    return variants


def test_half_whitespace_equivalent():
    fields = ("dose_status", "dose_unverifiable_reason", "dose_value", "dose_unit", "quantity", "frequency_code",
              "frequency_status", "drug_name_raw")
    for probe in [f"H{n}" for n in range(1, 13)]:
        text, expected = H_PROBES[probe]
        variants = _half_spacings(text)
        assert len(variants) >= 4, probe
        for v in variants:
            e = parse_entry(v)
            assert _dose(v) == expected, (probe, v)
            assert tuple(e[f] for f in fields) == tuple(parse_entry(text)[f] for f in fields), (probe, v)
    # A zero-width space is not whitespace: it breaks "เม็ดครึ่ง", so the result is fail-safe, never 1.5.
    assert _dose("วาร์ฟาริน 3 มก. 1 เม็ด\u200bครึ่ง") == UNPARSED
    for zw in ("\u200c", "\u200d", "\u2060", "\ufeff"):
        assert _dose(f"วาร์ฟาริน 3 มก. 1 เม็ด{zw}ครึ่ง") == UNPARSED


# T1/R1 segment removed from each probe; frequency must be the same with and without it.
SEGMENTS = ("ครึ่งชั่วโมง", "ครึ่ง ชั่วโมง", "ครึ่ง ชม.", "ครึ่งชม", "ครึ่งนาที", "ครึ่ง hr", " ต่อ วัน", "ต่อวัน", "/วัน",
            "/day", "/kg", " / kg", " per day")


def test_t1_r1_frequency_neutral():
    texts = [t for t, e in H_PROBES.values() if "ชั่วโมง" in t or "ชม" in t or "นาที" in t or " hr" in t]
    texts += [t for t, e, _ in U_PROBES.values() if e == PER]
    assert len(texts) >= 20
    for text in texts:
        seg = next(s for s in SEGMENTS if s in text)
        stripped = " ".join(text.replace(seg, " ", 1).split())
        got, base = parse_entry(text), parse_entry(stripped)
        assert (got["frequency_code"], got["frequency_status"]) == (base["frequency_code"], base["frequency_status"]), (
            text, stripped)


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
    # rev 2: R1 (per-unit amount) and T1 (Thai half-hour is a time)
    "R1-en-day": ("Metformin 1000 mg/day", ("unverifiable", "per_unit_amount", None, None, None), None, "R1"),
    "R1-th-tor": ("เมทฟอร์มิน 1000 มก.ต่อวัน", ("unverifiable", "per_unit_amount", None, None, None), None, "R1"),
    "R1-en-qw": ("Metformin 500 mg 2 tabs/day", ("unverifiable", "per_unit_amount", None, None, None), None, "R1"),
    "T1-H1": ("วาร์ฟาริน 3 มก. 1 เม็ด ก่อนอาหารครึ่งชั่วโมง", (R, None, 3.0, "mg", 1.0), None, "T1"),
    "T1-H9": ("วาร์ฟาริน 3 มก. ครึ่งเม็ด ครึ่งชั่วโมงก่อนอาหาร", (R, None, 3.0, "mg", 0.5), None, "T1"),
    "T1-H10": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ครึ่งชั่วโมงก่อนอาหาร", (R, None, 3.0, "mg", 1.5), None, "Q4"),
    "U12-F2-per": ("Metformin 500 mg 2 times per day", (R, None, 500.0, "mg", None), "q12h", "F2"),
    # rev 3: D1 (daily-total or divided-dose marker)
    "D1-th": ("เมทฟอร์มิน 1000 มก. แบ่งวันละ 2 ครั้ง", ("unverifiable", "per_unit_amount", None, None, None), "q12h", "D1"),
    "D1-th-before": ("เมทฟอร์มิน วันละ 1000 มก.", ("unverifiable", "per_unit_amount", None, None, None), None, "D1"),
    "D1-en": ("Metformin 1000 mg divided bid", ("unverifiable", "per_unit_amount", None, None, None), "q12h", "D1"),
    "V5-Q3-bound": ("Warfarin 3 mg 9 1/2 tab", (R, None, 3.0, "mg", 9.5), None, "Q3"),
    # s5r4: C1 (a word outside the closed free-text vocabulary in the dose region)
    "C1-en": ("Warfarin 3 mg 1 tab od (Coumadin)", ("unverifiable", "unparsed_token", None, None, None), "q24h", "C1"),
    "C1-th": ("วาร์ฟาริน 3 มก. 1 เม็ดครึง วันละ 1 ครั้ง", ("unverifiable", "unparsed_token", None, None, None), "q24h", "C1"),
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
    # rev 2: H3-H8, U1-U10, V1-V4, V6, W4-W5
    "วาร์ฟาริน 3 มก. 1 เม็ดครึ่งชั่วโมงก่อนอาหาร": "ambiguous_quantity",
    "วาร์ฟาริน 3 มก. 1 เม็ด ครึ่งชั่วโมงก่อนอาหาร": "ambiguous_quantity",
    "วาร์ฟาริน 3 มก. 1 เม็ด ครึ่ง ชม. ก่อนอาหาร": "ambiguous_quantity",
    "วาร์ฟาริน 3 มก. ครั้งละ 1 เม็ดครึ่งชั่วโมงก่อนอาหาร": "ambiguous_quantity",
    "วาร์ฟาริน 3 มก. วันละ 1 เม็ด ครึ่งชม ก่อนอาหาร": "ambiguous_quantity",
    "วาร์ฟาริน 3 มก. 1 เม็ดครึ่งนาที": "ambiguous_quantity",
    "Metformin 1000 mg/day": "per_unit_amount",
    "เมทฟอร์มิน 1000 มก./วัน": "per_unit_amount",
    "เมทฟอร์มิน 1000 มก.ต่อวัน": "per_unit_amount",
    "เมทฟอร์มิน 1000 มก. ต่อ วัน": "per_unit_amount",
    "Gentamicin 5 mg/kg q24h": "per_unit_amount",
    "Enoxaparin 1 mg / kg bid": "per_unit_amount",
    "Metformin 500 mg per day": "per_unit_amount",
    "Metformin 500 mg 2 tabs/day": "per_unit_amount",
    "เมทฟอร์มิน 500 มก. 2 เม็ด/วัน": "per_unit_amount",
    "Metformin 500-1000 mg/day": "per_unit_amount",
    "Warfarin 3 mg 30 1/2 tabs": "unparsed_token",
    "Warfarin 3 mg 30 ½ tab": "unparsed_token",
    "Warfarin 3 mg 10 1/2 tab": "unparsed_token",
    "วาร์ฟาริน 3 มก. 12 เม็ดครึ่ง": "unparsed_token",
    "Warfarin 3 mg 12x2": "unparsed_token",
    "Warfarin 3 mg 1 tab เริ่ม 5 มกราคม": "unparsed_token",
    "ยา 5 มลพิษ 1 เม็ด": "unparsed_token",
}


@pytest.mark.parametrize("text", list(NEGATIVE))
def test_grammar_negative(text):
    assert _dose(text) == ("unverifiable", NEGATIVE[text], None, None, None)


PARTNER = {"warfarin": "Warfarin 3 mg od", "acetaminophen": "Paracetamol 500 mg q6h", "metformin": "Metformin 500 mg bid"}


def _partnered(text: str) -> str | None:
    """The formulary ingredient of a negative case, if it has a two-source partner line."""
    found = load_formulary().resolve_name(parse_entry(text)["drug_name_raw"])
    return found[0] if len(found) == 1 and found[0] in PARTNER else None


@pytest.mark.parametrize("reason", ["range", "unparsed_token", "ambiguous_quantity", "per_unit_amount"])
def test_negative_raises_missing_dose(reason):
    cases = [t for t, r in NEGATIVE.items() if r == reason and _partnered(t)]
    assert len(cases) >= 3, cases
    for text in cases:
        clean = run(snapshot(home=["Amlodipine 5 mg od"], orders=["Amlodipine 5 mg od"]))
        ingredient = _partnered(text)
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
    # rev 3: >= 20 phrases put an INVISIBLE character between "ครึ่ง" and a time word.
    half_hidden = [p for p in phrases if "invisible" in p.adversarial and any(
        f"ครึ่ง{c}{tw}" in p.text for c in INVISIBLE_POINTS for tw in ("ชั่วโมง", "นาที"))]
    assert len(half_hidden) >= 20, len(half_hidden)

    report = harness(entry_tuple(parse_entry), phrases)
    assert report.safety == [], "\n".join(report.safety[:20])  # 1. safety: 0 misreads
    assert report.status == [], "\n".join(report.status[:20])  # 2. 100% dose_status and reason agreement
    assert report.reference == [], "\n".join(report.reference[:20])  # 3. reference == generator's built value
    assert report.over_ten == [], "\n".join(report.over_ten[:20])  # A17: no resolved quantity above 10
    # 5. closure (rev 3): 0 resolved lines holding an INVISIBLE, an unconsumed SLASH-LIKE or a D1 marker
    assert report.closure == [], "\n".join(report.closure[:20])
    assert min(report.closure_counts[k] for k in ("invisible", "slash_like", "daily_total")) >= 20, report.closure_counts
    # s5r4 A12: (c) P markers and (d) C1 firings are never resolved; (e) th_normalise == its standard spelling.
    assert min(report.closure_counts[k] for k in ("per_word", "c1")) >= 20, report.closure_counts
    assert report.canonical == [], "\n".join(report.canonical[:20])


def _piecewise_stub(text: str):
    """The pre-s5r3 failure mode: read pieces, ignore the rest. Drops a mixed number's whole part and reads the
    upper end of a range."""
    s = text.lower()
    strength = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|units?|มก\.?)", s)
    if not strength:
        return "not_stated", None, None, None, None
    qty = re.search(r"(\d+/\d+|\d+(?:\.\d+)?)\s*(?:tabs?|tablets?|caps?|เม็ด|แคปซูล)", s)
    unit = {"มก": "mg", "มก.": "mg", "units": "unit"}.get(strength.group(2), strength.group(2))
    quantity = None
    if qty:
        num, _, den = qty.group(1).partition("/")
        quantity = float(num) / float(den) if den and float(den) else float(num)
    return "resolved", float(strength.group(1)), unit, quantity, None


def test_fuzz_catches_piecewise_stub():
    report = harness(_piecewise_stub, generate())
    caught = report.safety_classes
    assert caught["Q3"] >= 1, caught  # mixed number: whole part dropped
    assert sum(n for c, n in caught.items() if c.startswith("range_")) >= 1, caught  # upper end of a range
    for cls in ("th_half_time", "per_unit", "qv_over", "invisible", "slash_like", "dotted_tail", "daily_total",
                "q4b_follower"):  # rev 3: 10 classes in all (§F.4)
        assert caught[cls] >= 1, (cls, caught)


# ---------------------------------------------------------------- CHK-SCOPE2-TH-PREFIX: undotted มก/มล only as a word

TH_PREFIX = {
    # "5 มกราคม" = 5 January, "มลพิษ" = pollution: no strength is stated, the stray 5 is not a dose.
    "วาร์ฟาริน 1 เม็ด วันละ 1 ครั้ง เริ่ม 5 มกราคม": ("unverifiable", "unparsed_token", None, None, None),
    "วาร์ฟาริน 1 เม็ด วันละ 1 ครั้ง เริ่ม 5มกราคม": ("unverifiable", "unparsed_token", None, None, None),
    "น้ำเกลือ 1 เม็ด 5 มลพิษ": ("unverifiable", "unparsed_token", None, None, None),
    "วาร์ฟาริน 1 เม็ด วันละ 1 ครั้ง": ("not_stated", None, None, None, 1.0),  # control line
    # A drug name that contains "มล" is not a stray unit.
    "แอมลอดิปีน 5 มก. 1 เม็ด": ("resolved", None, 5.0, "mg", 1.0),
    # Undotted units still read when they stand alone.
    "วาร์ฟาริน 3 มก 1 เม็ด": ("resolved", None, 3.0, "mg", 1.0),
    "วาร์ฟาริน 3มก 1 เม็ด": ("resolved", None, 3.0, "mg", 1.0),
    "ยาน้ำ 5 มล": ("resolved", None, 5.0, "ml", None),
}


@pytest.mark.parametrize("text", list(TH_PREFIX))
def test_thai_word_starting_with_unit_is_not_a_unit(text):
    status, reason, *dose = TH_PREFIX[text]
    assert _dose(text) == TH_PREFIX[text]
    assert reference_parse(text) == (status, *dose, reason)


def test_thai_date_prefix_raises_missing_dose():
    """Checker repro: home 'วาร์ฟาริน 1 เม็ด ... เริ่ม 5 มกราคม' vs order 'Warfarin 5 mg 1 tab od'."""
    home = "วาร์ฟาริน 1 เม็ด วันละ 1 ครั้ง เริ่ม 5 มกราคม"
    result = run(snapshot(home=[home], orders=["Warfarin 5 mg 1 tab od"]))
    dose_issues = [i for i in of_type(result, "missing_field") if i["field"] == "dose"]
    assert len(dose_issues) == 1
    assert dose_issues[0]["detail"]["field_status"] in ("unverifiable", "not_stated")
    assert dose_issues[0]["conflicting_sources"][0]["raw_span"] == home
    assert of_type(result, "dose_mismatch") == []


def test_thai_date_prefix_api_rules_only(client, login):
    """Same repro through POST /api/pharma/reconcile, mode rules_only, as pharmacist1."""
    login("pharmacist1")
    snap = snapshot(home=["วาร์ฟาริน 1 เม็ด วันละ 1 ครั้ง เริ่ม 5 มกราคม"], orders=["Warfarin 5 mg 1 tab od"])
    resp = client.post("/api/pharma/reconcile", json={"snapshot": snap.model_dump(mode="json"), "mode": "rules_only"})
    assert resp.status_code == 200
    body = resp.json()
    assert len([i for i in of_type(body, "missing_field") if i["field"] == "dose"]) == 1
    assert of_type(body, "dose_mismatch") == []


def test_fuzz_catches_substring_unit(monkeypatch):
    """The fuzz must detect the pre-fix tokeniser, which matched undotted มก/มล inside any Thai word.

    s5r4 amendment (C1): C1 now also rejects the Thai left over after a substring unit ("ราคม"), so the pre-fix
    tokeniser is checked on its own, with C1 switched off."""
    from app.pharma import mock_rules

    monkeypatch.setattr(mock_rules, "_WORD_ONLY", frozenset())
    monkeypatch.setattr(mock_rules, "_c1", lambda *args: None)
    report = harness(entry_tuple(mock_rules.parse_entry), generate())
    assert any("มกราคม" in line or "มลพิษ" in line or "มกรา" in line for line in report.safety), report.safety[:5]


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
                assert not {m.pid for m in trace.matches} & {"R1", "T1", "D1", "C1"}, entry["text"]  # rev 2-4: none hit
                text = normalise(entry["text"])  # rev 3: no INVISIBLE, no QF failure, no unconsumed SLASH-LIKE
                assert not any(is_invisible(c) for c in text), entry["text"]
                assert all(t.text == "/" and k in trace.consumed for k, t in enumerate(trace.tokens)
                           if is_slash_like(t.text[:1])), entry["text"]
                assert "ครึ่ง" not in text or reference_parse(text)[4] != "ambiguous_quantity", entry["text"]
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
    assert UNVERIFIABLE_WORDS["per_unit_amount"] == "an amount per day, per weight or per other unit, not per dose"
    ts = (REPO_ROOT / "web" / "lib" / "pharma.ts").read_text(encoding="utf-8")
    block = ts.split("export const UNVERIFIABLE_REASONS")[1].split("};")[0]
    for reason in REASONS:
        assert f'  {reason}: "{UNVERIFIABLE_WORDS[reason]}",' in block, reason


@pytest.mark.parametrize("reason", ["range", "unparsed_token", "per_unit_amount"])
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


def test_versions_bumped():
    assert (MOCK_RULES_VERSION, DOSE_GRAMMAR_VERSION, TEMPLATE_VERSION, PIPELINE_VERSION) == (
        "s5-mock-rules-2.3.0", "s5-dose-grammar-1.3.0", "template-1.3.0", "s5-pipeline-2.5.0")
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
