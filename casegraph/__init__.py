"""Case Graph: typed data, Node Library, Compiler, Executor, Output Store (slices s0 + s2).

``casegraph.evidence`` holds the s1 synthetic-dataset evidence schema; it is unified with
``casegraph.data`` (s2) in the Case Graph wiring slice.

Research prototype — not for clinical use. Submodules are imported explicitly
(``casegraph.compiler``, ``casegraph.executor`` ...) so ``python -m casegraph inspect`` stays light.
"""

from .evidence import (
    AllergyList,
    ClinicalText,
    Demographics,
    IntakeTranscript,
    LabSeries,
    MedicationList,
    TimedEvidence,
    Vitals,
    evidence_adapter,
)
from .types import EvidenceItem, Node, NodeType, TypedData

__all__ = [
    "AllergyList",
    "ClinicalText",
    "Demographics",
    "EvidenceItem",
    "IntakeTranscript",
    "LabSeries",
    "MedicationList",
    "Node",
    "NodeType",
    "TimedEvidence",
    "TypedData",
    "Vitals",
    "evidence_adapter",
]
