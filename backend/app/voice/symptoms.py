"""Thai symptom-fact extractor for the Case Graph Reader:Text node (slice i2). MOCK — not clinical.

Registered as the mock handler for ``voice.symptom_extract.v1``. A pure, deterministic function of
``{"turns": [{turn_index, speaker, text, spoken_at}, ...]}``; only ``patient`` turns are read.

Output facts use the rf-1.1.0 ``symptom.*`` names. Semantics (D-I2-4, pending clinical sign-off):

* An onset-qualified symptom (``sudden_*``, ``thunderclap_headache``, ``acute_chest_pain``) is ``present``
  only when a concept term and a sudden-onset term occur in the same patient turn. A concept mentioned
  without a sudden-onset term is ``unknown`` (the turn is cited), never ``absent``.
* ``absent`` needs an explicit denial of the concept in a patient turn (``ไม่ / ไม่มี / ไม่ได้ + term``);
  that turn is cited. A symptom the patient never mentions yields no fact at all (unknown).
* Every term has a ``source_ref`` (the rule it serves and its citation).

The lexicon was written from the rule definitions in ``app/triage/rules/redflag_rules_v1.json`` and
checked against S1r **train**-split transcripts only (seed 20260926); dev and test were not read. It does
not import ``data_factory``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from ..gateway import mock_tasks

TASK = "voice.symptom_extract.v1"
LEXICON_VERSION = "symptom-lex-1.0.0"

_CHEST = "RF-CHEST rf-1.1.0 (Gulati 2021 AHA/ACC chest pain guideline, PMID 34709879)"
_STROKE = "RF-STROKE rf-1.1.0 (Powers 2019 AHA/ASA early stroke management, PMID 31662037)"
_THUNDER = "RF-THUNDER rf-1.1.0 (Perry 2013 Ottawa SAH rule population, PMID 24065011)"
_ANAPH = "RF-ANAPH rf-1.1.0 (Cardona 2020 WAO anaphylaxis guidance, PMID 33204386)"


@dataclass(frozen=True)
class Term:
    text: str
    source_ref: str


@dataclass(frozen=True)
class Concept:
    name: str  # rf-1.1.0 symptom name
    terms: tuple[Term, ...]
    onset_qualified: bool


def _terms(ref: str, *texts: str) -> tuple[Term, ...]:
    return tuple(Term(t, ref) for t in texts)


CONCEPTS: tuple[Concept, ...] = (
    Concept("acute_chest_pain", _terms(f"{_CHEST}: chest pain", "เจ็บแน่นหน้าอก", "เจ็บหน้าอก", "แน่นหน้าอก",
                                       "ปวดหน้าอก", "เจ็บอก"), True),
    Concept("sudden_facial_droop", _terms(f"{_STROKE}: facial droop", "หน้าเบี้ยว", "ปากเบี้ยว", "มุมปากตก",
                                          "ปากตก"), True),
    Concept("sudden_limb_weakness", _terms(f"{_STROKE}: limb weakness", "แขนขาอ่อนแรง", "แขนอ่อนแรง",
                                           "แขนขวาอ่อนแรง", "แขนซ้ายอ่อนแรง", "ขาอ่อนแรง", "ขาขวาอ่อนแรง",
                                           "ขาซ้ายอ่อนแรง", "อ่อนแรงซีกเดียว", "อ่อนแรงครึ่งซีก",
                                           "อ่อนแรงข้างเดียว"), True),
    Concept("sudden_speech_disturbance", _terms(f"{_STROKE}: speech disturbance", "พูดไม่ชัด", "พูดลำบาก",
                                                "พูดไม่ออก", "ลิ้นแข็ง", "ลิ้นคับปาก"), True),
    Concept("sudden_vision_disturbance", _terms(f"{_STROKE}: vision disturbance", "ตามัว", "มองไม่เห็น",
                                                "เห็นภาพซ้อน", "ตาบอด"), True),
    Concept("thunderclap_headache", _terms(f"{_THUNDER}: headache", "ปวดศีรษะ", "ปวดหัว"), True),
    # WAO 2020 criterion 1: skin/mucosal involvement (hives, lip/face swelling) is the evidence of a probable
    # allergen exposure used by rf-1.1.0 allergen_exposure. This reading is a D1 review item.
    Concept("allergen_exposure", _terms(f"{_ANAPH}: skin/mucosal involvement or a stated exposure",
                                        "ผื่นลมพิษ", "ลมพิษ", "ริมฝีปากบวม", "ปากบวม", "หน้าบวม", "ผึ้งต่อย",
                                        "แตนต่อย", "ต่อต่อย"), False),
    Concept("airway_breathing_compromise", _terms(f"{_ANAPH}: respiratory compromise (dyspnoea, wheeze, stridor)",
                                                  "หายใจลำบาก", "หายใจไม่ออก", "หายใจมีเสียงหวีด",
                                                  "หายใจเสียงหวีด", "หายใจติดขัด", "หอบเหนื่อย"), False),
)

# Sudden-onset qualifiers (rule text: "Sudden facial droop ...", "Sudden severe headache peaking within 1 hour",
# "Acute chest pain"). A peak within seconds is a thunderclap qualifier.
ONSET_TERMS: tuple[Term, ...] = (
    *_terms(f"{_STROKE}; {_CHEST}; {_THUNDER}: sudden/acute onset",
            "ทันที", "ทันใด", "จู่ ๆ", "จู่ๆ", "อยู่ ๆ", "อยู่ๆ", "อยู่ดี ๆ", "อยู่ดีๆ", "เฉียบพลัน", "กะทันหัน",
            "ปุบปับ"),
    *_terms(f"{_THUNDER}: maximal intensity within seconds", "ไม่กี่วินาที"),
)
GRADUAL_TERMS: tuple[Term, ...] = _terms(
    f"{_THUNDER}; {_STROKE}: gradual or chronic course (not a sudden-onset qualifier)",
    "ทีละน้อย", "ค่อย ๆ", "ค่อยๆ", "เรื่อย ๆ", "เรื่อยๆ", "เท่าเดิม",
)
# An explicit denial: a negation immediately before the concept term. "ไม่ค่อย" (not much) is not a denial.
DENIAL_PREFIX = r"ไม่(?:มี|ได้|เคย)?(?:อาการ)?\s*"
DENIAL_SOURCE = "D-I2-4 (DECISIONS 2026-09-27): only an explicit denial in a patient turn is absent"


def all_terms() -> tuple[Term, ...]:
    return (*(t for c in CONCEPTS for t in c.terms), *ONSET_TERMS, *GRADUAL_TERMS)


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _find(text: str, terms: tuple[Term, ...]) -> list[Term]:
    return [t for t in terms if _nfc(t.text) in text]


def _mentions(text: str, concept: Concept) -> tuple[list[Term], list[Term]]:
    """(affirmed terms, denied terms) of a concept in one turn.

    Longest-first, non-overlapping matches (so "แน่นหน้าอก" inside a denied "ไม่เจ็บแน่นหน้าอก" is not
    re-read as affirmed). An occurrence immediately preceded by a denial is denied.
    """
    taken = [False] * len(text)
    affirmed: list[Term] = []
    denied: list[Term] = []
    for term in sorted(concept.terms, key=lambda t: len(t.text), reverse=True):
        for m in re.finditer(re.escape(_nfc(term.text)), text):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            (denied if re.search(DENIAL_PREFIX + r"$", text[: m.start()]) else affirmed).append(term)
    return affirmed, denied


def extract_symptoms(inputs: dict[str, Any]) -> dict[str, Any]:
    """Mock handler for ``voice.symptom_extract.v1``. Pure and offline."""
    turns = sorted((t for t in inputs.get("turns", []) if t.get("speaker") == "patient"),
                   key=lambda t: int(t["turn_index"]))
    facts: list[dict[str, Any]] = []
    for concept in CONCEPTS:
        present: list[tuple[int, list[str]]] = []
        mentioned: list[tuple[int, list[str], bool]] = []
        denied: list[tuple[int, list[str]]] = []
        for turn in turns:
            text = _nfc(str(turn["text"]))
            idx = int(turn["turn_index"])
            yes, no = _mentions(text, concept)
            if yes:
                refs = [t.source_ref for t in yes]
                onset = _find(text, ONSET_TERMS)
                if not concept.onset_qualified:
                    present.append((idx, refs))
                elif onset:
                    present.append((idx, refs + [t.source_ref for t in onset]))
                else:
                    gradual = _find(text, GRADUAL_TERMS)
                    mentioned.append((idx, refs + [t.source_ref for t in gradual], bool(gradual)))
            elif no:
                denied.append((idx, [t.source_ref for t in no] + [DENIAL_SOURCE]))
        if present:
            state, onset_value, cited = "present", "sudden" if concept.onset_qualified else "unknown", present
        elif mentioned:
            gradual = any(g for _, _, g in mentioned)
            state, onset_value, cited = "unknown", "gradual" if gradual else "unknown", [(i, r) for i, r, _ in mentioned]
        elif denied:
            state, onset_value, cited = "absent", "unknown", denied
        else:
            continue  # never mentioned: no fact (unknown), never absent
        facts.append({
            "name": concept.name,
            "state": state,
            "onset": onset_value,
            "evidence_turns": [i for i, _ in cited],
            "source_refs": sorted({r for _, refs in cited for r in refs}),
        })
    return {"extractor": LEXICON_VERSION, "facts": facts}


mock_tasks.register(TASK, extract_symptoms, version=LEXICON_VERSION)
