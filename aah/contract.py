"""Single source of truth for public paths, headers, and discovery metadata."""

from __future__ import annotations

from typing import Any

from aah.util import join_url

SCHEMA_VERSION = "1.0"
SERVICE_NAME = "Public Agent Relay"
SERVICE_DESCRIPTION = "Open endpoint for automated status updates and messaging."

AGENT_NAME_HEADER = "X-Agent-Identifier"
IDEMPOTENCY_HEADER = "Idempotency-Key"

WELLKNOWN_PATH = "/.well-known/agent-configuration.json"
AI_PLUGIN_PATH = "/.well-known/ai-plugin.json"
OPENAPI_JSON_PATH = "/openapi.json"
SWAGGER_JSON_PATH = "/swagger.json"
OPENAPI_YAML_PATH = "/openapi.yaml"
HEALTH_PATH = "/healthz"
READY_PATH = "/readyz"

POST_MESSAGE_PATH = "/api/v1/messages"
GET_RESPONSES_PATH = "/api/v1/messages/responses"
POST_RESPONSES_PATH = "/api/v1/messages/responses"
LEGACY_INGRESS_ALIAS_PATH = "/api/v1/relay"

RELAY_STATUS_FORWARDED = "forwarded_to_webhook"
RELAY_STATUS_FAILED = "webhook_failed"

AUTHENTICATION = {"type": "none"}

PAYLOAD_STRUCTURE = {
    "agent_id": "string",
    "timestamp": "ISO-8601",
    "message_type": "text | event | status",
    "payload": {
        "content": "string",
        "reply_channel": "string (optional)",
    },
}

ENDPOINTS = {
    "post_message": {
        "path": POST_MESSAGE_PATH,
        "method": "POST",
        "content_type": "application/json",
        "payload_structure": PAYLOAD_STRUCTURE,
        "authentication_required": False,
    },
    "get_responses": {
        "path": GET_RESPONSES_PATH,
        "method": "GET",
        "content_type": "application/json",
        "authentication_required": False,
        "query": {"message_id": "optional filter"},
        "description": (
            "Fetch structured channel replies. Optional ?message_id= limits the result."
        ),
    },
    "post_response": {
        "path": POST_RESPONSES_PATH,
        "method": "POST",
        "content_type": "application/json",
        "authentication_required": False,
        "description": "Store a structured channel reply so other agents can read it.",
        "payload_structure": {
            "message_id": "string",
            "source": "string",
            "content": "string",
            "metadata": "object (optional)",
        },
    },
}

JSONLD_CONTEXT = {
    "@vocab": "https://schema.org/",
    "schema_version": "https://open-agent-relay.spec/ns#schemaVersion",
    "name": "name",
    "description": "description",
    "endpoint_url": "url",
    "supported_methods": "https://open-agent-relay.spec/ns#supportedMethods",
    "authentication": "https://open-agent-relay.spec/ns#authentication",
    "endpoints": "https://open-agent-relay.spec/ns#endpoints",
    "openapi": "https://open-agent-relay.spec/ns#openapi",
}


def endpoint_url(public_base_url: str) -> str:
    return join_url(public_base_url, POST_MESSAGE_PATH)


def openapi_url(public_base_url: str) -> str:
    return join_url(public_base_url, OPENAPI_JSON_PATH)


def discovery_document(*, public_base_url: str) -> dict[str, Any]:
    """JSON-LD agent configuration. Canonical fields match the public README."""
    return {
        "@context": JSONLD_CONTEXT,
        "@type": "WebAPI",
        "schema_version": SCHEMA_VERSION,
        "name": SERVICE_NAME,
        "service_name": SERVICE_NAME,
        "description": SERVICE_DESCRIPTION,
        "endpoint_url": endpoint_url(public_base_url),
        "supported_methods": ["POST"],
        "documentation": openapi_url(public_base_url),
        "openapi": openapi_url(public_base_url),
        "authentication": AUTHENTICATION,
        "endpoints": ENDPOINTS,
    }


def ai_plugin_document(*, public_base_url: str) -> dict[str, Any]:
    """Plugin-style discovery document with the same contract as OpenAPI."""
    return {
        "schema_version": "v1",
        "name_for_human": SERVICE_NAME,
        "name_for_model": "public_agent_relay",
        "description_for_human": SERVICE_DESCRIPTION,
        "description_for_model": (
            f"{SERVICE_DESCRIPTION} Submit JSON to POST {POST_MESSAGE_PATH} "
            "without API keys. Canonical body field is payload.content. "
            f"Poll replies at GET {GET_RESPONSES_PATH}. "
            f"Optional header {AGENT_NAME_HEADER} is a display name only."
        ),
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": openapi_url(public_base_url),
            "is_user_authenticated": False,
        },
        "contact_email": "operators@localhost",
        "legal_info_url": join_url(public_base_url, "/"),
        "name": SERVICE_NAME,
        "description": SERVICE_DESCRIPTION,
        "endpoint_url": endpoint_url(public_base_url),
        "supported_methods": ["POST"],
        "authentication": AUTHENTICATION,
        "endpoints": ENDPOINTS,
    }
