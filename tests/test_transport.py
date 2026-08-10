from __future__ import annotations

import asyncio
import json
import unittest

from lython import (
    LythonHostError,
    LythonProtocolError,
    LythonTimeoutError,
    LythonTransport,
    OneShotRequestTemplate,
)


class FakeNative:
    def __init__(self, response: str | BaseException) -> None:
        self.response = response
        self.calls: list[tuple[str, str, float | None]] = []

    def request(self, request_id: str, message: str, timeout: float | None) -> str:
        self.calls.append((request_id, message, timeout))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class TransportTests(unittest.TestCase):
    def test_sends_typescript_message_directly_and_returns_event_data(self) -> None:
        native = FakeNative(
            '{"event":"on_get_characters_response","data":[{"id":"1"}]}'
        )
        transport = LythonTransport(
            native_module=native,
            default_timeout=42,
            request_id_factory=lambda: "request-1",
        )

        response = transport.request(
            {"cmd": "get_characters", "data": {"offset": 0, "limit": 10}},
            "on_get_characters_response",
        )

        self.assertEqual(response.request_id, "request-1")
        self.assertEqual(response.data, [{"id": "1"}])
        self.assertEqual(native.calls[0][0], "request-1")
        self.assertEqual(native.calls[0][2], 42.0)
        self.assertEqual(
            json.loads(native.calls[0][1]),
            {"cmd": "get_characters", "data": {"offset": 0, "limit": 10}},
        )
        self.assertNotIn("protocol", json.loads(native.calls[0][1]))

    def test_request_json_preserves_caller_serialization(self) -> None:
        native = FakeNative('{"event":"done","data":null}')
        transport = LythonTransport(native_module=native)
        message = '{ "cmd": "example", "data": null }'

        transport.request_json(message, "done")

        self.assertEqual(native.calls[0][1], message)

    def test_on_error_event_is_raised_as_host_error(self) -> None:
        native = FakeNative(
            '{"event":"on_error","data":{"message":"Model unavailable"}}'
        )
        transport = LythonTransport(native_module=native)

        with self.assertRaises(LythonHostError) as caught:
            transport.request({"cmd": "send_message", "data": []}, "on_message_end")

        self.assertEqual(str(caught.exception), "Model unavailable")
        self.assertEqual(caught.exception.code, "layla_api_error")

    def test_unexpected_terminal_event_is_protocol_error(self) -> None:
        native = FakeNative('{"event":"wrong_event","data":null}')
        transport = LythonTransport(native_module=native)

        with self.assertRaises(LythonProtocolError):
            transport.request({"cmd": "example", "data": None}, "expected_event")

    def test_native_timeout_is_translated(self) -> None:
        transport = LythonTransport(native_module=FakeNative(TimeoutError("late")))

        with self.assertRaises(LythonTimeoutError):
            transport.request({"cmd": "example", "data": None}, "done")

    def test_template_builds_existing_command_shape(self) -> None:
        native = FakeNative('{"event":"example_response","data":{"ok":true}}')
        transport = LythonTransport(native_module=native)
        template = OneShotRequestTemplate("example", "example_response")

        data = template.send(transport, {"value": 3})

        self.assertEqual(data, {"ok": True})
        message = json.loads(native.calls[0][1])
        self.assertEqual(message, {"cmd": "example", "data": {"value": 3}})


class AsyncTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_template_uses_one_shot_transport(self) -> None:
        native = FakeNative('{"event":"example_response","data":7}')
        transport = LythonTransport(native_module=native)
        template = OneShotRequestTemplate("example", "example_response")

        result = await template.send_async(transport, None)

        self.assertEqual(result, 7)
        self.assertEqual(len(native.calls), 1)

    async def test_async_native_call_runs_off_event_loop_thread(self) -> None:
        loop_thread = None
        native_thread = None

        class ThreadCapturingNative(FakeNative):
            def request(self, request_id, message, timeout):
                nonlocal native_thread
                import threading

                native_thread = threading.get_ident()
                return super().request(request_id, message, timeout)

        import threading

        loop_thread = threading.get_ident()
        native = ThreadCapturingNative('{"event":"done","data":null}')
        transport = LythonTransport(native_module=native)

        await transport.request_async({"cmd": "example", "data": None}, "done")

        self.assertNotEqual(native_thread, loop_thread)


if __name__ == "__main__":
    unittest.main()
