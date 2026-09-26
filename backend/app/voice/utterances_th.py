"""Reviewed patient-facing Thai utterance allowlist (the ONLY text the agent may speak).

Simulation-only placeholder pending clinical sign-off (Decision D1). Model output is never
spoken or rendered as an agent utterance. No advice, reassurance or disease-labelling wording.
"""

from __future__ import annotations

UTTERANCES_TH: dict[str, str] = {
    "ask.chief_complaint": "วันนี้มีอาการอะไรมาคะ",
    "reask.chief_complaint": "ขอทวนอีกครั้งนะคะ วันนี้ไม่สบายตรงไหนคะ",
    "ask.onset_duration": "มีอาการนี้มานานเท่าไรแล้วคะ",
    "reask.onset_duration": "ขอทราบอีกครั้งค่ะ เริ่มมีอาการตั้งแต่เมื่อไรคะ",
    "ask.severity": "ถ้าให้คะแนนความรุนแรง 0 ถึง 10 ตอนนี้ประมาณเท่าไรคะ",
    "reask.severity": "ขอทวนอีกครั้งนะคะ ถ้าให้คะแนน 0 ถึง 10 จะให้เท่าไรคะ",
    "ask.allergy_status": "เคยแพ้ยาอะไรไหมคะ",
    "reask.allergy_status": "ขอทวนอีกครั้งนะคะ มีประวัติแพ้ยาหรือไม่คะ",
    "ask.current_medications": "ตอนนี้ใช้ยาอะไรอยู่บ้างไหมคะ",
    "reask.current_medications": "ขอทราบอีกครั้งค่ะ ตอนนี้ใช้ยาอะไรอยู่บ้างคะ",
    "ask.relevant_history": "มีโรคประจำตัวหรือเคยเจ็บป่วยอะไรมาก่อนไหมคะ",
    "reask.relevant_history": "ขอทวนอีกครั้งนะคะ มีโรคประจำตัวไหมคะ",
    "handoff.complete": "ขอบคุณค่ะ พยาบาลจะมาดูแลต่อสักครู่นะคะ",
    "handoff.attempts_exhausted": "ขอบคุณค่ะ พยาบาลจะมาสอบถามเพิ่มเติมสักครู่นะคะ",
    "handoff.nurse_attention_phrase": "ขอบคุณค่ะ พยาบาลจะมาดูแลต่อทันทีนะคะ",
    "handoff.extraction_unavailable": "ขอบคุณค่ะ พยาบาลจะมาดูแลต่อสักครู่นะคะ",
}


def utterance(utterance_id: str) -> str:
    """Look up an allowlisted utterance. Unknown ids raise: there is no free-text fallback."""
    return UTTERANCES_TH[utterance_id]
