"""High-level resources for Layla's one-shot embedded Python APIs."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import LythonError, LythonProtocolError
from .transport import LythonTransport

_BASE64_IMAGE_DATA_URL = re.compile(
    r"^data:image/(?:gif|jpe?g|png|webp);base64,", re.IGNORECASE
)
_THINK_TAG = re.compile(r"<think>|</think>")


def _mapping(value: Any, description: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LythonProtocolError(f"{description} must be an object")
    return value


def _field(value: Any, key: str, description: str) -> Any:
    data = _mapping(value, description)
    if key not in data:
        raise LythonProtocolError(f"{description} must contain {key!r}")
    return data[key]


def _list_field(value: Any, key: str, description: str) -> list[Any]:
    data = _mapping(value, description)
    result = data.get(key)
    return result if isinstance(result, list) else []


class _Resource:
    def __init__(self, transport: LythonTransport) -> None:
        self._transport = transport

    def _request(
        self,
        command: str,
        response_event: str,
        data: Any,
        *,
        timeout: float | None,
    ) -> Any:
        return self._transport.request(
            {"cmd": command, "data": data},
            response_event,
            timeout=timeout,
        ).data

    async def _request_async(
        self,
        command: str,
        response_event: str,
        data: Any,
        *,
        timeout: float | None,
    ) -> Any:
        response = await self._transport.request_async(
            {"cmd": command, "data": data},
            response_event,
            timeout=timeout,
        )
        return response.data


class Characters(_Resource):
    def list(
        self, offset: int = 0, range: int = 10, *, timeout: float | None = None
    ) -> list[Any]:
        data = self._request(
            "get_characters",
            "on_get_characters_response",
            {"offset": offset, "limit": range},
            timeout=timeout,
        )
        return data if isinstance(data, list) else []

    async def list_async(
        self, offset: int = 0, range: int = 10, *, timeout: float | None = None
    ) -> list[Any]:
        data = await self._request_async(
            "get_characters",
            "on_get_characters_response",
            {"offset": offset, "limit": range},
            timeout=timeout,
        )
        return data if isinstance(data, list) else []

    def get_image(
        self, character_id: str, *, timeout: float | None = None
    ) -> str | None:
        data = self._request(
            "get_character_image",
            "on_get_character_image_response",
            {"character_id": character_id},
            timeout=timeout,
        )
        return data.get("image_data_base64") if isinstance(data, Mapping) else None

    async def get_image_async(
        self, character_id: str, *, timeout: float | None = None
    ) -> str | None:
        data = await self._request_async(
            "get_character_image",
            "on_get_character_image_response",
            {"character_id": character_id},
            timeout=timeout,
        )
        return data.get("image_data_base64") if isinstance(data, Mapping) else None

    def update(
        self, character: Mapping[str, Any], *, timeout: float | None = None
    ) -> str:
        result = self._request(
            "update_character",
            "on_update_character_response",
            {
                "character_id": _field(character, "id", "character"),
                "character_data": _field(character, "data", "character"),
            },
            timeout=timeout,
        )
        value = _field(result, "character_id", "character update response")
        if not isinstance(value, str):
            raise LythonProtocolError("updated character id must be a string")
        return value

    async def update_async(
        self, character: Mapping[str, Any], *, timeout: float | None = None
    ) -> str:
        result = await self._request_async(
            "update_character",
            "on_update_character_response",
            {
                "character_id": _field(character, "id", "character"),
                "character_data": _field(character, "data", "character"),
            },
            timeout=timeout,
        )
        value = _field(result, "character_id", "character update response")
        if not isinstance(value, str):
            raise LythonProtocolError("updated character id must be a string")
        return value


class Classifier(_Resource):
    def get_sentiment(
        self, text: str, *, timeout: float | None = None
    ) -> Mapping[str, Any]:
        result = self._request(
            "get_sentiment",
            "on_get_sentiment_response",
            {"text": text},
            timeout=timeout,
        )
        return _mapping(
            _field(result, "sentiment_values", "sentiment response"),
            "sentiment values",
        )

    async def get_sentiment_async(
        self, text: str, *, timeout: float | None = None
    ) -> Mapping[str, Any]:
        result = await self._request_async(
            "get_sentiment",
            "on_get_sentiment_response",
            {"text": text},
            timeout=timeout,
        )
        return _mapping(
            _field(result, "sentiment_values", "sentiment response"),
            "sentiment values",
        )


class Images(_Resource):
    def get_image_generation_models(
        self, *, timeout: float | None = None
    ) -> list[Any]:
        result = self._request(
            "get_image_generation_models",
            "on_get_image_generation_models_response",
            None,
            timeout=timeout,
        )
        return result if isinstance(result, list) else []

    async def get_image_generation_models_async(
        self, *, timeout: float | None = None
    ) -> list[Any]:
        result = await self._request_async(
            "get_image_generation_models",
            "on_get_image_generation_models_response",
            None,
            timeout=timeout,
        )
        return result if isinstance(result, list) else []

    def generate_image(
        self,
        prompt: str,
        img2img_base64: str | None = None,
        model_id: str | None = None,
        *,
        timeout: float | None = None,
    ) -> str | None:
        payload: dict[str, Any] = {"prompt": prompt}
        if img2img_base64 is not None:
            payload["img2img_base64"] = img2img_base64
        if model_id is not None:
            payload["model_id"] = model_id
        result = self._request(
            "generate_image",
            "on_generate_image_response",
            payload,
            timeout=timeout,
        )
        return result.get("image_data_base64") if isinstance(result, Mapping) else None

    async def generate_image_async(
        self,
        prompt: str,
        img2img_base64: str | None = None,
        model_id: str | None = None,
        *,
        timeout: float | None = None,
    ) -> str | None:
        payload: dict[str, Any] = {"prompt": prompt}
        if img2img_base64 is not None:
            payload["img2img_base64"] = img2img_base64
        if model_id is not None:
            payload["model_id"] = model_id
        result = await self._request_async(
            "generate_image",
            "on_generate_image_response",
            payload,
            timeout=timeout,
        )
        return result.get("image_data_base64") if isinstance(result, Mapping) else None


def _normalize_chat_message(message: Mapping[str, Any]) -> dict[str, Any]:
    role = _field(message, "role", "chat message")
    content = _field(message, "content", "chat message")
    normalized: dict[str, Any] = {"role": role}

    if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
        normalized["content"] = content
    else:
        text_parts: list[str] = []
        images: list[str] = []
        for part in content:
            part_data = _mapping(part, "chat content part")
            part_type = part_data.get("type")
            if part_type == "text":
                text = part_data.get("text")
                if not isinstance(text, str):
                    raise LythonError("chat text content parts must contain a string 'text'")
                text_parts.append(text)
            elif part_type == "image_url":
                image = _mapping(part_data.get("image_url"), "image_url content")
                url = image.get("url")
                if not isinstance(url, str) or not _BASE64_IMAGE_DATA_URL.match(url):
                    raise LythonError(
                        "Layla image inputs must use a base64 data URL for a PNG, "
                        "JPEG, GIF, or WEBP image"
                    )
                images.append(url)
            else:
                raise LythonError(f"unsupported chat content part: {part_type!r}")

        if len(images) > 1:
            raise LythonError(
                "Layla supports at most one image_url content part per chat message"
            )
        normalized["content"] = "\n".join(text_parts) if text_parts else None
        if images:
            normalized["image_base64"] = images[0]

    if "name" in message:
        normalized["name"] = message["name"]
    return normalized


def _split_reasoning(raw: str) -> tuple[str, str]:
    content: list[str] = []
    reasoning: list[str] = []
    in_reasoning = False
    start = 0
    for match in _THINK_TAG.finditer(raw):
        (reasoning if in_reasoning else content).append(raw[start : match.start()])
        in_reasoning = match.group() == "<think>"
        start = match.end()
    (reasoning if in_reasoning else content).append(raw[start:])
    return "".join(content), "".join(reasoning)


def _build_chat_completion(data: Any, model: str) -> dict[str, Any]:
    if isinstance(data, Mapping):
        direct = data.get("completion", data)
        if isinstance(direct, Mapping) and direct.get("object") == "chat.completion":
            return dict(direct)
        raw_content = data.get("msg", data.get("content", ""))
        supplied_reasoning = data.get("reasoning")
    elif isinstance(data, str):
        raw_content = data
        supplied_reasoning = None
    elif data is None:
        raw_content = ""
        supplied_reasoning = None
    else:
        raise LythonProtocolError("chat completion response data has an invalid shape")

    if not isinstance(raw_content, str):
        raise LythonProtocolError("chat completion content must be a string")
    content, tagged_reasoning = _split_reasoning(raw_content)
    reasoning = supplied_reasoning if isinstance(supplied_reasoning, str) else tagged_reasoning
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning"] = reasoning

    now = time.time()
    return {
        "id": f"chatcmpl-layla-{int(now * 1000)}-{uuid.uuid4().hex[:6]}",
        "object": "chat.completion",
        "created": int(now),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "stop",
            }
        ],
    }


class Completions(_Resource):
    def create(
        self,
        body: Mapping[str, Any] | None = None,
        *,
        messages: Sequence[Mapping[str, Any]] | None = None,
        model: str = "layla",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if body is not None:
            if messages is not None:
                raise TypeError("pass either body or messages, not both")
            messages = _field(body, "messages", "chat completion body")
            if body.get("model") is not None:
                model = body["model"]
            if body.get("stream"):
                raise LythonError("streaming chat completions are not available in lython")
        if messages is None:
            raise TypeError("messages is required")
        if not isinstance(model, str):
            raise TypeError("model must be a string")
        normalized = [_normalize_chat_message(message) for message in messages]
        data = self._request(
            "send_message", "on_message_end", normalized, timeout=timeout
        )
        return _build_chat_completion(data, model)

    async def create_async(
        self,
        body: Mapping[str, Any] | None = None,
        *,
        messages: Sequence[Mapping[str, Any]] | None = None,
        model: str = "layla",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if body is not None:
            if messages is not None:
                raise TypeError("pass either body or messages, not both")
            messages = _field(body, "messages", "chat completion body")
            if body.get("model") is not None:
                model = body["model"]
            if body.get("stream"):
                raise LythonError("streaming chat completions are not available in lython")
        if messages is None:
            raise TypeError("messages is required")
        if not isinstance(model, str):
            raise TypeError("model must be a string")
        normalized = [_normalize_chat_message(message) for message in messages]
        data = await self._request_async(
            "send_message", "on_message_end", normalized, timeout=timeout
        )
        return _build_chat_completion(data, model)


class Chat(_Resource):
    def __init__(self, transport: LythonTransport) -> None:
        super().__init__(transport)
        self.completions = Completions(transport)

    def get_inference_engines(self, *, timeout: float | None = None) -> list[str]:
        data = self._request(
            "get_inference_engines",
            "on_get_inference_engines_response",
            None,
            timeout=timeout,
        )
        return _list_field(data, "engines", "inference engines response")

    async def get_inference_engines_async(
        self, *, timeout: float | None = None
    ) -> list[str]:
        data = await self._request_async(
            "get_inference_engines",
            "on_get_inference_engines_response",
            None,
            timeout=timeout,
        )
        return _list_field(data, "engines", "inference engines response")

    def set_inference_engine(
        self, engine_name: str | None, *, timeout: float | None = None
    ) -> Mapping[str, Any]:
        return _mapping(
            self._request(
                "set_inference_engine",
                "on_set_inference_engine_response",
                {"engineName": engine_name},
                timeout=timeout,
            ),
            "set inference engine response",
        )

    async def set_inference_engine_async(
        self, engine_name: str | None, *, timeout: float | None = None
    ) -> Mapping[str, Any]:
        return _mapping(
            await self._request_async(
                "set_inference_engine",
                "on_set_inference_engine_response",
                {"engineName": engine_name},
                timeout=timeout,
            ),
            "set inference engine response",
        )

    def get_chat_history(
        self,
        session_id: str,
        offset: int = 0,
        range: int = 10,
        *,
        timeout: float | None = None,
    ) -> list[Any]:
        data = self._request(
            "get_chat_history",
            "on_get_chat_history_response",
            {"session_id": session_id, "offset": offset, "limit": range},
            timeout=timeout,
        )
        return _list_field(data, "messages", "chat history response")

    def get_chat_sessions(
        self,
        character_id: str,
        offset: int = 0,
        range: int = 10,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        return _mapping(
            self._request(
                "get_chat_sessions",
                "on_get_chat_sessions_response",
                {"character_id": character_id, "offset": offset, "limit": range},
                timeout=timeout,
            ),
            "chat sessions response",
        )

    def save_chat_message(
        self, message: Mapping[str, Any], *, timeout: float | None = None
    ) -> Mapping[str, Any]:
        return _mapping(
            self._request(
                "save_chat_message",
                "on_save_chat_message_response",
                dict(message),
                timeout=timeout,
            ),
            "saved chat message",
        )

    def schedule_chat_message(
        self, message: Mapping[str, Any], *, timeout: float | None = None
    ) -> Mapping[str, Any]:
        return _mapping(
            self._request(
                "scheduled_chat_message",
                "on_scheduled_chat_message",
                dict(message),
                timeout=timeout,
            ),
            "scheduled chat message",
        )

    def get_scheduled_chat_messages(
        self, *, timeout: float | None = None
    ) -> list[Any]:
        data = self._request(
            "get_scheduled_chat_messages",
            "on_get_scheduled_chat_messages_response",
            None,
            timeout=timeout,
        )
        return _list_field(data, "scheduled_messages", "scheduled messages response")

    def cancel_scheduled_chat_message(
        self, id: int, *, timeout: float | None = None
    ) -> Mapping[str, Any]:
        return _mapping(
            self._request(
                "cancel_scheduled_chat_message",
                "on_cancel_scheduled_chat_message",
                {"id": id},
                timeout=timeout,
            ),
            "cancel scheduled message response",
        )

    async def get_chat_history_async(self, session_id: str, offset: int = 0, range: int = 10, *, timeout: float | None = None) -> list[Any]:
        data = await self._request_async("get_chat_history", "on_get_chat_history_response", {"session_id": session_id, "offset": offset, "limit": range}, timeout=timeout)
        return _list_field(data, "messages", "chat history response")

    async def get_chat_sessions_async(self, character_id: str, offset: int = 0, range: int = 10, *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(await self._request_async("get_chat_sessions", "on_get_chat_sessions_response", {"character_id": character_id, "offset": offset, "limit": range}, timeout=timeout), "chat sessions response")

    async def save_chat_message_async(self, message: Mapping[str, Any], *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(await self._request_async("save_chat_message", "on_save_chat_message_response", dict(message), timeout=timeout), "saved chat message")

    async def schedule_chat_message_async(self, message: Mapping[str, Any], *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(await self._request_async("scheduled_chat_message", "on_scheduled_chat_message", dict(message), timeout=timeout), "scheduled chat message")

    async def get_scheduled_chat_messages_async(self, *, timeout: float | None = None) -> list[Any]:
        data = await self._request_async("get_scheduled_chat_messages", "on_get_scheduled_chat_messages_response", None, timeout=timeout)
        return _list_field(data, "scheduled_messages", "scheduled messages response")

    async def cancel_scheduled_chat_message_async(self, id: int, *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(await self._request_async("cancel_scheduled_chat_message", "on_cancel_scheduled_chat_message", {"id": id}, timeout=timeout), "cancel scheduled message response")


class Memories(_Resource):
    def list(self, character_id: str, offset: int = 0, range: int = 10, *, min_timestamp: int | None = None, max_timestamp: int | None = None, timeout: float | None = None) -> list[Any]:
        payload: dict[str, Any] = {"character_id": character_id, "offset": offset, "limit": range}
        if min_timestamp is not None:
            payload["min_timestamp"] = min_timestamp
        if max_timestamp is not None:
            payload["max_timestamp"] = max_timestamp
        data = self._request("get_memories", "on_get_memories_response", payload, timeout=timeout)
        return _list_field(data, "memories", "memories response")

    def get_top_memories(self, character_id: str, limit: int = 10, *, timeout: float | None = None) -> list[Any]:
        data = self._request("get_top_memories", "on_get_top_memories_response", {"character_id": character_id, "limit": limit}, timeout=timeout)
        return _list_field(data, "memories", "top memories response")

    def create_or_update(self, memories: Sequence[Mapping[str, Any]], *, timeout: float | None = None) -> list[Any]:
        data = self._request("create_or_update_memories", "on_create_or_update_memories_response", [dict(memory) for memory in memories], timeout=timeout)
        return _list_field(data, "memories", "saved memories response")

    async def list_async(self, character_id: str, offset: int = 0, range: int = 10, *, min_timestamp: int | None = None, max_timestamp: int | None = None, timeout: float | None = None) -> list[Any]:
        payload: dict[str, Any] = {"character_id": character_id, "offset": offset, "limit": range}
        if min_timestamp is not None:
            payload["min_timestamp"] = min_timestamp
        if max_timestamp is not None:
            payload["max_timestamp"] = max_timestamp
        data = await self._request_async("get_memories", "on_get_memories_response", payload, timeout=timeout)
        return _list_field(data, "memories", "memories response")

    async def get_top_memories_async(self, character_id: str, limit: int = 10, *, timeout: float | None = None) -> list[Any]:
        data = await self._request_async("get_top_memories", "on_get_top_memories_response", {"character_id": character_id, "limit": limit}, timeout=timeout)
        return _list_field(data, "memories", "top memories response")

    async def create_or_update_async(self, memories: Sequence[Mapping[str, Any]], *, timeout: float | None = None) -> list[Any]:
        data = await self._request_async("create_or_update_memories", "on_create_or_update_memories_response", [dict(memory) for memory in memories], timeout=timeout)
        return _list_field(data, "memories", "saved memories response")


class Personas(_Resource):
    def get(self, character_id: str | None = None, *, timeout: float | None = None) -> Mapping[str, Any]:
        data = self._request("get_persona", "on_get_persona_response", {"character_id": character_id}, timeout=timeout)
        return _mapping(_field(data, "persona", "persona response"), "persona")

    async def get_async(self, character_id: str | None = None, *, timeout: float | None = None) -> Mapping[str, Any]:
        data = await self._request_async("get_persona", "on_get_persona_response", {"character_id": character_id}, timeout=timeout)
        return _mapping(_field(data, "persona", "persona response"), "persona")


class TTS(_Resource):
    def get_voices(self, *, timeout: float | None = None) -> list[Any]:
        data = self._request("get_tts_voices", "on_get_tts_voices_response", None, timeout=timeout)
        return _list_field(data, "voices", "TTS voices response")

    def generate_voice(self, tts_voice_id: str | None, text: str, *, timeout: float | None = None) -> None:
        self._request("generate_voice", "on_finished_speaking", {"ttsVoiceId": tts_voice_id, "text": text}, timeout=timeout)

    def generate_voice_to_file(self, tts_voice_id: str | None, text: str, save: bool = False, *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(self._request("generate_voice_to_file", "on_generate_voice_to_file_response", {"ttsVoiceId": tts_voice_id, "text": text, "save": save}, timeout=timeout), "generate voice to file response")

    def stop_speaking(self, *, timeout: float | None = None) -> None:
        self._request("stop_speaking", "on_finished_speaking", None, timeout=timeout)

    async def get_voices_async(self, *, timeout: float | None = None) -> list[Any]:
        data = await self._request_async("get_tts_voices", "on_get_tts_voices_response", None, timeout=timeout)
        return _list_field(data, "voices", "TTS voices response")

    async def generate_voice_async(self, tts_voice_id: str | None, text: str, *, timeout: float | None = None) -> None:
        await self._request_async("generate_voice", "on_finished_speaking", {"ttsVoiceId": tts_voice_id, "text": text}, timeout=timeout)

    async def generate_voice_to_file_async(self, tts_voice_id: str | None, text: str, save: bool = False, *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(await self._request_async("generate_voice_to_file", "on_generate_voice_to_file_response", {"ttsVoiceId": tts_voice_id, "text": text, "save": save}, timeout=timeout), "generate voice to file response")

    async def stop_speaking_async(self, *, timeout: float | None = None) -> None:
        await self._request_async("stop_speaking", "on_finished_speaking", None, timeout=timeout)


class Utils(_Resource):
    def save_file(self, filename: str, content_base64: str, share: bool = False, *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(self._request("save_file", "on_save_file_response", {"filename": filename, "content_base64": content_base64, "share": share}, timeout=timeout), "save file response")

    def read_file(self, filename: str, *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(self._request("read_file", "on_read_file_response", {"filename": filename}, timeout=timeout), "read file response")

    async def save_file_async(self, filename: str, content_base64: str, share: bool = False, *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(await self._request_async("save_file", "on_save_file_response", {"filename": filename, "content_base64": content_base64, "share": share}, timeout=timeout), "save file response")

    async def read_file_async(self, filename: str, *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(await self._request_async("read_file", "on_read_file_response", {"filename": filename}, timeout=timeout), "read file response")


class Contextual(_Resource):
    """One-shot context lookup only; contextual pushed events are excluded."""

    def get_execution_context(self, *, timeout: float | None = None) -> Mapping[str, Any] | None:
        data = self._request("get_execution_context", "on_get_execution_context_response", None, timeout=timeout)
        return _mapping(data, "execution context") if data is not None else None

    async def get_execution_context_async(self, *, timeout: float | None = None) -> Mapping[str, Any] | None:
        data = await self._request_async("get_execution_context", "on_get_execution_context_response", None, timeout=timeout)
        return _mapping(data, "execution context") if data is not None else None


class LythonClient:
    """A reusable client providing Layla's embedded Python resources."""

    def __init__(self, transport: LythonTransport | None = None) -> None:
        self.transport = transport or LythonTransport()
        self.chat = Chat(self.transport)
        self.characters = Characters(self.transport)
        self.images = Images(self.transport)
        self.classifier = Classifier(self.transport)
        self.utils = Utils(self.transport)
        self.memories = Memories(self.transport)
        self.personas = Personas(self.transport)
        self.tts = TTS(self.transport)
        self.contextual = Contextual(self.transport)

    def notify(self, message: str) -> None:
        """Send a fire-and-forget notification string to the Layla host."""

        self.transport.notify(message)
