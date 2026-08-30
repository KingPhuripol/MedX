"""Run the frozen case set and emit an evaluation record.

`EVALUATION_CONTRACT.md` requires every result to trace to versions and a stated
decision-time policy. The record this produces validates against
`schemas/evaluation-record.schema.json` and is written with
`review_verdict: NOT_REVIEWED` — a run is not a verdict, and only an independent reviewer
issues one (`SAFETY_SPEC.md` §Verdict rubric).
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from innovation.evaluation.cases import EvaluationCase, load_cases
from innovation.evaluation.metrics import METRIC_DEFINITIONS, CaseResult, summarise
from innovation.frontdoor import FrontDoorService
from innovation.gateway import ModelGateway
from innovation.gateway.providers.base import ProviderFailure, ProviderTimeout
from innovation.gateway.registry import build_provider

DECISION_TIME_POLICY = (
    "Each case is assessed at its own declared decision_time. Evidence is selected by "
    "shared.snapshot.take_snapshot, which admits only events whose available_at_time is at "
    "or before that decision time; LABEL-modality evidence is excluded from live requests "
    "entirely. Retrospective labels present in a journey are therefore withheld by "
    "construction rather than by convention."
)

STATISTICS_PLAN = (
    "Descriptive rates over a frozen synthetic case set. No hypothesis test, no confidence "
    "interval, and no pass/fail threshold: the sample is small, author-constructed, and "
    "carries no clinical reference standard, so an interval would imply a precision the "
    "design cannot support. Metric definitions were frozen before the first run. Numerical "
    "safety thresholds are deliberately absent until clinical and sample-size review sets "
    "them in the Evaluation Contract."
)


def _code_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, cwd=Path(__file__).resolve().parents[2],
        ).stdout.strip()
    except Exception:
        return "unknown"


def _provider_for(case: EvaluationCase, provider_name: str | None):
    """Build the provider, injecting the failure a provider-failure case calls for."""
    if case.provider_behaviour == "timeout":
        return build_provider(provider_name, fail_with=ProviderTimeout("evaluation-injected timeout"))
    if case.provider_behaviour == "failure":
        return build_provider(provider_name, fail_with=ProviderFailure("evaluation-injected failure"))
    return build_provider(provider_name)


def run_case(case: EvaluationCase, provider_name: str | None = None) -> CaseResult:
    """Run one case end to end through the Front Door."""
    gateway = ModelGateway(_provider_for(case, provider_name))
    service = FrontDoorService(gateway)
    try:
        service.create_encounter(
            journey_id=case.journey_id,
            patient_id=f"patient-{case.case_id}",
            encounter_id=f"encounter-{case.case_id}",
            encounter_start=case.encounter_start,
            items=list(case.intake),
        )
        for item in case.appended:
            service.append_evidence(case.journey_id, item, default_time=case.encounter_start)

        recommendation = service.assess(service.journey(case.journey_id), case.decision_time)
        response = recommendation.response
        return CaseResult(
            case_id=case.case_id,
            scenario=case.scenario,
            expected_minimum_urgency=case.expected_minimum_urgency,
            observed_urgency=response.urgency.level,
            status=response.status,
            human_review_required=response.human_review.required,
            provider_behaviour=case.provider_behaviour,
            withheld_event_ids=tuple(e for e, _ in recommendation.withheld),
            evidence_used=tuple(response.urgency.evidence_ids),
            error_codes=tuple(e.code for e in response.errors),
        )
    finally:
        gateway.close()


def run_evaluation(
    *,
    evaluation_id: str = "EVAL-0001",
    provider_name: str | None = None,
    cases: tuple[EvaluationCase, ...] | None = None,
    manifest_ids: tuple[str, ...] = ("exp_0001",),
) -> tuple[dict, tuple[CaseResult, ...]]:
    """Run every case and build a contract-valid evaluation record."""
    cases = cases if cases is not None else load_cases()
    results = tuple(run_case(c, provider_name) for c in cases)
    metrics = summarise(results)

    provider = build_provider(provider_name)
    scenarios: dict[str, int] = {}
    for result in results:
        scenarios[result.scenario] = scenarios.get(result.scenario, 0) + 1

    record = {
        "evaluation_id": evaluation_id,
        "version": "1.0.0",
        "manifest_ids": list(manifest_ids),
        "code_revision": _code_revision(),
        "data_version": "frozen-synthetic-cases-1.0.0",
        "split_version": "synthetic-expert_test-1.0.0",
        "model_versions": [f"{provider.name}:{provider.model_version}"],
        "contract_versions": {
            "model_api": "1.0.0",
            "patient_journey": "1.0.0",
            "safety_policy": "safety-policy-v1",
        },
        "task": "CLINICAL_FRONT_DOOR",
        "decision_time_policy": DECISION_TIME_POLICY,
        "primary_metrics": [f"{k}={metrics[k]}" for k in ("under_triage_rate", "critical_case_sensitivity")],
        "secondary_metrics": [
            f"{k}={v}" for k, v in metrics.items()
            if k not in {"under_triage_rate", "critical_case_sensitivity"}
        ],
        "sample_sizes": {"cases": len(results), **{f"scenario:{k}": v for k, v in sorted(scenarios.items())}},
        "exclusions": [],
        "statistics_plan": STATISTICS_PLAN,
        "artifacts": ["tests/fixtures/cases/", "innovation/evaluation/metrics.py"],
        "status": "completed",
        "deviations": [
            "Synthetic cases only; no real or licensed patient data was used.",
            "expected_minimum_urgency is an author-declared fixture property, not a clinical "
            "reference standard, so these rates are not clinical error rates.",
            "The only providers are a deterministic mock and a fixed-path baseline; nothing "
            "here is evidence about medical capability.",
            "override_rate is null: no human reviewed these assessments.",
        ],
        "review_verdict": "NOT_REVIEWED",
    }
    return record, results


def format_report(record: dict, results: tuple[CaseResult, ...]) -> str:
    """Human-readable summary for the terminal."""
    lines = [
        "RESEARCH PROTOTYPE — synthetic evaluation, not clinical evidence",
        "",
        f"evaluation  {record['evaluation_id']}  code {record['code_revision']}  "
        f"model {', '.join(record['model_versions'])}",
        f"cases       {record['sample_sizes']['cases']}",
        "",
        f"{'case':32} {'scenario':22} {'expected≥':22} {'observed':22} status",
        "-" * 118,
    ]
    for r in results:
        marker = "  UNDER-TRIAGED" if r.under_triaged else ""
        lines.append(
            f"{r.case_id:32} {r.scenario:22} {r.expected_minimum_urgency:22} "
            f"{r.observed_urgency:22} {r.status}{marker}"
        )

    lines += ["", "Metrics (definitions frozen before the first run; no pass/fail threshold):"]
    for name in METRIC_DEFINITIONS:
        value = dict(
            [m.split("=", 1) for m in record["primary_metrics"] + record["secondary_metrics"]]
        ).get(name, "—")
        lines.append(f"  {name:28} {value}")

    lines += ["", "Deviations:"] + [f"  - {d}" for d in record["deviations"]]
    lines += ["", f"Review verdict: {record['review_verdict']} — a run is not a verdict."]
    return "\n".join(lines)


def main() -> int:
    record, results = run_evaluation()
    print(format_report(record, results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
