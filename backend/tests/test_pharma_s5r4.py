"""S5R4 (Pharma Agent v1.4): s5r3 dose grammar revision 3 (INVISIBLE, SLASH-LIKE, R1 TAIL, QF, D1).

Invisible characters are written as \\uXXXX escapes only; no test source stores one literally.
"""

import collections
import hashlib
import importlib.util
import sys
import time
import unicodedata
from pathlib import Path

import pytest

from app.pharma.formulary import load_formulary
from app.pharma.mock_rules import is_invisible, is_slash_like, normalise, parse_entry

from .pharma_dose_fuzz import REV3_CLASSES, entry_tuple, generate, harness
from .pharma_dose_reference import reference_parse
from .pharma_helpers import of_type, run, snapshot

# ---------------------------------------------------------------- A09 computed sets (full code-point sweep)

# s5r3 §G1, restated here: categories Cc/Cf/Co/Cs/Cn, or the explicit list.
G1_INVISIBLE_LIST = {0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F, 0x2800, 0x3164, 0xFFA0}
G1_INVISIBLE_LIST |= set(range(0xFE00, 0xFE10)) | set(range(0xE0100, 0xE01F0))
INVISIBLE_MUST = (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x2066, 0xFE0F)
SLASH_MUST = (0x002F, 0x005C, 0x2044, 0x2215, 0x2216, 0xFF0F, 0xFF3C, 0x29F8, 0xFE68)


def _g1_invisible(cp: int) -> bool:
    return unicodedata.category(chr(cp)) in ("Cc", "Cf", "Co", "Cs", "Cn") or cp in G1_INVISIBLE_LIST


def _g1_slash_like(cp: int) -> bool:
    name = unicodedata.name(chr(cp), "")
    return "SOLIDUS" in name or "SLASH" in name or cp == 0x2216


def test_invisible_set():
    t0 = time.perf_counter()
    diff = [hex(cp) for cp in range(0x110000) if is_invisible(chr(cp)) != _g1_invisible(cp)]
    elapsed = time.perf_counter() - t0
    assert diff == []
    assert all(is_invisible(chr(cp)) for cp in INVISIBLE_MUST)
    assert elapsed <= 5, elapsed
    # Each one makes a resolved line unverifiable, wherever it is inserted.
    base = "Warfarin 3 mg 1 tab od"
    assert parse_entry(base)["dose_status"] == "resolved"
    for cp in INVISIBLE_MUST:
        for at in (0, 8, 14, 16, len(base)):
            e = parse_entry(base[:at] + chr(cp) + base[at:])
            assert e["dose_status"] != "resolved", (hex(cp), at)


def test_slash_like_set():
    t0 = time.perf_counter()
    diff = [hex(cp) for cp in range(0x110000) if is_slash_like(chr(cp)) != _g1_slash_like(cp)]
    elapsed = time.perf_counter() - t0
    assert diff == []
    assert all(is_slash_like(chr(cp)) for cp in SLASH_MUST)
    assert elapsed <= 5, elapsed
    # Only an ASCII "/" inside FRAC, S2 or L1 is consumed: a look-alike never forms a fraction.
    assert parse_entry("Warfarin 3 mg 1/2 tab od")["quantity"] == 0.5
    for cp in SLASH_MUST[1:]:
        e = parse_entry(f"Warfarin 3 mg 1{chr(cp)}2 tab od")
        assert (e["dose_status"], e["dose_unverifiable_reason"]) == ("unverifiable", "unparsed_token"), hex(cp)


# ---------------------------------------------------------------- A04-A08 rev-3 probe tables (s5r3 SPEC rev 3)
# Row: (input, (status, reason, dose_value, dose_unit, quantity), Freq or None, segment whose removal must leave the
# frequency unchanged, or None). Inputs are exactly the spec rows; <U+XXXX> is written as a \uXXXX escape.

AMB = ("unverifiable", "ambiguous_quantity", None, None, None)
UNP = ("unverifiable", "unparsed_token", None, None, None)
PER = ("unverifiable", "per_unit_amount", None, None, None)
I1 = "วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง{}ชั่วโมงก่อนอาหาร"

