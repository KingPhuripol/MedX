"""Case Graph: typed data, Node Library, Compiler, Executor, Output Store (slices s0 + s2).

Research prototype — not for clinical use. Submodules are imported explicitly
(``casegraph.compiler``, ``casegraph.executor`` ...) so ``python -m casegraph inspect`` stays light.
"""

from .types import EvidenceItem, Node, NodeType, TypedData

__all__ = ["EvidenceItem", "Node", "NodeType", "TypedData"]
