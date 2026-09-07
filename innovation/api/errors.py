"""One error shape for the whole API.

Errors were FastAPI's default `{"detail": ...}`, and the shape differed depending on
whether the failure came from an `HTTPException` or from request validation. A client had
to handle two shapes and could not rely on either carrying a correlation id.

The envelope also carries the banner. An error is still a response from a research
prototype, and a caller that only ever sees failures should still be told what it is
talking to.

Nothing here leaks internals: the catch-all returns a stable code and a fixed message.
A traceback in a response body is a disclosure, and this service will be holding clinical
content once the contract permits it.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from innovation.config import BANNER
from innovation.logging import current_request_id

logger = logging.getLogger("innovation.api")

#: Codes the API adds on top of the contract's `ErrorCode`. The contract's codes describe
#: what went wrong with a *model request*; these describe what went wrong with an *HTTP*
#: request, and conflating the two would make `INVALID_REQUEST` mean two things.
STATUS_TO_CODE = {
    status.HTTP_400_BAD_REQUEST: "INVALID_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHENTICATED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "PAYLOAD_TOO_LARGE",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "SCHEMA_INVALID",
    status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}


def envelope(code: str, message: str, *, details: list | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": current_request_id(),
            "details": details or [],
        },
        "banner": BANNER,
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = STATUS_TO_CODE.get(exc.status_code, "ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations and messages are safe to return; the submitted value is not,
        # because for this API the submitted value can be clinical content.
        details = [
            {"location": list(error.get("loc", ())), "message": error.get("msg", "")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=envelope("SCHEMA_INVALID", "request does not match the schema", details=details),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Logged with the traceback, returned without it.
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=envelope(
                "INTERNAL_SAFE_FAILURE",
                "the request could not be completed; the failure has been logged",
            ),
        )
