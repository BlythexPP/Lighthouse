"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import yaml
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from aah import __version__
from aah.audit import setup_logging
from aah.config import Settings, load_settings
from aah.contract import SERVICE_DESCRIPTION, SERVICE_NAME
from aah.db import create_engine, init_db
from aah.errors import (
    AppError,
    app_error_handler,
    error_response,
    http_exception_handler,
    validation_error_handler,
)
from aah.openapi_loader import load_openapi_document
from aah.ratelimit import RateLimiter
from aah.routers.egress import router as egress_router
from aah.routers.keys import router as keys_router
from aah.routers.meta import router as meta_router
from aah.routers.relay import router as relay_router
from aah.store import Store
from aah.webhook import HttpWebhookClient, WebhookClient


def create_app(
    settings: Settings | None = None,
    webhook_client: WebhookClient | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    settings.validate_runtime()
    setup_logging(settings.log_level)

    engine = create_engine(settings.database_url)
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.webhook_timeout_seconds, connect=5.0),
        follow_redirects=False,
        headers={"User-Agent": f"{SERVICE_NAME}/{__version__}"},
    )
    if webhook_client is None:
        webhook_client = HttpWebhookClient(settings, http_client)
    elif isinstance(webhook_client, HttpWebhookClient):
        webhook_client.bind_http(http_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        session_factory = await init_db(engine)
        app.state.session_factory = session_factory
        app.state.store = Store(session_factory)
        app.state.http_client = http_client
        try:
            yield
        finally:
            await http_client.aclose()
            await engine.dispose()

    app = FastAPI(
        title=SERVICE_NAME,
        description=SERVICE_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        openapi_url=None,
    )
    openapi_document = load_openapi_document(settings.public_base_url)
    app.state.settings = settings
    app.state.webhook_client = webhook_client
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    app.state.openapi_document = openapi_document
    app.state.openapi_yaml = yaml.safe_dump(openapi_document, sort_keys=False, allow_unicode=True)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    @app.middleware("http")
    async def limit_body_and_cache(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > settings.max_body_bytes:
                return error_response(
                    413,
                    "payload_too_large",
                    f"Request body exceeds {settings.max_body_bytes} bytes.",
                )
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(meta_router)
    app.include_router(relay_router)
    app.include_router(egress_router)
    app.include_router(keys_router)

    def _openapi() -> dict:
        return app.state.openapi_document

    app.openapi = _openapi  # type: ignore[method-assign]
    return app
