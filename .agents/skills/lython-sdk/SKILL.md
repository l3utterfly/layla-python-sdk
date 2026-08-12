---
name: lython-sdk
description: Use the project-local `lython` Python SDK to call Layla's embedded one-shot APIs and automate Layla's host-owned WebView. Trigger when writing, reviewing, testing, or debugging Python that imports `lython`; building Lython scripts or agents; using `lython.page`, Playwright-like page or locator helpers, JavaScript evaluation, DOM automation, navigation, clicks, fills, or page-side waits; or accessing Layla characters, final chat completions, inference engines, chat history and schedules, sentiment, image generation, memories, personas, TTS, private files, or execution context. Do not use for the TypeScript `@layla-network/sdk`, React Native host/controller implementation, streaming responses, contextual event subscriptions, background audio, or unrelated Python work.
---

# Lython SDK

Use `lython` as the standard-library-only Python client for code running inside
Layla's embedded Python runtime. Prefer its high-level resource objects over the
private `lython_native` module or raw protocol messages.

## Work from the current project

1. Read [references/api.md](references/api.md) before choosing method signatures,
   return fields, or chat/image input shapes.
2. Treat `src/lython/resources.py`, `src/lython/browser.py`, and
   `src/lython/__init__.py` as the source of truth if the reference and
   implementation differ.
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
finite default timeout:

```python
from lython import LythonClient, LythonTransport

client = LythonClient(LythonTransport(default_timeout=120))
history = client.chat.get_chat_history("session-id")
```

Ordinary resource requests wait indefinitely by default. Supply a finite
`timeout` when an operation needs a deadline. Cancelling an awaiting task does
not cancel the underlying native request; only an explicit native timeout
bounds the worker thread. WebView operations have an independent host watchdog
described below.

## Automate Layla's WebView

Use the package-level `lython.page` for Layla's single host-owned automation
WebView. Do not create a browser process, use Playwright itself, call
`lython_native` directly, or construct raw `{cmd, data}` messages when the
high-level API covers the operation.

Use raw evaluation when custom DOM logic is needed. Its calling form matches
Playwright's `page.evaluate(expression, arg)`:

```python
import lython

lython.page.goto("https://example.com", timeout=30_000)
text = lython.page.evaluate(
    "selector => document.querySelector(selector)?.textContent",
    ".result",
)
```

An omitted argument is distinct from explicit `None`. The expression may
return a Promise, which the host awaits. Arguments and results must be JSON
serializable; JavaScript `undefined` becomes Python `None`. Project DOM nodes,
functions, and other JavaScript objects to plain data before returning because
Lython does not expose remote JS or element handles.

Prefer `Page` and `Locator` helpers for common operations:

```python
lython.page.fill("input[name=email]", "user@example.com")
lython.page.click("button[type=submit]")
lython.page.wait_for_selector(".result", state="visible", timeout=10_000)

items = lython.page.locator(".result-item")
texts = items.all_text_contents()
```

Available helpers include navigation, HTML/title reads, clicks, fills, text and
HTML reads, attributes, input values, visibility, counts, selector waits,
function waits, and timeout waits. Use the `_async` counterpart in asyncio
workflows. Locator operations re-query their CSS selector for every call.

Browser timeouts use Playwright's millisecond convention, unlike ordinary
Lython resource timeouts, which use seconds. Selector and function waits run as
Promises inside the WebView; do not implement Python-side or React Native-side
polling. An omitted browser timeout uses the host watchdog, currently 30
seconds, and zero disables that host watchdog. A configured native transport
timeout remains independent.

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
- Use `lython.notify(message)` for the intentional fire-and-forget host
  notification path. It calls `lython_native.send()` directly and therefore
  has no timeout or `_async` counterpart.
- Do not expose background-audio controls because they are fire-and-forget and
  event-driven.
- Return the documented dictionaries and lists; do not replace them with
  incompatible model classes.
- Keep the public Python API exclusively snake_case. Do not add camelCase
  compatibility aliases.

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

