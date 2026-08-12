from __future__ import annotations

import json
import unittest
from typing import Any

import lython
from lython import LythonClient, LythonProtocolError, LythonTransport, Locator, Page


class BrowserNative:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], float | None]] = []
        self.next_value: Any = None

    def send(self, message: str) -> None:
        raise AssertionError(f"unexpected notification: {message}")

    def request(self, request_id: str, message: str, timeout: float | None) -> str:
        request = json.loads(message)
        self.calls.append((request, timeout))
        if request["cmd"] == "webview_navigate":
            event = "on_webview_navigate_response"
            data = {"url": "https://example.com/final"}
        else:
            event = "on_webview_evaluate_response"
            data = {"value": self.next_value}
        return json.dumps({"event": event, "data": data}, separators=(",", ":"))


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
        self.assertEqual(native_timeout, 2.0)

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

    def test_wait_for_timeout_runs_inside_the_page(self) -> None:
        self.page.wait_for_timeout(250)

        request, native_timeout = self.last_call()
        self.assertEqual(request["data"]["argument"], 250.0)
        self.assertIn("setTimeout", request["data"]["expression"])
        self.assertEqual(request["data"]["timeout_ms"], 1250.0)
        self.assertEqual(native_timeout, 2.25)

    def test_page_content_and_title_validate_response_shapes(self) -> None:
        self.native.next_value = "<html></html>"
        self.assertEqual(self.page.content(), "<html></html>")
        self.native.next_value = "Example"
        self.assertEqual(self.page.title(), "Example")

        self.native.next_value = 7
        with self.assertRaises(LythonProtocolError):
            self.page.title()

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


if __name__ == "__main__":
    unittest.main()
