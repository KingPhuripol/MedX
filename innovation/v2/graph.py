"""Executable typed workflow DAGs and integrity-checked, no-network playback.

Artifacts contain synthetic tool inputs/outputs, not model chain-of-thought.
The compiler only selects registered operations; safety remains outside routing.
"""
from random import Random
from typing import Literal
from pydantic import Field, model_validator
from innovation.v2.models import Model, DesignSpec, DraftContent
from innovation.v2.store import DomainError, digest

OPERATORS = {
    "intake": ("snapshot", "proposals"), "check": ("snapshot", "gaps"),
    "draft": ("snapshot", "draft"), "verify": ("draft", "draft"),
}


class GraphNode(Model):
    node_id: str
    operator: Literal["intake", "check", "draft", "verify"]
    input_type: Literal["snapshot", "draft"]
    output_type: Literal["proposals", "gaps", "draft"]
    depends_on: list[str] = Field(default_factory=list)


class WorkflowGraph(Model):
    schema_version: Literal["workflow-dag-1.0"] = "workflow-dag-1.0"
    scope: Literal["workflow_not_model_architecture"] = "workflow_not_model_architecture"
    snapshot_checksum: str
    design_id: str
    nodes: list[GraphNode] = Field(min_length=1, max_length=4)
    max_tool_calls: Literal[8] = 8
    case_tool_budget: Literal[30] = 30
    case_turn_budget: Literal[20] = 20
    timeout_seconds: float

    @model_validator(mode="after")
    def typed_acyclic(self):
        seen = {}
        if sum(n.operator == "draft" for n in self.nodes) != 1:
            raise ValueError("exactly one draft operator required")
        for node in self.nodes:
            if node.node_id in seen or any(parent not in seen for parent in node.depends_on):
                raise ValueError("duplicate, cyclic or non-topological dependency")
            if (node.input_type, node.output_type) != OPERATORS[node.operator]:
                raise ValueError("operator type mismatch")
            if node.input_type == "draft" and not any(seen[p].output_type == "draft" for p in node.depends_on):
                raise ValueError("draft input requires a draft dependency")
            seen[node.node_id] = node
        DesignSpec(design_id=self.design_id, nodes=[n.operator for n in self.nodes])
        return self


def compile_graph(snapshot, design, timeout_seconds=30):
    selected = list(design.nodes)
    if design.routing == "adaptive":
        known = {f.kind for f in snapshot.evidence if f.state == "KNOWN"}
        gaps = {"CHIEF_COMPLAINT", "HISTORY", "MEDICATION", "ALLERGY"} - known
        conflicts = any(f.conflicts_with_event_ids or f.state != "KNOWN" for f in snapshot.evidence)
        selected = (["intake"] if gaps else []) + (["check"] if gaps or conflicts else []) + ["draft", "verify"]
    elif design.routing == "random":
        rng = Random(str(design.routing_seed) + snapshot.checksum)
        selected = [n for n in ("intake", "check") if rng.choice([True, False])] + ["draft"]
        if rng.choice([True, False]): selected.append("verify")
    nodes = []
    for name in selected:
        parents = [nodes[-1].node_id] if nodes else []
        nodes.append(GraphNode(node_id=name, operator=name, input_type=OPERATORS[name][0], output_type=OPERATORS[name][1], depends_on=parents))
    return WorkflowGraph(snapshot_checksum=snapshot.checksum, design_id=design.design_id, nodes=nodes, timeout_seconds=timeout_seconds)


def finish_artifact(run, content):
    artifact = run.provenance.get("execution")
    if artifact is None: return
    artifact["result"] = {"status": run.status, "response": run.response, "proposals": run.proposals,
        "error_code": run.error_code, "content": content.model_dump(mode="json") if content else None}
    artifact["checksum"] = digest({k: v for k, v in artifact.items() if k != "checksum"})


def replay(artifact):
    """Playback recorded results only; no provider invocation and no case mutation."""
    if not artifact or digest({k: v for k, v in artifact.items() if k != "checksum"}) != artifact.get("checksum"):
        raise DomainError(422, "GRAPH_ARTIFACT_INTEGRITY_FAILURE")
    WorkflowGraph.model_validate(artifact["graph"])
    result = artifact["result"]
    if result["content"] is not None:
        DraftContent.model_validate(result["content"])
    return {"mode": "recorded_playback", "external_calls": 0, "artifact_checksum": artifact["checksum"], "result": result}
