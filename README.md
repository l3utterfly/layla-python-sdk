# Lython SDK

`lython` is the standard-library-only Python SDK for code running inside
Layla's embedded Python runtime. It wraps the private `lython_native` string
transport with a versioned, JSON-encoded one-shot request protocol.

The SDK mirrors the one-shot API surface of `@layla-network/sdk` 7.2.2. It does
not provide streaming responses, progress events, contextual subscriptions, or
fire-and-forget notifications.

## High-level API

Import the package and use the same resource paths as the TypeScript SDK, with
Python-style method names:

```python
import lython

characters = lython.characters.list()
history = lython.chat.get_chat_history("session-id")
persona = lython.personas.get()

completion = lython.chat.completions.create(
    messages=[
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "Give me one chess tip."},
    ]
)
text = completion["choices"][0]["message"]["content"]
```

The resources are `characters`, `chat`, `classifier`, `images`, `memories`,
`personas`, `tts`, `utils`, and `contextual`. TypeScript camelCase aliases are
also available, so both `lython.characters.get_image(...)` and
`lython.characters.getImage(...)` work. Every synchronous method has an async
counterpart ending in `_async`, such as:

```python
characters = await lython.characters.list_async()
```

The mirrored one-shot methods are:

- `characters`: `list`, `get_image`, `update`
- `chat`: `completions.create`, inference-engine selection, history and
  session reads, message saves, and scheduled-message operations
- `classifier`: `get_sentiment`
- `images`: image-model listing and final-only `generate_image`
- `memories`: `list`, `get_top_memories`, `create_or_update`
- `personas`: `get`
- `tts`: voice listing, playback, generation to file, and stop
- `utils`: `save_file`, `read_file`
- `contextual`: `get_execution_context` only

Background-audio controls and all contextual `on`/`off` event subscriptions are
intentionally absent because they are not one-shot APIs.

For dependency injection or a non-default timeout, create a client explicitly:

```python
from lython import LythonClient, LythonTransport

client = LythonClient(LythonTransport(default_timeout=120))
characters = client.characters.list()
```

### One-shot chat

Only `chat.completions.create(...)` is implemented. It accepts OpenAI-shaped
text and base64 image messages and returns the same final `chat.completion`
dictionary as the TypeScript non-streaming call. Passing `stream=True` is an
error.

The host adapter must consolidate chat generation into one terminal event:

```json
{"event":"on_message_end","data":{"msg":"The complete final response"}}
```

`data` may instead be a complete OpenAI-shaped chat completion. A `reasoning`
field is preserved, and `<think>...</think>` content is separated into the
final message's `reasoning` field. Token events are not forwarded to Python.

## Protocol

The existing React Native WebView API messages remain unchanged. A request such
as:

```json
{"cmd":"get_characters","data":{"offset":0,"limit":10}}
```

is serialized once and stored verbatim in the Lython request envelope's
`message` field:

```json
{
  "protocol": "layla.lython",
  "version": 1,
  "type": "request",
  "message": "{\"cmd\":\"get_characters\",\"data\":{\"offset\":0,\"limit\":10}}"
}
```

The native request ID is passed separately to `lython_native.request()` and is
not duplicated in the JSON envelope.

A successful host response wraps the existing WebView event JSON in the same
way:

```json
{
  "protocol": "layla.lython",
  "version": 1,
  "type": "response",
  "ok": true,
  "message": "{\"event\":\"on_get_characters_response\",\"data\":[]}"
}
```

A failed host request uses a structured error:

```json
{
  "protocol": "layla.lython",
  "version": 1,
  "type": "response",
  "ok": false,
  "error": {
    "code": "host_error",
    "message": "Unable to load characters",
    "retryable": false
  }
}
```

An optional `message` may also be included in a failed response when the host
has an original `on_error` WebView event to preserve.

## Host integration

The React Native Lython request listener should:

1. Parse and validate the outer Lython request envelope.
2. Pass the inner `message` string directly to
   `RNWebviewApiService.handleLaylaApiMessage(message)`.
3. Capture the one terminal WebView API event for that command.
4. Encode that event as a JSON string in a success response envelope.
5. Call `Lython.respond(executionId, requestId, responseEnvelope)` exactly once.
6. Return an error envelope for malformed requests, unknown commands, handler
   errors, and `on_error` terminal events.

Commands that currently emit intermediate events must be adapted by the host
to produce a single terminal response. Intermediate chat tokens and image
generation progress are deliberately not part of this SDK.

## Request template

Future resource methods can share `OneShotRequestTemplate`, which binds an
existing WebView command name to its expected response event:

```python
from lython import LythonTransport, OneShotRequestTemplate

get_characters = OneShotRequestTemplate(
    command="get_characters",
    response_event="on_get_characters_response",
)

transport = LythonTransport(default_timeout=60.0)
characters = await get_characters.send_async(
    transport,
    {"offset": 0, "limit": 10},
)
```

`LythonTransport` lazily imports `lython_native`, so protocol code and tests can
run in an ordinary Python environment. Tests can inject a fake native module.

The async API uses `asyncio.to_thread()` because `lython_native.request()` is a
blocking native call. Cancelling the awaiting task does not cancel the native
request; the finite native timeout still bounds its lifetime.

## Development

The runtime package has no third-party dependencies. Tests use `unittest` from
the standard library:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```
