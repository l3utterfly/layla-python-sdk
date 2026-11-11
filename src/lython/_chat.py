"""Final-only OpenAI request adaptation and Layla reply decoding."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
import uuid
import warnings
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import LythonError, LythonProtocolError
from .transport import LythonTransport

_IMAGE = re.compile(r"^data:image/(?:gif|jpe?g|png|webp);base64,", re.I)
_STRING = r'"(?:[^"\\]|\\.)*"'


def _warn(message: str) -> None:
    warnings.warn(message, RuntimeWarning, stacklevel=3)


def _legacy_message(message: Mapping[str, Any]) -> dict[str, Any] | None:
    role = message.get("role")
    if role in ("tool", "function"):
        _warn(f"{role!r} message ignored: tool calling requires Layla 7.5 or newer")
        return None
    result = {"role": "system" if role == "developer" else role}
    content = message.get("content")
    if not isinstance(content, list):
        result["content"] = content
    else:
        texts: list[str] = []
        image = None
        for part in content:
            if not isinstance(part, Mapping):
                raise LythonProtocolError("chat content parts must be objects")
            kind = part.get("type")
            if kind == "text":
                if not isinstance(part.get("text"), str):
                    raise LythonProtocolError("chat text parts must contain a string")
                texts.append(part["text"])
            elif kind == "image_url":
                value = part.get("image_url")
                url = value.get("url") if isinstance(value, Mapping) else None
                if not isinstance(url, str) or not _IMAGE.match(url):
                    _warn("image ignored: legacy hosts require a base64 image data URL")
                elif image is not None:
                    _warn("extra image ignored: legacy hosts accept one image per message")
                else:
                    image = url
            else:
                _warn(f"{kind!r} content part ignored by the legacy chat protocol")
        result["content"] = "\n".join(texts) if texts else None
        if image is not None:
            result["image_base64"] = image
    if "name" in message:
        result["name"] = message["name"]
    return result


def prepare_body(
    body: Mapping[str, Any] | None,
    messages: Sequence[Mapping[str, Any]] | None,
    model: str,
    parameters: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    if body is not None:
        if not isinstance(body, Mapping):
            raise TypeError("body must be a mapping")
        if messages is not None or parameters:
            raise TypeError("pass either body or messages/keyword parameters, not both")
        request = dict(body)
        model = request.get("model", model)
    else:
        request = {**parameters, "messages": messages, "model": model}
    if request.get("stream"):
        raise LythonError("streaming chat completions are not available in lython")
    if not isinstance(model, str):
        raise TypeError("model must be a string")
    items = request.get("messages")
    if items is None:
        raise TypeError("messages is required")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        raise TypeError("messages must be a sequence of mappings")
    if any(not isinstance(item, Mapping) for item in items):
        raise TypeError("messages must contain mappings")
    # Copy so normalization and wire adaptation never mutate caller-owned messages.
    request["messages"] = [dict(item) for item in items]
    return request, model


class ChatProtocol:
    """Probe once per client, then choose the host's supported chat contract."""

    def __init__(self, transport: LythonTransport) -> None:
        self.transport = transport
        self._v2: bool | None = None
        self._lock = threading.Lock()
        self._generation_lock = threading.Lock()

    def _supports_v2(self, timeout: float | None) -> bool:
        with self._lock:
            if self._v2 is None:
                deadline = self.transport.default_timeout if timeout is None else timeout
                deadline = 2.0 if deadline is None else min(2.0, deadline)
                try:
                    context = self.transport.request(
                        {"cmd": "get_execution_context", "data": None},
                        "on_get_execution_context_response", timeout=deadline,
                    ).data
                    version = context.get("app_version") if isinstance(context, Mapping) else None
                    match = re.match(r"\s*v?(\d+)\.(\d+)", version, re.I) if isinstance(version, str) else None
                    self._v2 = bool(match and tuple(map(int, match.groups())) >= (7, 5))
                except LythonError:
                    self._v2 = False
            return self._v2

    @staticmethod
    def _message(body: dict[str, Any], modern: bool) -> dict[str, Any]:
        if modern:
            # The host streams internally; Python receives only on_message_end.
            try:
                payload = json.dumps({**body, "stream": True}, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError) as error:
                raise LythonProtocolError(f"chat body is not JSON serializable: {error}") from error
            return {"cmd": "send_message_v2", "data": payload}
        messages = [_legacy_message(message) for message in body["messages"]]
        return {"cmd": "send_message", "data": [m for m in messages if m is not None]}

    def request(self, body: dict[str, Any], timeout: float | None) -> Any:
        # The host owns one conversation/generation slot for this client.
        with self._generation_lock:
            return self.transport.request(
                self._message(body, self._supports_v2(timeout)),
                "on_message_end", timeout=timeout,
            ).data

    async def request_async(self, body: dict[str, Any], timeout: float | None) -> Any:
        return await asyncio.to_thread(self.request, body, timeout)


