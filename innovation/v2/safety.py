"""The v2 Front Door runs the same deterministic screen as the v1 gateway.

`docs/shared/MODEL_API_CONTRACT.md` requires every Front Door conclusion to carry the
deterministic red-flag and required-information findings. Until this module existed the
v2 case service — the path behind `/workspace`, which `innovation/config.py` enables by
default — produced drafts with no screen at all, so the safety layer that justifies the
product clinically was reachable only through the older `/ui` screens.

The rules are NOT reimplemented here. `innovation.gateway.safety.screen_evidence` is the
one implementation; this module only translates a v2 `CaseRevision` into the evidence
types that function reads. A second copy of the required-evidence rule would drift. The
v2 pilot explicitly disables the v1 structural unread-complaint flag because it escalated
every complaint-bearing case regardless of content; the limitation remains visible and
the policy has a distinct version. This is research-prototype behavior pending independent
clinical review, not a clinical threshold.
"""

from __future__ import annotations

from innovation.gateway.safety import screen_evidence
from shared.contracts.model_api import RedFlag
from innovation.v2.models import CaseRevision, SafetyScreen


SAFETY_POLICY_VERSION = "safety-policy-v2-pilot"


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
        # The pilot workspace does not turn the mere presence of free-text into an
        # UNKNOWN red flag. That old structural rule escalated every complaint-bearing
        # case independently of its contents. Clinical content remains explicitly
        # unevaluated below and all outputs still require physician review.
        flag_unread_complaint=False,
    )
    limitations = list(result.limitations)
    red_flags = list(result.red_flags)
    applied_rules = list(result.applied_rules)
    urgency_floor = result.urgency_floor
    if snapshot.care_context != "ED_FIRST_CONTACT_ADULT_NON_TRAUMA_NON_OBSTETRIC":
        red_flags.append(RedFlag(
            code="OUT_OF_SCOPE_PRESENTATION", state="TRIGGERED", evidence_ids=[]
        ))
        applied_rules.append("SCR-003-OUT-OF-SCOPE")
        limitations.append(
            f"Presentation is outside the evaluated care setting: {snapshot.care_context}."
        )
        urgency_floor = "URGENT_REVIEW"
    if any(fact.kind == "CHIEF_COMPLAINT" for fact in snapshot.evidence):
        limitations.append(
            "The deterministic screen does not evaluate free-text complaint severity; "
            "the complaint requires clinician review."
        )
    return SafetyScreen(
        policy_version=SAFETY_POLICY_VERSION,
        urgency_floor=urgency_floor,
        red_flags=red_flags,
        applied_rules=applied_rules,
        missing_required=sorted(result.missing_required),
        limitations=limitations,
    )