I_PROBES = {
    "I1": (I1.format("\u200b"), AMB, None, None),
    "I2": (I1.format("\u200c"), AMB, None, None),
    "I3": (I1.format("\u2060"), AMB, None, None),
    "I4": (I1.format("\u00ad"), AMB, None, None),
    "I5": (I1.format("\ufeff"), AMB, None, None),
    "I6": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ครึ่ง\u200bชั่วโมงก่อนอาหาร", AMB, None, None),
    "I7": ("Warfarin 3 mg 1 tab od\u200b", UNP, None, None),
    "I8": ("วาร์ฟาริน 3 มก. 1 เม็ด วันละ 1 ครั้ง\u2066", UNP, None, None),
    "I9": ("Warfarin 3 mg 1\ufe0f tab od", UNP, None, None),
    "I10": ("Warfarin 3 mg 1 tab\u200d/day", PER, None, None),
}
SL_PROBES = {
    "SL1": ("Metformin 1000 mg／day", PER, None, None),
    "SL2": ("Metformin 1000 mg∕day", PER, None, None),
    "SL3": ("Metformin 1000 mg\\day", PER, None, None),
    "SL4": ("เมทฟอร์มิน 1000 มก.／วัน", PER, None, None),
    "SL5": ("Gentamicin 5 mg⧸kg q24h", PER, "q24h", "⧸kg"),
    "SL6": ("Metformin 500 mg 2 tabs∕day", PER, None, None),
    "SL7": ("Metformin 1000 mg ⁄ day", PER, None, None),
    "SL8": ("Warfarin 3 mg 1⁄2 tab od", UNP, "q24h", "1⁄2 tab"),
    "SL9": ("Losartan/HCTZ 50 mg 1 tab od", UNP, "q24h", "/HCTZ"),
    "SL10": ("Warfarin 3 mg 1 tab od ก่อนอาหาร/หลังอาหาร", UNP, "q24h", "/หลังอาหาร"),
    "SL11": ("Warfarin 3 mg 1/2 tab od", ("resolved", None, 3.0, "mg", 0.5), "q24h", None),
}
DT_PROBES = {
    "DT1": ("Metformin 1000 mg./day", PER, None, None),
    "DT2": ("Metformin 1000 mg. per day", PER, None, None),
    "DT3": ("Levothyroxine 50 mcg./kg", PER, None, None),
    "DT4": ("Metformin 500 mg 2 tab./day", PER, None, None),
    "DT5": ("Metformin 500 mg 2 tabs. per day", PER, None, None),
    "DT6": ("เมทฟอร์มิน 1000 mg. ต่อวัน", PER, None, None),
    "DT7": ("Metformin 1000 mg (per day)", PER, None, None),
    "DT8": ("Metformin 1000 mg a day", PER, None, None),
    "DT9": ("Metformin 500 mg 2 tabs a day", PER, None, None),
    "DT10": ("เมทฟอร์มิน 1000 มก.\u0e48/วัน", PER, None, None),
    "DT11": ("Metformin 1000 mg | day", UNP, None, None),
    "DT12": ("Metformin 500 mg. bid", ("resolved", None, 500.0, "mg", None), "q12h", "."),
    "DT13": ("Metformin 500 mg 1 tab. bid", ("resolved", None, 500.0, "mg", 1.0), "q12h", "."),
    "DT14": ("Metformin 500 mg (1 tab) bid", ("resolved", None, 500.0, "mg", 1.0), "q12h", "(1 tab)"),
    "DT15": ("Metformin 500 mg once a day", ("resolved", None, 500.0, "mg", None), "q24h", None),
}
D_PROBES = {
    "D1": ("เมทฟอร์มิน 1000 มก. แบ่งวันละ 2 ครั้ง", PER, "q12h", "แบ่ง"),
    "D2": ("เมทฟอร์มิน 1000 มก. แบ่ง วันละ 2 ครั้ง", PER, "q12h", "แบ่ง"),
    "D3": ("เมทฟอร์มิน 1000 มก. แบ่งให้วันละ 2 ครั้ง", PER, "q12h", "แบ่งให้"),
    "D4": ("เมทฟอร์มิน 1000 มก. รวมวันละ 2 ครั้ง", PER, "q12h", "รวม"),
    "D5": ("เมทฟอร์มิน 1000 มก. ทั้งหมดต่อวัน", PER, None, None),
    "D6": ("เมทฟอร์มิน วันละ 1000 มก.", PER, None, None),
    "D7": ("Metformin 1000 mg in 2 divided doses", PER, None, None),
    "D8": ("Metformin 1000 mg divided bid", PER, "q12h", "divided"),
    "D9": ("Metformin 1000 mg daily, split bid", PER, None, None),
    "D10": ("Metformin total 1000 mg bid", PER, "q12h", "total"),
    "D11": ("เมทฟอร์มิน 500 มก. วันละ 2 ครั้ง", ("resolved", None, 500.0, "mg", None), "q12h", None),
    "D12": ("เมทฟอร์มิน 500 มก. ครั้งละ 1 เม็ด วันละ 2 ครั้ง", ("resolved", None, 500.0, "mg", 1.0), "q12h", None),
}
QF_PROBES = {
    "QF1": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่งชัวโมงก่อนอาหาร", AMB, None, None),
    "QF2": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่งช.ม ก่อนอาหาร", AMB, None, None),
    "QF3": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง mn ac", AMB, None, None),
    "QF4": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง(ก่อนอาหาร)", AMB, None, None),
    "QF5": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง 30 นาทีก่อนอาหาร", AMB, None, None),
    "QF6": ("วาร์ฟาริน 3 มก. ครั้งละ 1 เม็ดครึ่งชัวโมง", AMB, None, None),
    "QF7": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง", ("resolved", None, 3.0, "mg", 1.5), None, None),
    "QF8": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่งหลังอาหาร", ("resolved", None, 3.0, "mg", 1.5), None, None),
    "QF9": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่งพร้อมอาหาร", ("resolved", None, 3.0, "mg", 1.5), None, None),
    "QF10": ("Warfarin 3 mg 1 เม็ดครึ่ง od", ("resolved", None, 3.0, "mg", 1.5), "q24h", "ครึ่ง"),
    "QF11": ("วาร์ฟาริน 3 มก. 1 เม็ดครึ่ง ทุก 12 ชั่วโมง", ("resolved", None, 3.0, "mg", 1.5), "q12h", "ครึ่ง"),
    "QF12": ("โอเมพราโซล 20 มก. 1 แคปซูลครึ่ง ก่อนนอน", ("resolved", None, 20.0, "mg", 1.5), None, None),
}
REV3_PROBES = {**I_PROBES, **SL_PROBES, **DT_PROBES, **D_PROBES, **QF_PROBES}


