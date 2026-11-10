"""Load the canonical OpenAPI 3.0 document from disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def openapi_path() -> Path:
    return Path(__file__).resolve().parent.parent / "openapi.yaml"


def load_openapi_document(public_base_url: str) -> dict[str, Any]:
    path = openapi_path()
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError(f"OpenAPI document at {path} is not a mapping")
    document["servers"] = [
        {"url": public_base_url, "description": "Configured public base URL"}
    ]
    return document
