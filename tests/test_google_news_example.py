from __future__ import annotations

import argparse
import importlib.util
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


EXAMPLE_PATH = Path(__file__).parents[1] / "examples" / "google_news_search.py"
SPEC = importlib.util.spec_from_file_location("google_news_search", EXAMPLE_PATH)
assert SPEC is not None and SPEC.loader is not None
google_news_search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(google_news_search)


class GoogleNewsExampleTests(unittest.TestCase):
    def test_run_step_sends_progress_through_notify(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(google_news_search.lython, "notify") as notify,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            result = google_news_search._run_step(
                object(),
                "inspect results",
                lambda: {"count": 2},
                selector=".result",
                function="inspectResults",
            )

        self.assertEqual(result, {"count": 2})
        self.assertEqual(notify.call_count, 2)
        self.assertIn("START inspect results", notify.call_args_list[0].args[0])
        self.assertIn("OK inspect results", notify.call_args_list[1].args[0])
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_main_prints_results_and_returns_normally(self) -> None:
        args = argparse.Namespace(query="Layla AI", limit=2)
        results = [
            {
                "title": "Layla ships browser automation",
                "details": "Example News · 1 hour ago",
                "url": "https://example.com/layla-browser-automation",
            },
            {
                "title": "A second result",
                "details": "",
                "url": "https://example.com/second-result",
            },
        ]

        output = io.StringIO()
        with (
            patch.object(google_news_search, "parse_args", return_value=args),
            patch.object(
                google_news_search,
                "search_google_news",
                return_value=results,
            ),
            redirect_stdout(output),
        ):
            return_value = google_news_search.main()

        self.assertIsNone(return_value)
        self.assertEqual(
            output.getvalue(),
            'Google News results for "Layla AI":\n'
            "\n1. Layla ships browser automation\n"
            "   Example News · 1 hour ago\n"
            "   https://example.com/layla-browser-automation\n"
            "\n2. A second result\n"
            "   https://example.com/second-result\n",
        )

    def test_main_prints_failure_to_stderr_instead_of_system_exit(self) -> None:
        args = argparse.Namespace(query="Layla AI", limit=2)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(google_news_search, "parse_args", return_value=args),
            patch.object(
                google_news_search,
                "search_google_news",
                side_effect=ValueError("limit must be positive"),
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            return_value = google_news_search.main()

        self.assertIsNone(return_value)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "Search failed: limit must be positive\n")


if __name__ == "__main__":
    unittest.main()
