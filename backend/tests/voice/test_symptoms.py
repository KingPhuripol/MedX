"""Slice i2 I2-A06: Reader:Text symptom facts (voice.symptom_extract.v1). Unit transcripts are hand-written."""

from __future__ import annotations

import ast

import pytest

from app.voice.symptoms import CONCEPTS, LEXICON_VERSION, all_terms, extract_symptoms

from ..conftest import REPO_ROOT

TEXT_RULE_SYMPTOMS = {
    "RF-CHEST": {"acute_chest_pain"},
    "RF-STROKE": {"sudden_facial_droop", "sudden_limb_weakness", "sudden_speech_disturbance",
                  "sudden_vision_disturbance"},
    "RF-THUNDER": {"thunderclap_headache"},
    "RF-ANAPH": {"allergen_exposure", "airway_breathing_compromise"},
}


def _run(*patient_texts: str, nurse_first: bool = True) -> dict[str, dict]:
    turns = []
    for i, text in enumerate(patient_texts):
        if nurse_first:
            turns.append({"turn_index": 2 * i, "speaker": "nurse", "text": "มีอาการอะไรคะ",
                          "spoken_at": f"2030-01-01T08:{2 * i:02d}:00+07:00"})
        turns.append({"turn_index": 2 * i + 1, "speaker": "patient", "text": text,
                      "spoken_at": f"2030-01-01T08:{2 * i + 1:02d}:00+07:00"})
    out = extract_symptoms({"turns": turns})
    assert out["extractor"] == LEXICON_VERSION
    return {f["name"]: f for f in out["facts"]}


# (text, expected present symptom names). At least 3 per text rule, at least 2 of them without ทันที.
POSITIVES = {
    "RF-CHEST": [
        ("เจ็บหน้าอกขึ้นมาทันทีค่ะ", {"acute_chest_pain"}),
        ("จู่ ๆ ก็แน่นหน้าอกเหมือนมีอะไรทับค่ะ", {"acute_chest_pain"}),
        ("เจ็บแน่นหน้าอกเป็นขึ้นมาเฉียบพลันตอนเดินขึ้นบันได", {"acute_chest_pain"}),
        ("อยู่ดี ๆ ก็ปวดหน้าอกร้าวไปกรามครับ", {"acute_chest_pain"}),
    ],
    "RF-STROKE": [
        ("หน้าเบี้ยวขึ้นมาทันทีค่ะ", {"sudden_facial_droop"}),
        ("จู่ๆ แขนขวาอ่อนแรงและพูดไม่ชัดครับ", {"sudden_limb_weakness", "sudden_speech_disturbance"}),
        ("มองไม่เห็นข้างซ้ายเป็นขึ้นมากะทันหันค่ะ", {"sudden_vision_disturbance"}),
        ("มุมปากตก พูดลำบาก เป็นในไม่กี่วินาทีครับ", {"sudden_facial_droop", "sudden_speech_disturbance"}),
    ],
    "RF-THUNDER": [
        ("ปวดศีรษะรุนแรงที่สุดขึ้นมาทันทีครับ", {"thunderclap_headache"}),
        ("อยู่ ๆ ก็ปวดหัวแรงมากเหมือนโดนตีค่ะ", {"thunderclap_headache"}),
        ("ปวดหัวรุนแรงสุดในไม่กี่วินาทีค่ะ", {"thunderclap_headache"}),
    ],
    "RF-ANAPH": [
        ("ลมพิษขึ้นทั้งตัวและหายใจมีเสียงหวีดค่ะ", {"allergen_exposure", "airway_breathing_compromise"}),
        ("โดนผึ้งต่อยแล้วหายใจไม่ออกครับ", {"allergen_exposure", "airway_breathing_compromise"}),
        ("ริมฝีปากบวม หายใจลำบากค่ะ", {"allergen_exposure", "airway_breathing_compromise"}),
    ],
}

# Near-miss negatives per rule family: the rule's present facts must NOT be produced.
NEAR_MISSES = {
    "RF-CHEST": [
        "เจ็บหน้าอกเวลาบิดตัวหรือกดตรงนั้นครับ",
        "เจ็บแน่นหน้าอกเวลายกของ เป็นมา 3 สัปดาห์ค่ะ",
        "แน่นหน้าอกเป็น ๆ หาย ๆ มานานแล้วค่ะ",
    ],
    "RF-STROKE": [
        "หน้าเบี้ยวและพูดไม่ชัดมาตั้งแต่เป็นอัมพฤกษ์ อาการเท่าเดิมค่ะ",
        "นิ้วมือชาทั้งสองข้างครับ",
        "แขนขาอ่อนแรงซีกเดียวหลังเป็นอัมพฤกษ์ มาตรวจตามนัดค่ะ",
    ],
    "RF-THUNDER": [
        "ปวดศีรษะรุนแรงขึ้นทีละน้อยทุกวันค่ะ",
        "ปวดหัวรุนแรงขึ้นเรื่อย ๆ มาหลายวันครับ",
        "ปวดหัวตื้อ ๆ ตอนบ่ายค่ะ",
    ],
    "RF-ANAPH": [
        "หายใจลำบากเวลาเดินไกล ๆ มาหลายเดือนครับ",  # breathing only: no skin/mucosal sign
        "แพ้ยาเพนิซิลลินค่ะ",  # allergy history is not an exposure
        "เป็นหวัด คัดจมูก ไอค่ะ",
    ],
}


