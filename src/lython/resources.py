"""High-level resources for Layla's one-shot embedded Python APIs."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Mapping, Sequence
from typing import Any

from ._chat import ChatProtocol, build_completion, prepare_body
from .browser import Page
from .errors import LythonError, LythonProtocolError
from .transport import LythonTransport


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


def _optional_payload(**values: Any) -> dict[str, Any]:
    """Omit unset options while retaining zero, False, empty strings and lists."""
    return {key: value for key, value in values.items() if value is not None}


def _optional_string(value: Any, description: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise LythonProtocolError(f"{description} must be a string or None")
    return value


def _tag_deleted(result: Any) -> bool:
    value = _field(result, "deleted", "delete tag response")
    if not isinstance(value, bool):
        raise LythonProtocolError("deleted must be a boolean")
    return value


def _understand_payload(source: Mapping[str, Any], **options: Any) -> dict[str, Any]:
    source = _mapping(source, "understand source")
    audio, latents = source.get("audio_base64"), source.get("latents_base64")
    if (audio is None) == (latents is None):
        raise ValueError("source must contain exactly one of audio_base64 or latents_base64")
    if not isinstance(audio if audio is not None else latents, str):
        raise TypeError("audio_base64 and latents_base64 must be strings")
    return _optional_payload(audio_data_base64=audio, src_latents_base64=latents, **options)


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
        reference_images: Sequence[str] | None = None,
        timeout: float | None = None,
    ) -> str | None:
        payload: dict[str, Any] = {"prompt": prompt}
        if img2img_base64 is not None:
            payload["img2img_base64"] = img2img_base64
        if model_id is not None:
            payload["model_id"] = model_id
        if reference_images is not None:
            payload["reference_images"] = _reference_image_list(reference_images)
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
        reference_images: Sequence[str] | None = None,
        timeout: float | None = None,
    ) -> str | None:
        payload: dict[str, Any] = {"prompt": prompt}
        if img2img_base64 is not None:
            payload["img2img_base64"] = img2img_base64
        if model_id is not None:
            payload["model_id"] = model_id
        if reference_images is not None:
            payload["reference_images"] = _reference_image_list(reference_images)
        result = await self._request_async(
            "generate_image",
            "on_generate_image_response",
            payload,
            timeout=timeout,
        )
        return result.get("image_data_base64") if isinstance(result, Mapping) else None


    def get_tag_dictionaries(self, *, timeout: float | None = None) -> list[Any]:
        """List the host image-tag dictionaries."""
        result = self._request(
            "image_gen_tag_get_dictionaries", "on_image_gen_tag_get_dictionaries_response",
            None, timeout=timeout,
        )
        return result if isinstance(result, list) else []

    async def get_tag_dictionaries_async(self, *, timeout: float | None = None) -> list[Any]:
        """List the host image-tag dictionaries."""
        result = await self._request_async(
            "image_gen_tag_get_dictionaries", "on_image_gen_tag_get_dictionaries_response",
            None, timeout=timeout,
        )
        return result if isinstance(result, list) else []

    def get_tags(
        self,
        dictionary_filename: str,
        *,
        offset: int = 0,
        limit: int = 50,
        category: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """List a dictionary page, optionally filtered by category."""
        result = self._request(
            "image_gen_tag_get_tags", "on_image_gen_tag_get_tags_response",
            _optional_payload(
                dictionary_filename=dictionary_filename,
                offset=offset,
                limit=limit,
                category=category,
            ), timeout=timeout,
        )
        return _mapping(result, "tag page")

    async def get_tags_async(
        self,
        dictionary_filename: str,
        *,
        offset: int = 0,
        limit: int = 50,
        category: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """List a dictionary page, optionally filtered by category."""
        result = await self._request_async(
            "image_gen_tag_get_tags", "on_image_gen_tag_get_tags_response",
            _optional_payload(
                dictionary_filename=dictionary_filename,
                offset=offset,
                limit=limit,
                category=category,
            ), timeout=timeout,
        )
        return _mapping(result, "tag page")

    def get_tag(
        self,
        dictionary_filename: str,
        english: str,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any] | None:
        """Get an exact English tag, or None when absent."""
        result = self._request(
            "image_gen_tag_get_tag", "on_image_gen_tag_get_tag_response",
            {"dictionary_filename": dictionary_filename, "english": english}, timeout=timeout,
        )
        tag = _field(result, "tag", "tag response")
        return _mapping(tag, "tag") if tag is not None else None

    async def get_tag_async(
        self,
        dictionary_filename: str,
        english: str,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any] | None:
        """Get an exact English tag, or None when absent."""
        result = await self._request_async(
            "image_gen_tag_get_tag", "on_image_gen_tag_get_tag_response",
            {"dictionary_filename": dictionary_filename, "english": english}, timeout=timeout,
        )
        tag = _field(result, "tag", "tag response")
        return _mapping(tag, "tag") if tag is not None else None

    def upsert_tag(
        self,
        dictionary_filename: str,
        tag: Mapping[str, Any],
        replacing: str | None = None,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Create, replace or rename a tag in a dictionary."""
        result = self._request(
            "image_gen_tag_upsert_tag", "on_image_gen_tag_upsert_tag_response",
            {
                "dictionary_filename": dictionary_filename,
                "tag": dict(tag),
                "replacing": replacing,
            }, timeout=timeout,
        )
        return _mapping(_field(result, "tag", "upsert response"), "tag")

    async def upsert_tag_async(
        self,
        dictionary_filename: str,
        tag: Mapping[str, Any],
        replacing: str | None = None,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Create, replace or rename a tag in a dictionary."""
        result = await self._request_async(
            "image_gen_tag_upsert_tag", "on_image_gen_tag_upsert_tag_response",
            {
                "dictionary_filename": dictionary_filename,
                "tag": dict(tag),
                "replacing": replacing,
            }, timeout=timeout,
        )
        return _mapping(_field(result, "tag", "upsert response"), "tag")

    def delete_tag(
        self,
        dictionary_filename: str,
        english: str,
        *,
        timeout: float | None = None,
    ) -> bool:
        """Delete an exact tag; return False when already absent."""
        result = self._request(
            "image_gen_tag_delete_tag", "on_image_gen_tag_delete_tag_response",
            {"dictionary_filename": dictionary_filename, "english": english}, timeout=timeout,
        )
        return _tag_deleted(result)

    async def delete_tag_async(
        self,
        dictionary_filename: str,
        english: str,
        *,
        timeout: float | None = None,
    ) -> bool:
        """Delete an exact tag; return False when already absent."""
        result = await self._request_async(
            "image_gen_tag_delete_tag", "on_image_gen_tag_delete_tag_response",
            {"dictionary_filename": dictionary_filename, "english": english}, timeout=timeout,
        )
        return _tag_deleted(result)

    def search_tags(
        self,
        dictionary_filename: str,
        query: str,
        *,
        mode: str | None = None,
        offset: int = 0,
        limit: int = 50,
        category: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Search names and aliases with pagination; mode is name or prefix."""
        result = self._request(
            "image_gen_tag_search_tags", "on_image_gen_tag_search_tags_response",
            _optional_payload(
                dictionary_filename=dictionary_filename,
                query=query,
                mode=mode,
                offset=offset,
                limit=limit,
                category=category,
            ), timeout=timeout,
        )
        return _mapping(result, "tag search response")

    async def search_tags_async(
        self,
        dictionary_filename: str,
        query: str,
        *,
        mode: str | None = None,
        offset: int = 0,
        limit: int = 50,
        category: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Search names and aliases with pagination; mode is name or prefix."""
        result = await self._request_async(
            "image_gen_tag_search_tags", "on_image_gen_tag_search_tags_response",
            _optional_payload(
                dictionary_filename=dictionary_filename,
                query=query,
                mode=mode,
                offset=offset,
                limit=limit,
                category=category,
            ), timeout=timeout,
        )
        return _mapping(result, "tag search response")

    def suggest_tags(
        self,
        dictionary_filename: str,
        query: str,
        *,
        limit: int = 40,
        timeout: float | None = None,
    ) -> list[Any]:
        """Get ranked tag autocomplete suggestions."""
        result = self._request(
            "image_gen_tag_suggest_tags", "on_image_gen_tag_suggest_tags_response",
            {"dictionary_filename": dictionary_filename, "query": query, "limit": limit}, timeout=timeout,
        )
        return _list_field(result, "suggestions", "tag suggestions")

    async def suggest_tags_async(
        self,
        dictionary_filename: str,
        query: str,
        *,
        limit: int = 40,
        timeout: float | None = None,
    ) -> list[Any]:
        """Get ranked tag autocomplete suggestions."""
        result = await self._request_async(
            "image_gen_tag_suggest_tags", "on_image_gen_tag_suggest_tags_response",
            {"dictionary_filename": dictionary_filename, "query": query, "limit": limit}, timeout=timeout,
        )
        return _list_field(result, "suggestions", "tag suggestions")

def _reference_image_list(images: Sequence[str]) -> list[str]:
    if (
        not isinstance(images, Sequence)
        or isinstance(images, (str, bytes, bytearray))
        or any(not isinstance(image, str) for image in images)
    ):
        raise LythonError("reference_images must be a sequence of image data URI strings")
    return list(images)


def _nightmare_video_payload(
    model_id: str, prompt: str, options: Mapping[str, Any]
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model_id": model_id, "prompt": prompt}
    payload.update({key: value for key, value in options.items() if value is not None})
    seed = payload.get("seed")
    # Python integers can exceed the JS host's exact JSON-number range.
    if isinstance(seed, int) and not isinstance(seed, bool) and abs(seed) > 2**53 - 1:
        payload["seed"] = str(seed)
    return payload




class NightmareMobile(_Resource):
    """Final-only WAN video APIs using the host's latest UI-saved settings."""

    def get_models(self, *, timeout: float | None = None) -> list[Any]:
        result = self._request(
            "nightmaremobile_get_models", "on_nightmaremobile_get_models_response",
            None, timeout=timeout,
        )
        return result if isinstance(result, list) else []

    async def get_models_async(self, *, timeout: float | None = None) -> list[Any]:
        result = await self._request_async(
            "nightmaremobile_get_models", "on_nightmaremobile_get_models_response",
            None, timeout=timeout,
        )
        return result if isinstance(result, list) else []

    def generate_video(
        self, model_id: str, prompt: str, *,
        negative_prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
        frames: int | None = None,
        fps: float | None = None,
        seed: int | str | None = None,
        image_data_base64: str | None = None,
        end_image_data_base64: str | None = None,
        denoise_strength: float | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Return the MP4 data URI and metadata; capability limits are advisory."""
        payload = _nightmare_video_payload(model_id, prompt, {
            "negative_prompt": negative_prompt, "width": width, "height": height,
            "frames": frames, "fps": fps, "seed": seed,
            "image_data_base64": image_data_base64,
            "end_image_data_base64": end_image_data_base64,
            "denoise_strength": denoise_strength,
        })
        return _mapping(self._request(
            "nightmaremobile_generate_video", "on_nightmaremobile_generate_video_response",
            payload, timeout=timeout,
        ), "Nightmare Mobile video response")

    async def generate_video_async(
        self, model_id: str, prompt: str, *,
        negative_prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
        frames: int | None = None,
        fps: float | None = None,
        seed: int | str | None = None,
        image_data_base64: str | None = None,
        end_image_data_base64: str | None = None,
        denoise_strength: float | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        payload = _nightmare_video_payload(model_id, prompt, {
            "negative_prompt": negative_prompt, "width": width, "height": height,
            "frames": frames, "fps": fps, "seed": seed,
            "image_data_base64": image_data_base64,
            "end_image_data_base64": end_image_data_base64,
            "denoise_strength": denoise_strength,
        })
        return _mapping(await self._request_async(
            "nightmaremobile_generate_video", "on_nightmaremobile_generate_video_response",
            payload, timeout=timeout,
        ), "Nightmare Mobile video response")


class Completions(_Resource):
    """OpenAI-compatible final completions; no streaming or progress callbacks."""

    def __init__(self, transport: LythonTransport) -> None:
        super().__init__(transport)
        self._protocol = ChatProtocol(transport)

    def create(
        self, body: Mapping[str, Any] | None = None, *,
        messages: Sequence[Mapping[str, Any]] | None = None,
        model: str = "layla", timeout: float | None = None, **parameters: Any,
    ) -> dict[str, Any]:
        request, model = prepare_body(body, messages, model, parameters)
        return build_completion(self._protocol.request(request, timeout), model)

    async def create_async(
        self, body: Mapping[str, Any] | None = None, *,
        messages: Sequence[Mapping[str, Any]] | None = None,
        model: str = "layla", timeout: float | None = None, **parameters: Any,
    ) -> dict[str, Any]:
        request, model = prepare_body(body, messages, model, parameters)
        return build_completion(await self._protocol.request_async(request, timeout), model)


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

    async def get_chat_history_async(
        self,
        session_id: str,
        offset: int = 0,
        range: int = 10,
        *,
        timeout: float | None = None,
    ) -> list[Any]:
        data = await self._request_async("get_chat_history", "on_get_chat_history_response", {"session_id": session_id, "offset": offset, "limit": range}, timeout=timeout)
        return _list_field(data, "messages", "chat history response")

    async def get_chat_sessions_async(
        self,
        character_id: str,
        offset: int = 0,
        range: int = 10,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        return _mapping(await self._request_async("get_chat_sessions", "on_get_chat_sessions_response", {"character_id": character_id, "offset": offset, "limit": range}, timeout=timeout), "chat sessions response")

    async def save_chat_message_async(
        self,
        message: Mapping[str, Any],
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        return _mapping(await self._request_async("save_chat_message", "on_save_chat_message_response", dict(message), timeout=timeout), "saved chat message")

    async def schedule_chat_message_async(
        self,
        message: Mapping[str, Any],
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        return _mapping(await self._request_async("scheduled_chat_message", "on_scheduled_chat_message", dict(message), timeout=timeout), "scheduled chat message")

    async def get_scheduled_chat_messages_async(self, *, timeout: float | None = None) -> list[Any]:
        data = await self._request_async("get_scheduled_chat_messages", "on_get_scheduled_chat_messages_response", None, timeout=timeout)
        return _list_field(data, "scheduled_messages", "scheduled messages response")

    async def cancel_scheduled_chat_message_async(
        self,
        id: int,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        return _mapping(await self._request_async("cancel_scheduled_chat_message", "on_cancel_scheduled_chat_message", {"id": id}, timeout=timeout), "cancel scheduled message response")


class Memories(_Resource):
    def list(
        self,
        character_id: str,
        offset: int = 0,
        range: int = 10,
        *,
        min_timestamp: int | None = None,
        max_timestamp: int | None = None,
        timeout: float | None = None,
    ) -> list[Any]:
        payload: dict[str, Any] = {"character_id": character_id, "offset": offset, "limit": range}
        if min_timestamp is not None:
            payload["min_timestamp"] = min_timestamp
        if max_timestamp is not None:
            payload["max_timestamp"] = max_timestamp
        data = self._request("get_memories", "on_get_memories_response", payload, timeout=timeout)
        return _list_field(data, "memories", "memories response")

    def get_top_memories(
        self,
        character_id: str,
        limit: int = 10,
        *,
        timeout: float | None = None,
    ) -> list[Any]:
        data = self._request("get_top_memories", "on_get_top_memories_response", {"character_id": character_id, "limit": limit}, timeout=timeout)
        return _list_field(data, "memories", "top memories response")

    def create_or_update(
        self,
        memories: Sequence[Mapping[str, Any]],
        *,
        timeout: float | None = None,
    ) -> list[Any]:
        data = self._request("create_or_update_memories", "on_create_or_update_memories_response", [dict(memory) for memory in memories], timeout=timeout)
        return _list_field(data, "memories", "saved memories response")

    async def list_async(
        self,
        character_id: str,
        offset: int = 0,
        range: int = 10,
        *,
        min_timestamp: int | None = None,
        max_timestamp: int | None = None,
        timeout: float | None = None,
    ) -> list[Any]:
        payload: dict[str, Any] = {"character_id": character_id, "offset": offset, "limit": range}
        if min_timestamp is not None:
            payload["min_timestamp"] = min_timestamp
        if max_timestamp is not None:
            payload["max_timestamp"] = max_timestamp
        data = await self._request_async("get_memories", "on_get_memories_response", payload, timeout=timeout)
        return _list_field(data, "memories", "memories response")

    async def get_top_memories_async(
        self,
        character_id: str,
        limit: int = 10,
        *,
        timeout: float | None = None,
    ) -> list[Any]:
        data = await self._request_async("get_top_memories", "on_get_top_memories_response", {"character_id": character_id, "limit": limit}, timeout=timeout)
        return _list_field(data, "memories", "top memories response")

    async def create_or_update_async(
        self,
        memories: Sequence[Mapping[str, Any]],
        *,
        timeout: float | None = None,
    ) -> list[Any]:
        data = await self._request_async("create_or_update_memories", "on_create_or_update_memories_response", [dict(memory) for memory in memories], timeout=timeout)
        return _list_field(data, "memories", "saved memories response")


class Personas(_Resource):
    def get(
        self,
        character_id: str | None = None,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        data = self._request("get_persona", "on_get_persona_response", {"character_id": character_id}, timeout=timeout)
        return _mapping(_field(data, "persona", "persona response"), "persona")

    async def get_async(
        self,
        character_id: str | None = None,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        data = await self._request_async("get_persona", "on_get_persona_response", {"character_id": character_id}, timeout=timeout)
        return _mapping(_field(data, "persona", "persona response"), "persona")


class TTS(_Resource):
    def get_voices(self, *, timeout: float | None = None) -> list[Any]:
        data = self._request("get_tts_voices", "on_get_tts_voices_response", None, timeout=timeout)
        return _list_field(data, "voices", "TTS voices response")

    def generate_voice(
        self,
        tts_voice_id: str | None,
        text: str,
        *,
        timeout: float | None = None,
    ) -> None:
        self._request("generate_voice", "on_finished_speaking", {"ttsVoiceId": tts_voice_id, "text": text}, timeout=timeout)

    def generate_voice_to_file(
        self,
        tts_voice_id: str | None,
        text: str,
        save: bool = False,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        return _mapping(self._request("generate_voice_to_file", "on_generate_voice_to_file_response", {"ttsVoiceId": tts_voice_id, "text": text, "save": save}, timeout=timeout), "generate voice to file response")

    def stop_speaking(self, *, timeout: float | None = None) -> None:
        self._request("stop_speaking", "on_finished_speaking", None, timeout=timeout)

    async def get_voices_async(self, *, timeout: float | None = None) -> list[Any]:
        data = await self._request_async("get_tts_voices", "on_get_tts_voices_response", None, timeout=timeout)
        return _list_field(data, "voices", "TTS voices response")

    async def generate_voice_async(
        self,
        tts_voice_id: str | None,
        text: str,
        *,
        timeout: float | None = None,
    ) -> None:
        await self._request_async("generate_voice", "on_finished_speaking", {"ttsVoiceId": tts_voice_id, "text": text}, timeout=timeout)

    async def generate_voice_to_file_async(
        self,
        tts_voice_id: str | None,
        text: str,
        save: bool = False,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        return _mapping(await self._request_async("generate_voice_to_file", "on_generate_voice_to_file_response", {"ttsVoiceId": tts_voice_id, "text": text, "save": save}, timeout=timeout), "generate voice to file response")

    async def stop_speaking_async(self, *, timeout: float | None = None) -> None:
        await self._request_async("stop_speaking", "on_finished_speaking", None, timeout=timeout)


class Utils(_Resource):
    def save_file(
        self,
        filename: str,
        content_base64: str,
        share: bool = False,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        return _mapping(self._request("save_file", "on_save_file_response", {"filename": filename, "content_base64": content_base64, "share": share}, timeout=timeout), "save file response")

    def read_file(self, filename: str, *, timeout: float | None = None) -> Mapping[str, Any]:
        return _mapping(self._request("read_file", "on_read_file_response", {"filename": filename}, timeout=timeout), "read file response")

    async def save_file_async(
        self,
        filename: str,
        content_base64: str,
        share: bool = False,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        return _mapping(await self._request_async("save_file", "on_save_file_response", {"filename": filename, "content_base64": content_base64, "share": share}, timeout=timeout), "save file response")

    async def read_file_async(
        self,
        filename: str,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        return _mapping(await self._request_async("read_file", "on_read_file_response", {"filename": filename}, timeout=timeout), "read file response")


    def schedule_notification(
        self,
        notification: Mapping[str, Any],
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Schedule a one-time notification; timestamp is Unix milliseconds."""
        result = self._request(
            "schedule_notification", "on_schedule_notification_response",
            {
                "message": _field(notification, "message", "notification"),
                "timestamp": _field(notification, "timestamp", "notification"),
                "icon": notification.get("icon"),
            }, timeout=timeout,
        )
        return _mapping(result, "scheduled notification")

    async def schedule_notification_async(
        self,
        notification: Mapping[str, Any],
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Schedule a one-time notification; timestamp is Unix milliseconds."""
        result = await self._request_async(
            "schedule_notification", "on_schedule_notification_response",
            {
                "message": _field(notification, "message", "notification"),
                "timestamp": _field(notification, "timestamp", "notification"),
                "icon": notification.get("icon"),
            }, timeout=timeout,
        )
        return _mapping(result, "scheduled notification")

    def get_scheduled_notifications(self, *, timeout: float | None = None) -> list[Any]:
        """List the calling app's pending notifications."""
        result = self._request(
            "get_scheduled_notifications", "on_get_scheduled_notifications_response",
            None, timeout=timeout,
        )
        return _list_field(result, "scheduled_notifications", "notifications response")

    async def get_scheduled_notifications_async(self, *, timeout: float | None = None) -> list[Any]:
        """List the calling app's pending notifications."""
        result = await self._request_async(
            "get_scheduled_notifications", "on_get_scheduled_notifications_response",
            None, timeout=timeout,
        )
        return _list_field(result, "scheduled_notifications", "notifications response")

    def cancel_scheduled_notification(
        self,
        id: str,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Cancel a pending notification belonging to the calling app."""
        result = self._request(
            "cancel_scheduled_notification", "on_cancel_scheduled_notification_response",
            {"id": id}, timeout=timeout,
        )
        return _mapping(result, "cancel notification response")

    async def cancel_scheduled_notification_async(
        self,
        id: str,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Cancel a pending notification belonging to the calling app."""
        result = await self._request_async(
            "cancel_scheduled_notification", "on_cancel_scheduled_notification_response",
            {"id": id}, timeout=timeout,
        )
        return _mapping(result, "cancel notification response")

    def list_dir(self, path: str,*, timeout: float | None = None) -> list[Any]:
        """List relative paths and is_dir flags; use an empty path for the root."""
        result = self._request(
            "list_dir", "on_list_dir_response",
            {"path": path}, timeout=timeout,
        )
        return result if isinstance(result, list) else []

    async def list_dir_async(self, path: str,*, timeout: float | None = None) -> list[Any]:
        """List relative paths and is_dir flags; use an empty path for the root."""
        result = await self._request_async(
            "list_dir", "on_list_dir_response",
            {"path": path}, timeout=timeout,
        )
        return result if isinstance(result, list) else []

    def delete_file_or_dir(self, path: str,*, timeout: float | None = None) -> None:
        """Delete a private file or directory recursively after host acknowledgement."""
        result = self._request(
            "delete_file_or_dir", "on_delete_file_or_dir_response",
            {"path": path}, timeout=timeout,
        )
        return None

    async def delete_file_or_dir_async(self, path: str,*, timeout: float | None = None) -> None:
        """Delete a private file or directory recursively after host acknowledgement."""
        result = await self._request_async(
            "delete_file_or_dir", "on_delete_file_or_dir_response",
            {"path": path}, timeout=timeout,
        )
        return None


class Contextual(_Resource):
    """Execution context and side questions; no pushed-event subscriptions."""

    def get_execution_context(self, *, timeout: float | None = None) -> Mapping[str, Any] | None:
        data = self._request("get_execution_context", "on_get_execution_context_response", None, timeout=timeout)
        return _mapping(data, "execution context") if data is not None else None

    async def get_execution_context_async(
        self,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any] | None:
        data = await self._request_async("get_execution_context", "on_get_execution_context_response", None, timeout=timeout)
        return _mapping(data, "execution context") if data is not None else None


    def send_out_of_band_message(
        self,
        message: str,
        *,
        image_base64: str | None = None,
        json_schema: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> str:
        """Ask against the current conversation without adding to its history."""
        result = self._request(
            "send_out_of_band_message", "on_send_out_of_band_message_response",
            _optional_payload(
                message=message,
                image_base64=image_base64,
                json_schema=json_schema,
            ), timeout=timeout,
        )
        return _out_of_band_reply(result)

    async def send_out_of_band_message_async(
        self,
        message: str,
        *,
        image_base64: str | None = None,
        json_schema: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> str:
        """Ask against the current conversation without adding to its history."""
        result = await self._request_async(
            "send_out_of_band_message", "on_send_out_of_band_message_response",
            _optional_payload(
                message=message,
                image_base64=image_base64,
                json_schema=json_schema,
            ), timeout=timeout,
        )
        return _out_of_band_reply(result)


def _out_of_band_reply(result: Any) -> str:
    reply = _field(result, "msg", "out-of-band response")
    if not isinstance(reply, str):
        raise LythonProtocolError("out-of-band reply must be a string")
    return reply


class NeoDragon(_Resource):
    """Final-only NeoDragon host operations."""

    def generate_video(
        self,
        image_data_base64: str,
        prompt: str,
        *,
        seed: int | None = None,
        upscale: bool | None = None,
        fps: float | None = None,
        cinematic_prompt: bool | None = None,
        crop: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Generate an MP4 from an image data URI; return video and metadata."""
        result = self._request(
            "neodragon_generate_video", "on_neodragon_generate_video_response",
            _optional_payload(
                image_data_base64=image_data_base64,
                prompt=prompt,
                seed=seed,
                upscale=upscale,
                fps=fps,
                cinematic_prompt=cinematic_prompt,
                crop=crop,
            ), timeout=timeout,
        )
        return _mapping(result, "NeoDragon video response")

    async def generate_video_async(
        self,
        image_data_base64: str,
        prompt: str,
        *,
        seed: int | None = None,
        upscale: bool | None = None,
        fps: float | None = None,
        cinematic_prompt: bool | None = None,
        crop: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Generate an MP4 from an image data URI; return video and metadata."""
        result = await self._request_async(
            "neodragon_generate_video", "on_neodragon_generate_video_response",
            _optional_payload(
                image_data_base64=image_data_base64,
                prompt=prompt,
                seed=seed,
                upscale=upscale,
                fps=fps,
                cinematic_prompt=cinematic_prompt,
                crop=crop,
            ), timeout=timeout,
        )
        return _mapping(result, "NeoDragon video response")


class AceStep(_Resource):
    """Final-only AceStep host operations."""

    def __init__(self, transport: LythonTransport) -> None:
        super().__init__(transport)
        self._pass_lock = threading.Lock()

    def _request(self, command, response_event, data, *, timeout):
        # Every raw pass shares the same engine; discovery remains independent.
        if command == "ace_step_get_models":
            return super()._request(command, response_event, data, timeout=timeout)
        with self._pass_lock:
            return super()._request(command, response_event, data, timeout=timeout)

    async def _request_async(self, command, response_event, data, *, timeout):
        return await asyncio.to_thread(
            self._request, command, response_event, data, timeout=timeout,
        )

    def get_models(self, *, timeout: float | None = None) -> list[Any]:
        """List built-in and imported music models and their ready_for_use state."""
        result = self._request(
            "ace_step_get_models", "on_ace_step_get_models_response",
            None, timeout=timeout,
        )
        return result if isinstance(result, list) else []

    async def get_models_async(self, *, timeout: float | None = None) -> list[Any]:
        """List built-in and imported music models and their ready_for_use state."""
        result = await self._request_async(
            "ace_step_get_models", "on_ace_step_get_models_response",
            None, timeout=timeout,
        )
        return result if isinstance(result, list) else []

    def generate_music(
        self,
        prompt: str,
        lyrics: str | None = None,
        duration: float | None = None,
        *,
        model_id: str | None = None,
        timeout: float | None = None,
    ) -> str | None:
        """Generate music and return an audio data URI; duration is in seconds."""
        result = self._request(
            "ace_step_generate", "on_ace_step_generate_response",
            _optional_payload(
                prompt=prompt,
                lyrics=lyrics,
                duration=duration,
                model_id=model_id,
            ), timeout=timeout,
        )
        return _optional_string(_mapping(result, "music response").get("audio_data_base64") or None, "audio")

    async def generate_music_async(
        self,
        prompt: str,
        lyrics: str | None = None,
        duration: float | None = None,
        *,
        model_id: str | None = None,
        timeout: float | None = None,
    ) -> str | None:
        """Generate music and return an audio data URI; duration is in seconds."""
        result = await self._request_async(
            "ace_step_generate", "on_ace_step_generate_response",
            _optional_payload(
                prompt=prompt,
                lyrics=lyrics,
                duration=duration,
                model_id=model_id,
            ), timeout=timeout,
        )
        return _optional_string(_mapping(result, "music response").get("audio_data_base64") or None, "audio")

    def lm(
        self,
        request: Mapping[str, Any],
        *,
        model_id: str | None = None,
        use_gpu: bool | None = None,
        timeout: float | None = None,
    ) -> list[Any]:
        """Enrich a raw request into one request per batch variant without rendering."""
        result = self._request(
            "ace_step_lm", "on_ace_step_lm_response",
            _optional_payload(request=dict(request), model_id=model_id, use_gpu=use_gpu), timeout=timeout,
        )
        return _list_field(result, "requests", "LM response")

    async def lm_async(
        self,
        request: Mapping[str, Any],
        *,
        model_id: str | None = None,
        use_gpu: bool | None = None,
        timeout: float | None = None,
    ) -> list[Any]:
        """Enrich a raw request into one request per batch variant without rendering."""
        result = await self._request_async(
            "ace_step_lm", "on_ace_step_lm_response",
            _optional_payload(request=dict(request), model_id=model_id, use_gpu=use_gpu), timeout=timeout,
        )
        return _list_field(result, "requests", "LM response")

    def synth(
        self,
        request: Mapping[str, Any],
        *,
        model_id: str | None = None,
        use_gpu: bool | None = None,
        use_flash_attn: bool | None = None,
        vae_tile_size: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Render a raw request and return inline audio, seed and resolved request."""
        result = self._request(
            "ace_step_synth", "on_ace_step_synth_response",
            _optional_payload(
                request=dict(request),
                model_id=model_id,
                use_gpu=use_gpu,
                use_flash_attn=use_flash_attn,
                vae_tile_size=vae_tile_size,
            ), timeout=timeout,
        )
        return _mapping(result, "synth response")

    async def synth_async(
        self,
        request: Mapping[str, Any],
        *,
        model_id: str | None = None,
        use_gpu: bool | None = None,
        use_flash_attn: bool | None = None,
        vae_tile_size: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Render a raw request and return inline audio, seed and resolved request."""
        result = await self._request_async(
            "ace_step_synth", "on_ace_step_synth_response",
            _optional_payload(
                request=dict(request),
                model_id=model_id,
                use_gpu=use_gpu,
                use_flash_attn=use_flash_attn,
                vae_tile_size=vae_tile_size,
            ), timeout=timeout,
        )
        return _mapping(result, "synth response")

    def understand(
        self,
        source: Mapping[str, Any],
        *,
        model_id: str | None = None,
        request: Mapping[str, Any] | None = None,
        return_latents: bool | None = None,
        use_gpu: bool | None = None,
        use_flash_attn: bool | None = None,
        vae_tile_size: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Analyze exactly one source: audio_base64 or latents_base64."""
        result = self._request(
            "ace_step_understand", "on_ace_step_understand_response",
            _understand_payload(source, model_id=model_id, request=request, return_latents=return_latents, use_gpu=use_gpu, use_flash_attn=use_flash_attn, vae_tile_size=vae_tile_size), timeout=timeout,
        )
        return _mapping(result, "understand response")

    async def understand_async(
        self,
        source: Mapping[str, Any],
        *,
        model_id: str | None = None,
        request: Mapping[str, Any] | None = None,
        return_latents: bool | None = None,
        use_gpu: bool | None = None,
        use_flash_attn: bool | None = None,
        vae_tile_size: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Analyze exactly one source: audio_base64 or latents_base64."""
        result = await self._request_async(
            "ace_step_understand", "on_ace_step_understand_response",
            _understand_payload(source, model_id=model_id, request=request, return_latents=return_latents, use_gpu=use_gpu, use_flash_attn=use_flash_attn, vae_tile_size=vae_tile_size), timeout=timeout,
        )
        return _mapping(result, "understand response")

    def vae_encode(
        self,
        audio_base64: str,
        *,
        model_id: str | None = None,
        request: Mapping[str, Any] | None = None,
        use_gpu: bool | None = None,
        vae_tile_size: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Run the VAE pass; binary inputs/outputs cross the bridge as base64."""
        result = self._request(
            "ace_step_vae", "on_ace_step_vae_response",
            _optional_payload(
                audio_data_base64=audio_base64,
                model_id=model_id,
                request=request,
                use_gpu=use_gpu,
                vae_tile_size=vae_tile_size,
            ), timeout=timeout,
        )
        return _mapping(result, "VAE response")

    async def vae_encode_async(
        self,
        audio_base64: str,
        *,
        model_id: str | None = None,
        request: Mapping[str, Any] | None = None,
        use_gpu: bool | None = None,
        vae_tile_size: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Run the VAE pass; binary inputs/outputs cross the bridge as base64."""
        result = await self._request_async(
            "ace_step_vae", "on_ace_step_vae_response",
            _optional_payload(
                audio_data_base64=audio_base64,
                model_id=model_id,
                request=request,
                use_gpu=use_gpu,
                vae_tile_size=vae_tile_size,
            ), timeout=timeout,
        )
        return _mapping(result, "VAE response")

    def vae_decode(
        self,
        latents_base64: str,
        *,
        model_id: str | None = None,
        request: Mapping[str, Any] | None = None,
        use_gpu: bool | None = None,
        vae_tile_size: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Run the VAE pass; binary inputs/outputs cross the bridge as base64."""
        result = self._request(
            "ace_step_vae", "on_ace_step_vae_response",
            _optional_payload(
                latents_base64=latents_base64,
                model_id=model_id,
                request=request,
                use_gpu=use_gpu,
                vae_tile_size=vae_tile_size,
            ), timeout=timeout,
        )
        return _mapping(result, "VAE response")

    async def vae_decode_async(
        self,
        latents_base64: str,
        *,
        model_id: str | None = None,
        request: Mapping[str, Any] | None = None,
        use_gpu: bool | None = None,
        vae_tile_size: int | None = None,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Run the VAE pass; binary inputs/outputs cross the bridge as base64."""
        result = await self._request_async(
            "ace_step_vae", "on_ace_step_vae_response",
            _optional_payload(
                latents_base64=latents_base64,
                model_id=model_id,
                request=request,
                use_gpu=use_gpu,
                vae_tile_size=vae_tile_size,
            ), timeout=timeout,
        )
        return _mapping(result, "VAE response")


class DB(_Resource):
    """Final-only DB host operations."""

    def execute_sql(
        self,
        query: str,
        params: Sequence[Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Execute a private SQLite statement; return rows, rowsAffected and insertId."""
        result = self._request(
            "execute_sql", "on_execute_sql_response",
            _optional_payload(
                query=query,
                params=list(params) if params is not None else None,
            ), timeout=timeout,
        )
        return _mapping(result, "SQL response")

    async def execute_sql_async(
        self,
        query: str,
        params: Sequence[Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Mapping[str, Any]:
        """Execute a private SQLite statement; return rows, rowsAffected and insertId."""
        result = await self._request_async(
            "execute_sql", "on_execute_sql_response",
            _optional_payload(
                query=query,
                params=list(params) if params is not None else None,
            ), timeout=timeout,
        )
        return _mapping(result, "SQL response")


class Cloud(_Resource):
    """Final-only Cloud host operations."""

    def login(self, *, timeout: float | None = None) -> str | None:
        """Return the signed-in Layla Cloud access token, or None."""
        result = self._request(
            "layla_cloud_login", "on_layla_cloud_login",
            None, timeout=timeout,
        )
        return _optional_string(_field(result, "access_token", "cloud login response"), "access token")

    async def login_async(self, *, timeout: float | None = None) -> str | None:
        """Return the signed-in Layla Cloud access token, or None."""
        result = await self._request_async(
            "layla_cloud_login", "on_layla_cloud_login",
            None, timeout=timeout,
        )
        return _optional_string(_field(result, "access_token", "cloud login response"), "access token")


class STT(_Resource):
    """Final-only STT host operations."""

    def start_listening(self, *, timeout: float | None = None) -> None:
        """Start speech recognition and wait for acknowledgement; no transcript events."""
        result = self._request(
            "stt_start_listening", "on_stt_listening_started",
            None, timeout=timeout,
        )
        return None

    async def start_listening_async(self, *, timeout: float | None = None) -> None:
        """Start speech recognition and wait for acknowledgement; no transcript events."""
        result = await self._request_async(
            "stt_start_listening", "on_stt_listening_started",
            None, timeout=timeout,
        )
        return None

    def stop_listening(self, *, timeout: float | None = None) -> None:
        """Stop speech recognition and wait for acknowledgement."""
        result = self._request(
            "stt_stop_listening", "on_stt_listening_stopped",
            None, timeout=timeout,
        )
        return None

    async def stop_listening_async(self, *, timeout: float | None = None) -> None:
        """Stop speech recognition and wait for acknowledgement."""
        result = await self._request_async(
            "stt_stop_listening", "on_stt_listening_stopped",
            None, timeout=timeout,
        )
        return None


class LythonClient:
    """A reusable client providing Layla's embedded Python resources."""

    def __init__(self, transport: LythonTransport | None = None) -> None:
        self.transport = transport or LythonTransport()
        self.chat = Chat(self.transport)
        self.characters = Characters(self.transport)
        self.images = Images(self.transport)
        self.nightmare_mobile = NightmareMobile(self.transport)
        self.neodragon = NeoDragon(self.transport)
        self.acestep = AceStep(self.transport)
        self.db = DB(self.transport)
        self.cloud = Cloud(self.transport)
        self.stt = STT(self.transport)
        self.classifier = Classifier(self.transport)
        self.utils = Utils(self.transport)
        self.memories = Memories(self.transport)
        self.personas = Personas(self.transport)
        self.tts = TTS(self.transport)
        self.contextual = Contextual(self.transport)
        self.page = Page(self.transport)

    def notify(self, message: str) -> None:
        """Send a fire-and-forget notification string to the Layla host."""

        self.transport.notify(message)
