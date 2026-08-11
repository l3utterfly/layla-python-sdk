"""Reusable template for future one-shot SDK resource methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import LythonProtocolError
from .transport import LythonTransport


@dataclass(frozen=True, slots=True)
class OneShotRequestTemplate:
    """Bind a Layla command name to its one terminal response event."""

    command: str
    response_event: str

    def __post_init__(self) -> None:
        if not isinstance(self.command, str) or not self.command:
            raise LythonProtocolError("command must be a non-empty string")
        if not isinstance(self.response_event, str) or not self.response_event:
            raise LythonProtocolError("response_event must be a non-empty string")

    def build_message(self, data: Any = None) -> dict[str, Any]:
        """Build the exact ``{cmd, data}`` shape consumed by the RN service."""

        return {"cmd": self.command, "data": data}

    def send(
        self,
        transport: LythonTransport,
        data: Any = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Send synchronously and return the response event's ``data`` field."""

        return transport.request(
            self.build_message(data),
            self.response_event,
            timeout=timeout,
        ).data

    async def send_async(
        self,
        transport: LythonTransport,
        data: Any = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Send asynchronously and return the response event's ``data`` field."""

        response = await transport.request_async(
            self.build_message(data),
            self.response_event,
            timeout=timeout,
        )
        return response.data
