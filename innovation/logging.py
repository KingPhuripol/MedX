"""Structured logs with a correlation id, and a filter that keeps content out of them.

This is a safety control, not an operations nicety. Once Model API Contract 1.1.0 lets
evidence content cross the gateway, a stray `logger.info(request)` is a disclosure — and
the log is the one sink with no schema, no append-only trigger and no review.

So: every record is JSON, every record carries the request id, and every record passes a
filter that truncates long strings and drops fields whose names say they hold content.
The filter is deliberately crude. A precise filter that is sometimes wrong is worse than
a blunt one that is always applied.
"""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from datetime import datetime, timezone

#: Set per request by the middleware; read by the log formatter and the error envelope so
#: a caller's `request_id` and the server's log lines refer to the same thing.
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "front_door_request_id", default=None
)

#: Field names that may hold clinical content. Anything matching is replaced, never
#: truncated — a truncated complaint is still a complaint.
REDACT_SUBSTRINGS = ("value", "payload", "content", "text", "note", "complaint", "token", "secret")

MAX_STRING = 512
REDACTED = "[redacted]"


def current_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None = None) -> str:
    request_id = value or f"http-{uuid.uuid4().hex[:12]}"
    _request_id.set(request_id)
    return request_id


def redact(value, *, key: str = ""):
    """Recursively drop or shorten anything that could carry content."""
    if any(marker in key.lower() for marker in REDACT_SUBSTRINGS):
        return REDACTED
    if isinstance(value, dict):
        return {k: redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, key=key) for v in value]
    if isinstance(value, str) and len(value) > MAX_STRING:
        return value[:MAX_STRING] + f"...[truncated {len(value) - MAX_STRING} chars]"
    return value


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.msg, key=str(getattr(record, "field", "")))
            if isinstance(record.args, dict):
                record.args = redact(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(redact(a) for a in record.args)
        except Exception:  # pragma: no cover - a logging filter must never raise
            pass
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": current_request_id(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure(level: str = "INFO", fmt: str = "json") -> None:
    """Install the formatter and the redaction filter on the root handler."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter() if fmt == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
