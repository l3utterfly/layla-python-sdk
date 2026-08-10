---
name: lython-sdk
description: Use the project-local `lython` Python SDK to call Layla's embedded one-shot APIs. Trigger when writing, reviewing, testing, or debugging Python that imports `lython`; building Lython scripts or agents; or accessing Layla characters, final chat completions, inference engines, chat history and schedules, sentiment, image generation, memories, personas, TTS, private files, or execution context. Do not use for the TypeScript `@layla-network/sdk`, React Native host implementation, streaming responses, contextual event subscriptions, background audio, or unrelated Python work.
---

# Lython SDK

Use `lython` as the standard-library-only Python client for code running inside
Layla's embedded Python runtime. Prefer its high-level resource objects over the
private `lython_native` module or raw protocol messages.

## Work from the current project

1. Read [references/api.md](references/api.md) before choosing method signatures,
   return fields, or chat/image input shapes.
2. Treat `src/lython/resources.py` and `src/lython/__init__.py` as the source of
   truth if the reference and implementation differ.
3. Check `README.md` for the current host-side one-shot response contract when
   diagnosing integration behavior.
4. Preserve the existing `{cmd, data}` wire payloads. Do not invent HTTP
   endpoints, API keys, base URLs, or alternate command names.

## Choose the calling style

Use the package-level resources for ordinary embedded scripts:

```python
import lython

characters = lython.characters.list()
persona = lython.personas.get()
```

Use the `_async` counterpart inside an asyncio workflow. It moves the blocking
native request to a worker thread:

```python
characters = await lython.characters.list_async(timeout=60)
```

Use `LythonClient` only when injecting a transport for tests or configuring a
different default timeout:

```python
from lython import LythonClient, LythonTransport

client = LythonClient(LythonTransport(default_timeout=120))
history = client.chat.get_chat_history("session-id")
```

Supply a finite `timeout` when a request may take longer or shorter than the
default 60 seconds. Cancelling an awaiting task does not cancel the underlying
native request; its native timeout still bounds the worker thread.

## Keep chat final-only

Call only `lython.chat.completions.create(...)` or `create_async(...)`. Return
the OpenAI-shaped final `chat.completion` dictionary and read text from:

```python
completion = lython.chat.completions.create(
    messages=[{"role": "user", "content": "Give me one chess tip."}]
)
text = completion["choices"][0]["message"]["content"]
reasoning = completion["choices"][0]["message"].get("reasoning")
```

Never add or emulate a streaming iterator. Reject `stream=True`. The host must
consolidate tokens into the terminal `on_message_end` response; Lython does not
receive token events. Preserve OpenAI content-part input for images, including
one base64 image data URL at most per message.

## Respect the one-shot boundary

- Use final-only image generation; do not add progress callbacks or events.
- Use `contextual.get_execution_context`; do not add contextual `on`/`off`
  subscriptions.
- Do not expose background-audio controls because they are fire-and-forget and
  event-driven.
- Return dictionaries and lists matching the TypeScript SDK's one-shot
  projections; do not replace them with incompatible model classes.
- Keep snake_case as the primary Python API. Existing camelCase aliases are for
  TypeScript-path familiarity.

## Handle SDK errors

Catch the narrowest Lython exception needed. Use `LythonHostError` for a host
failure, `LythonTimeoutError` for native timeouts, and
`LythonNativeUnavailableError` when code is running outside Layla. All SDK
exceptions inherit from `LythonError`.

Do not hide protocol errors or silently fall back to mock results in production
code.

## Verify changes

When changing SDK usage, exercise the relevant response shape. When changing
this package or its skill, run:

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m unittest discover -s tests -v
```

For tests outside Layla, inject a fake native module through `LythonTransport`;
do not import or monkey-patch the private `lython_native` module globally.

