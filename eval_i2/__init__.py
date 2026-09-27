"""Slice i2 evaluation harness: Case Graph (Arm A) vs one prompt over the whole snapshot (Arm B), PROPOSAL Table 3.2
row "Case Graph". Runs product code in-process. Kept outside eval/adapters/ so the e1 adapter import allowlist
(app.voice/app.triage/app.gateway/app.db, never casegraph) stays intact; it reuses e1 gold, mapping v1 and hashes
and the S8r runner/ledger from eval/.

System Evaluation on synthetic data — not clinical performance. Rules, fixtures, extractor lexicon and gold share
authors, so the results are circular. One deterministic mock model: the comparison measures graph structure
(typed extraction, mandatory red-flag screening, abstention, call count, time), not model reasoning.
"""
