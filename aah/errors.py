"""Normalized JSON error responses for machine clients."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        self.headers = headers or {}


def error_body(code: str, message: str, details: list[Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return payload


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    merged = {"Cache-Control": "no-store"}
    if headers:
        merged.update(headers)
    return JSONResponse(
        status_code=status_code,
        content=error_body(code, message, details),
        headers=merged,
    )


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return error_response(
        exc.status_code,
        exc.code,
        exc.message,
        exc.details,
        headers=exc.headers,
    )


async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(
        400,
        "validation_error",
        "Request does not match the documented schema.",
        jsonable_encoder(exc.errors()),
    )


async def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    mapping = {
        404: ("not_found", "No such resource."),
        405: ("method_not_allowed", "Method not allowed for this path."),
        415: ("unsupported_media_type", "Content-Type must be application/json."),
    }
    code, message = mapping.get(exc.status_code, ("http_error", str(exc.detail)))
    return error_response(exc.status_code, code, message)
