# Lython one-shot API reference

This reference describes the embedded Python API. Methods are synchronous
unless suffixed with `_async`. Every method accepts keyword-only
`timeout: float | None`; every synchronous method has an `_async` counterpart.
The public API uses snake_case exclusively and provides no camelCase aliases.

## Contents

- [Characters](#characters)
- [Chat](#chat)
- [Classifier and images](#classifier-and-images)
- [Memories and personas](#memories-and-personas)
- [TTS and files](#tts-and-files)
- [Execution context](#execution-context)
- [Notifications](#notifications)
- [Errors and runtime](#errors-and-runtime)

## Characters

```python
lython.characters.list(offset=0, range=10) -> list[dict]
lython.characters.get_image(character_id) -> str | None
lython.characters.update(character) -> str
```

`character` has `id` and a Character Card V2 `data` object. `get_image` returns
a ready-to-use data URI. `update` returns the host-assigned character ID, which
may differ when a new character is created.

## Chat

```python
lython.chat.completions.create(
    body=None, *, messages=None, model="layla", timeout=None
) -> dict
lython.chat.get_inference_engines() -> list[str]
lython.chat.set_inference_engine(engine_name) -> dict
lython.chat.get_chat_history(session_id, offset=0, range=10) -> list[dict]
lython.chat.get_chat_sessions(character_id, offset=0, range=10) -> dict
lython.chat.save_chat_message(message) -> dict
lython.chat.schedule_chat_message(message) -> dict
lython.chat.get_scheduled_chat_messages() -> list[dict]
lython.chat.cancel_scheduled_chat_message(id) -> dict
```

Pass either an OpenAI-shaped `body` mapping or Python-style `messages=`, not
both. `stream=True` raises `LythonError`. The completion shape is:

```python
{
    "id": "chatcmpl-layla-...",
    "object": "chat.completion",
    "created": 1234567890,
    "model": "layla",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": "final visible text",
            # "reasoning": "optional reasoning text",
        },
        "finish_reason": "stop",
    }],
}
```

Text messages use `{"role": ..., "content": str | None, "name": ...}`.
Multimodal input uses OpenAI content parts:

```python
{
    "role": "user",
    "content": [
        {"type": "text", "text": "Describe this image."},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,..."},
        },
    ],
}
```

Only one PNG, JPEG, GIF, or WebP base64 data URL is allowed per message. Remote
URLs are rejected. Multiple text parts are joined with newlines. An image-only
message sends `content: None` plus `image_base64` on the native wire.

Chat history entries include `id`, `role`, optional `name`, `content`, optional
`image_base64`, `character_id`, `session_id`, and `timestamp`. Use `id <= 0` to
create and a positive ID to update.

Scheduled messages contain `id`, `character_id`, nullable `session_id`, future
`timestamp`, and `message`. Cancellation returns `id`, `success`, and optional
`message`.

## Classifier and images

```python
lython.classifier.get_sentiment(text) -> dict[str, float]
lython.images.get_image_generation_models() -> list[dict]
lython.images.generate_image(
    prompt, img2img_base64=None, model_id=None
) -> str | None
```

Image models have `id`, `name`, and `description`. Generated images and
`img2img_base64` use complete data URIs. Generation is final-only; progress
events are intentionally unavailable.

## Memories and personas

```python
lython.memories.list(
    character_id, offset=0, range=10,
    *, min_timestamp=None, max_timestamp=None
) -> list[dict]
lython.memories.get_top_memories(character_id, limit=10) -> list[dict]
lython.memories.create_or_update(memories) -> list[dict]
lython.personas.get(character_id=None) -> dict
```

Memory fields are `id`, `character_id`, `session_id`, `rawText`, `timestamp`,
nullable `summary`, and nullable `knowledgeGraphJSON`. Use `id <= 0` to create
and a positive ID to update. Personas contain `name` and `description`.

## TTS and files

```python
lython.tts.get_voices() -> list[dict]
lython.tts.generate_voice(tts_voice_id, text) -> None
lython.tts.generate_voice_to_file(
    tts_voice_id, text, save=False
) -> dict
lython.tts.stop_speaking() -> None

lython.utils.save_file(
    filename, content_base64, share=False
) -> dict
lython.utils.read_file(filename) -> dict
```

Pass `tts_voice_id=None` for the global default voice. TTS voices contain `id`,
`type`, `tags`, and `name`. Voice-to-file results contain `success`, nullable
`audio_data_base64`, nullable `filename`, and optional `message`.

`save_file` accepts raw base64 without a data URI prefix and returns `filename`,
`success`, and optional `message`. `read_file` returns `filename`, nullable
`content_base64` including its data URI prefix, and optional `message`.

## Execution context

```python
lython.contextual.get_execution_context() -> dict | None
```

The context contains `app_version`, nullable `character`, and nullable
`session_id`. No contextual event subscriptions exist in Lython.

## Notifications

```python
lython.notify(message) -> None
```

`notify` passes `message` unchanged to `lython_native.send()`. It is
fire-and-forget: it creates no request ID, waits for no response, accepts no
timeout, and has no `_async` counterpart. An explicit `LythonClient` exposes
the same API as `client.notify(message)`.

## Errors and runtime

The public exception hierarchy is:

```text
LythonError
├── LythonProtocolError
├── LythonHostError
└── LythonTransportError
    ├── LythonNativeUnavailableError
    ├── LythonTimeoutError
    └── LythonExecutionError
```

Real calls require Layla's embedded runtime, which injects the private
`lython_native` string transport. There is no HTTP client, API key, or base URL.
Use `LythonClient(LythonTransport(native_module=fake))` for ordinary Python
tests.
