from __future__ import annotations

import unittest
from unittest.mock import patch

import lython_api_diagnostics as diagnostics


class DiagnosticsReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        diagnostics.RESULTS.clear()
        diagnostics.NOTIFICATIONS_ENABLED = True

    def test_run_api_prints_result_and_notifies_progress(self) -> None:
        with (
            patch.object(diagnostics.lython, "notify") as notify,
            self.assertLogs(diagnostics.LOG, level="INFO") as logs,
        ):
            value = diagnostics.run_api(
                "characters.list",
                lambda: [{"id": "aria"}],
                purpose="List characters.",
            )

        self.assertEqual(value, [{"id": "aria"}])
        notify.assert_called_once_with(
            f"{diagnostics.MARKER} Running 1/{diagnostics.EXPECTED_API_COUNT}: "
            "characters.list"
        )
        output = "\n".join(logs.output)
        self.assertIn("RUN", output)
        self.assertIn("PASS", output)
        self.assertIn('result=[\n  {\n    "id": "aria"', output)

    def test_notify_failure_is_reported_once_and_diagnostics_continue(self) -> None:
        with (
            patch.object(
                diagnostics.lython,
                "notify",
                side_effect=RuntimeError("host unavailable"),
            ) as notify,
            self.assertLogs(diagnostics.LOG, level="WARNING") as logs,
        ):
            first = diagnostics.run_api("first", lambda: 1, purpose="First check.")
            second = diagnostics.run_api("second", lambda: 2, purpose="Second check.")

        self.assertEqual((first, second), (1, 2))
        self.assertEqual(notify.call_count, 1)
        self.assertFalse(diagnostics.NOTIFICATIONS_ENABLED)
        self.assertIn("progress notifications disabled", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
