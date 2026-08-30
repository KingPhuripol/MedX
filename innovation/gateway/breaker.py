"""Provider timeout and circuit breaker.

`PRODUCT_SPEC.md` §Non-functional requirements asks for both, with safe escalation.
`MODEL_API_CONTRACT.md` adds that retries must be "idempotent, bounded, and audited" and
that there is to be "no hidden retry storm".

The breaker is what makes that last part true. Without it, a provider that has been down
for an hour still gets called on every request, each one waiting out its full timeout —
the workflow becomes unusable precisely when a human most needs it to keep working.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Literal

BreakerState = Literal["CLOSED", "OPEN", "HALF_OPEN"]


@dataclass
class CircuitBreaker:
    """Stops calling a provider that is consistently failing.

    CLOSED    — calls pass through.
    OPEN      — calls are refused immediately; the workflow escalates to a human instead
                of stalling behind a dead provider.
    HALF_OPEN — after the cooldown, one probe is allowed. Success closes the circuit; a
                failure opens it again.
    """

    failure_threshold: int = 3
    reset_after_seconds: float = 30.0
    #: Injectable so tests do not sleep.
    clock: Callable[[], float] = time.monotonic

    _failures: int = 0
    _opened_at: float | None = None

    @property
    def state(self) -> BreakerState:
        if self._opened_at is None:
            return "CLOSED"
        if self.clock() - self._opened_at >= self.reset_after_seconds:
            return "HALF_OPEN"
        return "OPEN"

    def allow(self) -> bool:
        """Whether a call may be attempted now."""
        return self.state != "OPEN"

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self.clock()

    def describe(self) -> str:
        return f"{self.state} after {self._failures} consecutive failure(s)"