@pytest.mark.parametrize("rule", sorted(POSITIVES))
def test_symptom_extract_positive_paraphrases(rule):
    cases = POSITIVES[rule]
    assert len(cases) >= 3 and sum("ทันที" not in text for text, _ in cases) >= 2
    for text, expected in cases:
        facts = _run(text)
        present = {n for n, f in facts.items() if f["state"] == "present"}
        assert expected <= present, (text, facts)
        for name in expected:
            f = facts[name]
            assert f["evidence_turns"] == [1] and f["source_refs"], f
            concept = next(c for c in CONCEPTS if c.name == name)
            assert f["onset"] == ("sudden" if concept.onset_qualified else "unknown")


@pytest.mark.parametrize("rule", sorted(NEAR_MISSES))
def test_symptom_extract_near_miss(rule):
    texts = NEAR_MISSES[rule]
    assert len(texts) >= 3
    for text in texts:
        facts = _run(text)
        if rule == "RF-ANAPH":
            both = {"allergen_exposure", "airway_breathing_compromise"}
            assert not both <= {n for n, f in facts.items() if f["state"] == "present"}, (text, facts)
            continue
        for name in TEXT_RULE_SYMPTOMS[rule]:
            assert facts.get(name, {}).get("state") != "present", (text, facts)
            assert facts.get(name, {}).get("state") != "absent", (text, facts)  # a mention is never a denial


def test_symptom_extract_gradual_is_unknown_with_citation():
    facts = _run("ปวดศีรษะรุนแรงขึ้นทีละน้อยทุกวันค่ะ")
    f = facts["thunderclap_headache"]
    assert (f["state"], f["onset"], f["evidence_turns"]) == ("unknown", "gradual", [1])


def test_symptom_extract_explicit_denials():
    facts = _run("ไม่เจ็บหน้าอกค่ะ", "ไม่มีอาการหายใจลำบากค่ะ", "ไม่ได้ปวดหัวครับ", "ไม่เจ็บแน่นหน้าอกครับ")
    assert facts["acute_chest_pain"]["state"] == "absent" and facts["acute_chest_pain"]["evidence_turns"] == [1, 7]
    assert facts["airway_breathing_compromise"]["state"] == "absent"
    assert facts["airway_breathing_compromise"]["evidence_turns"] == [3]
    assert facts["thunderclap_headache"]["state"] == "absent" and facts["thunderclap_headache"]["evidence_turns"] == [5]
    for f in facts.values():
        assert f["source_refs"]


def test_symptom_extract_present_beats_later_denial_and_same_turn_onset_only():
    facts = _run("เจ็บหน้าอกขึ้นมาทันทีค่ะ", "ตอนนี้ไม่เจ็บหน้าอกแล้วค่ะ")
    assert facts["acute_chest_pain"]["state"] == "present"
    # the onset term in a different turn does not qualify the concept
    facts = _run("เจ็บหน้าอกค่ะ", "นั่งรถมาทันทีหลังเลิกงานค่ะ")
    assert facts["acute_chest_pain"]["state"] == "unknown"


@pytest.mark.parametrize("texts", [
    ("มีไข้ ไอ มา 3 วันค่ะ", "ไม่มียาที่ใช้ประจำค่ะ", "ไม่เคยแพ้ยาค่ะ"),
    ("ปัสสาวะแสบขัดค่ะ", "เป็นมา 2 วันค่ะ", "ลูกพามาค่ะ"),
])
def test_unmentioned_is_unknown(texts):
    """A transcript that mentions no target symptom yields no fact at all, and never an absent fact."""
    assert _run(*texts) == {}


def test_unmentioned_symptoms_never_absent_in_mixed_transcript():
    facts = _run("หน้าเบี้ยวขึ้นมาทันทีค่ะ", "ไม่เคยแพ้ยาค่ะ")
    assert set(facts) == {"sudden_facial_droop"}
    assert not any(f["state"] == "absent" for f in facts.values())


def test_nurse_turns_are_not_read():
    out = extract_symptoms({"turns": [
        {"turn_index": 0, "speaker": "nurse", "text": "เจ็บหน้าอกขึ้นมาทันทีไหมคะ", "spoken_at": "2030-01-01T08:00:00+07:00"},
        {"turn_index": 1, "speaker": "patient", "text": "มีไข้ค่ะ", "spoken_at": "2030-01-01T08:01:00+07:00"},
    ]})
    assert out["facts"] == []


def test_lexicon_sources():
    terms = all_terms()
    assert terms and all(t.source_ref.strip() for t in terms)
    rule_ids = {"RF-CHEST", "RF-STROKE", "RF-THUNDER", "RF-ANAPH"}
    for c in CONCEPTS:
        assert all(any(r in t.source_ref for r in rule_ids) for t in c.terms), c.name


def test_no_data_factory_imports_in_product_code():
    bad = []
    for root in (REPO_ROOT / "backend", REPO_ROOT / "casegraph"):
        for p in sorted(root.rglob("*.py")):
            if ".venv" in p.parts:
                continue
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                    [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                bad += [f"{p}: {m}" for m in mods if m.split(".")[0] == "data_factory"]
    assert bad == []
