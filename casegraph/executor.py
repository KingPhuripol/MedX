"""Typed Graph Executor (PROPOSAL 3.2.3).

Topological order via ``graphlib.TopologicalSorter``; independent ready nodes run concurrently on
``asyncio`` (sync provider/rule bodies via ``asyncio.to_thread``). Every node result goes to the
Output Store. Execution halts at the Human Checkpoint with ``pending_confirmation`` persisted in a
StateStore; ``resume`` records the reviewer decision. Failures are fail-safe: ``error`` with
``output=null``; Reasoning abstains when required inputs are missing or errored.

s2r: Red-flag reports per-rule ``evaluated``/``not_evaluated``; a screen that was not fully
performed escalates at the Human Checkpoint and is carried on every downstream suggestion.

i2: Reader:Text (``voice_extract``) = S3 extraction + symptom extractor; Red-flag = S4 rf-1.1.0 with vital
freshness windows; Reasoning's DepartmentSuggestion = S4 ``department.suggest``; Pharma via a named hook.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from graphlib import TopologicalSorter
from typing import Any

from app.gateway.contract import DataClass, GatewayRequest, GatewayResponse, canonical_sha256

from .compiler import ValidatedGraph, validate
from app.triage import department as s4_department

from . import reader_text, triage_bridge
from .data import (
    CLINICAL_TEXT_TYPES,
    PLACEHOLDER_RULE_SET,
    RF_110,
    Alerts,
    CareSuggestion,
    AllergyList,
    CaseSummary,
    ConfirmedEvidence,
    ConfirmedResult,
    Demographics,
    DepartmentEntry,
    DepartmentSuggestion,
    Evidence,
    IntakeTranscript,
    Findings,
    ImageTokens,
    MedicationCheck,
    MedicationIssues,
    MedicationList,
    RedFlagScreening,
    Vitals,
    VoiceIntakeFacts,
    dump_evidence,
    screening_status,
    sha256_json,
)
from .export import EdgeSpec, ExportedGraph, ExportedNode, GraphSpec, NodeSpec, Totals, import_graph, to_json
from .library import MODEL_PROVIDERS, VOICE_EXTRACT, output_types
from .providers import (
    PHARMA_HOOK,
    PLACEHOLDER_PHARMA_VERSION,
    GatewayClient,
    PharmaInput,
    red_flag_rules,
    resolve_pharma,
    vitals_reader_rules,
)
from .store import OutputStore, StateStore, StoreEntry, cache_key
from .types import NodeType

PENDING_KEY = "pending_review"
PHARMA_FACT_KINDS = frozenset({"allergy_status", "allergens", "current_medications"})
_ACTION_STATUS = {"confirm": "confirmed", "edit": "edited", "reject": "rejected"}


class ResumeError(Exception):
    """A Human Checkpoint resume request was refused (wrong role, not pending, bad action)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="microseconds")


@dataclass
class _Result:
    status: str
    output: dict[str, Any] | None = None
    missing_inputs: tuple[str, ...] = ()
    errored_inputs: tuple[str, ...] = ()
    reason: str | None = None
    gateway_calls: int = 0


@dataclass
class _Upstream:
    edge: EdgeSpec
    node: ExportedNode

    @property
    def ok(self) -> bool:
        return self.node.status == "ok" and self.node.output is not None

    @property
    def ref(self) -> str:
        return f"{self.node.id}:{self.node.output_sha256}"


@dataclass
class _Ctx:
    node: NodeSpec
    evidence: list[Evidence]
    upstream: list[_Upstream]
    input_hash: str
    T: datetime
    patient_ref: str
    stage: str | None = None
    calls: int = field(default=0)


def t_dependent(node: NodeSpec) -> bool:
    """Whether the node body reads the decision time ``T`` itself (beyond the evidence it is given).

    Red-flag rf-1.1.0 derives vital freshness and age from ``T`` (a vital fresh at an earlier ``T`` can be stale
    now), and a registered Pharma provider receives ``T`` as its snapshot ``as_of``. Reader:Text, Reasoning,
    the Vitals/Labs reader, imaging readers and the placeholder rules do not: that is tested, not assumed
    (``casegraph/tests/test_cg_t123_cache.py``). Red-flag is T-dependent by default (fail safe).
    """
    if node.type is NodeType.RED_FLAG:
        return node.model_version != PLACEHOLDER_RULE_SET
    if node.type is NodeType.PHARMA_AGENT and node.provider == "rules":
        return node.model_version != PLACEHOLDER_PHARMA_VERSION
    return False


