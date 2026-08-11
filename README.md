# Lython SDK

`lython` is the standard-library-only Python SDK for code running inside
Layla's embedded Python runtime. It communicates with the Layla host through
the private `lython_native` string transport.

Real API calls only work inside an active Layla embedded Python execution.
There is no HTTP endpoint, API key, or base URL. The package requires Python
3.14 or newer and has no third-party runtime dependencies.

## Contents

- [Quick start](#quick-start)
- [API conventions](#api-conventions)
- [API overview](#api-overview)
- [Characters](#characters)
- [Chat completions](#chat-completions)
- [Inference engines](#inference-engines)
- [Chat history and sessions](#chat-history-and-sessions)
- [Scheduled chat messages](#scheduled-chat-messages)
- [Sentiment classifier](#sentiment-classifier)
- [Image generation](#image-generation)
- [Memories](#memories)
- [Personas](#personas)
- [Text to speech](#text-to-speech)
- [Private files](#private-files)
- [Execution context](#execution-context)
- [Notifications](#notifications)
- [Explicit clients and timeouts](#explicit-clients-and-timeouts)
- [Low-level APIs](#low-level-apis)
- [Errors](#errors)
- [Runtime limitations](#runtime-limitations)
- [Host integration](#host-integration)
- [Development and releases](#development-and-releases)

## Quick start

Import `lython` and use its package-level resources:

```python
import lython

characters = lython.characters.list()
persona = lython.personas.get()

completion = lython.chat.completions.create(
    messages=[
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "Give me one chess tip."},
    ]
)
answer = completion["choices"][0]["message"]["content"]

lython.notify(f"Layla answered: {answer}")
```

## API conventions

The package-level resources are `characters`, `chat`, `classifier`, `images`,
`memories`, `personas`, `tts`, `utils`, and `contextual`.

Every one-shot resource method:

- is synchronous by default;
- accepts a keyword-only `timeout: float | None` argument;
- has an async counterpart with an `_async` suffix; and
- returns ordinary dictionaries, lists, strings, or `None`.

For example:

```python
import asyncio
import lython


async def main() -> None:
    characters = await lython.characters.list_async(timeout=30)
    persona = await lython.personas.get_async(timeout=30)
    print(characters, persona)


asyncio.run(main())
```

Async calls use a worker thread because the native request is blocking.
Cancelling the Python task does not cancel its underlying native request; the
request continues until Layla responds unless an explicit timeout bounds it.

The public Python API uses snake_case method names exclusively.

### Async methods

This table enumerates every async resource method.

| Resource | Async methods |
| --- | --- |
| `characters` | `list_async`, `get_image_async`, `update_async` |
| `chat.completions` | `create_async` |
| `chat` | `get_inference_engines_async`, `set_inference_engine_async`, `get_chat_history_async`, `get_chat_sessions_async`, `save_chat_message_async`, `schedule_chat_message_async`, `get_scheduled_chat_messages_async`, `cancel_scheduled_chat_message_async` |
| `classifier` | `get_sentiment_async` |
| `images` | `get_image_generation_models_async`, `generate_image_async` |
| `memories` | `list_async`, `get_top_memories_async`, `create_or_update_async` |
| `personas` | `get_async` |
| `tts` | `get_voices_async`, `generate_voice_async`, `generate_voice_to_file_async`, `stop_speaking_async` |
| `utils` | `save_file_async`, `read_file_async` |
| `contextual` | `get_execution_context_async` |

## API overview

| Resource | Methods | Result |
| --- | --- | --- |
| `characters` | `list`, `get_image`, `update` | Characters, image data URI, or character ID |
| `chat.completions` | `create` | Final OpenAI-shaped chat completion |
| `chat` | `get_inference_engines`, `set_inference_engine` | Engine names or selection result |
| `chat` | `get_chat_history`, `get_chat_sessions`, `save_chat_message` | Stored chat data |
| `chat` | `schedule_chat_message`, `get_scheduled_chat_messages`, `cancel_scheduled_chat_message` | Scheduled-message data |
| `classifier` | `get_sentiment` | Sentiment score mapping |
| `images` | `get_image_generation_models`, `generate_image` | Model metadata or image data URI |
| `memories` | `list`, `get_top_memories`, `create_or_update` | Memory dictionaries |
| `personas` | `get` | Persona dictionary |
| `tts` | `get_voices`, `generate_voice`, `generate_voice_to_file`, `stop_speaking` | Voice data, file result, or `None` |
| `utils` | `save_file`, `read_file` | Private-file result |
| `contextual` | `get_execution_context` | Execution context or `None` |
| Package/client | `notify` | `None` (fire-and-forget) |

The sections below document all 27 high-level operations. Add `_async` to any
one-shot method name and `await` it to use its async counterpart. `notify` is
the only exception because it does not wait for a response.

## Characters

### `characters.list`

```python
characters = lython.characters.list(
    offset=0,
    range=20,
    timeout=30,
)

for character in characters:
    print(character["id"])
```

Returns a page of character dictionaries. `range` controls the page size.

### `characters.get_image`

```python
image_data_uri = lython.characters.get_image("character-id")

if image_data_uri is not None:
    print(image_data_uri[:30])  # data:image/png;base64,...
```

Returns a complete image data URI or `None`.

### `characters.update`

```python
character_id = lython.characters.update(
    {
        "id": "character-id",
        "data": {
            "name": "Aria",
            "description": "A careful research assistant.",
        },
    }
)
```

The `data` value is a Character Card V2 object. Use the host's create/update
convention for `id`; the returned string is the host-assigned character ID and
may differ when a character is created.

## Chat completions

### `chat.completions.create`

```python
completion = lython.chat.completions.create(
    messages=[
        {"role": "system", "content": "Answer in one sentence."},
        {"role": "user", "content": "Why is the sky blue?"},
    ],
    model="layla",
    timeout=120,
)

message = completion["choices"][0]["message"]
print(message["content"])
print(message.get("reasoning"))
```

The result is a final, OpenAI-shaped `chat.completion` dictionary:

```python
{
    "id": "chatcmpl-layla-...",
    "object": "chat.completion",
    "created": 1234567890,
    "model": "layla",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "The final visible answer.",
                # "reasoning": "Optional reasoning text.",
            },
            "finish_reason": "stop",
        }
    ],
}
```

You may instead pass an OpenAI-shaped body as the first argument:

```python
completion = lython.chat.completions.create(
    {
        "model": "layla",
        "messages": [{"role": "user", "content": "Hello"}],
    }
)
```

Do not pass both `body` and `messages`. `stream=True` raises `LythonError`
because the embedded transport returns only a final response.

### Image input

Chat accepts OpenAI-style content parts with at most one base64 image data URI
per message:

```python
completion = lython.chat.completions.create(
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,iVBORw0KGgo..."
                    },
                },
            ],
        }
    ]
)
```

PNG, JPEG, GIF, and WebP data URIs are accepted. Remote image URLs and multiple
images in one message are rejected. Multiple text parts are joined with
newlines.

## Inference engines

### `chat.get_inference_engines`

```python
engines = lython.chat.get_inference_engines()
for engine_name in engines:
    print(engine_name)
```

### `chat.set_inference_engine`

```python
result = lython.chat.set_inference_engine("local-engine-name")
print(result.get("success"))

# None restores the host's default selection when supported.
lython.chat.set_inference_engine(None)
```

## Chat history and sessions

### `chat.get_chat_history`

```python
history = lython.chat.get_chat_history(
    "session-id",
    offset=0,
    range=50,
)

for message in history:
    print(message["role"], message["content"])
```

History entries contain `id`, `role`, optional `name`, `content`, optional
`image_base64`, `character_id`, `session_id`, and `timestamp`.

### `chat.get_chat_sessions`

```python
page = lython.chat.get_chat_sessions(
    "character-id",
    offset=0,
    range=20,
)

for session in page.get("sessions", []):
    print(session["session_id"])
```

This method returns the host's paginated session response dictionary.

### `chat.save_chat_message`

```python
saved = lython.chat.save_chat_message(
    {
        "id": 0,
        "role": "user",
        "content": "Remember this message.",
        "character_id": "character-id",
        "session_id": "session-id",
        "timestamp": 1_785_000_000_000,
    }
)
print(saved["id"])
```

Use `id <= 0` to create a message and a positive ID to update one.

## Scheduled chat messages

### `chat.schedule_chat_message`

```python
scheduled = lython.chat.schedule_chat_message(
    {
        "id": 0,
        "character_id": "character-id",
        "session_id": "session-id",  # May be None.
        "timestamp": 1_785_000_000_000,  # Future Unix time in milliseconds.
        "message": "This is a scheduled message.",
    }
)
scheduled_id = scheduled["id"]
```

### `chat.get_scheduled_chat_messages`

```python
scheduled_messages = lython.chat.get_scheduled_chat_messages()
for scheduled in scheduled_messages:
    print(scheduled["id"], scheduled["message"])
```

### `chat.cancel_scheduled_chat_message`

```python
result = lython.chat.cancel_scheduled_chat_message(scheduled_id)
if not result["success"]:
    print(result.get("message", "Cancellation failed"))
```

The cancellation result contains `id`, `success`, and an optional `message`.

## Sentiment classifier

### `classifier.get_sentiment`

```python
scores = lython.classifier.get_sentiment("I am delighted with the result.")
dominant_sentiment = max(scores, key=scores.get)
print(dominant_sentiment, scores[dominant_sentiment])
```

Returns a mapping from sentiment labels to numeric scores.

## Image generation

### `images.get_image_generation_models`

```python
models = lython.images.get_image_generation_models()
for model in models:
    print(model["id"], model["name"], model["description"])
```

### `images.generate_image`

```python
image_data_uri = lython.images.generate_image(
    "A watercolor landscape at sunrise",
    model_id="model-id",
    timeout=300,
)
```

For image-to-image generation, supply a complete source-image data URI:

```python
image_data_uri = lython.images.generate_image(
    "Convert this scene to a pencil sketch",
    img2img_base64="data:image/png;base64,iVBORw0KGgo...",
    model_id="model-id",
    timeout=300,
)
```

The method returns a complete generated-image data URI or `None`. Generation
is final-only; progress callbacks and events are not available.

## Memories

Memory dictionaries use these fields: `id`, `character_id`, `session_id`,
`rawText`, `timestamp`, nullable `summary`, and nullable `knowledgeGraphJSON`.

### `memories.list`

```python
memories = lython.memories.list(
    "character-id",
    offset=0,
    range=50,
    min_timestamp=1_700_000_000_000,
    max_timestamp=1_800_000_000_000,
)
```

The timestamp bounds are optional.

### `memories.get_top_memories`

```python
top_memories = lython.memories.get_top_memories(
    "character-id",
    limit=10,
)
```

### `memories.create_or_update`

```python
saved_memories = lython.memories.create_or_update(
    [
        {
            "id": 0,
            "character_id": "character-id",
            "session_id": "session-id",
            "rawText": "The user prefers concise answers.",
            "timestamp": 1_785_000_000_000,
            "summary": "Prefers concise answers",
            "knowledgeGraphJSON": None,
        }
    ]
)
```

Use `id <= 0` to create a memory and a positive ID to update one.

## Personas

### `personas.get`

```python
# Get the global/default persona.
persona = lython.personas.get()

# Or get the persona associated with a character.
character_persona = lython.personas.get("character-id")

print(persona["name"], persona["description"])
```

## Text to speech

### `tts.get_voices`

```python
voices = lython.tts.get_voices()
for voice in voices:
    print(voice["id"], voice["name"], voice["type"], voice["tags"])
```

### `tts.generate_voice`

```python
# Pass None to use the global default voice.
lython.tts.generate_voice(None, "Hello from Layla.", timeout=120)

# Or select a returned voice ID.
lython.tts.generate_voice(voices[0]["id"], "Hello again.")
```

This plays speech through the Layla host and returns `None` after the terminal
speaking event.

### `tts.generate_voice_to_file`

```python
result = lython.tts.generate_voice_to_file(
    tts_voice_id=None,
    text="Save this speech as audio.",
    save=True,
    timeout=120,
)

if result["success"]:
    print(result.get("filename"))
    audio_data_uri = result.get("audio_data_base64")
else:
    print(result.get("message"))
```

The result contains `success`, nullable `audio_data_base64`, nullable
`filename`, and an optional `message`.

### `tts.stop_speaking`

```python
lython.tts.stop_speaking()
```

## Private files

### `utils.save_file`

```python
import base64

content_base64 = base64.b64encode(b"Hello from Lython\n").decode("ascii")
result = lython.utils.save_file(
    "notes/hello.txt",
    content_base64,
    share=False,
)

print(result["filename"], result["success"])
```

`content_base64` must be raw base64 without a data URI prefix. Set `share=True`
to ask the host to share the file. The result contains `filename`, `success`,
and an optional `message`.

### `utils.read_file`

```python
result = lython.utils.read_file("notes/hello.txt")

if result.get("content_base64") is not None:
    content_data_uri = result["content_base64"]
else:
    print(result.get("message", "File could not be read"))
```

The returned `content_base64`, when present, includes its data URI prefix.

## Execution context

### `contextual.get_execution_context`

```python
context = lython.contextual.get_execution_context()

if context is not None:
    print(context["app_version"])
    print(context.get("character"))
    print(context.get("session_id"))
```

The context contains `app_version`, nullable `character`, and nullable
`session_id`. Contextual event subscriptions are intentionally not exposed.

## Notifications

### `notify`

```python
lython.notify("Import complete")
```

`lython.notify(message)` passes the string directly to
`lython_native.send()` and returns `None` once dispatch finishes. It does not
create a request ID, encode a `{cmd, data}` request, wait for a response, accept
a timeout, or have an async counterpart.

## Explicit clients and timeouts

Package-level resources share a default client with no timeout, so requests wait
indefinitely for Layla to respond. Create an explicit client to configure a
finite default or inject a native transport in tests:

```python
from lython import LythonClient, LythonTransport

transport = LythonTransport(default_timeout=120)
client = LythonClient(transport)

history = client.chat.get_chat_history("session-id")
client.notify("History loaded")
```

A per-call timeout overrides the transport default:

```python
completion = client.chat.completions.create(
    messages=[{"role": "user", "content": "Write a short story."}],
    timeout=300,
)
```

The transport defaults to `timeout=None`, which has no native deadline. Timeouts
must otherwise be finite, non-negative numbers.

## Low-level APIs

Most applications should use the high-level resources. The following public
APIs are available for host integration, extensions, and testing.

### `LythonTransport`

```python
from lython import LythonTransport

transport = LythonTransport(default_timeout=None)
response = transport.request(
    {"cmd": "get_characters", "data": {"offset": 0, "limit": 10}},
    "on_get_characters_response",
)

print(response.request_id)
print(response.event)
print(response.data)
```

Its public methods are:

```text
transport.notify(message) -> None
transport.request(message, expected_event, *, timeout=None) -> OneShotResponse
transport.request_json(message, expected_event, *, timeout=None) -> OneShotResponse
await transport.request_async(message, expected_event, *, timeout=None) -> OneShotResponse
await transport.request_json_async(message, expected_event, *, timeout=None) -> OneShotResponse
```

`request_json` validates caller-provided JSON and sends it unchanged. A
`OneShotResponse` has `request_id`, `event`, `data`, `message`, and
`raw_message` fields.

For an ordinary Python test, inject a fake object implementing `send(message)`
and `request(request_id, message, timeout)`:

```python
import json
from lython import LythonClient, LythonTransport


class FakeNative:
    def send(self, message: str) -> None:
        pass

    def request(
        self,
        request_id: str,
        message: str,
        timeout: float | None,
    ) -> str:
        request = json.loads(message)
        if request["cmd"] == "get_characters":
            return '{"event":"on_get_characters_response","data":[]}'
        return '{"event":"on_error","data":{"message":"Unsupported"}}'


client = LythonClient(LythonTransport(native_module=FakeNative()))
assert client.characters.list() == []
```

### `OneShotRequestTemplate`

Bind an existing Layla command to its expected terminal event:

```python
from lython import LythonTransport, OneShotRequestTemplate

get_characters = OneShotRequestTemplate(
    command="get_characters",
    response_event="on_get_characters_response",
)

message = get_characters.build_message({"offset": 0, "limit": 10})
characters = get_characters.send(
    LythonTransport(),
    {"offset": 0, "limit": 10},
)
```

`send_async` is the async counterpart. Both return only the terminal event's
`data` field.

### Protocol codecs

```python
from lython import decode_layla_event, decode_layla_request, encode_layla_request

request_json = encode_layla_request(
    {"cmd": "get_characters", "data": {"offset": 0, "limit": 10}}
)
request = decode_layla_request(request_json)
event = decode_layla_event(
    '{"event":"on_get_characters_response","data":[]}'
)
```

`decode_layla_request` requires a JSON object with a non-empty string `cmd`.
`decode_layla_event` requires a JSON object with a non-empty string `event`.
`encode_layla_request` emits compact, strict JSON and rejects non-serializable
or non-finite values.

### Resource classes

`Chat`, `Characters`, `Classifier`, `Contextual`, `Images`, `Memories`,
`Personas`, `TTS`, and `Utils` are public, primarily for type annotations and
custom client composition. A `LythonClient` creates all of them against one
transport.

## Errors

All SDK-defined exceptions inherit from `LythonError`:

```text
LythonError
├── LythonProtocolError
├── LythonHostError
└── LythonTransportError
    ├── LythonNativeUnavailableError
    ├── LythonTimeoutError
    └── LythonExecutionError
```

Catch the narrowest error relevant to the operation:

```python
from lython import (
    LythonHostError,
    LythonNativeUnavailableError,
    LythonTimeoutError,
)

try:
    characters = lython.characters.list(timeout=10)
except LythonTimeoutError:
    print("Layla did not respond before the deadline")
except LythonNativeUnavailableError:
    print("This code is not running inside Layla")
except LythonHostError as error:
    print(error.code, str(error))
```

`LythonHostError` also exposes `details`, `retryable`, and `raw_message`.

## Runtime limitations

- Chat completions are final-only; no streaming iterator is exposed.
- Image generation is final-only; no progress callbacks are exposed.
- Context is a one-shot lookup; contextual `on`/`off` subscriptions are absent.
- Background-audio controls are absent because they are fire-and-forget and
  event-driven.
- `notify` is the intentional fire-and-forget exception and has no timeout or
  async form.

## Host integration

Requests use the existing React Native WebView API message shape. For example,
the native request receives:

```json
{"cmd":"get_characters","data":{"offset":0,"limit":10}}
```

The native request ID is passed separately to `lython_native.request()` and is
not duplicated in the JSON. The host returns one terminal WebView event:

```json
{"event":"on_get_characters_response","data":[]}
```

Host failures use `on_error`:

```json
{"event":"on_error","data":{"message":"Unable to load characters"}}
```

The React Native Lython request listener should:

1. Pass the request JSON directly to
   `RNWebviewApiService.handleLaylaApiMessage(message)`.
2. Capture the one terminal WebView API event for that command.
3. Encode the event directly as JSON.
4. Call `Lython.respond(executionId, requestId, responseMessage)` exactly once.
5. Return `on_error` for malformed requests, unknown commands, and handler
   errors.

For chat, the host must consolidate generation into one terminal event:

```json
{"event":"on_message_end","data":{"msg":"The complete final response"}}
```

`data` may instead be a complete OpenAI-shaped completion. Reasoning is
preserved, and `<think>...</think>` content is separated into the final
message's `reasoning` field.

## Development and releases

Run the standard-library test suite from the repository root:

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m unittest discover -s tests -v
```

GitHub Releases contain a universal wheel and source distribution. To publish:

1. Update `project.version` in `pyproject.toml` and commit it.
2. Create a matching tag, such as `v0.1.0` for version `0.1.0`.
3. Push the tag to GitHub.

The release workflow tests, builds, and checks both distributions before
creating the GitHub Release. A tag that does not match `project.version` is
rejected.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
