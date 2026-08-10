from __future__ import annotations

import json
import unittest
from typing import Any

import lython
from lython import (
    LythonClient,
    LythonError,
    LythonTransport,
)


class RoutingNative:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.notifications: list[str] = []
        self.responses: dict[str, tuple[str, Any]] = {
            "get_characters": ("on_get_characters_response", [{"id": "aria"}]),
            "get_character_image": (
                "on_get_character_image_response",
                {"character_id": "aria", "image_data_base64": "data:image/png;base64,AA=="},
            ),
            "update_character": ("on_update_character_response", {"character_id": "aria-2"}),
            "get_sentiment": ("on_get_sentiment_response", {"sentiment_values": {"joy": 0.9}}),
            "get_image_generation_models": (
                "on_get_image_generation_models_response",
                [{"id": "sd", "name": "SD", "description": "Local"}],
            ),
            "generate_image": ("on_generate_image_response", {"image_data_base64": "data:image/png;base64,BB=="}),
            "send_message": ("on_message_end", {"msg": "<think>briefly</think>Hello"}),
            "get_inference_engines": ("on_get_inference_engines_response", {"engines": ["local"]}),
            "set_inference_engine": ("on_set_inference_engine_response", {"success": True, "engineName": "local"}),
            "get_chat_history": ("on_get_chat_history_response", {"session_id": "s1", "messages": [{"id": 1}]}),
            "get_chat_sessions": ("on_get_chat_sessions_response", {"character_id": "aria", "sessions": [{"session_id": "s1"}]}),
            "save_chat_message": ("on_save_chat_message_response", {"id": 1, "content": "saved"}),
            "scheduled_chat_message": ("on_scheduled_chat_message", {"id": 2, "message": "later"}),
            "get_scheduled_chat_messages": ("on_get_scheduled_chat_messages_response", {"scheduled_messages": [{"id": 2}]}),
            "cancel_scheduled_chat_message": ("on_cancel_scheduled_chat_message", {"id": 2, "success": True}),
            "get_memories": ("on_get_memories_response", {"character_id": "aria", "memories": [{"id": 3}]}),
            "get_top_memories": ("on_get_top_memories_response", {"character_id": "aria", "memories": [{"id": 4}]}),
            "create_or_update_memories": ("on_create_or_update_memories_response", {"character_id": "aria", "memories": [{"id": 5}]}),
            "get_persona": ("on_get_persona_response", {"character_id": None, "persona": {"name": "Alex", "description": "User"}}),
            "get_tts_voices": ("on_get_tts_voices_response", {"voices": [{"id": "v1"}]}),
            "generate_voice": ("on_finished_speaking", None),
            "generate_voice_to_file": ("on_generate_voice_to_file_response", {"success": True, "audio_data_base64": "data:audio/wav;base64,AA==", "filename": None}),
            "stop_speaking": ("on_finished_speaking", None),
            "save_file": ("on_save_file_response", {"filename": "a.txt", "success": True}),
            "read_file": ("on_read_file_response", {"filename": "a.txt", "content_base64": "data:text/plain;base64,QQ=="}),
            "get_execution_context": ("on_get_execution_context_response", {"app_version": "1", "character": None, "session_id": None}),
        }

    def send(self, message: str) -> None:
        self.notifications.append(message)

    def request(self, request_id: str, message: str, timeout: float | None) -> str:
        request = json.loads(message)
        self.calls.append(request)
        event, data = self.responses[request["cmd"]]
        return json.dumps({"event": event, "data": data}, separators=(",", ":"))


class ResourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.native = RoutingNative()
        self.client = LythonClient(LythonTransport(native_module=self.native))

    def test_all_one_shot_resource_paths(self) -> None:
        chat_message = {
            "id": 0,
            "role": "user",
            "content": "saved",
            "character_id": "aria",
            "session_id": "s1",
            "timestamp": 1,
        }
        scheduled = {"id": 0, "character_id": "aria", "session_id": None, "timestamp": 2, "message": "later"}
        memory = {"id": 0, "character_id": "aria", "session_id": "s1", "rawText": "raw", "timestamp": 1, "summary": None, "knowledgeGraphJSON": None}

        self.assertEqual(self.client.characters.list(), [{"id": "aria"}])
        self.assertTrue(self.client.characters.get_image("aria").startswith("data:image"))
        self.assertEqual(self.client.characters.update({"id": "aria", "data": {}}), "aria-2")
        self.assertEqual(self.client.classifier.get_sentiment("great"), {"joy": 0.9})
        self.assertEqual(self.client.images.get_image_generation_models()[0]["id"], "sd")
        self.assertTrue(self.client.images.generate_image("portrait").startswith("data:image"))

        completion = self.client.chat.completions.create(messages=[{"role": "user", "content": "Hi"}])
        self.assertEqual(completion["choices"][0]["message"]["content"], "Hello")
        self.assertEqual(completion["choices"][0]["message"]["reasoning"], "briefly")
        self.assertEqual(self.client.chat.get_inference_engines(), ["local"])
        self.assertTrue(self.client.chat.set_inference_engine("local")["success"])
        self.assertEqual(self.client.chat.get_chat_history("s1"), [{"id": 1}])
        self.assertEqual(self.client.chat.get_chat_sessions("aria")["sessions"][0]["session_id"], "s1")
        self.assertEqual(self.client.chat.save_chat_message(chat_message)["id"], 1)
        self.assertEqual(self.client.chat.schedule_chat_message(scheduled)["id"], 2)
        self.assertEqual(self.client.chat.get_scheduled_chat_messages(), [{"id": 2}])
        self.assertTrue(self.client.chat.cancel_scheduled_chat_message(2)["success"])

        self.assertEqual(self.client.memories.list("aria"), [{"id": 3}])
        self.assertEqual(self.client.memories.get_top_memories("aria"), [{"id": 4}])
        self.assertEqual(self.client.memories.create_or_update([memory]), [{"id": 5}])
        self.assertEqual(self.client.personas.get()["name"], "Alex")
        self.assertEqual(self.client.tts.get_voices(), [{"id": "v1"}])
        self.assertIsNone(self.client.tts.generate_voice(None, "hello"))
        self.assertTrue(self.client.tts.generate_voice_to_file(None, "hello")["success"])
        self.assertIsNone(self.client.tts.stop_speaking())
        self.assertTrue(self.client.utils.save_file("a.txt", "QQ==")["success"])
        self.assertTrue(self.client.utils.read_file("a.txt")["content_base64"].startswith("data:"))
        self.assertEqual(self.client.contextual.get_execution_context()["app_version"], "1")

        self.assertEqual(set(self.native.responses), {call["cmd"] for call in self.native.calls})

    def test_client_notify_sends_without_waiting_for_a_response(self) -> None:
        self.assertIsNone(self.client.notify("Import complete"))
        self.assertEqual(self.native.notifications, ["Import complete"])
        self.assertEqual(self.native.calls, [])

    def test_package_notify_uses_default_client(self) -> None:
        default_client = lython._client
        try:
            lython._client = self.client
            self.assertIsNone(lython.notify("Index refreshed"))
        finally:
            lython._client = default_client

        self.assertEqual(self.native.notifications, ["Index refreshed"])
        self.assertIn("notify", lython.__all__)

    def test_chat_normalizes_openai_image_parts_and_has_no_streaming(self) -> None:
        image = "data:image/png;base64,AA=="
        self.client.chat.completions.create(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "one"},
                            {"type": "text", "text": "two"},
                            {"type": "image_url", "image_url": {"url": image}},
                        ],
                    }
                ]
            }
        )
        sent = self.native.calls[-1]["data"][0]
        self.assertEqual(sent["content"], "one\ntwo")
        self.assertEqual(sent["image_base64"], image)

        with self.assertRaises(LythonError):
            self.client.chat.completions.create({"messages": [], "stream": True})
        with self.assertRaises(LythonError):
            self.client.chat.completions.create(
                messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.com/a.png"}}]}]
            )

    def test_optional_image_fields_are_omitted(self) -> None:
        self.client.images.generate_image("portrait")
        self.assertEqual(self.native.calls[-1]["data"], {"prompt": "portrait"})

    def test_typescript_method_aliases_are_available(self) -> None:
        self.assertEqual(self.client.characters.getImage("aria"), self.client.characters.get_image("aria"))
        self.assertEqual(self.client.chat.getInferenceEngines(), ["local"])


class AsyncResourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_counterparts_use_async_transport(self) -> None:
        native = RoutingNative()
        client = LythonClient(LythonTransport(native_module=native))
        self.assertEqual(await client.characters.list_async(), [{"id": "aria"}])
        completion = await client.chat.completions.create_async(messages=[{"role": "user", "content": "Hi"}])
        self.assertEqual(completion["choices"][0]["message"]["content"], "Hello")


if __name__ == "__main__":
    unittest.main()
