"""Versioned JSON envelopes around the existing Layla WebView protocol."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import LythonProtocolError

PROTOCOL_NAME = "layla.lython"
PROTOCOL_VERSION = 1
REQUEST_TYPE = "request"
RESPONSE_TYPE = "response"


@dataclass(frozen=True, slots=True)
class ErrorPayload:
    """A host failure encoded in a response envelope."""

    code: str
    message: str
    details: Any = None
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class ResponseEnvelope:
    """A validated Lython host response."""

    ok: bool
    message: str | None = None
    error: ErrorPayload | None = None


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


def encode_request_envelope(message: str) -> str:
    """Wrap a raw TypeScript request JSON string for ``lython_native``."""

    decode_layla_request(message)
    return _encode_object(
        {
            "protocol": PROTOCOL_NAME,
            "version": PROTOCOL_VERSION,
            "type": REQUEST_TYPE,
            "message": message,
        },
        "Lython request envelope",
    )


def decode_request_envelope(raw: str) -> str:
    """Validate a host-side request envelope and return its raw inner message."""

    envelope = _decode_object(raw, "Lython request envelope")
    _validate_envelope_header(envelope, REQUEST_TYPE)

    message = envelope.get("message")
    if not isinstance(message, str):
        raise LythonProtocolError(
            "Lython request envelope must contain a string 'message'"
        )
    decode_layla_request(message)
    return message


def encode_success_response(message: str) -> str:
    """Wrap a raw terminal TypeScript response event as a successful response."""

    decode_layla_event(message)
    return _encode_object(
        {
            "protocol": PROTOCOL_NAME,
            "version": PROTOCOL_VERSION,
            "type": RESPONSE_TYPE,
            "ok": True,
            "message": message,
        },
        "Lython response envelope",
    )


def encode_error_response(
    code: str,
    message: str,
    *,
    details: Any = None,
    retryable: bool = False,
    layla_message: str | None = None,
) -> str:
    """Create a structured failure response, optionally preserving ``on_error``."""

    if not isinstance(code, str) or not code:
        raise LythonProtocolError("Host error code must be a non-empty string")
    if not isinstance(message, str) or not message:
        raise LythonProtocolError("Host error message must be a non-empty string")
    if not isinstance(retryable, bool):
        raise LythonProtocolError("Host error retryable flag must be a boolean")
    if layla_message is not None:
        decode_layla_event(layla_message)

    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    if details is not None:
        error["details"] = details

    envelope: dict[str, Any] = {
        "protocol": PROTOCOL_NAME,
        "version": PROTOCOL_VERSION,
        "type": RESPONSE_TYPE,
        "ok": False,
        "error": error,
    }
    if layla_message is not None:
        envelope["message"] = layla_message
    return _encode_object(envelope, "Lython response envelope")


def decode_response_envelope(raw: str) -> ResponseEnvelope:
    """Decode and validate a response returned by ``lython_native.request``."""

    envelope = _decode_object(raw, "Lython response envelope")
    _validate_envelope_header(envelope, RESPONSE_TYPE)

    ok = envelope.get("ok")
    if not isinstance(ok, bool):
        raise LythonProtocolError(
            "Lython response envelope must contain a boolean 'ok'"
        )

    inner_message = envelope.get("message")
    if inner_message is not None:
        if not isinstance(inner_message, str):
            raise LythonProtocolError(
                "Lython response envelope 'message' must be a string"
            )
        decode_layla_event(inner_message)

    if ok:
        if inner_message is None:
            raise LythonProtocolError(
                "Successful Lython response must contain a response 'message'"
            )
        return ResponseEnvelope(ok=True, message=inner_message)

    raw_error = envelope.get("error")
    if not isinstance(raw_error, dict):
        raise LythonProtocolError(
            "Failed Lython response must contain an 'error' object"
        )

    code = raw_error.get("code")
    error_message = raw_error.get("message")
    retryable = raw_error.get("retryable", False)
    if not isinstance(code, str) or not code:
        raise LythonProtocolError("Host error must contain a non-empty string 'code'")
    if not isinstance(error_message, str) or not error_message:
        raise LythonProtocolError(
            "Host error must contain a non-empty string 'message'"
        )
    if not isinstance(retryable, bool):
        raise LythonProtocolError("Host error 'retryable' must be a boolean")

    return ResponseEnvelope(
        ok=False,
        message=inner_message,
        error=ErrorPayload(
            code=code,
            message=error_message,
            details=raw_error.get("details"),
            retryable=retryable,
        ),
    )


def _validate_envelope_header(envelope: Mapping[str, Any], expected_type: str) -> None:
    if envelope.get("protocol") != PROTOCOL_NAME:
        raise LythonProtocolError(
            f"Unsupported protocol: {envelope.get('protocol')!r}"
        )
    if envelope.get("version") != PROTOCOL_VERSION:
        raise LythonProtocolError(
            f"Unsupported protocol version: {envelope.get('version')!r}"
        )
    if envelope.get("type") != expected_type:
        raise LythonProtocolError(
            f"Expected a {expected_type!r} envelope, got {envelope.get('type')!r}"
        )