def _tool_call(block: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(block)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("name"), str) and parsed["name"]:
        name = parsed["name"]
        identifier = parsed.get("tool_call_id", parsed.get("id", ""))
        arguments = parsed.get("arguments", parsed.get("parameters"))
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False, separators=(",", ":")) if arguments is not None else "{}"
    else:
        # Preserve partial/invalid arguments just as the public SDK does.
        match = re.search(r'"name"\s*:\s*(' + _STRING + ')', block)
        if not match:
            _warn("tool call ignored: the reply contains no tool name")
            return None
        name = json.loads(match[1])
        if not name:
            return None
        match = re.search(r'"(?:tool_call_id|id)"\s*:\s*(' + _STRING + ')', block)
        identifier = json.loads(match[1]) if match else ""
        match = re.search(r'"(?:arguments|parameters)"\s*:\s*', block)
        arguments = "{}"
        if match:
            arguments = re.split(r',\s*"(?:tool_call_id|id)"\s*:', block[match.end():], maxsplit=1)[0].strip() or "{}"
    return {
        "id": identifier if isinstance(identifier, str) else "",
        "type": "function", "function": {"name": name, "arguments": arguments},
    }


def parse_reply(raw: str) -> tuple[str, str, list[dict[str, Any]]]:
    """Decode reasoning and complete or truncated tool blocks from final text."""
    content: list[str] = []
    reasoning: list[str] = []
    calls: list[dict[str, Any]] = []
    thinking = False
    gap: str | None = None
    position = 0
    tag = re.compile(r"<tool_call>|<think>|</think>")
    while position < len(raw):
        match = tag.search(raw, position)
        end = match.start() if match else len(raw)
        text = raw[position:end]
        if thinking:
            reasoning.append(text)
        elif gap is not None and not text.strip():
            gap += text
        else:
            if gap is not None:
                content.append(gap)
                gap = None
            content.append(text)
        if not match:
            break
        position = match.end()
        if match[0] == "<tool_call>":
            gap = None
            close = raw.find("</tool_call>", position)
            call = _tool_call(raw[position:close if close >= 0 else len(raw)])
            if call:
                calls.append(call)
            gap = ""
            position = close + len("</tool_call>") if close >= 0 else len(raw)
        else:
            thinking = match[0] == "<think>"
    if gap:
        content.append(gap)
    return "".join(content), "".join(reasoning), calls


def build_completion(data: Any, model: str) -> dict[str, Any]:
    if isinstance(data, Mapping):
        direct = data.get("completion", data)
        if isinstance(direct, Mapping) and direct.get("object") == "chat.completion":
            return dict(direct)
        raw = data.get("msg", data.get("content", ""))
        supplied_reasoning = data.get("reasoning")
    elif isinstance(data, str) or data is None:
        raw, supplied_reasoning = data or "", None
    else:
        raise LythonProtocolError("chat completion response data has an invalid shape")
    if not isinstance(raw, str):
        raise LythonProtocolError("chat completion content must be a string")
    content, reasoning, calls = parse_reply(raw)
    message: dict[str, Any] = {"role": "assistant", "content": content, "refusal": None}
    reasoning = supplied_reasoning if isinstance(supplied_reasoning, str) else reasoning
    if reasoning:
        message["reasoning"] = reasoning
    if calls:
        message["tool_calls"] = calls
    now = time.time()
    return {
        "id": f"chatcmpl-layla-{int(now * 1000)}-{uuid.uuid4().hex[:6]}",
        "object": "chat.completion", "created": int(now), "model": model,
        "choices": [{"index": 0, "message": message,
                     "finish_reason": "tool_calls" if calls else "stop", "logprobs": None}],
    }
