from __future__ import annotations

import unittest

from lython import (
    LythonProtocolError,
    decode_layla_event,
    decode_layla_request,
    encode_layla_request,
)


class ProtocolTests(unittest.TestCase):
    def test_request_round_trip_has_no_outer_envelope(self) -> None:
        encoded = encode_layla_request(
            {"cmd": "get_characters", "data": {"offset": 0, "limit": 10}}
        )

        self.assertEqual(
            encoded,
            '{"cmd":"get_characters","data":{"offset":0,"limit":10}}',
        )
        self.assertEqual(
            decode_layla_request(encoded),
            {"cmd": "get_characters", "data": {"offset": 0, "limit": 10}},
        )

    def test_response_event_decodes_directly(self) -> None:
        event = '{"event":"on_get_characters_response","data":[]}'

        self.assertEqual(
            decode_layla_event(event),
            {"event": "on_get_characters_response", "data": []},
        )

    def test_rejects_non_object_request(self) -> None:
        with self.assertRaises(LythonProtocolError):
            decode_layla_request("[]")

    def test_rejects_response_without_event(self) -> None:
        with self.assertRaises(LythonProtocolError):
            decode_layla_event('{"data":null}')


if __name__ == "__main__":
    unittest.main()