def _dose(text: str) -> tuple:
    e = parse_entry(text)
    return e["dose_status"], e["dose_unverifiable_reason"], e["dose_value"], e["dose_unit"], e["quantity"]


def _check(probe: str) -> None:
    text, expected, freq, _ = REV3_PROBES[probe]
    assert _dose(text) == expected, (probe, text)
    status, reason, *dose = expected
    assert reference_parse(text) == (status, *dose, reason), (probe, text)  # the independent reference agrees
    if freq:
        assert parse_entry(text)["frequency_code"] == freq, (probe, text)


@pytest.mark.parametrize("probe", list(I_PROBES))
def test_probe_invisible(probe):
    _check(probe)
    if probe == "I1":
        assert parse_entry(I_PROBES["I1"][0])["quantity"] != 1.5


@pytest.mark.parametrize("probe", list(SL_PROBES))
def test_probe_slash_like(probe):
    _check(probe)


@pytest.mark.parametrize("probe", list(DT_PROBES))
def test_probe_unit_tail(probe):
    _check(probe)


@pytest.mark.parametrize("probe", list(D_PROBES))
def test_probe_daily_total(probe):
    _check(probe)


@pytest.mark.parametrize("probe", list(QF_PROBES))
def test_probe_q4b_follower(probe):
    _check(probe)
    # Joined and spaced forms around "ครึ่ง" give identical output (A08).
    text = QF_PROBES[probe][0]
    fields = ("dose_status", "dose_unverifiable_reason", "dose_value", "dose_unit", "quantity", "frequency_code",
              "frequency_status", "drug_name_raw")
    head, _, rest = text.partition("ครึ่ง")
    variants = {h + "ครึ่ง" + r for h in (head.rstrip(" "), head.rstrip(" ") + " ")
                for r in (rest.lstrip(" "), " " + rest.lstrip(" ") if rest.strip() else "")}
    assert len(variants) >= 2
    base = tuple(parse_entry(text)[f] for f in fields)
    for v in variants:
        assert tuple(parse_entry(v)[f] for f in fields) == base, (probe, v)


