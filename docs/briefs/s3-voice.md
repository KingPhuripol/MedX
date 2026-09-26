# S3 brief — Thai voice stack (scout, 2026-09-26)

Vendor-reported numbers, not independently verified. No public Thai medical ASR benchmark exists.

## Thai ASR (CER: TVSpeech / Gigaspeech2 / FLEURS, from arXiv:2601.13044 Table 6)
| Model | CER | License |
|---|---|---|
| Typhoon Whisper Large-v3 | 6.32 / 4.69 / 9.98 | MIT |
| Typhoon Whisper Turbo | 6.85 / 4.79 / 10.52 | check card |
| Pathumma-whisper-th-large-v3 (NECTEC) | 10.36 / 5.84 / 6.29 | Apache-2.0 |
| Typhoon ASR Realtime (115M, streaming, CPU) | 9.99 / 6.81 / 13.87 | CC-BY-4.0 |
| Thonburian (biodatlab) large-v3 | 18.96 / 13.22 / 16.50 | MIT |

Risk: English drug names in Thai speech get transliterated into Thai script.

## Thai TTS
KhanomTan v1.1 (Apache-2.0, open fallback) · Azure th-TH Achara/Niwat (commercial) · F5-TTS-THAI (license conflict with CC-BY-NC base — verify) · MMS-TTS-tha (CC-BY-NC) · Chirp 3 HD th-TH (no custom pronunciation).

## LiveKit Agents
Apache-2.0, fully self-hostable. Cascade STT→LLM→TTS; LLM via OpenAI-compatible base_url (the Model Gateway). Turn detector does **not** support Thai → use Silero VAD. Non-streaming Whisper needs `StreamAdapter` + VAD. Realtime mode: late transcripts, tool-calling bug (#2383). Local Thai reference: aws-samples/sample-SEAVoice-LiveKit (Typhoon ASR + Kokoro, p50 TTFA 3.67 s).

## Evaluation reference
Su et al., JMIR Nursing 2026;9:e88567: field-level F1 per field, macro-F1 with 95% CI, hallucination rate, κ, noninferiority vs human transcript. Add a ground-truth-transcript condition to separate ASR error from extraction error.

## Recommendation
Text-first cascade now → add Typhoon Whisper Large-v3 (local) + Silero VAD + TTS (Azure for demo / KhanomTan open) → realtime optional behind the Gateway.

## Owner decisions
(a) accept non-commercial-licensed TTS or not; (b) verify F5-TTS-THAI license; (c) may cloud STT/TTS receive synthetic-only audio (record in `docs/DECISIONS.md`).

Sources: arxiv.org/html/2601.13044v1 · huggingface.co/typhoon-ai · huggingface.co/nectec/Pathumma-whisper-th-large-v3 · github.com/biodatlab/thonburian-whisper · docs.livekit.io/agents · github.com/livekit/agents/issues/4148 · github.com/livekit/agents/issues/2383 · github.com/aws-samples/sample-SEAVoice-LiveKit · pmc.ncbi.nlm.nih.gov/articles/PMC13240795
