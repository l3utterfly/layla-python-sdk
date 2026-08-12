"""Playwright-like helpers for Layla's single host-owned WebView."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .errors import LythonHostError, LythonProtocolError, LythonTimeoutError
from .transport import LythonTransport

_OMITTED = object()

SelectorState = Literal["attached", "detached", "visible", "hidden"]
LoadState = Literal["load"]

_DEFAULT_TIMEOUT_MS = 30_000.0


@dataclass(frozen=True)
class FrameError:
    """The error a frame's evaluation raised, when ``FrameResult.error`` is set."""

    name: str
    message: str


@dataclass(frozen=True)
class FrameResult:
    """Result of evaluating an expression in a single frame.

    ``webview_evaluate`` runs the expression in every frame of the document (the
    top frame plus all nested iframes, including cross-origin ones), so a single
    call yields one :class:`FrameResult` per frame, depth-first from the top.
    """

    #: ``location.href`` of the frame that produced this result.
    url: str
    #: The frame's evaluation result (JSON value), or ``None`` if it raised.
    content: Any
    #: Present when the frame's evaluation raised; ``content`` is then ``None``.
    error: FrameError | None = None

_LOCATOR_ACTION_EXPRESSION = r"""
async ({ selector, action, value, name, state, key }) => {
  const isVisible = (element) => {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' ||
        style.visibility === 'collapse') return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const isEnabled = (element) =>
    !(element && 'disabled' in element && element.disabled);
  const find = () => document.querySelector(selector);
  const waitFor = (predicate) => new Promise((resolve, reject) => {
    const check = () => {
      try {
        const result = predicate();
        if (result) {
          resolve(result);
        } else {
          window.setTimeout(check, 50);
        }
      } catch (error) {
        reject(error);
      }
    };
    check();
  });
  const waitForState = async (requestedState) => {
    if (requestedState === 'attached') return await waitFor(() => find());
    if (requestedState === 'detached') return await waitFor(() => !find());
    if (requestedState === 'visible') return await waitFor(() => {
      const element = find();
      return isVisible(element) ? element : false;
    });
    if (requestedState === 'hidden') return await waitFor(() => {
      const element = find();
      return !element || !isVisible(element);
    });
    throw new TypeError(`Unsupported selector state: ${requestedState}`);
  };

  if (action === 'count') return document.querySelectorAll(selector).length;
  if (action === 'all_text_contents') {
    return Array.from(document.querySelectorAll(selector), (element) => element.textContent || '');
  }
  if (action === 'is_visible') return isVisible(find());
  if (action === 'wait') {
    await waitForState(state);
    return null;
  }

  const requiredState = action === 'click' || action === 'fill' || action === 'press'
    ? 'visible'
    : 'attached';
  const element = await waitForState(requiredState);

  if (action === 'click') {
    await waitFor(() => isEnabled(element));
    element.scrollIntoView({ block: 'center', inline: 'center' });
    element.click();
    return null;
  }
  if (action === 'fill') {
    await waitFor(() => isEnabled(element));
    element.focus();
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      const prototype = element instanceof HTMLInputElement
        ? HTMLInputElement.prototype
        : HTMLTextAreaElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
      if (setter) setter.call(element, value);
      else element.value = value;
    } else if (element.isContentEditable) {
      element.textContent = value;
    } else {
      throw new TypeError('fill() requires an input, textarea, or contenteditable element.');
    }
    element.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
    element.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
    return null;
  }
  if (action === 'press') {
    await waitFor(() => isEnabled(element));
    element.focus();
    const eventOptions = { key, bubbles: true, cancelable: true, composed: true };
    const shouldContinue = element.dispatchEvent(new KeyboardEvent('keydown', eventOptions));
    element.dispatchEvent(new KeyboardEvent('keypress', eventOptions));
    element.dispatchEvent(new KeyboardEvent('keyup', eventOptions));
    if (shouldContinue && key === 'Enter') {
      const form = element.form || element.closest?.('form');
      if (form) form.requestSubmit();
    }
    return null;
  }
  if (action === 'text_content') return element.textContent;
  if (action === 'inner_text') return element.innerText;
  if (action === 'inner_html') return element.innerHTML;
  if (action === 'get_attribute') return element.getAttribute(name);
  if (action === 'input_value') {
    if (!('value' in element)) throw new TypeError('input_value() requires a form control.');
    return element.value;
  }
  throw new TypeError(`Unsupported locator action: ${action}`);
}
"""

