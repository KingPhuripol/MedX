"""Typed Pydantic base classes shared by the Case Graph (PROPOSAL 3.2.1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class TypedData(BaseModel):
    """Base for every typed value flowing through a case graph. Immutable, no extra fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EvidenceItem(TypedData):
    """One evidence item. ``available_at_time`` gates what a decision at time T may see."""

    data_type: str = Field(min_length=1)
    patient_ref: str = Field(min_length=1)
    event_time: AwareDatetime
    available_at_time: AwareDatetime
    source: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    version: str = Field(min_length=1)


class NodeType(str, Enum):
    """Node types of PROPOSAL Table 3.1 (slice s2)."""

    READER_TEXT = "reader_text"
    READER_VITALS_LABS = "reader_vitals_labs"
    READER_CXR = "reader_cxr"
    READER_CT_MRI = "reader_ct_mri"
    RED_FLAG = "red_flag"
    PHARMA_AGENT = "pharma_agent"
    REASONING = "reasoning"
    HUMAN_CHECKPOINT = "human_checkpoint"


class Node(BaseModel, ABC):
    """Abstract typed node. Cannot be instantiated directly."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_type: NodeType
    input_types: tuple[str, ...]
    output_types: tuple[str, ...]
    provider: str

    @abstractmethod
    def describe(self) -> str:
        """Short, safe, typed description of the node (no hidden reasoning)."""