def _dump(*models) -> dict[str, Any]:
    return {type(m).__name__: m.model_dump(mode="json") for m in models}


class _SchemaInvalid(Exception):
    pass


def _source_types(output: dict[str, Any]) -> set[str]:
    """Evidence types a Findings / ImageTokens output was derived from (ImageTokens carry ``modality``)."""
    types = set(output.get("source_data_types", ()))
    modality = output.get("modality")
    return types | (set(modality.split("+")) if isinstance(modality, str) else set())


def _alerts_of(nodes: list[ExportedNode] | tuple[ExportedNode, ...]) -> dict[str, Any] | None:
    """The Alerts output of an ok Red-flag node, else None (absent or errored -> ``unavailable``)."""
    rf = next((n for n in nodes if n.type is NodeType.RED_FLAG), None)
    return rf.output.get("Alerts") if rf is not None and rf.status == "ok" and rf.output is not None else None


def department_from_s4(derived: dict[str, Any], s4: Any, rfs: str) -> DepartmentSuggestion:
    """The S4 ``DepartmentSuggestion`` as the Case Graph type (same fields; gateway fields renamed)."""
    return DepartmentSuggestion(
        **derived, status=s4.status, top3=tuple(DepartmentEntry(**e.model_dump()) for e in s4.top3),
        uncertainty=s4.uncertainty, uncertainty_label=s4.uncertainty_label,
        missing_information=tuple(s4.missing_information), reason=s4.reason, gateway_provider=s4.provider,
        gateway_model_version=s4.model_version, contract_version=s4.contract_version,
        request_sha256=s4.request_sha256, red_flag_screening=rfs,  # type: ignore[arg-type]
    )


def red_flag_screening(nodes: list[ExportedNode] | tuple[ExportedNode, ...]) -> RedFlagScreening:
    rf = next((n for n in nodes if n.type is NodeType.RED_FLAG), None)
    return RedFlagScreening.from_alerts(_alerts_of(nodes), rf.model_version if rf is not None else RF_110)


