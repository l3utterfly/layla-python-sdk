"""JSON codecs for the existing Layla WebView messages."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .errors import LythonProtocolError

def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _decode_object(raw: str, description: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise LythonProtocolError(f"{description} must be a JSON string")

    try:
        value = json.loads(raw, parse_constant=_reject_non_json_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LythonProtocolError(f"{description} is not valid JSON: {exc}") from exc

    if not isinstance(value, dict):
        raise LythonProtocolError(f"{description} must decode to a JSON object")
    return value


def _encode_object(value: Mapping[str, Any], description: str) -> str:
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise LythonProtocolError(f"{description} is not JSON serializable: {exc}") from exc


def decode_layla_request(message: str) -> dict[str, Any]:
    """Validate and decode an unmodified TypeScript SDK request message."""

    request = _decode_object(message, "Layla request message")
    command = request.get("cmd")
    if not isinstance(command, str) or not command:
        raise LythonProtocolError(
            "Layla request message must contain a non-empty string 'cmd'"
        )
    return request


def encode_layla_request(message: Mapping[str, Any]) -> str:
    """Serialize an existing ``{cmd, data}`` request without changing its shape."""

    raw = _encode_object(message, "Layla request message")
    decode_layla_request(raw)
    return raw


def decode_layla_event(message: str) -> dict[str, Any]:
    """Validate and decode an unmodified TypeScript SDK response event."""

    event = _decode_object(message, "Layla response message")
    event_name = event.get("event")
    if not isinstance(event_name, str) or not event_name:
        raise LythonProtocolError(
            "Layla response message must contain a non-empty string 'event'"
        )
    return event
