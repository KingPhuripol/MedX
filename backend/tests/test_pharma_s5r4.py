"""S5R4 (Pharma Agent v1.4): s5r3 dose grammar revision 3 (INVISIBLE, SLASH-LIKE, R1 TAIL, QF, D1).

Invisible characters are written as \\uXXXX escapes only; no test source stores one literally.
"""

import time
import unicodedata

from app.pharma.mock_rules import is_invisible, is_slash_like, parse_entry

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