def test_t1_r1_frequency_neutral():
    """A15 (rev 3 extension to SL, DT, D and QF): every probe with a Freq gives it, and so does the same entry with
    its SLASH-LIKE / R1 / D1 / QF segment removed."""
    rows = [(p, t, f, seg) for p, (t, _, f, seg) in REV3_PROBES.items() if f]
    assert {p.rstrip("0123456789") for p, *_ in rows} == {"SL", "DT", "D", "QF"}
    for probe, text, freq, seg in rows:
        got = parse_entry(text)
        assert got["frequency_code"] == freq, probe
        if seg:
            assert seg in text, probe
            stripped = " ".join(text.replace(seg, " ", 1).split())
            base = parse_entry(stripped)
            assert (got["frequency_code"], got["frequency_status"]) == (base["frequency_code"], base["frequency_status"]), (
                probe, stripped)


# ---------------------------------------------------------------- A10 unverifiable is visible (two-source snapshot)

PARTNER = {"warfarin": "Warfarin 3 mg od", "metformin": "Metformin 500 mg bid"}


@pytest.mark.parametrize("probe", ["I1", "SL1", "DT1", "D1", "QF1"])
def test_negative_raises_missing_dose(probe):
    text, expected, _, _ = REV3_PROBES[probe]
    reason = expected[1]
    found = load_formulary().resolve_name(parse_entry(text)["drug_name_raw"])
    assert len(found) == 1 and found[0] in PARTNER, (probe, found)
    clean = run(snapshot(home=["Amlodipine 5 mg od"], orders=["Amlodipine 5 mg od"]))
    result = run(snapshot(home=[text], orders=[PARTNER[found[0]]]))
    dose_issues = [i for i in of_type(result, "missing_field") if i["field"] == "dose"]
    assert len(dose_issues) == 1, probe
    [mf] = dose_issues
    assert (mf["detail"]["field_status"], mf["detail"]["unverifiable_reason"]) == ("unverifiable", reason), probe
    assert mf["conflicting_sources"][0]["raw_span"] == normalise(text)
    assert of_type(result, "dose_mismatch") == [], probe
    assert result["unchecked_by_reason"]["unverifiable"] - clean["unchecked_by_reason"]["unverifiable"] == 1, probe


# ---------------------------------------------------------------- A03 constants next to the table

def test_rev3_constants_single():
    from app.pharma import mock_rules as m

    assert m.NEUTRAL == frozenset(" .,;:()[]+&")
    assert set(m.QF) == {"th", "en"} and len(m.QF["th"]) == 13 and len(m.QF["en"]) == 19
    assert m.INVISIBLE_EXTRA == frozenset(G1_INVISIBLE_LIST)
    assert m.D1_LEXICON["en"] == frozenset({"divided", "divide", "split", "total", "doses"})
    assert m.D1_LEXICON["th"] == ("แบ่ง", "รวม", "ทั้งหมด", "ทั้งวัน")


# ---------------------------------------------------------------- A13 the fuzz has teeth on the e6a354f parser

LEGACY = Path(__file__).parent / "legacy" / "mock_rules_e6a354f.py"
LEGACY_SHA256 = "26ef62596f3d0d50640461ef7ea50078ed0ec105ebf1036b872cc8cb3a30f377"  # git show e6a354f:backend/app/pharma/mock_rules.py


def test_fuzz_catches_e6a354f():
    assert hashlib.sha256(LEGACY.read_bytes()).hexdigest() == LEGACY_SHA256
    spec = importlib.util.spec_from_file_location("mock_rules_e6a354f", LEGACY)
    legacy = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = legacy  # dataclasses resolve string annotations through sys.modules
    try:
        spec.loader.exec_module(legacy)
    finally:
        del sys.modules[spec.name]
    assert legacy.MOCK_RULES_VERSION == "s5-mock-rules-2.1.0"
    report = harness(entry_tuple(legacy.parse_entry), generate())  # same harness, same seed
    for cls in ("invisible", "slash_like", "dotted_tail", "daily_total", "q4b_follower"):
        assert report.safety_classes[cls] >= 1, (cls, report.safety_classes)


def test_fuzz_rev3_classes_cover_every_form():
    """Each rev-3 class (>= 20 phrases) cycles through its whole choice list at seed 5303."""
    counts = collections.Counter(a for p in generate() for a in p.adversarial)
    for cls, (_, choices) in REV3_CLASSES.items():
        assert counts[cls] >= max(20, len(choices)), (cls, counts[cls], len(choices))
