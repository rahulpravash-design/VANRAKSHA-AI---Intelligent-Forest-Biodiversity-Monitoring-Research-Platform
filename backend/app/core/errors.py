"""Domain exceptions and the handlers that turn them into HTTP responses."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class VanrakshaError(Exception):
    """Base class for errors the API maps onto a specific status code."""

    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Request could not be processed."

    def __init__(self, detail: str | None = None, **context: Any) -> None:
        super().__init__(detail or self.detail)
        self.detail = detail or self.detail
        self.context = context


class NotFoundError(VanrakshaError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found."


class ConflictError(VanrakshaError):
    status_code = status.HTTP_409_CONFLICT
    detail = "Resource already exists."


class ValidationError(VanrakshaError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    detail = "Request payload is not valid."


class AuthenticationError(VanrakshaError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Authentication failed."


class PermissionDeniedError(VanrakshaError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "You do not have permission to perform this action."


class InactiveAccountError(VanrakshaError):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "This account has been deactivated."


class RateLimitedError(VanrakshaError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail = "Too many attempts. Please try again shortly."


class UploadTooLargeError(VanrakshaError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    detail = "Uploaded file is larger than the configured limit."


class AIEngineError(VanrakshaError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = "The AI engine is unavailable."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(VanrakshaError)
    async def _domain_error(_request: Request, exc: VanrakshaError) -> JSONResponse:
        headers = {}
        if isinstance(exc, AuthenticationError):
            headers["WWW-Authenticate"] = "Bearer"
        if isinstance(exc, RateLimitedError) and "retry_after" in exc.context:
            headers["Retry-After"] = str(int(exc.context["retry_after"]))
        payload: dict[str, Any] = {"detail": exc.detail}
        if exc.context:
            payload["context"] = {
                k: v for k, v in exc.context.items() if k != "retry_after"
            } or None
            if payload["context"] is None:
                payload.pop("context")
        return JSONResponse(payload, status_code=exc.status_code, headers=headers or None)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Flatten Pydantic's error list into something a form can display.
        fields: dict[str, str] = {}
        for error in exc.errors():
            location = [str(part) for part in error.get("loc", []) if part != "body"]
            fields[".".join(location) or "body"] = error.get("msg", "invalid value")
        return JSONResponse(
            {"detail": "Request payload is not valid.", "fields": fields},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
