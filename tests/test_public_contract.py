"""Public SDK wire contracts, with one terminal native response per call."""

from __future__ import annotations

import inspect
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import lython
from lython import LythonClient, LythonError, LythonHostError, LythonProtocolError, LythonTransport


class Native:
    def __init__(self, version="v7.6.2"):
        self.version = version
        self.calls = []
        self.timeouts = []
        self.response = None
        self.error = False
        self.reply = "<think>consider</think>Answer"

    def request(self, request_id, message, timeout=None):
        request = json.loads(message)
        self.calls.append(request)
        self.timeouts.append(timeout)
        command = request["cmd"]
        if command == "get_execution_context":
            return json.dumps({"event": "on_get_execution_context_response", "data": {"app_version": self.version}})
        if self.error:
            return json.dumps({"event": "on_error", "data": {"message": "host rejected", "code": "test_error"}})
        if command in ("send_message", "send_message_v2"):
            return json.dumps({"event": "on_message_end", "data": {"msg": self.reply}})
        event, data = self.response
        return json.dumps({"event": event, "data": data})


# name, arguments, keyword options, command, payload, response data, public result
CASES = [
    ("images.get_tag_dictionaries", (), {}, "image_gen_tag_get_dictionaries", None, [{"filename": "a.csv"}], [{"filename": "a.csv"}]),
    ("images.get_tags", ("a.csv",), {"offset": 0, "limit": 0, "category": 0}, "image_gen_tag_get_tags", {"dictionary_filename": "a.csv", "offset": 0, "limit": 0, "category": 0}, {"tags": [], "total": 4}, {"tags": [], "total": 4}),
    ("images.get_tag", ("a.csv", "cat"), {}, "image_gen_tag_get_tag", {"dictionary_filename": "a.csv", "english": "cat"}, {"tag": None}, None),
    ("images.upsert_tag", ("a.csv", {"english": "cat"}), {"replacing": "kitten"}, "image_gen_tag_upsert_tag", {"dictionary_filename": "a.csv", "tag": {"english": "cat"}, "replacing": "kitten"}, {"tag": {"english": "cat"}}, {"english": "cat"}),
    ("images.delete_tag", ("a.csv", "cat"), {}, "image_gen_tag_delete_tag", {"dictionary_filename": "a.csv", "english": "cat"}, {"deleted": False}, False),
    ("images.search_tags", ("a.csv", "cat"), {"mode": "prefix", "offset": 2, "limit": 0, "category": 0}, "image_gen_tag_search_tags", {"dictionary_filename": "a.csv", "query": "cat", "mode": "prefix", "offset": 2, "limit": 0, "category": 0}, {"tags": [], "total": 3}, {"tags": [], "total": 3}),
    ("images.suggest_tags", ("a.csv", "ca"), {"limit": 0}, "image_gen_tag_suggest_tags", {"dictionary_filename": "a.csv", "query": "ca", "limit": 0}, {"suggestions": []}, []),
    ("utils.schedule_notification", ({"message": "Hello", "timestamp": 123},), {}, "schedule_notification", {"message": "Hello", "timestamp": 123, "icon": None}, {"id": "n1"}, {"id": "n1"}),
    ("utils.get_scheduled_notifications", (), {}, "get_scheduled_notifications", None, {"scheduled_notifications": [{"id": "n1"}]}, [{"id": "n1"}]),
    ("utils.cancel_scheduled_notification", ("n1",), {}, "cancel_scheduled_notification", {"id": "n1"}, {"id": "n1"}, {"id": "n1"}),
    ("utils.list_dir", ("",), {}, "list_dir", {"path": ""}, [{"path": "a", "is_dir": True}], [{"path": "a", "is_dir": True}]),
    ("utils.delete_file_or_dir", ("a",), {}, "delete_file_or_dir", {"path": "a"}, None, None),
    ("contextual.send_out_of_band_message", ("Judge",), {"image_base64": "data:image/png;base64,AA==", "json_schema": {"type": "object"}}, "send_out_of_band_message", {"message": "Judge", "image_base64": "data:image/png;base64,AA==", "json_schema": {"type": "object"}}, {"msg": "yes"}, "yes"),
    ("neodragon.generate_video", ("data:image/png;base64,AA==", "Move"), {"seed": 0, "upscale": False, "fps": 1, "cinematic_prompt": False, "crop": {"x": 0, "y": 0, "width": 1, "height": 1}}, "neodragon_generate_video", {"image_data_base64": "data:image/png;base64,AA==", "prompt": "Move", "seed": 0, "upscale": False, "fps": 1, "cinematic_prompt": False, "crop": {"x": 0, "y": 0, "width": 1, "height": 1}}, {"video_data_base64": "data:video/mp4;base64,AA==", "seed": 0}, {"video_data_base64": "data:video/mp4;base64,AA==", "seed": 0}),
    ("acestep.get_models", (), {}, "ace_step_get_models", None, [{"modelId": "ace", "ready_for_use": True}], [{"modelId": "ace", "ready_for_use": True}]),
    ("acestep.generate_music", ("Music", "", 0), {"model_id": "ace"}, "ace_step_generate", {"prompt": "Music", "lyrics": "", "duration": 0, "model_id": "ace"}, {"audio_data_base64": "data:audio/wav;base64,AA=="}, "data:audio/wav;base64,AA=="),
    ("acestep.lm", ({"caption": "music", "unknown": 42},), {"model_id": "ace", "use_gpu": False}, "ace_step_lm", {"request": {"caption": "music", "unknown": 42}, "model_id": "ace", "use_gpu": False}, {"requests": [{"caption": "music", "audio_codes": "x"}]}, [{"caption": "music", "audio_codes": "x"}]),
    ("acestep.synth", ({"caption": "music", "seed": "18446744073709551615"},), {"model_id": "ace", "use_gpu": False, "use_flash_attn": False, "vae_tile_size": 0}, "ace_step_synth", {"request": {"caption": "music", "seed": "18446744073709551615"}, "model_id": "ace", "use_gpu": False, "use_flash_attn": False, "vae_tile_size": 0}, {"seed": "42", "request": {}}, {"seed": "42", "request": {}}),
    ("acestep.understand", ({"audio_base64": "audio"},), {"request": {"lm_temperature": 0}, "return_latents": False, "model_id": "ace", "use_gpu": False, "use_flash_attn": False, "vae_tile_size": 0}, "ace_step_understand", {"audio_data_base64": "audio", "request": {"lm_temperature": 0}, "return_latents": False, "model_id": "ace", "use_gpu": False, "use_flash_attn": False, "vae_tile_size": 0}, {"request": {"caption": "music"}}, {"request": {"caption": "music"}}),
    ("acestep.vae_encode", ("audio",), {"model_id": "ace", "request": {}, "use_gpu": False, "vae_tile_size": 0}, "ace_step_vae", {"audio_data_base64": "audio", "model_id": "ace", "request": {}, "use_gpu": False, "vae_tile_size": 0}, {"latents_base64": "latent"}, {"latents_base64": "latent"}),
    ("acestep.vae_decode", ("latent",), {"request": {"output_format": "mp3"}}, "ace_step_vae", {"latents_base64": "latent", "request": {"output_format": "mp3"}}, {"audio_data_base64": "audio"}, {"audio_data_base64": "audio"}),
    ("db.execute_sql", ("SELECT ?", [0, False, None, ""]), {}, "execute_sql", {"query": "SELECT ?", "params": [0, False, None, ""]}, {"rows": [{"n": 0}], "rowsAffected": 0, "insertId": 0}, {"rows": [{"n": 0}], "rowsAffected": 0, "insertId": 0}),
    ("cloud.login", (), {}, "layla_cloud_login", None, {"access_token": None}, None),
    ("stt.start_listening", (), {}, "stt_start_listening", None, None, None),
    ("stt.stop_listening", (), {}, "stt_stop_listening", None, None, None),
]


