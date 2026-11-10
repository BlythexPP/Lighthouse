"""Public discovery, OpenAPI, and health endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy.ext.asyncio import async_sessionmaker

from aah.contract import (
    AI_PLUGIN_PATH,
    HEALTH_PATH,
    LLMS_TXT_PATH,
    OPENAPI_JSON_PATH,
    OPENAPI_YAML_PATH,
    READY_PATH,
    ROBOTS_TXT_PATH,
    SERVICE_NAME,
    SWAGGER_JSON_PATH,
    WELLKNOWN_LLMS_TXT_PATH,
    WELLKNOWN_PATH,
    ai_plugin_document,
    discovery_document,
    llms_txt,
    robots_txt,
)
from aah.db import ping_db
from aah.errors import error_response

router = APIRouter()


def _public_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=60",
    }


def _crawler_text(content: str) -> PlainTextResponse:
    return PlainTextResponse(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers=_public_headers(),
    )


@router.get(LLMS_TXT_PATH, include_in_schema=False)
@router.get(WELLKNOWN_LLMS_TXT_PATH, include_in_schema=False)
async def crawler_llms_txt(request: Request) -> PlainTextResponse:
    return _crawler_text(llms_txt(public_base_url=request.app.state.settings.public_base_url))


@router.get(ROBOTS_TXT_PATH, include_in_schema=False)
async def crawler_robots_txt(request: Request) -> PlainTextResponse:
    return _crawler_text(robots_txt(public_base_url=request.app.state.settings.public_base_url))


@router.get(WELLKNOWN_PATH, include_in_schema=False)
async def agent_configuration(request: Request) -> JSONResponse:
    document = discovery_document(
        public_base_url=request.app.state.settings.public_base_url
    )
    return JSONResponse(
        content=document,
        media_type="application/ld+json",
        headers=_public_headers(),
    )


@router.get(AI_PLUGIN_PATH, include_in_schema=False)
async def ai_plugin(request: Request) -> JSONResponse:
    document = ai_plugin_document(
        public_base_url=request.app.state.settings.public_base_url
    )
    return JSONResponse(content=document, headers=_public_headers())


@router.get(OPENAPI_JSON_PATH, include_in_schema=False)
@router.get(SWAGGER_JSON_PATH, include_in_schema=False)
async def openapi_json(request: Request) -> JSONResponse:
    return JSONResponse(content=request.app.state.openapi_document, headers=_public_headers())


@router.get(OPENAPI_YAML_PATH, include_in_schema=False)
async def openapi_yaml(request: Request) -> Response:
    return PlainTextResponse(
        content=request.app.state.openapi_yaml,
        media_type="application/yaml",
        headers=_public_headers(),
    )


@router.get(HEALTH_PATH, include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@router.get(READY_PATH, include_in_schema=False)
async def readyz(request: Request) -> JSONResponse:
    session_factory: async_sessionmaker = request.app.state.session_factory
    try:
        await ping_db(session_factory)
    except Exception:
        return error_response(503, "not_ready", "Database is not reachable.")
    webhook_configured = request.app.state.settings.webhook_url_value() is not None
    return JSONResponse(
        {
            "status": "ready",
            "service": SERVICE_NAME,
            "database": "ok",
            "webhook_configured": webhook_configured,
        }
    )
