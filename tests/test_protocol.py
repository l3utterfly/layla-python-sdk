from __future__ import annotations

import json
import unittest

from lython import (
    LythonProtocolError,
    decode_request_envelope,
    decode_response_envelope,
    encode_error_response,
    encode_request_envelope,
    encode_success_response,
)


class ProtocolTests(unittest.TestCase):
    def test_request_envelope_preserves_inner_json_exactly(self) -> None:
        inner = '{ "cmd": "get_characters", "data": {"offset": 0, "limit": 10} }'

        encoded = encode_request_envelope(inner)

        self.assertEqual(decode_request_envelope(encoded), inner)
        self.assertEqual(json.loads(encoded)["message"], inner)

    def test_success_response_preserves_event_json(self) -> None:
        event = '{"event":"on_get_characters_response","data":[]}'

        response = decode_response_envelope(encode_success_response(event))

        self.assertTrue(response.ok)
        self.assertEqual(response.message, event)
        self.assertIsNone(response.error)

    def test_error_response_round_trip(self) -> None:
        encoded = encode_error_response(
            "host_error",
            "Unable to load characters",
            details={"source": "database"},
            retryable=True,
        )

        response = decode_response_envelope(encoded)

        self.assertFalse(response.ok)
        self.assertEqual(response.error.code, "host_error")
        self.assertEqual(response.error.message, "Unable to load characters")
        self.assertEqual(response.error.details, {"source": "database"})
        self.assertTrue(response.error.retryable)

    def test_rejects_wrong_protocol_version(self) -> None:
        raw = json.dumps(
            {
                "protocol": "layla.lython",
                "version": 2,
                "type": "response",
                "ok": True,
                "message": '{"event":"done","data":null}',
            }
        )

        with self.assertRaises(LythonProtocolError):
            decode_response_envelope(raw)

    def test_rejects_non_object_inner_message(self) -> None:
        with self.assertRaises(LythonProtocolError):
            encode_request_envelope("[]")


if __name__ == "__main__":
    unittest.main()