_WAIT_FOR_FUNCTION_EXPRESSION = r"""
async ({ expression, hasArgument, argument, polling }) => {
  const predicate = (0, eval)(`(${expression}\n)`);
  const run = async () => {
    const value = typeof predicate === 'function'
      ? (hasArgument ? predicate(argument) : predicate())
      : predicate;
    return await value;
  };
  return await new Promise((resolve, reject) => {
    const check = async () => {
      try {
        const result = await run();
        if (result) {
          resolve(result);
          return;
        }
        if (polling === 'raf') window.requestAnimationFrame(check);
        else window.setTimeout(check, polling);
      } catch (error) {
        reject(error);
      }
    };
    void check();
  });
}
"""

def _validate_non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value


def _validate_timeout_ms(timeout: float | None) -> float | None:
    if timeout is None:
        return None
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("timeout must be a finite non-negative number or None")
    value = float(timeout)
    if not math.isfinite(value) or value < 0:
        raise ValueError("timeout must be a finite non-negative number or None")
    return value


def _native_timeout_seconds(timeout_ms: float | None) -> float | None:
    if timeout_ms is None or timeout_ms == 0:
        return None
    # Let the host watchdog win the race and deliver its richer WebView error.
    return timeout_ms / 1000 + 1


def _deadline_for_timeout(timeout_ms: float | None) -> float | None:
    if timeout_ms == 0:
        return None
    effective_timeout = _DEFAULT_TIMEOUT_MS if timeout_ms is None else timeout_ms
    return time.monotonic() + effective_timeout / 1000


def _remaining_timeout_ms(deadline: float | None) -> float:
    if deadline is None:
        return 0.0
    return max(0.0, (deadline - time.monotonic()) * 1000)


def _is_retryable_context_error(error: LythonHostError) -> bool:
    return error.retryable and error.code == "webview_context_destroyed"


def _response_field(data: Any, key: str, description: str) -> Any:
    if not isinstance(data, Mapping) or key not in data:
        raise LythonProtocolError(f"{description} must contain {key!r}")
    return data[key]


def _parse_frame_results(value: Any) -> list[FrameResult]:
    """Parse the per-frame array a ``webview_evaluate`` response now carries."""

    if not isinstance(value, list):
        raise LythonProtocolError(
            "WebView evaluation response value must be a list of frame results"
        )
    frames: list[FrameResult] = []
    for item in value:
        if not isinstance(item, Mapping) or "url" not in item or "content" not in item:
            raise LythonProtocolError(
                "each WebView frame result must contain 'url' and 'content'"
            )
        url = item["url"]
        if not isinstance(url, str):
            raise LythonProtocolError("WebView frame result 'url' must be a string")
        raw_error = item.get("error")
        error: FrameError | None = None
        if raw_error is not None:
            if not isinstance(raw_error, Mapping):
                raise LythonProtocolError("WebView frame result 'error' must be an object")
            error = FrameError(
                name=str(raw_error.get("name", "Error")),
                message=str(raw_error.get("message", "")),
            )
        frames.append(FrameResult(url=url, content=item["content"], error=error))
    return frames


def _top_frame_content(frames: list[FrameResult]) -> Any:
    """Reduce the per-frame array to the top frame's value for scalar callers.

    The bootstrap emits the frame where evaluation started (the top frame) first,
    so ``frames[0]`` is the top document. This preserves Playwright-style single
    value semantics for :meth:`Page.evaluate`, :meth:`Page.content`, locators, and
    friends, while :meth:`Page.evaluate_all_frames` exposes every frame. An empty
    array (e.g. an action settled by navigation before any frame replied) reads as
    ``None``, and a top-frame error is re-raised like the old on_error path.
    """

    if not frames:
        return None
    top = frames[0]
    if top.error is not None:
        raise LythonHostError(
            top.error.message or "WebView evaluation failed",
            code="webview_evaluation_error",
            details={"name": top.error.name},
            retryable=False,
        )
    return top.content


class Page:
    """The single WebView controlled by the active Layla Python screen.

    Browser timeouts use Playwright's millisecond convention. Evaluation values
    must be JSON serializable because Lython does not expose remote JS handles.
    """

    def __init__(self, transport: LythonTransport) -> None:
        self._transport = transport

    def goto(self, url: str, *, timeout: float | None = None) -> str:
        """Navigate to *url* and return the final URL after redirects."""

        url = _validate_non_empty_string(url, "url")
        timeout_ms = _validate_timeout_ms(timeout)
        data: dict[str, Any] = {"url": url}
        if timeout_ms is not None:
            data["timeout_ms"] = timeout_ms
        response = self._transport.request(
            {"cmd": "webview_navigate", "data": data},
            "on_webview_navigate_response",
            timeout=_native_timeout_seconds(timeout_ms),
        ).data
        final_url = _response_field(response, "url", "WebView navigation response")
        if not isinstance(final_url, str):
            raise LythonProtocolError("WebView navigation response url must be a string")
        return final_url

    async def goto_async(self, url: str, *, timeout: float | None = None) -> str:
        """Async counterpart of :meth:`goto`."""

        url = _validate_non_empty_string(url, "url")
        timeout_ms = _validate_timeout_ms(timeout)
        data: dict[str, Any] = {"url": url}
        if timeout_ms is not None:
            data["timeout_ms"] = timeout_ms
        response = await self._transport.request_async(
            {"cmd": "webview_navigate", "data": data},
            "on_webview_navigate_response",
            timeout=_native_timeout_seconds(timeout_ms),
        )
        final_url = _response_field(response.data, "url", "WebView navigation response")
        if not isinstance(final_url, str):
            raise LythonProtocolError("WebView navigation response url must be a string")
        return final_url

    def wait_for_url(
        self,
        url: str,
        *,
        wait_until: LoadState = "load",
        timeout: float | None = None,
    ) -> None:
        """Wait for the current or a future main-frame URL to match *url*."""

        url = _validate_non_empty_string(url, "url")
        self._validate_load_state(wait_until, "wait_until")
        timeout_ms = _validate_timeout_ms(timeout)
        data: dict[str, Any] = {"url": url, "wait_until": wait_until}
        if timeout_ms is not None:
            data["timeout_ms"] = timeout_ms
        self._transport.request(
            {"cmd": "webview_wait_for_url", "data": data},
            "on_webview_wait_for_url_response",
            timeout=_native_timeout_seconds(timeout_ms),
        )

    async def wait_for_url_async(
        self,
        url: str,
        *,
        wait_until: LoadState = "load",
        timeout: float | None = None,
    ) -> None:
        """Async counterpart of :meth:`wait_for_url`."""

        url = _validate_non_empty_string(url, "url")
        self._validate_load_state(wait_until, "wait_until")
        timeout_ms = _validate_timeout_ms(timeout)
        data: dict[str, Any] = {"url": url, "wait_until": wait_until}
        if timeout_ms is not None:
            data["timeout_ms"] = timeout_ms
        await self._transport.request_async(
            {"cmd": "webview_wait_for_url", "data": data},
            "on_webview_wait_for_url_response",
            timeout=_native_timeout_seconds(timeout_ms),
        )

    def wait_for_load_state(
        self,
        state: LoadState = "load",
        *,
        timeout: float | None = None,
    ) -> None:
        """Wait for the current document to reach *state*."""

        self._validate_load_state(state, "state")
        timeout_ms = _validate_timeout_ms(timeout)
        data: dict[str, Any] = {"state": state}
        if timeout_ms is not None:
            data["timeout_ms"] = timeout_ms
        self._transport.request(
            {"cmd": "webview_wait_for_load_state", "data": data},
            "on_webview_wait_for_load_state_response",
            timeout=_native_timeout_seconds(timeout_ms),
        )

    async def wait_for_load_state_async(
        self,
        state: LoadState = "load",
        *,
        timeout: float | None = None,
    ) -> None:
        """Async counterpart of :meth:`wait_for_load_state`."""

        self._validate_load_state(state, "state")
        timeout_ms = _validate_timeout_ms(timeout)
        data: dict[str, Any] = {"state": state}
        if timeout_ms is not None:
            data["timeout_ms"] = timeout_ms
        await self._transport.request_async(
            {"cmd": "webview_wait_for_load_state", "data": data},
            "on_webview_wait_for_load_state_response",
            timeout=_native_timeout_seconds(timeout_ms),
        )

    def evaluate(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Evaluate JavaScript using Playwright's ``evaluate(expression, arg)`` form."""

        return self._evaluate(expression, arg, timeout=timeout, wait_for_navigation=False)

    async def evaluate_async(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Async counterpart of :meth:`evaluate`."""

        return await self._evaluate_async(
            expression, arg, timeout=timeout, wait_for_navigation=False
        )

    def evaluate_all_frames(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        timeout: float | None = None,
    ) -> list[FrameResult]:
        """Evaluate *expression* in every frame and return one result per frame.

        Unlike :meth:`evaluate`, which returns only the top document's value, this
        returns a :class:`FrameResult` for the top frame and every nested iframe
        (including cross-origin ones the top document cannot reach through the
        DOM), depth-first from the top. It is up to the caller to decide which
        frames to use — e.g. filter by ``url`` or ignore frames whose ``content``
        is empty.
        """

        return self._evaluate_frames(
            expression, arg, timeout=timeout, wait_for_navigation=False
        )

    async def evaluate_all_frames_async(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        timeout: float | None = None,
    ) -> list[FrameResult]:
        """Async counterpart of :meth:`evaluate_all_frames`."""

        return await self._evaluate_frames_async(
            expression, arg, timeout=timeout, wait_for_navigation=False
        )

    def _evaluate(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        timeout: float | None,
        wait_for_navigation: bool,
    ) -> Any:
        frames = self._evaluate_frames(
            expression, arg, timeout=timeout, wait_for_navigation=wait_for_navigation
        )
        return _top_frame_content(frames)

    async def _evaluate_async(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        timeout: float | None,
        wait_for_navigation: bool,
    ) -> Any:
        frames = await self._evaluate_frames_async(
            expression, arg, timeout=timeout, wait_for_navigation=wait_for_navigation
        )
        return _top_frame_content(frames)

    def _evaluate_frames(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        timeout: float | None,
        wait_for_navigation: bool,
    ) -> list[FrameResult]:
        expression = _validate_non_empty_string(expression, "expression")
        timeout_ms = _validate_timeout_ms(timeout)
        data: dict[str, Any] = {"expression": expression}
        if arg is not _OMITTED:
            data["argument"] = arg
        if timeout_ms is not None:
            data["timeout_ms"] = timeout_ms
        if wait_for_navigation:
            data["wait_for_navigation"] = True
        response = self._transport.request(
            {"cmd": "webview_evaluate", "data": data},
            "on_webview_evaluate_response",
            timeout=_native_timeout_seconds(timeout_ms),
        ).data
        value = _response_field(response, "value", "WebView evaluation response")
        return _parse_frame_results(value)

    async def _evaluate_frames_async(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        timeout: float | None,
        wait_for_navigation: bool,
    ) -> list[FrameResult]:
        expression = _validate_non_empty_string(expression, "expression")
        timeout_ms = _validate_timeout_ms(timeout)
        data: dict[str, Any] = {"expression": expression}
        if arg is not _OMITTED:
            data["argument"] = arg
        if timeout_ms is not None:
            data["timeout_ms"] = timeout_ms
        if wait_for_navigation:
            data["wait_for_navigation"] = True
        response = await self._transport.request_async(
            {"cmd": "webview_evaluate", "data": data},
            "on_webview_evaluate_response",
            timeout=_native_timeout_seconds(timeout_ms),
        )
        value = _response_field(response.data, "value", "WebView evaluation response")
        return _parse_frame_results(value)

    def locator(self, selector: str) -> Locator:
        """Create a reusable CSS locator without querying the page yet."""

        return Locator(self, selector)

    def content(self, *, timeout: float | None = None) -> str:
        value = self.evaluate("() => document.documentElement.outerHTML", timeout=timeout)
        if not isinstance(value, str):
            raise LythonProtocolError("page content must be a string")
        return value

    async def content_async(self, *, timeout: float | None = None) -> str:
        value = await self.evaluate_async(
            "() => document.documentElement.outerHTML", timeout=timeout
        )
        if not isinstance(value, str):
            raise LythonProtocolError("page content must be a string")
        return value

    def frames_content(self, *, timeout: float | None = None) -> list[FrameResult]:
        """Return the ``outerHTML`` of every frame as :class:`FrameResult` values.

        Convenience over :meth:`evaluate_all_frames`: each result's ``content`` is
        that frame's serialized HTML (or ``None`` if the frame errored).
        """

        return self.evaluate_all_frames(
            "() => document.documentElement.outerHTML", timeout=timeout
        )

    async def frames_content_async(
        self, *, timeout: float | None = None
    ) -> list[FrameResult]:
        """Async counterpart of :meth:`frames_content`."""

        return await self.evaluate_all_frames_async(
            "() => document.documentElement.outerHTML", timeout=timeout
        )

    def title(self, *, timeout: float | None = None) -> str:
        value = self.evaluate("() => document.title", timeout=timeout)
        if not isinstance(value, str):
            raise LythonProtocolError("page title must be a string")
        return value

    async def title_async(self, *, timeout: float | None = None) -> str:
        value = await self.evaluate_async("() => document.title", timeout=timeout)
        if not isinstance(value, str):
            raise LythonProtocolError("page title must be a string")
        return value

    def wait_for_function(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        polling: float | Literal["raf"] = "raf",
        timeout: float | None = None,
    ) -> Any:
        payload = self._wait_for_function_payload(expression, arg, polling)
        return self._evaluate_retrying_navigation(
            _WAIT_FOR_FUNCTION_EXPRESSION, payload, timeout=timeout
        )

    async def wait_for_function_async(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        polling: float | Literal["raf"] = "raf",
        timeout: float | None = None,
    ) -> Any:
        payload = self._wait_for_function_payload(expression, arg, polling)
        return await self._evaluate_retrying_navigation_async(
            _WAIT_FOR_FUNCTION_EXPRESSION, payload, timeout=timeout
        )

    def wait_for_function_all_frames(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        polling_ms: float = 250.0,
        timeout: float | None = None,
    ) -> list[FrameResult]:
        """Poll *expression* across every frame until one returns a truthy value.

        Returns the full per-frame result list once at least one frame's
        ``content`` is truthy (and not an error). Unlike :meth:`wait_for_function`,
        which polls *inside* each frame and can only observe the top document,
        this polls from the host side — so ``expression`` must return immediately
        (a probe, not a blocking wait) and it can observe conditions inside
        cross-origin iframes the top frame cannot reach.

        Raises :class:`LythonTimeoutError` if no frame matches before *timeout*
        (Playwright's default of 30s when omitted; ``0`` waits indefinitely).
        """

        timeout_ms = _validate_timeout_ms(timeout)
        interval_ms = _validate_timeout_ms(polling_ms) or 0.0
        deadline = _deadline_for_timeout(timeout_ms)
        while True:
            attempt_timeout = 0.0 if deadline is None else max(_remaining_timeout_ms(deadline), 1.0)
            try:
                frames = self._evaluate_frames(
                    expression, arg, timeout=attempt_timeout, wait_for_navigation=False
                )
            except LythonHostError as error:
                if not _is_retryable_context_error(error) or (
                    deadline is not None and _remaining_timeout_ms(deadline) <= 0
                ):
                    raise
                frames = []
            if any(frame.error is None and frame.content for frame in frames):
                return frames
            if deadline is not None and _remaining_timeout_ms(deadline) <= 0:
                raise LythonTimeoutError(
                    "wait_for_function_all_frames timed out before any frame matched"
                )
            if interval_ms > 0:
                wait = interval_ms
                if deadline is not None:
                    wait = min(wait, _remaining_timeout_ms(deadline))
                if wait > 0:
                    # Sleep on the host, not via wait_for_timeout(): the latter
                    # broadcasts a setTimeout to every frame and would inherit the
                    # all-frames aggregate delay, timing out on a slow/unresponsive
                    # frame during generation.
                    time.sleep(wait / 1000)

    async def wait_for_function_all_frames_async(
        self,
        expression: str,
        arg: Any = _OMITTED,
        *,
        polling_ms: float = 250.0,
        timeout: float | None = None,
    ) -> list[FrameResult]:
        """Async counterpart of :meth:`wait_for_function_all_frames`."""

        timeout_ms = _validate_timeout_ms(timeout)
        interval_ms = _validate_timeout_ms(polling_ms) or 0.0
        deadline = _deadline_for_timeout(timeout_ms)
        while True:
            attempt_timeout = 0.0 if deadline is None else max(_remaining_timeout_ms(deadline), 1.0)
            try:
                frames = await self._evaluate_frames_async(
                    expression, arg, timeout=attempt_timeout, wait_for_navigation=False
                )
            except LythonHostError as error:
                if not _is_retryable_context_error(error) or (
                    deadline is not None and _remaining_timeout_ms(deadline) <= 0
                ):
                    raise
                frames = []
            if any(frame.error is None and frame.content for frame in frames):
                return frames
            if deadline is not None and _remaining_timeout_ms(deadline) <= 0:
                raise LythonTimeoutError(
                    "wait_for_function_all_frames timed out before any frame matched"
                )
            if interval_ms > 0:
                wait = interval_ms
                if deadline is not None:
                    wait = min(wait, _remaining_timeout_ms(deadline))
                if wait > 0:
                    # Host-side sleep; see the sync method for why not
                    # wait_for_timeout_async().
                    await asyncio.sleep(wait / 1000)

    def wait_for_timeout(self, timeout: float) -> None:
        """Wait *timeout* milliseconds.

        The wait runs on the host, like Playwright's driver-side
        ``wait_for_timeout`` — not inside the page. A page-side timer would be
        broadcast to every frame and inherit the all-frames aggregate delay,
        which both inflates short waits (to the per-frame timeout) and can time
        out on an unresponsive frame. The WebView keeps running while we sleep.
        """
        delay = _validate_timeout_ms(timeout)
        assert delay is not None
        if delay > 0:
            time.sleep(delay / 1000)

    async def wait_for_timeout_async(self, timeout: float) -> None:
        """Async counterpart of :meth:`wait_for_timeout`."""
        delay = _validate_timeout_ms(timeout)
        assert delay is not None
        if delay > 0:
            await asyncio.sleep(delay / 1000)

    def wait_for_selector(
        self,
        selector: str,
        *,
        state: SelectorState = "visible",
        timeout: float | None = None,
    ) -> Locator | None:
        locator = self.locator(selector)
        locator.wait_for(state=state, timeout=timeout)
        return None if state in ("hidden", "detached") else locator

    async def wait_for_selector_async(
        self,
        selector: str,
        *,
        state: SelectorState = "visible",
        timeout: float | None = None,
    ) -> Locator | None:
        locator = self.locator(selector)
        await locator.wait_for_async(state=state, timeout=timeout)
        return None if state in ("hidden", "detached") else locator

    def click(
        self,
        selector: str,
        *,
        timeout: float | None = None,
        no_wait_after: bool | None = None,
    ) -> None:
        self.locator(selector).click(timeout=timeout, no_wait_after=no_wait_after)

    async def click_async(
        self,
        selector: str,
        *,
        timeout: float | None = None,
        no_wait_after: bool | None = None,
    ) -> None:
        await self.locator(selector).click_async(
            timeout=timeout, no_wait_after=no_wait_after
        )

    def press(
        self,
        selector: str,
        key: str,
        *,
        timeout: float | None = None,
        no_wait_after: bool | None = None,
    ) -> None:
        self.locator(selector).press(
            key, timeout=timeout, no_wait_after=no_wait_after
        )

    async def press_async(
        self,
        selector: str,
        key: str,
        *,
        timeout: float | None = None,
        no_wait_after: bool | None = None,
    ) -> None:
        await self.locator(selector).press_async(
            key, timeout=timeout, no_wait_after=no_wait_after
        )

    def fill(self, selector: str, value: str, *, timeout: float | None = None) -> None:
        self.locator(selector).fill(value, timeout=timeout)

    async def fill_async(
        self, selector: str, value: str, *, timeout: float | None = None
    ) -> None:
        await self.locator(selector).fill_async(value, timeout=timeout)

    def text_content(self, selector: str, *, timeout: float | None = None) -> str | None:
        return self.locator(selector).text_content(timeout=timeout)

    async def text_content_async(
        self, selector: str, *, timeout: float | None = None
    ) -> str | None:
        return await self.locator(selector).text_content_async(timeout=timeout)

    def inner_text(self, selector: str, *, timeout: float | None = None) -> str:
        return self.locator(selector).inner_text(timeout=timeout)

    async def inner_text_async(self, selector: str, *, timeout: float | None = None) -> str:
        return await self.locator(selector).inner_text_async(timeout=timeout)

    def inner_html(self, selector: str, *, timeout: float | None = None) -> str:
        return self.locator(selector).inner_html(timeout=timeout)

    async def inner_html_async(self, selector: str, *, timeout: float | None = None) -> str:
        return await self.locator(selector).inner_html_async(timeout=timeout)

    def get_attribute(
        self, selector: str, name: str, *, timeout: float | None = None
    ) -> str | None:
        return self.locator(selector).get_attribute(name, timeout=timeout)

    async def get_attribute_async(
        self, selector: str, name: str, *, timeout: float | None = None
    ) -> str | None:
        return await self.locator(selector).get_attribute_async(name, timeout=timeout)

    def is_visible(self, selector: str, *, timeout: float | None = None) -> bool:
        return self.locator(selector).is_visible(timeout=timeout)

    async def is_visible_async(self, selector: str, *, timeout: float | None = None) -> bool:
        return await self.locator(selector).is_visible_async(timeout=timeout)

    def _evaluate_retrying_navigation(
        self,
        expression: str,
        arg: Any,
        *,
        timeout: float | None,
    ) -> Any:
        timeout_ms = _validate_timeout_ms(timeout)
        deadline = _deadline_for_timeout(timeout_ms)
        while True:
            remaining = _remaining_timeout_ms(deadline)
            attempt_timeout = 0.0 if deadline is None else remaining
            try:
                return self._evaluate(
                    expression,
                    arg,
                    timeout=attempt_timeout,
                    wait_for_navigation=False,
                )
            except LythonHostError as error:
                remaining = _remaining_timeout_ms(deadline)
                if not _is_retryable_context_error(error) or (
                    deadline is not None and remaining <= 0
                ):
                    raise
                self.wait_for_load_state(
                    timeout=0.0 if deadline is None else remaining
                )

    async def _evaluate_retrying_navigation_async(
        self,
        expression: str,
        arg: Any,
        *,
        timeout: float | None,
    ) -> Any:
        timeout_ms = _validate_timeout_ms(timeout)
        deadline = _deadline_for_timeout(timeout_ms)
        while True:
            remaining = _remaining_timeout_ms(deadline)
            attempt_timeout = 0.0 if deadline is None else remaining
            try:
                return await self._evaluate_async(
                    expression,
                    arg,
                    timeout=attempt_timeout,
                    wait_for_navigation=False,
                )
            except LythonHostError as error:
                remaining = _remaining_timeout_ms(deadline)
                if not _is_retryable_context_error(error) or (
                    deadline is not None and remaining <= 0
                ):
                    raise
                await self.wait_for_load_state_async(
                    timeout=0.0 if deadline is None else remaining
                )

    @staticmethod
    def _wait_for_function_payload(
        expression: str,
        arg: Any,
        polling: float | Literal["raf"],
    ) -> dict[str, Any]:
        expression = _validate_non_empty_string(expression, "expression")
        if polling != "raf":
            polling = _validate_timeout_ms(polling)  # type: ignore[arg-type]
            if polling is None:
                raise ValueError("polling must be 'raf' or a finite non-negative number")
        return {
            "expression": expression,
            "hasArgument": arg is not _OMITTED,
            "argument": None if arg is _OMITTED else arg,
            "polling": polling,
        }

    @staticmethod
    def _validate_load_state(state: str, name: str) -> None:
        if state != "load":
            raise ValueError(f"{name} must be 'load'")


class Locator:
    """A reusable CSS selector evaluated afresh for every operation."""

    def __init__(self, page: Page, selector: str) -> None:
        self._page = page
        self.selector = _validate_non_empty_string(selector, "selector")

    def __repr__(self) -> str:
        return f"Locator({self.selector!r})"

    def wait_for(
        self,
        *,
        state: SelectorState = "visible",
        timeout: float | None = None,
    ) -> None:
        self._validate_state(state)
        self._action("wait", state=state, timeout=timeout)

    async def wait_for_async(
        self,
        *,
        state: SelectorState = "visible",
        timeout: float | None = None,
    ) -> None:
        self._validate_state(state)
        await self._action_async("wait", state=state, timeout=timeout)

    def click(
        self,
        *,
        timeout: float | None = None,
        no_wait_after: bool | None = None,
    ) -> None:
        self._validate_no_wait_after(no_wait_after)
        self._action(
            "click", timeout=timeout, wait_for_navigation=no_wait_after is not True
        )

    async def click_async(
        self,
        *,
        timeout: float | None = None,
        no_wait_after: bool | None = None,
    ) -> None:
        self._validate_no_wait_after(no_wait_after)
        await self._action_async(
            "click", timeout=timeout, wait_for_navigation=no_wait_after is not True
        )

    def press(
        self,
        key: str,
        *,
        timeout: float | None = None,
        no_wait_after: bool | None = None,
    ) -> None:
        key = _validate_non_empty_string(key, "key")
        self._validate_no_wait_after(no_wait_after)
        self._action(
            "press",
            key=key,
            timeout=timeout,
            wait_for_navigation=no_wait_after is not True,
        )

    async def press_async(
        self,
        key: str,
        *,
        timeout: float | None = None,
        no_wait_after: bool | None = None,
    ) -> None:
        key = _validate_non_empty_string(key, "key")
        self._validate_no_wait_after(no_wait_after)
        await self._action_async(
            "press",
            key=key,
            timeout=timeout,
            wait_for_navigation=no_wait_after is not True,
        )

    def fill(self, value: str, *, timeout: float | None = None) -> None:
        if not isinstance(value, str):
            raise TypeError("value must be a string")
        self._action("fill", value=value, timeout=timeout)

    async def fill_async(self, value: str, *, timeout: float | None = None) -> None:
        if not isinstance(value, str):
            raise TypeError("value must be a string")
        await self._action_async("fill", value=value, timeout=timeout)

    def text_content(self, *, timeout: float | None = None) -> str | None:
        value = self._action("text_content", timeout=timeout)
        if value is not None and not isinstance(value, str):
            raise LythonProtocolError("locator text_content result must be a string or None")
        return value

    async def text_content_async(self, *, timeout: float | None = None) -> str | None:
        value = await self._action_async("text_content", timeout=timeout)
        if value is not None and not isinstance(value, str):
            raise LythonProtocolError("locator text_content result must be a string or None")
        return value

    def inner_text(self, *, timeout: float | None = None) -> str:
        return self._string_action("inner_text", timeout)

    async def inner_text_async(self, *, timeout: float | None = None) -> str:
        return await self._string_action_async("inner_text", timeout)

    def inner_html(self, *, timeout: float | None = None) -> str:
        return self._string_action("inner_html", timeout)

    async def inner_html_async(self, *, timeout: float | None = None) -> str:
        return await self._string_action_async("inner_html", timeout)

    def get_attribute(self, name: str, *, timeout: float | None = None) -> str | None:
        name = _validate_non_empty_string(name, "name")
        value = self._action("get_attribute", name=name, timeout=timeout)
        if value is not None and not isinstance(value, str):
            raise LythonProtocolError("locator attribute result must be a string or None")
        return value

    async def get_attribute_async(
        self, name: str, *, timeout: float | None = None
    ) -> str | None:
        name = _validate_non_empty_string(name, "name")
        value = await self._action_async("get_attribute", name=name, timeout=timeout)
        if value is not None and not isinstance(value, str):
            raise LythonProtocolError("locator attribute result must be a string or None")
        return value

    def input_value(self, *, timeout: float | None = None) -> str:
        return self._string_action("input_value", timeout)

    async def input_value_async(self, *, timeout: float | None = None) -> str:
        return await self._string_action_async("input_value", timeout)

    def is_visible(self, *, timeout: float | None = None) -> bool:
        value = self._action("is_visible", timeout=timeout)
        if not isinstance(value, bool):
            raise LythonProtocolError("locator is_visible result must be a boolean")
        return value

    async def is_visible_async(self, *, timeout: float | None = None) -> bool:
        value = await self._action_async("is_visible", timeout=timeout)
        if not isinstance(value, bool):
            raise LythonProtocolError("locator is_visible result must be a boolean")
        return value

    def count(self, *, timeout: float | None = None) -> int:
        value = self._action("count", timeout=timeout)
        if isinstance(value, bool) or not isinstance(value, int):
            raise LythonProtocolError("locator count result must be an integer")
        return value

    async def count_async(self, *, timeout: float | None = None) -> int:
        value = await self._action_async("count", timeout=timeout)
        if isinstance(value, bool) or not isinstance(value, int):
            raise LythonProtocolError("locator count result must be an integer")
        return value

    def all_text_contents(self, *, timeout: float | None = None) -> list[str]:
        value = self._action("all_text_contents", timeout=timeout)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise LythonProtocolError("locator all_text_contents result must be a string list")
        return value

    async def all_text_contents_async(self, *, timeout: float | None = None) -> list[str]:
        value = await self._action_async("all_text_contents", timeout=timeout)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise LythonProtocolError("locator all_text_contents result must be a string list")
        return value

    def _action(
        self,
        action: str,
        *,
        timeout: float | None = None,
        wait_for_navigation: bool = False,
        **data: Any,
    ) -> Any:
        argument = {"selector": self.selector, "action": action, **data}
        if action == "wait":
            return self._page._evaluate_retrying_navigation(
                _LOCATOR_ACTION_EXPRESSION, argument, timeout=timeout
            )
        return self._page._evaluate(
            _LOCATOR_ACTION_EXPRESSION,
            argument,
            timeout=timeout,
            wait_for_navigation=wait_for_navigation,
        )

    async def _action_async(
        self,
        action: str,
        *,
        timeout: float | None = None,
        wait_for_navigation: bool = False,
        **data: Any,
    ) -> Any:
        argument = {"selector": self.selector, "action": action, **data}
        if action == "wait":
            return await self._page._evaluate_retrying_navigation_async(
                _LOCATOR_ACTION_EXPRESSION, argument, timeout=timeout
            )
        return await self._page._evaluate_async(
            _LOCATOR_ACTION_EXPRESSION,
            argument,
            timeout=timeout,
            wait_for_navigation=wait_for_navigation,
        )

    def _string_action(self, action: str, timeout: float | None) -> str:
        value = self._action(action, timeout=timeout)
        if not isinstance(value, str):
            raise LythonProtocolError(f"locator {action} result must be a string")
        return value

    async def _string_action_async(self, action: str, timeout: float | None) -> str:
        value = await self._action_async(action, timeout=timeout)
        if not isinstance(value, str):
            raise LythonProtocolError(f"locator {action} result must be a string")
        return value

    @staticmethod
    def _validate_state(state: str) -> None:
        if state not in ("attached", "detached", "visible", "hidden"):
            raise ValueError("state must be 'attached', 'detached', 'visible', or 'hidden'")

    @staticmethod
    def _validate_no_wait_after(value: bool | None) -> None:
        if value is not None and not isinstance(value, bool):
            raise TypeError("no_wait_after must be a boolean or None")


__all__ = [
    "FrameError",
    "FrameResult",
    "LoadState",
    "Locator",
    "Page",
    "SelectorState",
]
