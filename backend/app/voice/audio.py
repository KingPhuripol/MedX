"""Audio interface for the cascade (ASR -> LLM -> TTS). Local stubs only in slice s3.

No speech SDKs, no network. Real Thai ASR/TTS arrive later behind these same protocols (Decision D2),
and any external speech service needs a recorded approval and synthetic audio only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from .models import AddTurnBody, HumanSpeaker


@dataclass(frozen=True)
class ASRResult:
    status: Literal["ok", "not_configured", "error"]
    transcript: str | None
    lang: str
    engine: str


class ASRProvider(Protocol):
    def transcribe(self, audio: bytes, lang: str = "th") -> ASRResult: ...


class TTSProvider(Protocol):
    def synthesize(self, text_th: str) -> bytes: ...


class LocalStubASR:
    """Never fabricates text: always ``not_configured`` with no transcript."""

    engine = "local-stub-asr"

    def transcribe(self, audio: bytes, lang: str = "th") -> ASRResult:
        return ASRResult(status="not_configured", transcript=None, lang=lang, engine=self.engine)


class LocalStubTTS:
    """Deterministic silence: 16-bit mono PCM zeros, 100 ms at 16 kHz."""

    SAMPLE_RATE = 16_000

    def synthesize(self, text_th: str) -> bytes:
        return b"\x00\x00" * (self.SAMPLE_RATE // 10)


def asr_to_turn(result: ASRResult, speaker: HumanSpeaker, started_at: datetime, ended_at: datetime) -> AddTurnBody:
    """An ASR transcript becomes exactly the same Turn input as typed text."""
    if result.status != "ok" or not result.transcript:
        raise ValueError(f"ASR produced no transcript (status={result.status})")
    return AddTurnBody(speaker=speaker, text=result.transcript, started_at=started_at, ended_at=ended_at)
