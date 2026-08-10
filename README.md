# Lython SDK

`lython` is the standard-library-only Python SDK for code running inside
Layla's embedded Python runtime. It wraps the private `lython_native` string
transport with the existing JSON-encoded Layla WebView message format.

The SDK mirrors the one-shot API surface of `@layla-network/sdk` 7.2.2 and also
provides a fire-and-forget host notification API. It does not provide streaming
responses, progress events, or contextual subscriptions.

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

lython.notify("Import complete")
```

`lython.notify(message)` passes the string directly to `lython_native.send()`
and returns `None` as soon as the native call finishes dispatching it. It does
not create a request ID, encode a `{cmd, data}` message, wait for a response, or
accept a timeout. Because there is nothing to await, it has no `_async`
counterpart. Use `client.notify(message)` when working with an explicit
`LythonClient`.

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

Requests are the existing React Native WebView API messages. For example,
`lython_native.request()` receives this JSON string directly:

```json
{"cmd":"get_characters","data":{"offset":0,"limit":10}}
```

The native request ID is passed separately to `lython_native.request()` and is
not duplicated in the JSON message. The host returns the terminal WebView event
directly:

```json
{"event":"on_get_characters_response","data":[]}
```

Host failures use the existing `on_error` event:

```json
{"event":"on_error","data":{"message":"Unable to load characters"}}
```

## Host integration

The React Native Lython request listener should:

1. Pass the request JSON string directly to
   `RNWebviewApiService.handleLaylaApiMessage(message)`.
2. Capture the one terminal WebView API event for that command.
3. Encode that event directly as a JSON string.
4. Call `Lython.respond(executionId, requestId, responseMessage)` exactly once.
5. Return an `on_error` event for malformed requests, unknown commands, and
   handler errors.

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

## Releases

GitHub Releases contain a universal Python wheel and a source distribution.
To publish a release:

1. Update `project.version` in `pyproject.toml` and commit the change.
2. Create a matching tag, such as `v0.1.0` for package version `0.1.0`.
3. Push the tag to GitHub.

The release workflow runs the test suite, builds and checks both distributions,
and then creates the GitHub Release with automatically generated notes. A tag
that does not match `project.version` is rejected.

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.
