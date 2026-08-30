"""The Model Gateway.

Every provider is reached through here. The gateway validates, authorizes, checks
temporal validity, budgets, calls the provider, runs the deterministic
pre-inference screen, calls the provider, merges the screen with the provider output
under the safety layer, validates the response, and audits — in that order.

The ordering is the contract, not an implementation detail. `INVALID_REQUEST`,
`TEMPORAL_VIOLATION` and `UNAUTHORIZED_DATA` are all blocked *before* a provider is
called, so a rejected request never reaches a provider and a future-dated or
unauthorized payload never leaves the process.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import uuid
from datetime import datetime, timezone

from innovation.gateway.audit import AuditLog, AuditRecord
from innovation.gateway.breaker import CircuitBreaker
from innovation.gateway.providers.base import (
    Provider,
    ProviderFailure,
    ProviderOutput,
    ProviderTimeout,
)
from innovation.gateway.safety import SafetyPolicy, ScreenResult
from shared.contracts.errors import ContractViolation, ErrorCode
from shared.contracts.model_api import (
    CONTRACT_VERSION,
    GatewayRequest,
    GatewayResponse,
    GraphRef,
    HumanReview,
    Provenance,
    ResponseError,
    Uncertainty,
    Urgency,
)

SUPPORTED_CONTRACT_VERSIONS = frozenset({"1.0.0"})

#: Classifications that may never be sent to an external provider without a recorded
#: approval (DEC-0006, `CLAUDE.md` §Non-negotiable data rules 7).
EXTERNAL_RESTRICTED_CLASSIFICATIONS = frozenset(
    {"DEIDENTIFIED_APPROVED", "IDENTIFIABLE_OR_LINKABLE", "RESTRICTED_DERIVATIVE"}
)

EXTERNAL_PROVIDERS = frozenset({"external_prototype"})

ALL_REVIEW_ACTIONS = ["CONFIRM", "MODIFY", "REJECT", "REQUEST_INFORMATION", "ESCALATE"]


class ModelGateway:
    """Single entry point to every model provider."""

    def __init__(
        self,
        provider: Provider,
        *,
        audit_log: AuditLog | None = None,
        safety_policy: SafetyPolicy | None = None,
        breaker: CircuitBreaker | None = None,
        enforce_timeout: bool = True,
    ) -> None:
        self.provider = provider
        self.audit = audit_log or AuditLog()
        self.safety = safety_policy or SafetyPolicy()
        self.breaker = breaker or CircuitBreaker()
        self._enforce_timeout = enforce_timeout
        self._seen_request_ids: dict[str, GatewayResponse] = {}
        #: One worker: provider calls are serialised per gateway, which is what makes the
        #: deadline meaningful rather than merely advisory.
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="gateway-provider"
        )

    def close(self) -> None:
        """Release the provider worker. Safe to call more than once."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ public API

    def infer(self, payload: dict | GatewayRequest) -> GatewayResponse:
        """Run one request end to end. Always returns a contract-valid response.

        Failures become `FAILED_SAFE` responses carrying a structured error, rather than
        exceptions escaping to the caller. A client that receives a response can always
        render it; there is no path that completes without `human_review.required`.
        """
        started_at = datetime.now(timezone.utc)

        try:
            request = self._parse(payload)
        except ContractViolation as violation:
            return self._safe_failure_without_request(payload, violation, started_at)

        # Idempotency (contract test 9): a repeated request ID returns the recorded
        # response instead of calling the provider again.
        if request.request_id in self._seen_request_ids:
            return self._seen_request_ids[request.request_id]

        try:
            self._check_temporal_validity(request)
            self._check_authorization(request)
            self._check_budget(request)
            # Deterministic screen runs BEFORE the provider (CLINICAL_WORKFLOW step 3, A1).
            # Its findings are established independently of whatever the model then says.
            screen_result = self.safety.screen(request)
            output = self._call_provider(request)
            response = self._build_response(request, output, started_at, screen_result)
        except ContractViolation as violation:
            response = self._safe_failure(request, violation, started_at)

        self._seen_request_ids[request.request_id] = response
        return response

    # ----------------------------------------------------------------- validation

    def _parse(self, payload: dict | GatewayRequest) -> GatewayRequest:
        if isinstance(payload, GatewayRequest):
            request = payload
        else:
            try:
                request = GatewayRequest.model_validate(payload)
            except Exception as exc:  # pydantic ValidationError and friends
                raise ContractViolation(
                    ErrorCode.INVALID_REQUEST, f"request failed contract validation: {exc}"
                ) from exc

        if request.contract_version not in SUPPORTED_CONTRACT_VERSIONS:
            # An unknown major version fails safe rather than being best-guessed.
            raise ContractViolation(
                ErrorCode.INVALID_REQUEST,
                f"unsupported contract_version {request.contract_version}",
            )
        return request

    def _check_temporal_validity(self, request: GatewayRequest) -> None:
        """Block evidence that did not exist at the decision time.

        This is the hard rule from `CLAUDE.md` §Non-negotiable data rules 3. It is
        enforced here as well as at snapshot time, because a request may be assembled by
        any client and the gateway is the boundary that cannot be bypassed.
        """
        future = sorted(
            e.evidence_id for e in request.evidence if e.available_at_time > request.decision_time
        )
        if future:
            raise ContractViolation(
                ErrorCode.TEMPORAL_VIOLATION,
                "evidence is not available at decision_time: " + ", ".join(future),
            )

    def _check_authorization(self, request: GatewayRequest) -> None:
        """Refuse classification/provider combinations that are not approved."""
        auth = request.authorization
        is_external = self.provider.name in EXTERNAL_PROVIDERS

        classifications = {e.data_classification for e in request.evidence}
        classifications.add(auth.data_classification)
        restricted = classifications & EXTERNAL_RESTRICTED_CLASSIFICATIONS

        if is_external and restricted:
            if not auth.external_provider_allowed:
                raise ContractViolation(
                    ErrorCode.UNAUTHORIZED_DATA,
                    "external provider is not permitted for classifications: "
                    + ", ".join(sorted(restricted)),
                )
            if auth.approval_id is None:
                raise ContractViolation(
                    ErrorCode.UNAUTHORIZED_DATA,
                    "a recorded approval_id is required to send classifications "
                    + ", ".join(sorted(restricted))
                    + " to an external provider",
                )

    def _check_budget(self, request: GatewayRequest) -> None:
        """Refuse paid work that has no recorded approval."""
        constraints = request.provider_constraints
        if constraints.cost_class == "APPROVED_PAID" and request.authorization.approval_id is None:
            raise ContractViolation(
                ErrorCode.BUDGET_EXCEEDED,
                "cost_class APPROVED_PAID requires a recorded approval_id",
            )

    # ------------------------------------------------------------------- provider

    def _call_provider(self, request: GatewayRequest) -> ProviderOutput:
        # A provider that has been failing is not called at all. Refusing immediately
        # keeps the human workflow usable instead of stalling it behind a dead service,
        # and it is what stops a retry storm forming.
        if not self.breaker.allow():
            raise ContractViolation(
                ErrorCode.INTERNAL_SAFE_FAILURE,
                f"provider circuit is {self.breaker.describe()}; not called",
                retryable=True,
            )

        try:
            output = self._invoke_with_deadline(request)
        except ProviderTimeout as exc:
            self.breaker.record_failure()
            raise ContractViolation(
                ErrorCode.PROVIDER_TIMEOUT,
                f"provider exceeded {request.provider_constraints.timeout_ms} ms",
                retryable=True,
            ) from exc
        except ProviderFailure as exc:
            self.breaker.record_failure()
            raise ContractViolation(
                ErrorCode.INTERNAL_SAFE_FAILURE, f"provider failed safely: {exc}"
            ) from exc
        except Exception as exc:
            # An adapter that raises something unexpected is quarantined, never rendered.
            self.breaker.record_failure()
            raise ContractViolation(
                ErrorCode.INVALID_PROVIDER_OUTPUT, f"provider raised an unhandled error: {exc}"
            ) from exc

        if not isinstance(output, ProviderOutput):
            # A malformed return is a provider failure too — it must count towards the
            # breaker, or a consistently broken adapter would be retried forever.
            self.breaker.record_failure()
            raise ContractViolation(
                ErrorCode.INVALID_PROVIDER_OUTPUT, "provider did not return a ProviderOutput"
            )

        self.breaker.record_success()
        return output

    def _invoke_with_deadline(self, request: GatewayRequest) -> ProviderOutput:
        """Call the provider, honouring `provider_constraints.timeout_ms`.

        The deadline was previously passed to providers and enforced by nobody. It runs on
        a worker thread so that a provider which never returns cannot hold the request
        open indefinitely.

        Known limitation, stated rather than hidden: Python cannot kill the worker, so a
        genuinely hung provider leaks one thread until the process ends. The caller is
        still released on time and the breaker opens after repeated timeouts, so the
        workflow stays usable — but this is a prototype-grade mitigation, not a fix.
        """
        if not self._enforce_timeout:
            return self.provider.infer(request)

        future = self._executor.submit(self.provider.infer, request)
        try:
            return future.result(timeout=request.provider_constraints.timeout_ms / 1000)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise ProviderTimeout(
                f"no response within {request.provider_constraints.timeout_ms} ms"
            ) from exc

    # ------------------------------------------------------------------- response

    def _build_response(
        self,
        request: GatewayRequest,
        output: ProviderOutput,
        started_at: datetime,
        screen_result: "ScreenResult | None" = None,
    ) -> GatewayResponse:
        decision = self.safety.apply(
            request,
            output.urgency,
            output.red_flags,
            screen_result,
            out_of_distribution=output.uncertainty.out_of_distribution,
        )

        errors: list[ResponseError] = []
        status = "COMPLETED"

        if output.unsupported_evidence_ids:
            # Surfaced, never silently ignored: an unusable image must not read as a
            # normal one (`SAFETY_SPEC.md`, missing-modality hallucination).
            errors.append(
                ResponseError(
                    code="UNSUPPORTED_MODALITY",
                    message="provider could not use evidence: "
                    + ", ".join(sorted(output.unsupported_evidence_ids)),
                    retryable=False,
                )
            )
            status = "ABSTAINED"

        if any(r.startswith("SR-004") or r.startswith("SR-005") for r in decision.applied_rules):
            errors.append(
                ResponseError(
                    code="LOW_CONFIDENCE",
                    message="provider output did not meet the abstention policy; escalated for review",
                    retryable=False,
                )
            )

        if decision.urgency.level == "INSUFFICIENT_INFORMATION":
            status = "ABSTAINED"
        if decision.status_floor == "ESCALATED":
            status = "ESCALATED"

        limitations = list(output.uncertainty.limitations) + list(decision.limitations)
        uncertainty = Uncertainty(
            method=output.uncertainty.method,
            limitations=limitations,
            out_of_distribution=output.uncertainty.out_of_distribution,
            abstention_reason=output.uncertainty.abstention_reason
            or ("Deterministic safety policy required escalation" if decision.applied_rules else None),
        )

        completed_at = datetime.now(timezone.utc)
        response = GatewayResponse(
            contract_version=CONTRACT_VERSION,
            request_id=request.request_id,
            response_id=f"res-{uuid.uuid5(uuid.NAMESPACE_URL, request.request_id).hex[:12]}",
            provider=self.provider.name,
            model_version=output.model_version,
            status=status,
            urgency=decision.urgency,
            red_flags=list(decision.red_flags),
            care_pathways=list(output.care_pathways),
            next_information=list(output.next_information),
            uncertainty=uncertainty,
            human_review=HumanReview(required=True, allowed_actions=ALL_REVIEW_ACTIONS),
            graph=GraphRef(
                graph_schema_version=output.graph_schema_version,
                graph_id=output.graph_id,
                graph_ref=output.graph_ref,
            ),
            provenance=Provenance(
                input_checksum=self.request_checksum(request),
                provider_version=output.provider_version,
                config_version=output.config_version,
                policy_version=self.safety.version,
                started_at=started_at,
                completed_at=completed_at,
            ),
            errors=errors,
        )

        self._audit(request, response, decision.applied_rules, started_at, completed_at)
        return response

    def _safe_failure(
        self, request: GatewayRequest, violation: ContractViolation, started_at: datetime
    ) -> GatewayResponse:
        """A refusal is still a contract-valid response that a client can render."""
        completed_at = datetime.now(timezone.utc)
        response = GatewayResponse(
            contract_version=CONTRACT_VERSION,
            request_id=request.request_id,
            response_id=f"res-{uuid.uuid5(uuid.NAMESPACE_URL, request.request_id).hex[:12]}",
            provider=self.provider.name,
            model_version="unavailable",
            status="FAILED_SAFE",
            urgency=Urgency(level="INSUFFICIENT_INFORMATION", confidence=None, evidence_ids=[]),
            red_flags=[],
            care_pathways=[],
            next_information=[],
            uncertainty=Uncertainty(
                method="gateway-contract-enforcement",
                limitations=[
                    "The request was refused before inference; no clinical conclusion was produced.",
                ],
                out_of_distribution=None,
                abstention_reason=violation.message,
            ),
            human_review=HumanReview(required=True, allowed_actions=ALL_REVIEW_ACTIONS),
            graph=None,
            provenance=Provenance(
                input_checksum=self.request_checksum(request),
                provider_version="unavailable",
                config_version="unavailable",
                policy_version=self.safety.version,
                started_at=started_at,
                completed_at=completed_at,
            ),
            errors=[
                ResponseError(
                    code=violation.code.value,
                    message=violation.message,
                    retryable=violation.retryable,
                )
            ],
        )
        self._audit(request, response, (), started_at, completed_at)
        return response

    def _safe_failure_without_request(
        self, payload: object, violation: ContractViolation, started_at: datetime
    ) -> GatewayResponse:
        """A payload too malformed to parse still gets a contract-valid refusal.

        Identifiers are taken from the payload only if they are plain strings, so a
        malformed request cannot inject structure into the response or the audit record.
        """
        raw = payload if isinstance(payload, dict) else {}
        request_id = raw.get("request_id")
        journey_id = raw.get("journey_id")
        if not isinstance(request_id, str) or len(request_id) < 6:
            request_id = "req-unparsable"
        if not isinstance(journey_id, str) or len(journey_id) < 4:
            journey_id = "unknown"

        completed_at = datetime.now(timezone.utc)
        response = GatewayResponse(
            contract_version=CONTRACT_VERSION,
            request_id=request_id,
            response_id=f"res-{uuid.uuid5(uuid.NAMESPACE_URL, request_id).hex[:12]}",
            provider=self.provider.name,
            model_version="unavailable",
            status="FAILED_SAFE",
            urgency=Urgency(level="INSUFFICIENT_INFORMATION", confidence=None, evidence_ids=[]),
            red_flags=[],
            care_pathways=[],
            next_information=[],
            uncertainty=Uncertainty(
                method="gateway-contract-enforcement",
                limitations=["The request could not be parsed; no clinical conclusion was produced."],
                out_of_distribution=None,
                abstention_reason=violation.message,
            ),
            human_review=HumanReview(required=True, allowed_actions=ALL_REVIEW_ACTIONS),
            graph=None,
            provenance=Provenance(
                input_checksum="unparsable-request",
                provider_version="unavailable",
                config_version="unavailable",
                policy_version=self.safety.version,
                started_at=started_at,
                completed_at=completed_at,
            ),
            errors=[
                ResponseError(
                    code=violation.code.value, message=violation.message, retryable=False
                )
            ],
        )
        self.audit.append(
            AuditRecord(
                request_id=request_id,
                journey_id=journey_id,
                decision_time="unknown",
                task="unknown",
                contract_version=CONTRACT_VERSION,
                provider=self.provider.name,
                provider_version=None,
                model_version=None,
                policy_version=self.safety.version,
                status="FAILED_SAFE",
                urgency_level="INSUFFICIENT_INFORMATION",
                evidence_ids=(),
                rejected_evidence=(),
                applied_safety_rules=(),
                error_codes=(violation.code.value,),
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
            )
        )
        return response

    # ---------------------------------------------------------------------- utils

    @staticmethod
    def request_checksum(request: GatewayRequest) -> str:
        """Digest of the request, over references only — never payload content."""
        payload = json.dumps(
            {
                "request_id": request.request_id,
                "journey_id": request.journey_id,
                "decision_time": request.decision_time.isoformat(),
                "task": request.task,
                "evidence": sorted(
                    f"{e.evidence_id}@{e.available_at_time.isoformat()}" for e in request.evidence
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _audit(
        self,
        request: GatewayRequest,
        response: GatewayResponse,
        applied_rules: tuple[str, ...],
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        rejected = tuple(
            (e.evidence_id, "FUTURE_EVIDENCE")
            for e in request.evidence
            if e.available_at_time > request.decision_time
        )
        self.audit.append(
            AuditRecord(
                request_id=request.request_id,
                journey_id=request.journey_id,
                decision_time=request.decision_time.isoformat(),
                task=request.task,
                contract_version=request.contract_version,
                provider=self.provider.name,
                provider_version=response.provenance.provider_version,
                model_version=response.model_version,
                policy_version=self.safety.version,
                status=response.status,
                urgency_level=response.urgency.level,
                evidence_ids=tuple(e.evidence_id for e in request.evidence),
                rejected_evidence=rejected,
                applied_safety_rules=applied_rules,
                error_codes=tuple(e.code for e in response.errors),
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
            )
        )
