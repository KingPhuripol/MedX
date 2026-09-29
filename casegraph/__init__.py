"""Case Graph: typed data, Node Library, Compiler, Executor, Output Store (slices s0, s2, i2).

``casegraph.data`` is the single evidence type system (slice i2): the s1 dataset types live there and
``casegraph.sources.s1r`` loads S1r snapshots into it.

Research prototype — not for clinical use. Submodules are imported explicitly
(``casegraph.compiler``, ``casegraph.executor`` ...) so ``python -m casegraph inspect`` stays light.
"""

from .data import (
    CLINICAL_TEXT_TYPES,
    EVIDENCE_ADAPTER,
    AllergyList,
    ClinicalText,
    Demographics,
    Evidence,
    IntakeTranscript,
    LabSeries,
    MedicationList,
    Vitals,
    VoiceIntakeFacts,
)
from .types import EvidenceItem, Node, NodeType, TypedData

__all__ = [
    "CLINICAL_TEXT_TYPES",
    "EVIDENCE_ADAPTER",
    "AllergyList",
    "ClinicalText",
    "Demographics",
    "Evidence",
    "EvidenceItem",
    "IntakeTranscript",
    "LabSeries",
    "MedicationList",
    "Node",
    "NodeType",
    "TypedData",
    "Vitals",
    "VoiceIntakeFacts",
]
