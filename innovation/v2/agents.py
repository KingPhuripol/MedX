"""Bounded function-calling harness shared by the MedX agents (DEC-0021).

An agent is a system prompt, a context, a fixed list of read-only tools and a typed output.
The model may only call tools on that list; every call is budgeted, timed and traced, and
the final answer must validate against the output model. No tool writes clinical state:
agents return proposals that a person confirms through the ordinary audited endpoints.

Providers without function calling (the offline mock) run the same tools in list order and
build the answer deterministically, so tests and demos exercise the same trace path.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import monotonic
from typing import Callable
from pydantic_core import to_jsonable_python
from innovation.v2.models import ToolEvent
from innovation.v2.store import DomainError

MAX_CALLS = 8


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    fn: Callable
    parameters: dict = field(default_factory=lambda: {'type': 'object', 'properties': {}, 'additionalProperties': False})

    def spec(self):
        return {'type': 'function', 'function': {'name': self.name, 'description': self.description,
                                                 'parameters': self.parameters}}


def run_agent(provider, *, system, context, tools, output, offline, timeout=30):
    """Return (validated output, trace). Raises DomainError on any breach; callers fail safe."""
    allowed = {tool.name: tool for tool in tools}
    trace: list[ToolEvent] = []
    start = monotonic()

    def call(name, args):
        if name not in allowed:
            raise DomainError(403, 'TOOL_FORBIDDEN')
        if len(trace) >= MAX_CALLS:
            raise DomainError(429, 'TOOL_BUDGET_EXCEEDED')
        if monotonic() - start > timeout:
            raise DomainError(504, 'RUN_TIMEOUT')
        began = monotonic()
        event = ToolEvent(sequence=len(trace) + 1, tool=name, evidence_ids=[], status='COMPLETED')
        try:
            return to_jsonable_python(allowed[name].fn(**args))
        except TypeError:
            event.status, event.error_code = 'FAILED', 'INVALID_TOOL_ARGUMENTS'
            raise DomainError(502, 'INVALID_TOOL_ARGUMENTS') from None
        except Exception as exc:
            event.status, event.error_code = 'FAILED', getattr(exc, 'code', 'TOOL_FAILED')
            raise
        finally:
            event.elapsed_ms = (monotonic() - began) * 1000
            trace.append(event)

    if 'tools' not in provider.capabilities or not hasattr(provider, 'tool_step'):
        results = {tool.name: call(tool.name, {}) for tool in tools if not tool.parameters.get('required')}
        return output.model_validate(offline(results)), trace

    messages = [{'role': 'system', 'content': system},
                {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}]
    specs = [tool.spec() for tool in tools]
    while True:
        step = provider.tool_step(messages, specs, output)
        if step.get('final') is not None:
            try:
                return output.model_validate(step['final']), trace
            except ValueError:
                raise DomainError(502, 'INVALID_PROVIDER_OUTPUT') from None
        if not step.get('tool_calls'):
            raise DomainError(502, 'INVALID_PROVIDER_OUTPUT')
        messages.append(step['message'])
        for tool_call in step['tool_calls']:
            try:
                args = json.loads(tool_call.get('arguments') or '{}')
            except ValueError:
                args = None
            if not isinstance(args, dict):
                raise DomainError(502, 'INVALID_TOOL_ARGUMENTS')
            result = call(tool_call['name'], args)
            messages.append({'role': 'tool', 'tool_call_id': tool_call['id'],
                             'content': json.dumps(result, ensure_ascii=False)})
