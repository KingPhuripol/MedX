"""Node Library (PROPOSAL Table 3.1) and provider configuration.

The Library declares, per node type, its input/output data types, required inputs, allowed
providers and whether it is mandatory. ``ProviderConfig`` is the experiment/deployment setting that
assigns one provider (plus ``model_version`` and params) to each node type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .data import CLINICAL_TEXT_TYPES, PLACEHOLDER_RULE_SET, RF_110
from .types import NodeType

HUMAN_PROVIDERS = ("human:nurse", "human:physician", "human:pharmacist")
MODEL_PROVIDERS = frozenset(
    {"project_model", "external_model", "encoder_2d", "encoder_3d", "classifier", "segmentation"}
)
# Slice i2: Reader:Text provider = S3 voice extraction (+ the i2 symptom extractor) behind the Model Gateway.
VOICE_EXTRACT = "voice_extract"
VOICE_EXTRACT_VERSION = "voice-extract-1.0"
IMAGE_ENCODERS = frozenset({"encoder_2d", "encoder_3d"})


@dataclass(frozen=True)
class NodeDecl:
    node_type: NodeType
    input_types: tuple[str, ...]
    output_types: tuple[str, ...]
    required_inputs: tuple[str, ...]
    allowed_providers: tuple[str, ...]
    mandatory: bool = False
    evidence_types: tuple[str, ...] = ()  # the input types read directly from the snapshot


def requirement_key(data_type: str, source: str) -> str:
    """A Reasoning requirement: a ``data_type`` output derived from evidence of type ``source``."""
    return f"{data_type}<-{source}"


class LibraryConfig(BaseModel):
    """Library-level settings.

    ``reasoning_required_inputs`` is a documented PLACEHOLDER (not clinical): the clinically defined
    required-input set for Reasoning belongs to a later slice with clinical review.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reasoning_required_inputs: tuple[str, ...] = (
        requirement_key("Findings", "ClinicalText"),
        requirement_key("Findings", "Vitals"),
    )


_READER_OUTPUTS_IMAGING = ("ImageTokens", "Findings")
REASONING_OUTPUTS = ("CaseSummary", "DepartmentSuggestion", "CareSuggestion")


def node_decls(library_config: LibraryConfig | None = None) -> dict[NodeType, NodeDecl]:
    cfg = library_config or LibraryConfig()
    return {
        NodeType.READER_TEXT: NodeDecl(
            NodeType.READER_TEXT, CLINICAL_TEXT_TYPES, ("Findings",), ("ClinicalText",),
            (VOICE_EXTRACT, "project_model", "external_model"), evidence_types=CLINICAL_TEXT_TYPES,
        ),
        NodeType.READER_VITALS_LABS: NodeDecl(
            NodeType.READER_VITALS_LABS, ("Vitals", "LabSeries"), ("Findings",), ("Vitals|LabSeries",),
            ("rules", "project_model"), evidence_types=("Vitals", "LabSeries"),
        ),
        NodeType.READER_CXR: NodeDecl(
            NodeType.READER_CXR, ("CXRImage",), _READER_OUTPUTS_IMAGING, ("CXRImage",),
            ("encoder_2d", "external_model", "classifier"), evidence_types=("CXRImage",),
        ),
        NodeType.READER_CT_MRI: NodeDecl(
            NodeType.READER_CT_MRI, ("CTVolume", "MRIVolume"), _READER_OUTPUTS_IMAGING, ("CTVolume|MRIVolume",),
            ("encoder_3d", "external_model", "segmentation"), evidence_types=("CTVolume", "MRIVolume"),
        ),
        NodeType.RED_FLAG: NodeDecl(
            NodeType.RED_FLAG, ("Findings", "Vitals", "Demographics"), ("Alerts",), (), ("rules",), mandatory=True,
            evidence_types=("Vitals", "Demographics"),
        ),
        NodeType.PHARMA_AGENT: NodeDecl(
            NodeType.PHARMA_AGENT, ("MedicationList", "Findings"), ("MedicationIssues",), ("MedicationList",),
            ("project_model", "rules"), evidence_types=("MedicationList",),
        ),
        # i2: Reasoning reads Demographics/Vitals directly to build the S4 Case for department.suggest.
        NodeType.REASONING: NodeDecl(
            NodeType.REASONING, ("Findings", "ImageTokens", "Alerts", "Demographics", "Vitals"), REASONING_OUTPUTS,
            cfg.reasoning_required_inputs, ("project_model", "external_model"),
            evidence_types=("Demographics", "Vitals"),
        ),
        NodeType.HUMAN_CHECKPOINT: NodeDecl(
            NodeType.HUMAN_CHECKPOINT, ("Alerts", "MedicationIssues", *REASONING_OUTPUTS), ("ConfirmedResult",),
            ("Alerts",), HUMAN_PROVIDERS, mandatory=True,
        ),
    }


LIBRARY: dict[NodeType, NodeDecl] = node_decls()
READERS = (NodeType.READER_TEXT, NodeType.READER_VITALS_LABS, NodeType.READER_CXR, NodeType.READER_CT_MRI)


def output_types(node_type: NodeType, provider: str) -> tuple[str, ...]:
    """Concrete output types given the provider. Imaging readers emit ImageTokens only via an encoder."""
    decl = LIBRARY[node_type]
    if node_type in (NodeType.READER_CXR, NodeType.READER_CT_MRI):
        return ("ImageTokens",) if provider in IMAGE_ENCODERS else ("Findings",)
    return decl.output_types


class ProviderAssignment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


PLACEHOLDER_RED_FLAG_VERSION = PLACEHOLDER_RULE_SET  # reachable only by an explicit assignment
RULES_VERSIONS = {
    NodeType.READER_VITALS_LABS: "placeholder-vitals-reader-0.1",
    NodeType.RED_FLAG: RF_110,  # i2: the S4 engine; placeholder-redflag-0.2 only by explicit config
    NodeType.PHARMA_AGENT: "placeholder-pharma-0.2",  # s2r: check_results + status
}


def _default_assignments() -> dict[NodeType, ProviderAssignment]:
    a = ProviderAssignment
    return {
        NodeType.READER_TEXT: a(provider=VOICE_EXTRACT, model_version=VOICE_EXTRACT_VERSION),
        NodeType.READER_VITALS_LABS: a(provider="rules", model_version=RULES_VERSIONS[NodeType.READER_VITALS_LABS]),
        NodeType.READER_CXR: a(provider="encoder_2d", model_version="enc2d-mock-0.1"),
        NodeType.READER_CT_MRI: a(provider="encoder_3d", model_version="enc3d-mock-0.1"),
        NodeType.RED_FLAG: a(provider="rules", model_version=RULES_VERSIONS[NodeType.RED_FLAG]),
        NodeType.PHARMA_AGENT: a(provider="rules", model_version=RULES_VERSIONS[NodeType.PHARMA_AGENT]),
        NodeType.REASONING: a(provider="project_model", model_version="proj-mock-0.1"),
        NodeType.HUMAN_CHECKPOINT: a(provider="human:nurse", model_version="human"),  # i2: the nurse endpoints
    }


class ProviderConfig(BaseModel):
    """Node type -> provider assignment. This is the experiment/deployment setting (3.2.2 step 3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assignments: dict[NodeType, ProviderAssignment] = Field(default_factory=_default_assignments)
    library: LibraryConfig = Field(default_factory=LibraryConfig)

    def with_assignment(self, node_type: NodeType, assignment: ProviderAssignment) -> "ProviderConfig":
        return self.model_copy(update={"assignments": {**self.assignments, node_type: assignment}})
