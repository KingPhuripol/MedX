"""Fixed, typed tool registry. Designs cannot replace tool implementations or roles."""
from dataclasses import dataclass
from typing import Any
from pydantic import TypeAdapter
from innovation.v2.models import Model, CaseRevision, DraftContent, ConversationResult
from innovation.v2.providers import ProviderResult
from innovation.v2.store import DomainError


class ToolInput(Model):
    snapshot: CaseRevision
    text: str
    role: str


@dataclass(frozen=True)
class ToolSpec:
    output: Any
    roles: frozenset = frozenset({'intake', 'physician'})


REGISTRY = {
    'read_snapshot': ToolSpec(CaseRevision),
    'propose_information': ToolSpec(list[dict]),
    'check_information': ToolSpec(list[str]),
    'retrieve_reference': ToolSpec(list[dict]),
    'create_draft': ToolSpec(ProviderResult),
    'verify_draft': ToolSpec(DraftContent),
    'conversation': ToolSpec(ConversationResult),
}


def invoke(name, inputs, execute):
    context = ToolInput.model_validate(inputs)
    spec = REGISTRY.get(name)
    if spec is None or context.role not in spec.roles:
        raise DomainError(403, 'TOOL_FORBIDDEN')
    return TypeAdapter(spec.output).validate_python(execute())


def schemas():
    return {name: {'input': ToolInput.model_json_schema(),
        'output': TypeAdapter(spec.output).json_schema(), 'roles': sorted(spec.roles)}
        for name, spec in REGISTRY.items()}
