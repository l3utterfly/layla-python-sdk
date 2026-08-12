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

## Keep embedded-script output executor-friendly

Treat stdout as the result channel consumed by the calling LLM. Print the final
successful result in a concise, self-contained format such as JSON or clearly
labeled Markdown. Send progress updates, selector diagnostics, and other debug
information through `lython.notify(message)`. Reserve stderr exclusively for
genuine errors that prevent the script from producing its result.

Never call `sys.exit()`, `exit()`, or raise `SystemExit` in a Lython script.
Layla's embedded executor treats `SystemExit`, including `SystemExit(0)`, as an
execution error and can discard the successful stdout result. On an expected
failure, print an actionable error to stderr and return normally. Let an
unexpected exception propagate only when the caller needs the execution to be
reported as failed.

```python
import json
import sys

import lython

lython.notify("Starting task")
try:
    result = run_task()
except ExpectedTaskError as error:
    print(f"Task failed: {error}", file=sys.stderr, flush=True)
else:
    print(json.dumps(result, ensure_ascii=False))
```

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

Prefer direct navigation when a search or filter is represented by a stable
GET-style URL. Encode parameters instead of manually concatenating user input,
then use locator actions only for state that must be selected in the page:

```python
from urllib.parse import urlencode

search_url = "https://www.google.com/search?" + urlencode({"hl": "en", "q": query})
lython.page.goto(search_url, timeout=30_000)
lython.page.locator('a[href*="tbm=nws"], a[href*="udm=5"]').click(timeout=30_000)
```

Do not fill and submit a search form merely to reach the same deterministic
URL. If the site does not expose stable URL parameters, use `fill()` plus
`click()` or `press()` normally.

Available helpers include navigation, URL/load-state waits, HTML/title reads,
clicks, key presses, fills, text and HTML reads, attributes, input values,
visibility, counts, selector waits, function waits, and timeout waits. Use the
`_async` counterpart in asyncio workflows. Locator operations re-query their
CSS selector for every call.

Keep `evaluate()` navigation-unaware. Locator `click()` and `press()` arm the
host navigation watcher unless `no_wait_after=True`. Use `wait_for_url()` when
the destination matters. Selector and function waits retry across document
replacement within their original overall timeout; never replay arbitrary
evaluations because they may have side effects.

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

