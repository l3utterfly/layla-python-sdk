"""Exception hierarchy for the Lython SDK."""

from __future__ import annotations

from typing import Any


class LythonError(Exception):
    """Base class for SDK-defined errors."""


class LythonProtocolError(LythonError, ValueError):
    """A request or response did not conform to the Lython protocol."""


class LythonTransportError(LythonError):
    """The native transport could not complete a request."""


class LythonNativeUnavailableError(LythonTransportError):
    """The private ``lython_native`` module is unavailable."""


class LythonTimeoutError(LythonTransportError, TimeoutError):
    """The native request reached its configured timeout."""


class LythonExecutionError(LythonTransportError, RuntimeError):
    """The active embedded Python execution closed or became unavailable."""


class LythonHostError(LythonError):
    """The React Native host returned a structured failure response."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "host_error",
        details: Any = None,
        retryable: bool = False,
        raw_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details
        self.retryable = retryable
        self.raw_message = raw_message