def terminal(command):
    return {"layla_cloud_login": "on_layla_cloud_login", "stt_start_listening": "on_stt_listening_started", "stt_stop_listening": "on_stt_listening_stopped"}.get(command, f"on_{command}_response")


def method(client, path, suffix=""):
    resource, name = path.split(".")
    return getattr(getattr(client, resource), name + suffix)


class PublicContractTests(unittest.TestCase):
    def test_new_one_shot_contracts(self):
        for path, args, kwargs, command, payload, response, expected in CASES:
            with self.subTest(method=path):
                native = Native()
                native.response = terminal(command), response
                client = LythonClient(LythonTransport(native_module=native))
                self.assertEqual(method(client, path)(*args, **kwargs, timeout=17), expected)
                self.assertEqual(native.calls, [{"cmd": command, "data": payload}])
                self.assertEqual(native.timeouts, [17])

    def test_host_errors_propagate_for_every_new_method(self):
        for path, args, kwargs, *_ in CASES:
            with self.subTest(method=path):
                native = Native()
                native.error = True
                client = LythonClient(LythonTransport(native_module=native))
                with self.assertRaises(LythonHostError) as caught:
                    method(client, path)(*args, **kwargs)
                self.assertEqual(caught.exception.code, "test_error")

    def test_default_options_and_latent_source(self):
        native = Native()
        client = LythonClient(LythonTransport(native_module=native))
        native.response = terminal("ace_step_understand"), {}
        client.acestep.understand({"latents_base64": "latent"})
        self.assertEqual(native.calls[-1]["data"], {"src_latents_base64": "latent"})
        for source in ({}, {"audio_base64": "a", "latents_base64": "l"}):
            with self.assertRaises(ValueError):
                client.acestep.understand(source)
        native.response = terminal("image_gen_tag_get_tags"), {}
        client.images.get_tags("a.csv")
        self.assertEqual(native.calls[-1]["data"], {"dictionary_filename": "a.csv", "offset": 0, "limit": 50})
        native.response = terminal("image_gen_tag_upsert_tag"), {"tag": {"english": "cat"}}
        client.images.upsert_tag("a.csv", {"english": "cat"})
        self.assertIsNone(native.calls[-1]["data"]["replacing"])
        native.response = terminal("execute_sql"), {}
        client.db.execute_sql("SELECT 1")
        self.assertEqual(native.calls[-1]["data"], {"query": "SELECT 1"})
        native.response = terminal("layla_cloud_login"), {"access_token": "token"}
        self.assertEqual(client.cloud.login(), "token")

    def test_exports_and_no_callback_apis(self):
        client = LythonClient()
        for name in ("acestep", "neodragon", "db", "cloud", "stt"):
            self.assertIn(name, lython.__all__)
            self.assertIsInstance(getattr(lython, name), type(getattr(client, name)))
        for path, *_ in CASES:
            call = method(client, path)
            signature = inspect.signature(call)
            self.assertNotIn("on_progress", signature.parameters)
            self.assertFalse(hasattr(getattr(client, path.split('.')[0]), "on"))
        self.assertFalse(hasattr(client.chat.completions, "stream"))
        self.assertFalse(hasattr(client, "background_audio"))


