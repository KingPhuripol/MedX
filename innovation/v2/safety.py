"""The v2 Front Door runs the same deterministic screen as the v1 gateway.

`docs/shared/MODEL_API_CONTRACT.md` requires every Front Door conclusion to carry the
deterministic red-flag and required-information findings. Until this module existed the
v2 case service — the path behind `/workspace`, which `innovation/config.py` enables by
default — produced drafts with no screen at all, so the safety layer that justifies the
product clinically was reachable only through the older `/ui` screens.

The rules are NOT reimplemented here. `innovation.gateway.safety.screen_evidence` is the
one implementation; this module only translates a v2 `CaseRevision` into the evidence
types that function reads. A second copy of SCR-001/SCR-002 would drift.
"""

from __future__ import annotations

from innovation.gateway.safety import SAFETY_POLICY_VERSION, screen_evidence
from innovation.v2.models import CaseRevision, SafetyScreen


def screen_case(snapshot: CaseRevision) -> SafetyScreen:
    """Deterministic screen over a case snapshot, before any provider result is used.

    Evidence counts as present by *kind*, not by whether the answer was known. This
    matches the v1 gateway exactly: there, `EvidenceRef` carries no intake state, so an
    asked-but-unknown vital sign already satisfies SCR-001. Tightening that is a clinical
    rule change and needs review, tests and a Decision Log entry per `SAFETY_SPEC.md`;
    it must not arrive as a side effect of wiring a second caller.
    """
    result = screen_evidence(
        {fact.kind for fact in snapshot.evidence},
        complaint_evidence_ids=[
            fact.event_id for fact in snapshot.evidence if fact.kind == "CHIEF_COMPLAINT"
        ],
    )
    return SafetyScreen(
        policy_version=SAFETY_POLICY_VERSION,
        urgency_floor=result.urgency_floor,
        red_flags=list(result.red_flags),
        applied_rules=list(result.applied_rules),
        missing_required=sorted(result.missing_required),
        limitations=list(result.limitations),
    )
