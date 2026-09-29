from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

import casegraph
from casegraph import EvidenceItem, Node, NodeType, TypedData

T0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
VALID = dict(
    data_type="vital_signs",
    patient_ref="SYN-0001",
    event_time=T0,
    available_at_time=T0,
    source="synthetic-fixture",
    provenance="casegraph/tests",
    version="0.1.0",
)


def test_package_imports_and_exports_base_types():
    assert issubclass(EvidenceItem, TypedData)
    # s0 asserted NodeType.PLACEHOLDER; superseded by slice s2 (Table 3.1 node types).
    assert {t.value for t in NodeType} == {
        "reader_text", "reader_vitals_labs", "reader_cxr", "reader_ct_mri",
        "red_flag", "pharma_agent", "reasoning", "human_checkpoint",
    }
    assert not hasattr(NodeType, "PLACEHOLDER")


def test_valid_evidence_item():
    item = EvidenceItem(**VALID)
    assert item.available_at_time == T0


@pytest.mark.parametrize("missing", ["available_at_time", "source", "provenance", "version"])
def test_evidence_item_requires_field(missing):
    data = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(ValidationError):
        EvidenceItem(**data)


def test_evidence_item_requires_timezone_aware_times():
    with pytest.raises(ValidationError):
        EvidenceItem(**{**VALID, "available_at_time": datetime(2026, 1, 1, 8, 0)})


def test_node_is_abstract():
    with pytest.raises(TypeError):
        Node(node_type=NodeType.READER_TEXT, input_types=(), output_types=(), provider="mock")


def test_node_subclass_can_be_instantiated():
    class Echo(Node):
        def describe(self) -> str:
            return "echo"

    node = Echo(node_type=NodeType.READER_TEXT, input_types=("a",), output_types=("a",), provider="mock")
    assert node.describe() == "echo"


def test_compiler_and_executor_exist_as_of_s2():
    """Supersedes s0 ``test_no_compiler_or_executor_symbols`` ("Those are slice S2").

    s0 asserted the absence of compile/execute symbols; slice s2 delivers them as explicit
    modules. ``casegraph.types`` itself still holds typed base classes only.
    """
    import casegraph.types as t

    assert not any("compile" in n.lower() or "execute" in n.lower() for n in dir(t))
    assert not any("compile" in n.lower() or "execute" in n.lower() for n in casegraph.__all__)

    from casegraph.compiler import compile_graph, validate
    from casegraph.executor import Executor

    assert callable(compile_graph) and callable(validate) and callable(Executor)
