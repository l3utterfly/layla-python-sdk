from __future__ import annotations

import unittest
from unittest.mock import patch

import lython_api_diagnostics as diagnostics


class DiagnosticsReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        diagnostics.RESULTS.clear()
        diagnostics.NOTIFICATIONS_ENABLED = True

    def test_run_api_notifies_success_after_the_call(self) -> None:
        events = []
        with patch.object(
            diagnostics.lython,
            "notify",
            side_effect=lambda message: events.append(("notify", message)),
        ) as notify:
            value = diagnostics.run_api(
                "characters.list",
                lambda: events.append(("call", None)) or [{"id": "aria"}],
                purpose="List characters.",
            )

        self.assertEqual(value, [{"id": "aria"}])
        notify.assert_called_once_with(
            f"{diagnostics.MARKER} PASS 1/{diagnostics.EXPECTED_API_COUNT}: "
            "characters.list"
        )
        self.assertEqual([event[0] for event in events], ["call", "notify"])

    def test_run_api_failure_is_logged_and_not_notified(self) -> None:
        with (
            patch.object(diagnostics.lython, "notify") as notify,
            self.assertLogs(diagnostics.LOG, level="ERROR") as logs,
        ):
            value = diagnostics.run_api(
                "characters.list",
                lambda: (_ for _ in ()).throw(RuntimeError("broken")),
                purpose="List characters.",
            )

        self.assertIs(value, diagnostics.MISSING)
        notify.assert_not_called()
        self.assertIn("FAIL", "\n".join(logs.output))

    def test_notify_failure_is_reported_once_and_diagnostics_continue(self) -> None:
        with (
            patch.object(
                diagnostics.lython,
                "notify",
                side_effect=RuntimeError("host unavailable"),
            ) as notify,
            self.assertLogs(diagnostics.LOG, level="ERROR") as logs,
        ):
            first = diagnostics.run_api("first", lambda: 1, purpose="First check.")
            second = diagnostics.run_api("second", lambda: 2, purpose="Second check.")

        self.assertEqual((first, second), (1, 2))
        self.assertEqual(notify.call_count, 1)
        self.assertFalse(diagnostics.NOTIFICATIONS_ENABLED)
        self.assertIn("success notifications disabled", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
