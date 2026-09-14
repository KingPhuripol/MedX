"""Configuration and dated integration evidence; never infer readiness from a URL."""
import json
from innovation.v2.store import digest


def fingerprint(settings):
    return digest({'reasoning_url': settings.v2_provider_url, 'model': settings.v2_model,
        'transport':settings.v2_transport,'capabilities':settings.v2_capabilities,
        'speech_url':settings.v2_speech_url,'speech_model':settings.v2_speech_model,
        'synthesis_url':settings.v2_synthesis_url,'synthesis_model':settings.v2_synthesis_model})


def inspect(settings):
    report=None
    if settings.v2_readiness_report:
        try:
            candidate=json.loads(settings.v2_readiness_report.read_text())
            from innovation.v2.evaluation import manifest
            if candidate.get('configuration_fingerprint')==fingerprint(settings) and candidate.get('manifest',{}).get('source_hash')==manifest()['source_hash']:
                report=candidate
        except (ValueError,OSError):
            pass
    passed=bool(report and report.get('connectivity_and_smoke_passed') is True)
    return {'reasoning':{'configured':bool(settings.v2_provider_url),
        'connectivity':'PASSED' if passed else 'NOT_VERIFIED',
        'smoke':'PASSED' if passed else 'NOT_VERIFIED',
        'evaluation':'NOT_VERIFIED', 'checked_at':report.get('checked_at') if report else None},
        'transcription':{'configured':bool(settings.v2_speech_url),'connectivity':'NOT_VERIFIED','smoke':'NOT_VERIFIED','evaluation':'NOT_VERIFIED'},
        'synthesis':{'configured':bool(settings.v2_synthesis_url),'connectivity':'NOT_VERIFIED','smoke':'NOT_VERIFIED','evaluation':'NOT_VERIFIED'},
        'clinical_validation':'NOT_REVIEWED'}
