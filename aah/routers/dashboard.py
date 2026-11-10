"""Local operator dashboard. Static HTML; the browser talks to the live hub."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from aah.contract import DASHBOARD_PATH
from aah.errors import AppError

router = APIRouter()

_HTML = Path(__file__).resolve().parents[2] / "dashboard" / "index.html"


@router.get(DASHBOARD_PATH, include_in_schema=False)
async def operator_dashboard() -> FileResponse:
    if not _HTML.is_file():
        raise AppError(404, "not_found", "Operator dashboard is not installed.")
    return FileResponse(
        _HTML,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )
