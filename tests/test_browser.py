from __future__ import annotations

import json
import unittest
from typing import Any
from unittest import mock

import lython
from lython import LythonClient, LythonProtocolError, LythonTransport, Locator, Page


class BrowserNative:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], float | None]] = []
        # Scalar the top frame "returns"; wrapped into the per-frame array shape.
        self.next_value: Any = None
        # Set to override with an explicit list of frame-result dicts.
        self.next_frames: Any = None

    def send(self, message: str) -> None:
        raise AssertionError(f"unexpected notification: {message}")

    def _evaluate_value(self) -> Any:
        if self.next_frames is not None:
            return self.next_frames
        return [{"url": "https://example.com/final", "content": self.next_value}]

    def request(self, request_id: str, message: str, timeout: float | None) -> str:
        request = json.loads(message)
        self.calls.append((request, timeout))
        if request["cmd"] == "webview_navigate":
            event = "on_webview_navigate_response"
            data = {"url": "https://example.com/final"}
        elif request["cmd"] == "webview_wait_for_url":
            event = "on_webview_wait_for_url_response"
            data = {"url": "https://example.com/final"}
        elif request["cmd"] == "webview_wait_for_load_state":
            event = "on_webview_wait_for_load_state_response"
            data = {"state": "load", "url": "https://example.com/final"}
        else:
            event = "on_webview_evaluate_response"
            data = {"value": self._evaluate_value()}
        return json.dumps({"event": event, "data": data}, separators=(",", ":"))


class NavigationRaceNative(BrowserNative):
    def __init__(self) -> None:
        super().__init__()
        self.evaluation_count = 0

    def request(self, request_id: str, message: str, timeout: float | None) -> str:
        request = json.loads(message)
        if request["cmd"] != "webview_evaluate":
            return super().request(request_id, message, timeout)

        self.calls.append((request, timeout))
        self.evaluation_count += 1
        if self.evaluation_count == 1:
            return json.dumps(
                {
                    "event": "on_error",
                    "data": {
                        "code": "webview_context_destroyed",
                        "message": "document replaced",
                        "retryable": True,
                    },
                },
                separators=(",", ":"),
            )
        return json.dumps(
            {
                "event": "on_webview_evaluate_response",
                "data": {
                    "value": [{"url": "https://example.com/final", "content": True}]
                },
            },
            separators=(",", ":"),
        )


class WaitAllFramesNative(BrowserNative):
    """Answers successive probe evaluations from a scripted sequence.

    ``wait_for_function_all_frames`` polls the probe and sleeps between polls on
    the host, so every ``webview_evaluate`` it issues is a probe; each advances
    the sequence (the last entry repeats once exhausted).
    """

    def __init__(self, probe_results: list[Any]) -> None:
        super().__init__()
        self._probe_results = probe_results
        self.probe_calls = 0

    def request(self, request_id: str, message: str, timeout: float | None) -> str:
        request = json.loads(message)
        if request["cmd"] != "webview_evaluate":
            return super().request(request_id, message, timeout)

        self.calls.append((request, timeout))
        index = min(self.probe_calls, len(self._probe_results) - 1)
        value = self._probe_results[index]
        self.probe_calls += 1
        return json.dumps(
            {"event": "on_webview_evaluate_response", "data": {"value": value}},
            separators=(",", ":"),
        )


class BrowserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.native = BrowserNative()
        self.client = LythonClient(LythonTransport(native_module=self.native))
        self.page = self.client.page

    def last_call(self) -> tuple[dict[str, Any], float | None]:
        return self.native.calls[-1]

    def test_page_is_available_from_client_and_package(self) -> None:
        self.assertIsInstance(self.page, Page)
        self.assertIsInstance(lython.page, Page)
        self.assertIn("page", lython.__all__)
        self.assertIn("Page", lython.__all__)
        self.assertIn("Locator", lython.__all__)

    def test_goto_uses_navigation_protocol_and_returns_final_url(self) -> None:
        final_url = self.page.goto("https://example.com", timeout=2_500)

        request, native_timeout = self.last_call()
        self.assertEqual(final_url, "https://example.com/final")
        self.assertEqual(
            request,
            {
                "cmd": "webview_navigate",
                "data": {"url": "https://example.com", "timeout_ms": 2500.0},
            },
        )
        self.assertEqual(native_timeout, 3.5)

    def test_evaluate_preserves_omitted_argument(self) -> None:
        self.native.next_value = 3

        value = self.page.evaluate("() => 3")

        request, native_timeout = self.last_call()
        self.assertEqual(value, 3)
        self.assertEqual(
            request,
            {"cmd": "webview_evaluate", "data": {"expression": "() => 3"}},
        )
        self.assertIsNone(native_timeout)

    def test_evaluate_preserves_explicit_none_argument_and_disabled_timeout(self) -> None:
        self.page.evaluate("value => value", None, timeout=0)

        request, native_timeout = self.last_call()
        self.assertEqual(
            request["data"],
            {
                "expression": "value => value",
                "argument": None,
                "timeout_ms": 0.0,
            },
        )
        self.assertIsNone(native_timeout)

    def test_navigation_waits_use_lifecycle_protocol(self) -> None:
        self.page.wait_for_url("**/search**", timeout=2_500)
        request, native_timeout = self.last_call()
        self.assertEqual(
            request,
            {
                "cmd": "webview_wait_for_url",
                "data": {
                    "url": "**/search**",
                    "wait_until": "load",
                    "timeout_ms": 2500.0,
                },
            },
        )
        self.assertEqual(native_timeout, 3.5)

        self.page.wait_for_load_state()
        request, _ = self.last_call()
        self.assertEqual(
            request,
            {"cmd": "webview_wait_for_load_state", "data": {"state": "load"}},
        )

    def test_locator_actions_are_built_on_raw_evaluate(self) -> None:
        locator = self.page.locator(".submit")
        self.assertEqual(repr(locator), "Locator('.submit')")

        locator.click(timeout=1_000)
        request, native_timeout = self.last_call()
        self.assertEqual(request["cmd"], "webview_evaluate")
        self.assertEqual(
            request["data"]["argument"],
            {"selector": ".submit", "action": "click"},
        )
        self.assertIn("document.querySelector", request["data"]["expression"])
        self.assertEqual(request["data"]["timeout_ms"], 1000.0)
        self.assertTrue(request["data"]["wait_for_navigation"])
        self.assertEqual(native_timeout, 2.0)

        locator.click(no_wait_after=True)
        request, _ = self.last_call()
        self.assertNotIn("wait_for_navigation", request["data"])

        locator.press("Enter")
        request, _ = self.last_call()
        self.assertEqual(request["data"]["argument"]["action"], "press")
        self.assertEqual(request["data"]["argument"]["key"], "Enter")
        self.assertTrue(request["data"]["wait_for_navigation"])

        locator.fill("Send")
        request, _ = self.last_call()
        self.assertEqual(
            request["data"]["argument"],
            {"selector": ".submit", "action": "fill", "value": "Send"},
        )

    def test_locator_read_helpers_validate_and_return_values(self) -> None:
        locator = self.page.locator(".item")

        self.native.next_value = "Hello"
        self.assertEqual(locator.text_content(), "Hello")
        self.assertEqual(locator.inner_text(), "Hello")
        self.assertEqual(locator.inner_html(), "Hello")
        self.assertEqual(locator.input_value(), "Hello")
        self.assertEqual(locator.get_attribute("data-id"), "Hello")

        self.native.next_value = True
        self.assertTrue(locator.is_visible())
        self.native.next_value = 2
        self.assertEqual(locator.count(), 2)
        self.native.next_value = ["one", "two"]
        self.assertEqual(locator.all_text_contents(), ["one", "two"])

    def test_wait_for_selector_uses_page_side_wait_and_state(self) -> None:
        locator = self.page.wait_for_selector("#ready", state="attached", timeout=500)

        self.assertIsInstance(locator, Locator)
        request, _ = self.last_call()
        self.assertEqual(
            request["data"]["argument"],
            {"selector": "#ready", "action": "wait", "state": "attached"},
        )
        self.assertIn("window.setTimeout(check, 50)", request["data"]["expression"])

        self.assertIsNone(self.page.wait_for_selector("#gone", state="detached"))

    def test_wait_for_function_preserves_argument_and_polling(self) -> None:
        self.native.next_value = {"ready": True}

        result = self.page.wait_for_function(
            "value => value.ready && value",
            {"ready": True},
            polling=25,
            timeout=2_000,
        )

        self.assertEqual(result, {"ready": True})
        request, _ = self.last_call()
        argument = request["data"]["argument"]
        self.assertEqual(argument["expression"], "value => value.ready && value")
        self.assertTrue(argument["hasArgument"])
        self.assertEqual(argument["argument"], {"ready": True})
        self.assertEqual(argument["polling"], 25.0)

    def test_retryable_wait_survives_document_replacement(self) -> None:
        native = NavigationRaceNative()
        page = LythonClient(LythonTransport(native_module=native)).page

        self.assertTrue(page.wait_for_function("() => true", timeout=2_000))

        self.assertEqual(
            [request["cmd"] for request, _ in native.calls],
            [
                "webview_evaluate",
                "webview_wait_for_load_state",
                "webview_evaluate",
            ],
        )

    def test_wait_for_timeout_sleeps_on_the_host_without_a_webview_call(self) -> None:
        with mock.patch("lython.browser.time.sleep") as sleep:
            self.page.wait_for_timeout(250)

        sleep.assert_called_once_with(0.25)
        # No WebView round-trip: the wait must not broadcast a page-side timer.
        self.assertEqual(self.native.calls, [])

    def test_wait_for_timeout_zero_neither_sleeps_nor_calls_the_webview(self) -> None:
        with mock.patch("lython.browser.time.sleep") as sleep:
            self.page.wait_for_timeout(0)

        sleep.assert_not_called()
        self.assertEqual(self.native.calls, [])

    def test_page_content_and_title_validate_response_shapes(self) -> None:
        self.native.next_value = "<html></html>"
        self.assertEqual(self.page.content(), "<html></html>")
        self.native.next_value = "Example"
        self.assertEqual(self.page.title(), "Example")

        self.native.next_value = 7
        with self.assertRaises(LythonProtocolError):
            self.page.title()

    def test_evaluate_unwraps_the_top_frame_from_the_frame_array(self) -> None:
        self.native.next_frames = [
            {"url": "https://example.com/final", "content": {"title": "Top"}},
            {"url": "https://embed.example.com/", "content": {"title": "Embed"}},
        ]
        self.assertEqual(self.page.evaluate("() => x"), {"title": "Top"})

    def test_evaluate_reads_none_from_an_empty_frame_array(self) -> None:
        self.native.next_frames = []
        self.assertIsNone(self.page.evaluate("() => x"))

    def test_evaluate_raises_when_the_top_frame_errored(self) -> None:
        self.native.next_frames = [
            {
                "url": "https://example.com/final",
                "content": None,
                "error": {"name": "TypeError", "message": "boom"},
            }
        ]
        with self.assertRaises(lython.LythonHostError) as caught:
            self.page.evaluate("() => x")
        self.assertEqual(caught.exception.code, "webview_evaluation_error")
        self.assertEqual(str(caught.exception), "boom")

    def test_evaluate_all_frames_returns_a_result_per_frame(self) -> None:
        from lython import FrameResult

        self.native.next_frames = [
            {"url": "https://example.com/final", "content": "<html>top</html>"},
            {
                "url": "https://embed.example.com/",
                "content": None,
                "error": {"name": "SecurityError", "message": "blocked"},
            },
        ]
        frames = self.page.evaluate_all_frames("() => document.documentElement.outerHTML")

        request, _ = self.last_call()
        self.assertEqual(request["cmd"], "webview_evaluate")
        self.assertEqual(len(frames), 2)
        self.assertIsInstance(frames[0], FrameResult)
        self.assertEqual(frames[0].url, "https://example.com/final")
        self.assertEqual(frames[0].content, "<html>top</html>")
        self.assertIsNone(frames[0].error)
        self.assertEqual(frames[1].url, "https://embed.example.com/")
        self.assertIsNone(frames[1].content)
        assert frames[1].error is not None
        self.assertEqual(frames[1].error.name, "SecurityError")
        self.assertEqual(frames[1].error.message, "blocked")

    def test_frames_content_reads_outer_html_from_every_frame(self) -> None:
        self.native.next_frames = [
            {"url": "https://example.com/final", "content": "<html>top</html>"},
            {"url": "https://embed.example.com/", "content": "<html>embed</html>"},
        ]
        frames = self.page.frames_content()

        request, _ = self.last_call()
        self.assertIn("document.documentElement.outerHTML", request["data"]["expression"])
        self.assertEqual(
            [frame.content for frame in frames],
            ["<html>top</html>", "<html>embed</html>"],
        )

    def test_evaluate_rejects_a_non_list_response_value(self) -> None:
        self.native.next_frames = {"not": "a list"}
        with self.assertRaises(LythonProtocolError):
            self.page.evaluate("() => x")

    def test_wait_for_function_all_frames_polls_until_a_frame_matches(self) -> None:
        native = WaitAllFramesNative(
            [
                [{"url": "https://example.com/top", "content": False}],
                [
                    {"url": "https://example.com/top", "content": False},
                    {"url": "https://embed.example.com/", "content": True},
                ],
            ]
        )
        page = LythonClient(LythonTransport(native_module=native)).page

        frames = page.wait_for_function_all_frames("() => !!x", polling_ms=1, timeout=5_000)

        self.assertEqual(native.probe_calls, 2)
        self.assertEqual(len(frames), 2)
        self.assertTrue(frames[1].content)
        self.assertEqual(frames[1].url, "https://embed.example.com/")

    def test_wait_for_function_all_frames_times_out_when_no_frame_matches(self) -> None:
        native = WaitAllFramesNative([[{"url": "https://example.com/top", "content": 0}]])
        page = LythonClient(LythonTransport(native_module=native)).page

        with self.assertRaises(lython.LythonTimeoutError):
            page.wait_for_function_all_frames("() => false", polling_ms=1, timeout=10)

    def test_invalid_browser_arguments_fail_before_transport(self) -> None:
        with self.assertRaises(TypeError):
            self.page.evaluate("")
        with self.assertRaises(TypeError):
            self.page.locator(" ")
        with self.assertRaises(ValueError):
            self.page.goto("https://example.com", timeout=float("inf"))
        with self.assertRaises(ValueError):
            self.page.locator("div").wait_for(state="ready")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            self.page.locator("input").fill(3)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            self.page.wait_for_load_state("networkidle")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            self.page.locator("button").click(no_wait_after="yes")  # type: ignore[arg-type]

        self.assertEqual(self.native.calls, [])


class AsyncBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_page_and_locator_operations(self) -> None:
        native = BrowserNative()
        page = LythonClient(LythonTransport(native_module=native)).page

        self.assertEqual(
            await page.goto_async("https://example.com"),
            "https://example.com/final",
        )
        native.next_value = {"ok": True}
        self.assertEqual(
            await page.evaluate_async("value => value", {"ok": True}),
            {"ok": True},
        )
        native.next_value = None
        await page.locator("button").click_async()
        self.assertEqual(native.calls[-1][0]["data"]["argument"]["action"], "click")

        native.next_frames = [
            {"url": "https://example.com/final", "content": "<html>top</html>"},
            {"url": "https://embed.example.com/", "content": "<html>embed</html>"},
        ]
        frames = await page.evaluate_all_frames_async(
            "() => document.documentElement.outerHTML"
        )
        self.assertEqual(
            [(frame.url, frame.content) for frame in frames],
            [
                ("https://example.com/final", "<html>top</html>"),
                ("https://embed.example.com/", "<html>embed</html>"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
