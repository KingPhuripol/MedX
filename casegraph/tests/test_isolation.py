"""Providers only through the Gateway; audit; data policy: S2-A20."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.gateway.contract import GatewayRequest
from casegraph.compiler import build_snapshot, compile_graph
from casegraph.library import MODEL_PROVIDERS
from casegraph.providers import mock_provider

from .conftest import FakeProvider, compile_case, s2_config
from .fixtures import F1_T2, F2_T, f1
from casegraph.executor import Executor
from casegraph.providers import LocalGateway
from casegraph.store import MemoryStateStore, OutputStore

CASEGRAPH = Path(__file__).resolve().parents[1]
ADAPTERS = ".".join(["gateway", "adapters"])  # built so this file does not self-match
SDKS = {"openai", "anthropic", "google.generativeai", "google.genai", "vertexai", "cohere", "mistralai",
        "groq", "together", "litellm", "langchain", "langchain_openai", "langchain_anthropic", "boto3",
        "httpx", "requests", "langgraph"}
AUDIT_FIELDS = {"provider", "model_version", "contract_version", "data_class", "request_sha256", "status",
                "latency_ms"}
SENTINEL = "SENTINEL-RAW-INPUT-7f3a"


def test_casegraph_provider_isolation():
    files = sorted(CASEGRAPH.rglob("*.py"))
    assert len(files) >= 10
    violations = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        if ADAPTERS in text:
            violations.append(f"{path}: references gateway adapters")
        for node in ast.walk(ast.parse(text)):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for mod in mods:
                if ADAPTERS in mod or any(mod == s or mod.startswith(s + ".") for s in SDKS):
                    violations.append(f"{path}: imports {mod}")
    assert violations == []


def _with_sentinel():
    items = f1()
    items[0] = items[0].model_copy(update={"text": f"{items[0].text} {SENTINEL}"})
    return items


def test_one_gateway_call_and_audit_per_model_node(env):
    graphs = [
        env.executor().run_sync(compile_graph(build_snapshot(_with_sentinel(), F1_T2), s2_config())),
        env.executor().run_sync(compile_case("F2", F2_T)),
    ]
    model_nodes = [n for g in graphs for n in g.nodes if n.provider in MODEL_PROVIDERS]
    assert len(model_nodes) == 6
    # i2: Reasoning = S4 department.suggest call + the summary/care call (2); every other model node 1
    assert all(n.gateway_calls == (2 if n.id == "reasoning" else 1) and not n.cached for n in model_nodes)
    assert all(n.gateway_calls == 0 for g in graphs for n in g.nodes if n.provider not in MODEL_PROVIDERS)
    assert env.calls == sum(n.gateway_calls for n in model_nodes) == len(env.audit)
    for rec in env.audit:
        assert rec["action"] == "gateway.invoke" and rec["outcome"] == rec["details"]["status"]
        assert AUDIT_FIELDS <= set(rec["details"])
    assert SENTINEL not in json.dumps(env.audit)
    # failures are audited too, still exactly once per call
    env.audit.clear()
    env.gateways["project_model"] = LocalGateway(FakeProvider(mode="error"), audit_sink=env.audit.append)
    fresh = Executor(env.gateways, OutputStore(), MemoryStateStore())  # empty cache
    g = fresh.run_sync(compile_case("F2", F2_T))
    assert g.node("reader_text").status == "error"
    assert [r["outcome"] for r in env.audit if r["target"] == "task/reader_text"] == ["error"]


def test_mock_provider_deterministic(env):
    gw = env.gateways["project_model"]
    req = GatewayRequest(task="reader_text", inputs={"b": 2, "a": [1, "x"]}, data_class="synthetic")
    a, b = gw.invoke(req), gw.invoke(GatewayRequest.model_validate(req.model_dump()))
    assert json.dumps(a.output, sort_keys=True).encode() == json.dumps(b.output, sort_keys=True).encode()
    assert a.request_sha256 == b.request_sha256 and a.model_version == "proj-mock-0.1"
    assert mock_provider("v-x").model_version == "v-x" and mock_provider("v-y").model_version == "v-y"


@pytest.mark.parametrize("data_class", ["mimic", "hospital", "real", "unknown"])
def test_external_gateway_rejects_non_synthetic_at_runtime(env, data_class):
    resp = env.gateways["external_model"].invoke(
        GatewayRequest(task="reasoning", inputs={"x": 1}, data_class=data_class))
    assert (resp.status, resp.reason, resp.output) == ("rejected", "policy_non_synthetic", None)
    assert env.audit[-1]["details"]["data_class"] == data_class