class Executor:
    def __init__(
        self,
        gateways: Mapping[str, GatewayClient],
        output_store: OutputStore,
        state_store: StateStore,
        *,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.gateways = gateways
        self.outputs = output_store
        self.state = state_store
        self.clock = clock  # used for confirmation times (injectable for tests)
        self.node_executions: Counter[str] = Counter()  # node bodies actually run (incl. rules)

    # ------------------------------------------------------------------------------------ run

    def run_sync(self, graph: ValidatedGraph) -> ExportedGraph:
        return asyncio.run(self.run(graph))

    async def run(self, graph: ValidatedGraph) -> ExportedGraph:
        if not isinstance(graph, ValidatedGraph) or not graph.is_authentic:
            raise TypeError("Executor accepts only a ValidatedGraph issued by casegraph.compiler.validate")
        if graph.snapshot is None:
            raise ValueError("graph carries no snapshot payload; use casegraph.store.replay")
        # Re-check the exact (spec, snapshot) pair about to run, so a token can never vouch for a
        # graph other than the one validated. Raises GraphValidationError before any side effect.
        validate(graph.spec, graph.snapshot)
        spec, items = graph.spec, {i.item_id: i for i in graph.snapshot.items}
        self.state.save_graph(spec, graph.snapshot.items)  # insert-only: versions are immutable
        t0 = time.perf_counter()
        preds = {n.id: {e.src for e in spec.edges if e.dst == n.id} for n in spec.nodes}
        sorter = TopologicalSorter(preds)
        sorter.prepare()
        results: dict[str, ExportedNode] = {}
        running: dict[asyncio.Task, str] = {}
        while sorter.is_active():
            for nid in sorter.get_ready():
                # All predecessors are done here: a node never starts before them.
                task = asyncio.create_task(self._run_node(spec, spec.node(nid), items, dict(results)))
                running[task] = nid
            done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                nid = running.pop(task)
                results[nid] = task.result()
                sorter.done(nid)
        nodes = tuple(results[n.id] for n in spec.nodes)
        exported = ExportedGraph(
            **spec.model_dump(exclude={"nodes"}),
            nodes=nodes,
            red_flag_screening=red_flag_screening(nodes),
            totals=Totals(
                gateway_calls=sum(n.gateway_calls for n in nodes),
                node_executions=sum(not n.cached for n in nodes),
                wall_time_ms=round((time.perf_counter() - t0) * 1000, 3),
            ),
        )
        self.state.save_run(spec.graph_id, to_json(exported))
        return exported

    async def _run_node(
        self, spec: GraphSpec, node: NodeSpec, items: dict[str, Evidence], results: dict[str, ExportedNode]
    ) -> ExportedNode:
        started = _now()
        upstream = [_Upstream(e, results[e.src]) for e in spec.edges if e.dst == node.id]
        evidence = [items[r] for r in node.evidence_refs]
        hashed: dict[str, Any] = {
            "evidence": [[i.item_id, i.content_sha256()] for i in evidence],
            "upstream": sorted([u.node.id, u.edge.data_type, u.node.status, u.node.output_sha256] for u in upstream),
        }
        if t_dependent(node):  # cg-t123: a body that reads T must not be served an output computed at another T
            hashed["T"] = spec.T.isoformat()
        input_hash = sha256_json(hashed)
        key = cache_key(node.type.value, node.provider, node.model_version, node.params, input_hash)
        base = node.model_dump()
        entry = self.outputs.get(key)
        if entry is not None and entry.status != "error":
            return ExportedNode(
                **base, cache_key=key, status=entry.status, started_at=_iso(started), ended_at=_iso(_now()),
                gateway_calls=0, cached=True, output=entry.output, output_sha256=entry.output_sha256,
                missing_inputs=entry.missing_inputs, errored_inputs=entry.errored_inputs, reason=entry.reason,
            )
        self.node_executions[node.id] += 1
        ctx = _Ctx(node, evidence, upstream, input_hash, spec.T, spec.patient_ref, spec.stage)
        try:
            res = await asyncio.to_thread(self._body, ctx)
        except Exception:  # fail safe: never fabricate an output
            res = _Result("error", reason="node_exception")
        res.gateway_calls = ctx.calls
        if res.status == "error":
            res.output = None
        ended = _now()
        out_sha = sha256_json(res.output)
        self.outputs.put(
            StoreEntry(
                cache_key=key, node_type=node.type.value, status=res.status, output=res.output,  # type: ignore[arg-type]
                output_sha256=out_sha, missing_inputs=res.missing_inputs, errored_inputs=res.errored_inputs,
                reason=res.reason, started_at=_iso(started), ended_at=_iso(ended), gateway_calls=res.gateway_calls,
            )
        )
        return ExportedNode(
            **base, cache_key=key, status=res.status, started_at=_iso(started), ended_at=_iso(ended),
            gateway_calls=res.gateway_calls, cached=False, output=res.output, output_sha256=out_sha,
            missing_inputs=res.missing_inputs, errored_inputs=res.errored_inputs, reason=res.reason,
        )

    # --------------------------------------------------------------------------------- bodies

    def _body(self, ctx: _Ctx) -> _Result:
        t = ctx.node.type
        if t is NodeType.RED_FLAG:
            return self._red_flag(ctx)
        if t is NodeType.REASONING:
            return self._reasoning(ctx)
        if t is NodeType.HUMAN_CHECKPOINT:
            return self._checkpoint(ctx)
        if t is NodeType.PHARMA_AGENT:
            return self._pharma(ctx)
        return self._reader(ctx)

    def _derived(self, ctx: _Ctx, extra_refs: list[str] | None = None) -> dict[str, Any]:
        refs = [i.item_id for i in ctx.evidence] + [u.ref for u in ctx.upstream if u.ok] + (extra_refs or [])
        return {"produced_by": ctx.node.id, "input_refs": tuple(refs), "provider": ctx.node.provider,
                "model_version": ctx.node.model_version}

    def _invoke(self, ctx: _Ctx, request: GatewayRequest, key: str | None = None) -> GatewayResponse | None:
        """Send one request through the node provider's gateway (None: no such gateway). Counts the call.

        ``key`` names another gateway (the Pharma hook uses ``pharma_agent``: its node provider is ``rules``)."""
        gateway = self.gateways.get(key or ctx.node.provider)
        if gateway is None:
            return None
        ctx.calls += 1
        return gateway.invoke(request)

    def _call(self, ctx: _Ctx, inputs: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """One gateway call. Returns (output, request_sha256, error_reason)."""
        request = GatewayRequest(
            task=ctx.node.type.value,
            inputs={"model_version": ctx.node.model_version, "params": ctx.node.params, **inputs},
            data_class=DataClass(ctx.node.data_class),
        )
        response = self._invoke(ctx, request)
        if response is None:
            return None, None, "provider_unavailable"
        if response.status != "ok" or response.output is None:
            return None, response.request_sha256, f"gateway_{response.status}:{response.reason}"
        return response.output, response.request_sha256, None

    @staticmethod
    def _text(output: dict[str, Any]) -> str:
        text = output.get("text")
        if not isinstance(text, str) or not text:
            raise _SchemaInvalid("output.text must be a non-empty string")
        return text

    def _reader(self, ctx: _Ctx) -> _Result:
        node = ctx.node
        source_types = tuple(sorted({i.data_type for i in ctx.evidence}))
        if node.provider == "rules":
            statements = vitals_reader_rules(ctx.evidence)  # type: ignore[arg-type]
            return _Result("ok", _dump(Findings(**self._derived(ctx), source_data_types=source_types,
                                                statements=statements)))
        if node.type is NodeType.READER_TEXT and (
            node.provider == VOICE_EXTRACT or any(isinstance(i, VoiceIntakeFacts) for i in ctx.evidence)
        ):
            return self._voice_reader(ctx)
        if node.provider not in MODEL_PROVIDERS:
            return _Result("error", reason="provider_unsupported")
        output, req_sha, err = self._call(ctx, {"evidence": dump_evidence(ctx.evidence)})
        if err:
            return _Result("error", reason=err)
        try:
            text = self._text(output)  # type: ignore[arg-type]
        except _SchemaInvalid:
            return _Result("error", reason="schema_invalid")
        if output_types(node.type, node.provider) == ("ImageTokens",):
            tokens = ImageTokens(
                **self._derived(ctx), modality="+".join(source_types), encoder_provider=node.provider,
                token_ref=f"gateway-request:{req_sha}", token_sha256=sha256_json({"text": text}),
            )
            return _Result("ok", _dump(tokens))
        return _Result("ok", _dump(Findings(**self._derived(ctx), source_data_types=source_types,
                                            statements=(text,))))

    def _voice_reader(self, ctx: _Ctx) -> _Result:
        """Reader:Text = S3 voice extraction + ``voice.symptom_extract.v1`` (i2 scope 3).

        A transcript, when present, is always the source; ``VoiceIntakeFacts`` pass through with 0 calls
        only when there is no transcript. A plain ClinicalText note gets one generic ``reader_text`` call.
        With a model provider other than ``voice_extract`` (s2 configuration), transcripts and notes go to
        that one generic call and ``VoiceIntakeFacts`` still pass through (structured facts need no model).
        """
        T = ctx.T
        notes = [i for i in ctx.evidence if i.data_type == "ClinicalText"]
        dc = DataClass(ctx.node.data_class)

        def invoke(task: str, inputs: dict[str, Any]) -> tuple[dict[str, Any], str]:
            response = self._invoke(ctx, GatewayRequest(task=task, inputs=inputs, data_class=dc))
            if response is None:
                raise reader_text.ReaderError("provider_unavailable")
            if response.status != "ok" or response.output is None:
                raise reader_text.ReaderError(f"gateway_{response.status}:{response.reason}")
            return response.output, response.model_version

        if ctx.node.provider not in (VOICE_EXTRACT, *MODEL_PROVIDERS):
            return _Result("error", reason="provider_unsupported")
        voice_evidence = [i for i in ctx.evidence if isinstance(i, (IntakeTranscript, VoiceIntakeFacts))]
        skipped: list[str] = []
        if ctx.node.provider != VOICE_EXTRACT:  # s2 configuration: transcripts go to the one generic call
            notes = [i for i in ctx.evidence if not isinstance(i, VoiceIntakeFacts)]
            facts_items = [i for i in voice_evidence if isinstance(i, VoiceIntakeFacts)]
            has_transcript = any(isinstance(i, IntakeTranscript) for i in ctx.evidence)
            voice_evidence = [] if has_transcript else facts_items
            if has_transcript:
                skipped = [f"{i.item_id}: not read (a transcript is present and is the source)" for i in facts_items]
        try:
            intake, facts, statements, read_types = reader_text.read_clinical_text(voice_evidence, T, invoke)
            statements += skipped
            if notes:
                output, _, err = self._call(ctx, {"evidence": dump_evidence(notes)})
                if err:
                    return _Result("error", reason=err)
                statements.append(self._text(output))  # type: ignore[arg-type]
                read_types |= {i.data_type for i in notes}
        except reader_text.ReaderError as exc:
            return _Result("error", reason=f"reader_text:{str(exc)[:120]}")
        except _SchemaInvalid:
            return _Result("error", reason="schema_invalid")
        findings = Findings(**self._derived(ctx), source_data_types=tuple(sorted(read_types)),
                            statements=tuple(statements), facts=tuple(facts), intake=tuple(intake))
        return _Result("ok", _dump(findings))

    def _findings_inputs(self, ctx: _Ctx) -> list[tuple[str, dict[str, Any], str]]:
        return [(u.ref, u.node.output["Findings"], u.node.model_version) for u in ctx.upstream
                if u.ok and u.edge.data_type == "Findings" and "Findings" in u.node.output]  # type: ignore[operator]

    def _red_flag(self, ctx: _Ctx) -> _Result:
        vitals = [i for i in ctx.evidence if isinstance(i, Vitals)]
        findings = [u for u in ctx.upstream if u.edge.data_type == "Findings"]
        errored = tuple(sorted(u.node.id for u in ctx.upstream if u.node.status == "error"))
        if ctx.node.model_version == RF_110:
            return self._red_flag_rf110(ctx, errored)
        if ctx.node.model_version != PLACEHOLDER_RULE_SET:
            return _Result("error", reason="rule_set_unsupported", errored_inputs=errored)
        # An input type is missing when absent or when any of its producers errored (s2r).
        absent = {
            "Findings": not any(u.ok for u in findings) or any(u.node.status == "error" for u in findings),
            "Vitals": not vitals,
        }
        rule_results, alerts = red_flag_rules(vitals)
        missing = tuple(sorted({t for t, gone in absent.items() if gone}
                               | {m for r in rule_results for m in r.missing_inputs}))
        output = Alerts(
            **self._derived(ctx), status=screening_status(rule_results, missing), alerts=alerts,
            rule_results=rule_results,
            rules_evaluated=tuple(sorted(r.rule_id for r in rule_results if not r.missing_inputs)),
            rules_not_evaluated=tuple(sorted(r.rule_id for r in rule_results if r.missing_inputs)),
            missing_inputs=missing, rule_set_version=PLACEHOLDER_RULE_SET,
        )
        return _Result("ok", _dump(output), missing_inputs=missing, errored_inputs=errored)

    def _red_flag_rf110(self, ctx: _Ctx, errored: tuple[str, ...]) -> _Result:
        """S4 rf-1.1.0 over snapshot Demographics/Vitals (within freshness windows) and Reader:Text Findings."""
        findings = [u for u in ctx.upstream if u.edge.data_type == "Findings"]
        extra = ("Findings",) if any(u.node.status == "error" for u in findings) else ()
        adapted = triage_bridge.build_case(
            ctx.patient_ref, ctx.T, ctx.evidence, self._findings_inputs(ctx),
            freshness=triage_bridge.load_freshness(), data_class=ctx.node.data_class,
        )
        screen = triage_bridge.screen_rf110(adapted, extra)
        output = Alerts(**self._derived(ctx), status=screening_status(screen.rule_results, screen.missing_inputs),
                        **triage_bridge.screen_fields(adapted, screen))
        return _Result("ok", _dump(output), missing_inputs=output.missing_inputs, errored_inputs=errored)

    @staticmethod
    def _conversation_facts(ctx: _Ctx) -> tuple[dict[str, Any], ...]:
        """Reader:Text intake values (allergy / medication facts from the conversation), the only Findings Pharma reads."""
        out = []
        for u in ctx.upstream:
            if u.ok and u.edge.data_type == "Findings" and u.node.type is NodeType.READER_TEXT:
                out += [v for v in u.node.output["Findings"].get("intake", ())  # type: ignore[index]
                        if v["kind"] in PHARMA_FACT_KINDS]
        return tuple(out)

    def _allergy_gate(self, ctx: _Ctx, allergies: list[AllergyList], hook_api: int | None,
                      label: str) -> tuple[MedicationCheck, ...]:
        """Allergy evidence that is missing or unknown is ``not_evaluated``, never read as "no allergy" (rule 6).

        The placeholder rules (api 1) never cross-check allergies against orders: that check is stated as not
        evaluated instead of being silently skipped."""
        def gate(check: str, missing: tuple[str, ...]) -> MedicationCheck:
            return MedicationCheck(medication="*", check=check, missing_inputs=missing, evaluated_on=(), fired=None,
                                   status=screening_status([False], missing, allow_partial=False), label=label)
        out: list[MedicationCheck] = []
        latest = max(allergies, key=lambda a: (a.available_at_time, a.item_id), default=None)
        if latest is None:
            out.append(gate("allergy_record", ("AllergyList",)))
        elif latest.status == "unknown":
            out.append(gate("allergy_record", ("AllergyList.status=unknown",)))
        if hook_api == 1:
            out.append(gate("allergy_conflict", ("allergy_conflict_check:not_implemented_by_provider",)))
        return tuple(out)

    def _pharma(self, ctx: _Ctx) -> _Result:
        lists = [i for i in ctx.evidence if isinstance(i, MedicationList)]
        allergies = [i for i in ctx.evidence if isinstance(i, AllergyList)]
        if ctx.node.provider == "rules":
            hook = resolve_pharma(ctx.node.model_version)  # the named Pharma Agent hook (i2 scope 8)
            if hook is None:
                return _Result("error", reason="pharma_provider_unregistered")
            if hook.api == 2:
                dc = DataClass(ctx.node.data_class)

                def invoke(request: GatewayRequest) -> GatewayResponse:
                    response = self._invoke(ctx, request, key=PHARMA_HOOK)
                    if response is None:
                        return GatewayResponse(status="error", provider="none", model_version="unknown", output=None,
                                               reason="provider_unavailable", latency_ms=0.0,
                                               request_sha256=canonical_sha256(request))
                    return response

                checks, issues = hook.fn(PharmaInput(  # type: ignore[arg-type]
                    tuple(lists), tuple(allergies), self._conversation_facts(ctx), ctx.T, dc.value, invoke))
            else:
                checks, issues = hook.fn(lists)  # type: ignore[arg-type]
            if ctx.stage is not None:  # staged graphs state missing allergy data; legacy graphs are unchanged
                checks = (*checks, *self._allergy_gate(ctx, allergies, hook.api, hook.label))
            missing = tuple(sorted({m for c in checks for m in c.missing_inputs}))
            output = MedicationIssues(
                **self._derived(ctx), status=screening_status(checks, missing), issues=issues, check_results=checks,
                checks_not_evaluated=tuple(c for c in checks if c.missing_inputs), missing_inputs=missing,
                rule_set_version=ctx.node.model_version, label=hook.label,
            )
            return _Result("ok", _dump(output))
        upstream = {u.node.id: u.node.output for u in ctx.upstream if u.ok}
        output, _, err = self._call(ctx, {"evidence": dump_evidence([*lists, *allergies]), "upstream": upstream})
        if err:
            return _Result("error", reason=err)
        try:
            text = self._text(output)  # type: ignore[arg-type]
        except _SchemaInvalid:
            return _Result("error", reason="schema_invalid")
        # The model path runs no structured rule check: it is explicitly not_evaluated (s2r).
        missing = ("structured_rule_checks",)
        return _Result("ok", _dump(MedicationIssues(
            **self._derived(ctx), status=screening_status((), missing), issues=(), check_results=(),
            checks_not_evaluated=(), missing_inputs=missing, summary=text)))

    def _reasoning(self, ctx: _Ctx) -> _Result:
        errored = tuple(sorted(u.node.id for u in ctx.upstream if u.node.status == "error"))
        missing = []
        if not isinstance(ctx.node.params.get("required_inputs"), list):
            # s2r sweep: an undeclared requirement list must not read as "nothing required"
            return _Result("error", reason="required_inputs_undeclared", errored_inputs=errored)
        for req in ctx.node.params["required_inputs"]:
            data_type, _, source = req.partition("<-")
            # i2: "ClinicalText" names the family (transcripts and extracted facts enter as ClinicalText)
            sources = set(CLINICAL_TEXT_TYPES) if source == "ClinicalText" else {source}
            satisfied = any(
                u.ok and u.edge.data_type == data_type
                and (not source or sources & _source_types(u.node.output.get(data_type, {})))
                for u in ctx.upstream
            )
            if not satisfied:
                missing.append(req)
        if missing:  # abstain: 0 gateway calls, no Summary/Suggestion object
            return _Result("abstained", None, missing_inputs=tuple(missing), errored_inputs=errored)
        d = self._derived(ctx)
        rfs = red_flag_screening([u.node for u in ctx.upstream]).status
        # i2 scope 5: the department part is S4 department.suggest on the S4 Case (latest wins, no freshness)
        adapted = triage_bridge.build_case(ctx.patient_ref, ctx.T, ctx.evidence, self._findings_inputs(ctx),
                                           data_class=ctx.node.data_class)

        def invoke_department(request: GatewayRequest) -> GatewayResponse:
            response = self._invoke(ctx, request)
            if response is None:
                return GatewayResponse(status="error", provider="none", model_version="unknown", output=None,
                                       reason="provider_unavailable", latency_ms=0.0,
                                       request_sha256=canonical_sha256(request))
            return response

        s4 = s4_department.suggest(adapted.snapshot(), invoke_department)
        suggestion = department_from_s4(d, s4, rfs)
        if s4.status == "abstained" and ctx.calls == 0:  # S4 REQUIRED_FIELDS / conflict: 0 calls
            return _Result("abstained", _dump(suggestion), missing_inputs=suggestion.missing_information,
                           errored_inputs=errored, reason=s4.reason)
        upstream = {u.node.id: u.node.output for u in ctx.upstream if u.ok}
        output, _, err = self._call(ctx, {"upstream": upstream})
        if err:
            return _Result("error", reason=err, errored_inputs=errored)
        try:
            text = self._text(output)  # type: ignore[arg-type]
            # s2r: an absent key is schema_invalid, never "no care"; an explicit empty list is.
            if "care" not in output:  # type: ignore[operator]
                raise _SchemaInvalid("care key is required")
            care = output["care"]  # type: ignore[index]
            if not isinstance(care, list) or not all(isinstance(c, str) for c in care):
                raise _SchemaInvalid("care")
        except _SchemaInvalid:
            return _Result("error", reason="schema_invalid", errored_inputs=errored)
        return _Result(
            "ok",
            _dump(CaseSummary(**d, text=text, red_flag_screening=rfs), suggestion,
                  CareSuggestion(**d, items=tuple(care), red_flag_screening=rfs)),
            errored_inputs=errored,
        )

    def _checkpoint(self, ctx: _Ctx) -> _Result:
        upstream_nodes = [u.node for u in ctx.upstream if u.edge.data_type == "Alerts"]
        alerts = _alerts_of(upstream_nodes)
        screening = red_flag_screening(upstream_nodes)
        reasons = []  # accumulates: every applicable reason is recorded
        if screening.status == "unavailable":
            reasons.append("red_flag_unavailable")
        if screening.status == "not_evaluated":
            reasons.append("red_flag_not_evaluated")
        if screening.status == "partially_evaluated":
            reasons.append("red_flag_partially_evaluated")
        if alerts is not None and any(a["severity"] == "urgent" for a in alerts["alerts"]):
            reasons.append("urgent_red_flag")
        by_node: dict[str, ExportedNode] = {u.node.id: u.node for u in ctx.upstream}
        payload = {
            "required_role": ctx.node.provider.split(":", 1)[1],
            "escalation": bool(reasons),
            "escalation_reasons": reasons,
            "red_flag_screening": screening.model_dump(mode="json"),  # i2: rule set, label, scope, counts, readings
            "screening_summary": screening.summary(),  # never "no red flags" (C2)
            "vital_readings": [r.model_dump(mode="json") for r in screening.readings],  # read time + age (C1)
            "conflicts": list(screening.conflicts),  # same-timestamp conflicts (C4)
            "alerts": alerts,
            # each entry carries the screening status so a suggestion never reads as "screening passed"
            "for_review": {nid: {**n.output, "red_flag_screening": screening.status} for nid, n in sorted(by_node.items())
                           if n.status == "ok" and n.output is not None and n.type is not NodeType.RED_FLAG},
            "abstained": {nid: list(n.missing_inputs) for nid, n in sorted(by_node.items()) if n.status == "abstained"},
            "abstained_outputs": {nid: n.output for nid, n in sorted(by_node.items())
                                  if n.status == "abstained" and n.output is not None},
            # direct upstream failures plus failures that upstream nodes reported from further up
            "errored": sorted({nid for nid, n in by_node.items() if n.status == "error"}
                              | {e for n in by_node.values() for e in n.errored_inputs}),
            # cg-t123: results earlier checkpoints confirmed/edited and that were available at T (never rejected ones:
            # a reject appends nothing). Context for the reviewer, shown apart from this version's `for_review`.
            "prior_confirmed": self._prior_confirmed(ctx),
            "input_hash": ctx.input_hash,
        }
        return _Result("pending_confirmation", {PENDING_KEY: payload})

    @staticmethod
    def _prior_confirmed(ctx: _Ctx) -> list[dict[str, Any]]:
        out = []
        for c in sorted((i for i in ctx.evidence if isinstance(i, ConfirmedEvidence)),
                        key=lambda i: (i.available_at_time, i.item_id)):
            r = c.result
            payload = r.payload
            content = payload.get("for_review") if r.action == "confirm" and isinstance(payload, dict) else payload
            out.append({"item_id": c.item_id, "graph_id": r.graph_id, "action": r.action,
                        "reviewer_role": r.reviewer_role, "reviewer_id": r.reviewer_id,
                        "confirmed_at": _iso(r.confirmed_at), "available_at_time": _iso(c.available_at_time),
                        "content": content})
        return out

    # --------------------------------------------------------------------------- export/resume

    def export(self, graph_id: str) -> ExportedGraph:
        run_json = self.state.load_run(graph_id)
        if run_json is None:
            raise KeyError(graph_id)
        return import_graph(run_json)

    def resume(
        self,
        graph_id: str,
        action: str,
        reviewer_id: str,
        reviewer_role: str,
        edited_payload: dict[str, Any] | None = None,
    ) -> ConfirmedResult:
        """Record a reviewer decision at the Human Checkpoint. Makes no gateway call."""
        if action not in _ACTION_STATUS:
            raise ResumeError(f"unknown action {action!r}")
        graph = self.export(graph_id)
        hc = graph.by_type(NodeType.HUMAN_CHECKPOINT)
        if hc is None or hc.status != "pending_confirmation" or hc.output is None:
            raise ResumeError(f"{graph_id}: checkpoint is not pending confirmation")
        if hc.provider != f"human:{reviewer_role}":
            raise ResumeError(f"{graph_id}: checkpoint requires {hc.provider}, not human:{reviewer_role}")
        if action == "edit" and edited_payload is None:
            raise ResumeError("edit requires edited_payload")
        pending = hc.output[PENDING_KEY]
        now = self.clock()
        if now.tzinfo is None:
            raise ResumeError(f"{graph_id}: confirmation clock returned a naive datetime")
        if now < graph.T:
            # The payload depends on evidence up to T; stamping it earlier would leak it into
            # snapshots before T (data rule 3). Refuse before any state is written.
            raise ResumeError(
                f"{graph_id}: confirmation time {now.isoformat()} is earlier than graph T {graph.T.isoformat()}"
            )
        result = ConfirmedResult(
            produced_by=hc.id, input_refs=(f"{hc.id}:{hc.output_sha256}",), provider=hc.provider,
            model_version=hc.model_version, action=action, graph_id=graph_id,  # type: ignore[arg-type]
            reviewer_id=reviewer_id, reviewer_role=reviewer_role,  # type: ignore[arg-type]
            confirmed_at=now, checkpoint_input_hash=pending["input_hash"],
            payload={"confirm": pending, "edit": edited_payload, "reject": None}[action],
        )
        updated = hc.model_copy(update={"status": _ACTION_STATUS[action],
                                        "confirmation": result.model_dump(mode="json")})
        graph = graph.model_copy(update={"nodes": tuple(updated if n.id == hc.id else n for n in graph.nodes)})
        self.state.save_run(graph_id, to_json(graph))
        if action != "reject":  # the confirmed result re-enters the record, visible from `now` onwards
            self.state.append_evidence(
                ConfirmedEvidence(
                    item_id=f"confirmed:{graph_id}:{hc.id}", patient_ref=graph.patient_ref,
                    event_time=now, available_at_time=now, source="human_checkpoint",
                    provenance=f"casegraph/{graph_id}/{hc.id}", version="1", data_class=hc.data_class,  # type: ignore[arg-type]
                    result=result,
                )
            )
        return result
