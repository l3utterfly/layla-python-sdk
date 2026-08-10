"""One-shot request transport over the private ``lython_native`` module."""

from __future__ import annotations

import asyncio
import importlib
import math
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Protocol

from .errors import (
    LythonExecutionError,
    LythonHostError,
    LythonNativeUnavailableError,
    LythonProtocolError,
    LythonTimeoutError,
    LythonTransportError,
)
from .protocol import (
    decode_layla_event,
    decode_layla_request,
    encode_layla_request,
)


class NativeModule(Protocol):
    """The subset of ``lython_native`` used by this SDK."""

    def send(self, message: str) -> None: ...

    def request(
        self,
        request_id: str,
        message: str,
        timeout: float | None = None,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class OneShotResponse:
    """A validated terminal event returned for one request."""

    request_id: str
    event: str
    data: Any
    message: Mapping[str, Any]
    raw_message: str


class LythonTransport:
    """Send one-shot requests and fire-and-forget notifications to Layla."""

    def __init__(
        self,
        *,
        default_timeout: float | None = 60.0,
        native_module: NativeModule | None = None,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.default_timeout = self._validate_timeout(default_timeout)
        self._native_module = native_module
        self._request_id_factory = request_id_factory or (lambda: uuid.uuid4().hex)

    def notify(self, message: str) -> None:
        """Send a fire-and-forget notification string directly to the host."""

        if not isinstance(message, str):
            raise TypeError("message must be a string")

        native = self._get_native_module()
        send = getattr(native, "send", None)
        if not callable(send):
            raise LythonNativeUnavailableError(
                "lython_native does not expose a callable send()"
            )

        try:
            send(message)
        except RuntimeError as exc:
            raise LythonExecutionError(str(exc)) from exc
        except ValueError as exc:
            raise LythonTransportError(str(exc)) from exc
        except LythonTransportError:
            raise
        except Exception as exc:
            raise LythonTransportError(
                f"Native notification failed: {exc}"
            ) from exc

    def request(
        self,
        message: Mapping[str, Any],
        expected_event: str,
        *,
        timeout: float | None = None,
    ) -> OneShotResponse:
        """Serialize and send an existing ``{cmd, data}`` Layla request."""

        return self.request_json(
            encode_layla_request(message),
            expected_event,
            timeout=timeout,
        )

    def request_json(
        self,
        message: str,
        expected_event: str,
        *,
        timeout: float | None = None,
    ) -> OneShotResponse:
        """Send already-serialized Layla request JSON without reconstructing it."""

        if not isinstance(expected_event, str) or not expected_event:
            raise LythonProtocolError("expected_event must be a non-empty string")

        native_timeout = (
            self.default_timeout if timeout is None else self._validate_timeout(timeout)
        )
        request_id = self._request_id_factory()
        if not isinstance(request_id, str) or not request_id:
            raise LythonProtocolError(
                "request_id_factory must return a non-empty string"
            )

        # Validate caller-provided JSON, then pass it through unchanged. The
        # native request ID already carries the correlation information.
        decode_layla_request(message)
        native = self._get_native_module()
        request = getattr(native, "request", None)
        if not callable(request):
            raise LythonNativeUnavailableError(
                "lython_native does not expose a callable request()"
            )

        try:
            raw_response = request(request_id, message, native_timeout)
        except TimeoutError as exc:
            raise LythonTimeoutError(
                f"Layla request {request_id} timed out"
            ) from exc
        except RuntimeError as exc:
            raise LythonExecutionError(str(exc)) from exc
        except ValueError as exc:
            raise LythonTransportError(str(exc)) from exc
        except LythonTransportError:
            raise
        except Exception as exc:
            raise LythonTransportError(
                f"Native request {request_id} failed: {exc}"
            ) from exc

        event_message = decode_layla_event(raw_response)
        event_name = event_message["event"]

        if event_name == "on_error":
            data = event_message.get("data")
            host_message = (
                data.get("message")
                if isinstance(data, dict) and isinstance(data.get("message"), str)
                else "Layla host request failed"
            )
            raise LythonHostError(
                host_message,
                code="layla_api_error",
                raw_message=raw_response,
            )

        if event_name != expected_event:
            raise LythonProtocolError(
                f"Expected response event {expected_event!r}, got {event_name!r}"
            )

        return OneShotResponse(
            request_id=request_id,
            event=event_name,
            data=event_message.get("data"),
            message=event_message,
            raw_message=raw_response,
        )

    async def request_async(
        self,
        message: Mapping[str, Any],
        expected_event: str,
        *,
        timeout: float | None = None,
    ) -> OneShotResponse:
        """Run a blocking native request outside the asyncio event-loop thread."""

        message_json = encode_layla_request(message)
        return await self.request_json_async(
            message_json,
            expected_event,
            timeout=timeout,
        )

    async def request_json_async(
        self,
        message: str,
        expected_event: str,
        *,
        timeout: float | None = None,
    ) -> OneShotResponse:
        """Async counterpart of :meth:`request_json`."""

        return await asyncio.to_thread(
            self.request_json,
            message,
            expected_event,
            timeout=timeout,
        )

    def _get_native_module(self) -> NativeModule:
        if self._native_module is not None:
            return self._native_module

        try:
            module: ModuleType = importlib.import_module("lython_native")
        except ModuleNotFoundError as exc:
            if exc.name != "lython_native":
                raise
            raise LythonNativeUnavailableError(
                "lython_native is only available inside an active Layla "
                "embedded Python execution"
            ) from exc

        self._native_module = module  # type: ignore[assignment]
        return self._native_module

    @staticmethod
    def _validate_timeout(timeout: float | None) -> float | None:
        if timeout is None:
            return None
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("timeout must be a finite non-negative number or None")
        value = float(timeout)
        if not math.isfinite(value) or value < 0:
            raise ValueError("timeout must be a finite non-negative number or None")
        return value