class ChatContractTests(unittest.TestCase):
    def test_already_structured_completions_are_preserved(self):
        from lython._chat import build_completion
        completion = {"object": "chat.completion", "choices": [{"message": {"role": "assistant", "content": "ok", "tool_calls": []}}], "usage": {"total_tokens": 4}}
        self.assertEqual(build_completion(completion, "layla"), completion)
        self.assertEqual(build_completion({"completion": completion}, "layla"), completion)
        with self.assertRaises(LythonProtocolError):
            build_completion({"msg": []}, "layla")

    def test_modern_body_preserves_tools_options_and_multiple_images(self):
        native = Native()
        client = LythonClient(LythonTransport(native_module=native))
        body = {"model": "custom", "temperature": 0, "response_format": {"type": "json_object"},
                "tools": [{"type": "function", "function": {"name": "lookup"}}],
                "tool_choice": "auto", "messages": [
                    {"role": "assistant", "tool_calls": [{"id": "c1"}]},
                    {"role": "tool", "tool_call_id": "c1", "content": "42"},
                    {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}] * 2}]}
        original = json.loads(json.dumps(body))
        result = client.chat.completions.create(body, timeout=8)
        self.assertEqual(native.calls[-1]["cmd"], "send_message_v2")
        self.assertEqual(json.loads(native.calls[-1]["data"]), {**body, "stream": True})
        self.assertEqual(body, original)
        self.assertEqual(result["choices"][0]["message"], {"role": "assistant", "content": "Answer", "reasoning": "consider", "refusal": None})
        self.assertIsNone(result["choices"][0]["logprobs"])
        self.assertEqual(result["model"], "custom")
        client.chat.completions.create(messages=[], tools=[], temperature=0)
        self.assertEqual(json.loads(native.calls[-1]["data"])["temperature"], 0)
        self.assertEqual(sum(c["cmd"] == "get_execution_context" for c in native.calls), 1)
        self.assertEqual(native.timeouts[:2], [2, 8])

    def test_legacy_fallback_maps_developer_and_ignores_unsupported_parts(self):
        for version in ("7.4.9", "invalid", None):
            with self.subTest(version=version):
                native = Native(version)
                client = LythonClient(LythonTransport(native_module=native))
                image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}
                with self.assertWarns(RuntimeWarning):
                    client.chat.completions.create(messages=[{"role": "developer", "content": "policy"}, {"role": "tool", "content": "42"}, {"role": "user", "content": [image, image, {"type": "file"}]}])
                self.assertEqual(native.calls[-1], {"cmd": "send_message", "data": [{"role": "system", "content": "policy"}, {"role": "user", "content": None, "image_base64": "data:image/png;base64,AA=="}]})

    def test_version_probe_error_or_timeout_falls_back(self):
        native = Native()
        client = LythonClient(LythonTransport(native_module=native))
        original = native.request
        def request(request_id, message, timeout=None):
            if json.loads(message)["cmd"] == "get_execution_context":
                raise TimeoutError()
            return original(request_id, message, timeout)
        with patch.object(native, "request", side_effect=request):
            client.chat.completions.create(messages=[])
        self.assertEqual(native.calls[-1]["cmd"], "send_message")

    def test_tool_call_results_and_truncated_arguments(self):
        native = Native()
        client = LythonClient(LythonTransport(native_module=native))
        native.reply = '<think>plan</think>Look. <tool_call>{"name":"lookup","arguments":{"q":"<think>literal</think>"},"tool_call_id":"c1"}</tool_call>\n<tool_call>{"name":"other","parameters":{"x":2},"id":"c2"}</tool_call>'
        choice = client.chat.completions.create(messages=[])["choices"][0]
        self.assertEqual(choice["message"]["content"], "Look. ")
        self.assertEqual(choice["message"]["reasoning"], "plan")
        self.assertEqual(choice["finish_reason"], "tool_calls")
        calls = choice["message"]["tool_calls"]
        self.assertEqual(calls[0]["id"], "c1")
        self.assertEqual(json.loads(calls[0]["function"]["arguments"]), {"q": "<think>literal</think>"})
        self.assertEqual(calls[1]["id"], "c2")
        native.reply = '<tool_call>{"name":"lookup","arguments":{"q":"par'
        choice = client.chat.completions.create(messages=[])["choices"][0]
        self.assertEqual(choice["message"]["content"], "")
        self.assertEqual(choice["message"]["tool_calls"][0]["function"]["arguments"], '{"q":"par')

    def test_streaming_rejected_before_any_host_request(self):
        native = Native()
        client = LythonClient(LythonTransport(native_module=native))
        with self.assertRaises(LythonError):
            client.chat.completions.create(messages=[], stream=True)
        self.assertEqual(native.calls, [])


