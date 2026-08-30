"""Deterministic safety layer — `docs/innovation/SAFETY_SPEC.md`.

These rules run independently of the model and a model cannot relax them. That is the
whole point: if the safety behaviour lived inside the provider, a provider swap would
silently change it, and a low-confidence model could talk its way out of an escalation.

The layer sees evidence *references*, not payloads, because the gateway routes
references so that raw patient content never passes through it. So these rules reason
about which evidence types are present, what the model declared, and what is missing —
not about clinical content. That is a real limit and is stated in every response's
`uncertainty.limitations`, never papered over.

Changing any rule here requires clinical review, tests, and a Decision Log entry
(`SAFETY_SPEC.md` §Deterministic controls), and bumping `SAFETY_POLICY_VERSION`.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.contracts.model_api import (
    URGENCY_SEVERITY,
    GatewayRequest,
    RedFlag,
    Urgency,
)

SAFETY_POLICY_VERSION = "safety-policy-v1"

#: Evidence a Clinical Front Door conclusion needs before it may be anything other than
#: an abstention. Absence is not a negative finding — it is an unanswered question.
REQUIRED_FRONT_DOOR_EVIDENCE: frozenset[str] = frozenset({"CHIEF_COMPLAINT", "VITAL"})


@dataclass(frozen=True)
class SafetyDecision:
    """What the deterministic layer concluded, and why.

    `applied_rules` is kept so an audit record can show which rule forced an outcome
    rather than leaving an escalation unexplained.
    """

    urgency: Urgency
    red_flags: tuple[RedFlag, ...]
    status_floor: str | None
    applied_rules: tuple[str, ...]
    limitations: tuple[str, ...]


class SafetyPolicy:
    """Applies the deterministic rules to a provider's proposed output."""

    version = SAFETY_POLICY_VERSION

    def missing_required_evidence(self, request: GatewayRequest) -> frozenset[str]:
        """Required evidence types absent from the request, for front-door tasks."""
        if request.task != "CLINICAL_FRONT_DOOR":
            return frozenset()
        present = {e.event_type for e in request.evidence}
        return frozenset(REQUIRED_FRONT_DOOR_EVIDENCE - present)

    def apply(
        self,
        request: GatewayRequest,
        proposed_urgency: Urgency,
        proposed_red_flags: tuple[RedFlag, ...],
    ) -> SafetyDecision:
        """Return the urgency and status floor that the response must respect.

        Urgency is only ever raised. There is no path through this method that lowers a
        provider's urgency, which is what "a model cannot override them downward" means
        in practice.
        """
        rules: list[str] = []
        limitations: list[str] = []
        urgency_floor = proposed_urgency.level
        status_floor: str | None = None

        def raise_to(level: str, rule: str) -> None:
            nonlocal urgency_floor
            if URGENCY_SEVERITY[level] > URGENCY_SEVERITY[urgency_floor]:
                urgency_floor = level
            rules.append(rule)

        # SR-001 — a triggered red flag outranks any diagnostic ranking.
        # A provider that reports a triggered flag alongside a routine urgency is
        # contradicting itself; the flag wins.
        if any(f.state == "TRIGGERED" for f in proposed_red_flags):
            raise_to("IMMEDIATE_REVIEW", "SR-001-TRIGGERED_RED_FLAG")
            status_floor = "ESCALATED"

        # SR-002 — an unevaluable red flag is not a negative one. If the evidence needed
        # to rule a flag in or out is absent, the flag is UNKNOWN and the case is
        # escalated rather than quietly treated as clear.
        if any(f.state == "UNKNOWN" for f in proposed_red_flags):
            raise_to("URGENT_REVIEW", "SR-002-UNKNOWN_RED_FLAG")
            status_floor = status_floor or "ESCALATED"
            limitations.append(
                "At least one red flag could not be evaluated from the available evidence "
                "and is reported as UNKNOWN, not as absent."
            )

        # SR-003 — missing required information cannot yield a confident low-acuity
        # conclusion. The system abstains and asks, instead of fabricating certainty.
        missing = self.missing_required_evidence(request)
        if missing:
            raise_to("URGENT_REVIEW", "SR-003-MISSING_REQUIRED_EVIDENCE")
            status_floor = status_floor or "ESCALATED"
            limitations.append(
                "Required evidence for a front-door conclusion was absent at decision time: "
                + ", ".join(sorted(missing))
            )

        # SR-004 — the gateway sees references, not payloads. Say so, always, so that no
        # reader infers the deterministic layer inspected clinical content.
        limitations.append(
            "Deterministic safety rules evaluate evidence metadata and declared provider "
            "output only; they do not inspect evidence payloads."
        )

        final_urgency = Urgency(
            level=urgency_floor,
            # Confidence is dropped when the deterministic layer overrides the provider:
            # the number described the provider's own conclusion and does not transfer to
            # a level the provider did not assign.
            confidence=proposed_urgency.confidence
            if urgency_floor == proposed_urgency.level
            else None,
            evidence_ids=proposed_urgency.evidence_ids,
        )

        return SafetyDecision(
            urgency=final_urgency,
            red_flags=proposed_red_flags,
            status_floor=status_floor,
            applied_rules=tuple(rules),
            limitations=tuple(limitations),
        )
