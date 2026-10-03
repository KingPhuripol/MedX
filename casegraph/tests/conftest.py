from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from casegraph.compiler import build_snapshot, compile_graph
from casegraph.executor import Executor
from casegraph.library import ProviderAssignment, ProviderConfig
from casegraph.types import NodeType
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


S1R_SEED = 20260926


@pytest.fixture(scope="session")
def s1r_dataset(tmp_path_factory) -> Path:
    """S1r at seed 20260926, generated once per session by the factory CLI in a subprocess
    (no ``data_factory`` import under casegraph/). Tests never compile the test split."""
    out = tmp_path_factory.mktemp("s1r") / "v1"
    root = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, "-m", "data_factory", "generate", "--seed", str(S1R_SEED), "--out", str(out)],
                   cwd=root, check=True, capture_output=True)
    return out


def s2_config(base: ProviderConfig | None = None) -> ProviderConfig:
    """The s2/s2r test configuration: placeholder Red-flag rules, a project_model Reader:Text and a physician
    Human Checkpoint.

    Slice i2 moved the *default* config to rf-1.1.0 and the voice_extract reader; the s2/s2r executor,
    screening and replay tests pin the configuration they were written for (placeholder rules stay
    reachable by explicit assignment only). The i2 tests use the default config.
    """
    cfg = base or ProviderConfig()
    cfg = cfg.with_assignment(NodeType.RED_FLAG, ProviderAssignment(provider="rules",
                                                                  model_version="placeholder-redflag-0.2"))
    # cg-t123: the default Pharma is the S5 pipeline; s2/s2r tests pin the placeholder they were written for
    cfg = cfg.with_assignment(NodeType.PHARMA_AGENT, ProviderAssignment(provider="rules",
                                                                      model_version="placeholder-pharma-0.2"))
    # i2: the default checkpoint is the nurse confirm endpoint (human:nurse); s2 tests resume as a physician
    cfg = cfg.with_assignment(NodeType.HUMAN_CHECKPOINT, ProviderAssignment(provider="human:physician",
                                                                         model_version="human"))
    return cfg.with_assignment(NodeType.READER_TEXT, ProviderAssignment(provider="project_model",
                                                                      model_version="proj-mock-0.1"))


def compile_case(name: str, T, config: ProviderConfig | None = None, **kw):
    return compile_graph(build_snapshot(FIXTURES[name](), T), config or s2_config(), **kw)


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