class SerializationTests(unittest.TestCase):
    def test_chat_and_music_passes_never_overlap_their_shared_engine(self):
        for resource in ("chat", "acestep"):
            with self.subTest(resource=resource):
                first_entered = threading.Event()
                second_started = threading.Event()
                second_entered = threading.Event()
                release_first = threading.Event()
                calls = []
                class BlockingNative(Native):
                    def request(self, request_id, message, timeout=None):
                        command = json.loads(message)["cmd"]
                        if command == "get_execution_context":
                            return super().request(request_id, message, timeout)
                        calls.append(command)
                        if len(calls) == 1:
                            first_entered.set()
                            if not release_first.wait(2):
                                raise TimeoutError()
                        else:
                            second_entered.set()
                        if resource == "chat":
                            return json.dumps({"event": "on_message_end", "data": {"msg": "ok"}})
                        return json.dumps({"event": terminal(command), "data": {"requests": [], "seed": "1"}})
                client = LythonClient(LythonTransport(native_module=BlockingNative()))
                first_call = (lambda: client.chat.completions.create(messages=[])) if resource == "chat" else (lambda: client.acestep.lm({"caption": "x"}))
                def second_call():
                    second_started.set()
                    if resource == "chat":
                        return client.chat.completions.create(messages=[])
                    return client.acestep.synth({"caption": "x"})
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(first_call)
                    try:
                        self.assertTrue(first_entered.wait(1))
                        second = executor.submit(second_call)
                        self.assertTrue(second_started.wait(1))
                        self.assertFalse(second_entered.wait(0.05))
                    finally:
                        release_first.set()
                    first.result(timeout=1)
                    second.result(timeout=1)
                self.assertTrue(second_entered.is_set())


class AsyncPublicContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_new_async_wire_contract_and_timeout(self):
        for path, args, kwargs, command, payload, response, expected in CASES:
            with self.subTest(method=path):
                native = Native()
                native.response = terminal(command), response
                client = LythonClient(LythonTransport(native_module=native))
                self.assertEqual(await method(client, path, "_async")(*args, **kwargs, timeout=19), expected)
                self.assertEqual(native.calls, [{"cmd": command, "data": payload}])
                self.assertEqual(native.timeouts, [19])

    async def test_async_chat_has_the_same_modern_contract(self):
        native = Native()
        client = LythonClient(LythonTransport(native_module=native))
        result = await client.chat.completions.create_async(messages=[], tools=[], temperature=0)
        self.assertEqual(native.calls[-1]["cmd"], "send_message_v2")
        self.assertEqual(json.loads(native.calls[-1]["data"])["tools"], [])
        self.assertEqual(result["choices"][0]["message"]["content"], "Answer")

    async def test_async_host_errors(self):
        for path, args, kwargs, *_ in CASES:
            with self.subTest(method=path):
                native = Native()
                native.error = True
                client = LythonClient(LythonTransport(native_module=native))
                with self.assertRaises(LythonHostError):
                    await method(client, path, "_async")(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
