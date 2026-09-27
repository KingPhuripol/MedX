from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from casegraph.compiler import build_snapshot, compile_graph
from casegraph.executor import Executor
from casegraph.library import ProviderConfig
from casegraph.providers import LocalGateway, mock_gateways
from casegraph.store import OutputStore, SQLiteStateStore

from .fixtures import FIXTURES


@dataclass
class Env:
    root: Path
    audit: list[dict] = field(default_factory=list)
    gateways: dict[str, LocalGateway] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.gateways:
            self.gateways = mock_gateways(audit_sink=self.audit.append)

    def executor(self, **kw) -> Executor:
        """A fresh Executor + fresh store instances on the same files (process-equivalent)."""
        return Executor(self.gateways, OutputStore(self.root / "outputs"), SQLiteStateStore(self.root / "state.db"), **kw)

    @property
    def calls(self) -> int:
        return sum(g.calls for g in self.gateways.values())


@pytest.fixture
def env(tmp_path) -> Env:
    return Env(tmp_path)


def compile_case(name: str, T, config: ProviderConfig | None = None, **kw):
    return compile_graph(build_snapshot(FIXTURES[name](), T), config, **kw)


class FakeProvider:
    """Test provider behind the gateway seam: ok / error / rejected / schema_invalid / raise per task."""

    def __init__(self, name="fake", model_version="fake-0.1", mode="ok", tasks=None, barrier=None):
        self.name = name
        self.model_version = model_version
        self.mode = mode
        self.tasks = tasks
        self.barrier = barrier

    def invoke(self, request, request_sha256):
        from app.gateway.provider import ProviderResult

        if self.barrier is not None and request.task.startswith("reader_"):
            self.barrier.wait(timeout=5)  # a sequential executor never reaches n parties -> error
        mode = self.mode if self.tasks is None or request.task in self.tasks else "ok"
        if mode == "raise":
            raise RuntimeError("provider internals")
        if mode in ("error", "rejected"):
            return ProviderResult(status=mode, model_version=self.model_version, output=None, reason=f"fake_{mode}")
        if mode == "schema_invalid":
            return ProviderResult(status="ok", model_version=self.model_version, output={"unexpected": 1})
        output = {"text": f"fake {self.model_version} {request_sha256[:12]}"}
        if request.task == "reasoning":  # s2r: absent department/care keys are schema_invalid; state them explicitly
            output.update(department=None, care=[])
        return ProviderResult(status="ok", model_version=self.model_version, output=output)
