"""Refusal errors (slice s8/s8r). Research prototype - not for clinical use."""


class RunRefused(RuntimeError):
    """The run is not allowed; no results are written (CLI exit 2)."""


class LedgerIntegrityError(RunRefused):
    """The ledger is missing, malformed, re-ordered, truncated or edited (CLI exit 2). Nothing is written."""
