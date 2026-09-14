import httpx
import pytest
from innovation.v2.providers import HttpProvider, ExternalConfig, HttpSpeech
from innovation.v2.store import Store, DomainError


def test_zero_budget_prevents_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('zero budget must prevent transport creation')
    monkeypatch.setattr(httpx, 'Client', forbidden)
    store = Store()
    provider = HttpProvider(ExternalConfig('https://example.invalid', 'secret', 'model', 0, 0), store, [])
    with pytest.raises(DomainError, match='PAID_BUDGET_EXCEEDED'):
        provider.request('/infer', {})
    store.close()


@pytest.mark.parametrize('failure', ['timeout', 'malformed', 'http'])
def test_transport_errors_sanitized_and_reservation_retained(monkeypatch, failure):
    client = httpx.Client
    def transport(request):
        assert request.headers['Authorization'] == 'Bearer secret'
        if failure == 'timeout':
            raise httpx.ReadTimeout('secret upstream details')
        return httpx.Response(500 if failure == 'http' else 200, text='not json')
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client(transport=httpx.MockTransport(transport), **kwargs))
    store = Store()
    provider = HttpProvider(ExternalConfig('https://example.invalid', 'secret', 'model', 1, 1), store, [])
    with pytest.raises(DomainError) as error:
        provider.request('/infer', {})
    assert error.value.code in {'PROVIDER_TIMEOUT', 'PROVIDER_FAILURE'}
    assert 'secret' not in str(error.value)
    with pytest.raises(DomainError, match='PAID_BUDGET_EXCEEDED'):
        provider.request('/infer', {})
    store.close()


def test_speech_cannot_confirm_transcript(monkeypatch):
    client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'text': 'ข้อความสังเคราะห์', 'confirmed': True})), **kwargs))
    store = Store()
    provider = HttpProvider(ExternalConfig('https://example.invalid', 'secret', 'model', 1, 1), store, [])
    assert HttpSpeech(provider).transcribe(b'abc', 'audio/webm').confirmed is False
    store.close()


def test_budget_rejects_nonfinite():
    store = Store()
    for ceiling, amount in [(float('inf'), 1), (1, float('nan'))]:
        with pytest.raises(DomainError, match='PAID_BUDGET_EXCEEDED'):
            store.reserve(ceiling, amount)
    store.close()
