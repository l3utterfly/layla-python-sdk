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

    def test_reference_edit_pins_qwen_and_uses_generated_source_as_a_reference(self) -> None:
        source = "data:image/png;base64,YQ=="
        models = [{"id": "other"}, {"id": diagnostics.REFERENCE_IMAGE_MODEL_ID}]
        with patch.object(diagnostics.lython.images, "generate_image", return_value=source) as generate:
            self.assertEqual(diagnostics.diagnostic_reference_edit(models, source), source)
        self.assertEqual(generate.call_args.kwargs, {
            "model_id": "qwen-image-2.1-turbo-htp", "reference_images": [source],
            "timeout": diagnostics.GENERATION_TIMEOUT_SECONDS,
        })

    def test_reference_edit_skips_a_missing_model_or_failed_source_generation(self) -> None:
        with patch.object(diagnostics.lython.images, "generate_image") as generate:
            with self.assertRaises(diagnostics.SkipAPI):
                diagnostics.diagnostic_reference_edit([], "data:image/png;base64,YQ==")
            with self.assertRaises(diagnostics.SkipAPI):
                diagnostics.diagnostic_reference_edit([{"id": diagnostics.REFERENCE_IMAGE_MODEL_ID}], diagnostics.MISSING)
        generate.assert_not_called()

    def test_wan_diagnostic_pins_model_and_uses_explicit_fps_and_frames(self) -> None:
        source = "data:image/png;base64,YQ=="
        models = [{"id": diagnostics.WAN_MODEL_ID, "downloaded": True}]
        with patch.object(diagnostics.lython.nightmare_mobile, "generate_video", return_value={"seed": "42"}) as generate:
            self.assertEqual(diagnostics.diagnostic_wan_video(models, source), {"seed": "42"})
        self.assertEqual(generate.call_args.args[0], "wan22_ti2v_turbo")
        self.assertEqual(generate.call_args.kwargs, {
            "width": 512, "height": 320, "frames": 25, "fps": 24, "seed": 42,
            "image_data_base64": source, "timeout": diagnostics.VIDEO_GENERATION_TIMEOUT_SECONDS,
        })

    def test_wan_diagnostic_skips_an_undownloaded_model(self) -> None:
        with patch.object(diagnostics.lython.nightmare_mobile, "generate_video") as generate:
            with self.assertRaises(diagnostics.SkipAPI):
                diagnostics.diagnostic_wan_video([{"id": diagnostics.WAN_MODEL_ID, "downloaded": False}], diagnostics.MISSING)
        generate.assert_not_called()

    def test_wan_terminal_validator_checks_mp4_seed_and_metadata(self) -> None:
        valid = {"model_id": diagnostics.WAN_MODEL_ID, "video_data_base64": "data:video/mp4;base64,bXA0",
            "seed": "42", "width": 512, "height": 320, "frame_count": 25, "fps": 24, "duration_ms": 1042}
        diagnostics.require_wan_video(valid)
        for field, value in [("seed", 42), ("frame_count", 0), ("video_data_base64", "https://example.com/video.mp4")]:
            with self.subTest(field=field), self.assertRaises(diagnostics.APIReportedFailure):
                diagnostics.require_wan_video({**valid, field: value})

    def test_main_registers_all_media_checks_and_matches_the_report_count(self) -> None:
        def record_without_running(name, call, *, purpose, validate=None):
            diagnostics.RESULTS.append(diagnostics.TestResult(name, "SKIP", 0, "host not invoked"))
            return diagnostics.MISSING

        with patch.object(diagnostics, "run_api", side_effect=record_without_running), patch.object(diagnostics.LOG, "warning"):
            diagnostics.main()
        names = [result.name for result in diagnostics.RESULTS]
        self.assertEqual(len(names), diagnostics.EXPECTED_API_COUNT)
        self.assertIn("images.generate_image.reference_images", names)
        self.assertIn("nightmare_mobile.get_models", names)
        self.assertIn("nightmare_mobile.generate_video", names)


if __name__ == "__main__":
    unittest.main()
