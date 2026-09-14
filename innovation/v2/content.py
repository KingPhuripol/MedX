"""Content evidence report; lexical checks are not clinical or semantic ground truth."""
import json


def assess(content, snapshot, *, extractive=False):
    available={f.event_id:f for f in snapshot.evidence}
    cited=set(content.evidence_ids)
    report={'invalid_evidence_ids':sorted(cited-set(available)),
        'uncited_evidence_ids':sorted(set(available)-cited),
        'clinical_verdict':'NOT_REVIEWED','semantic_verdict':'HUMAN_REVIEW_REQUIRED',
        'rubric':['Does every patient-specific statement follow from cited evidence?',
            'Are time, negation, unknown, refusal and unavailable states preserved?',
            'Are important omissions and contradictions visible?',
            'Are diagnostic suggestions distinct from confirmed findings?']}
    if extractive:
        expected=[]
        for f in snapshot.evidence:
            if f.state != 'KNOWN':
                value = f.state
            elif isinstance(f.value, str):
                value = f.value
            else:
                value = json.dumps(f.value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
            expected.append(f'{f.kind}: {value}')
        actual=content.summary.splitlines()
        report.update(unsupported_lines=[s for s in actual if s not in expected],
            omitted_lines=[s for s in expected if s not in actual],
            semantic_verdict='EXTRACTIVE_CHECK_ONLY')
    return report
