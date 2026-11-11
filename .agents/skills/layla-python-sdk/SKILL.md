---
name: layla-python-sdk
description: Use the project-local `lython` Python SDK to call Layla's embedded one-shot APIs and automate Layla's host-owned WebView. Trigger when writing, reviewing, testing, or debugging Python that imports `lython`; building Lython scripts or agents; using `lython.page`, Playwright-like page or locator helpers, JavaScript evaluation, DOM automation, navigation, clicks, fills, or page-side waits; or accessing Layla characters, final chat completions, inference engines, chat history and schedules, sentiment, image generation and reference editing, Nightmare Mobile video generation, memories, personas, TTS, private files, or execution context. Do not use for the TypeScript `@layla-network/sdk`, React Native host/controller implementation, streaming responses, contextual event subscriptions, background audio, or unrelated Python work.
---

# Layla Python SDK (`lython`)

`layla-python-sdk` is the distribution; it imports as `lython`. It is the
standard-library-only client for code running **inside Layla's embedded Python
runtime**. There is no HTTP client, API key, or base URL — every call rides
Layla's private `lython_native` string transport as a `{cmd, data}` message.

Always prefer the high-level resource objects over the private `lython_native`
module or hand-built protocol messages.

## Before you write code

1. Read [references/api.md](references/api.md) for exact signatures, return
   fields, and chat/image input shapes.
2. If the reference and the code disagree, the code wins:
   `src/lython/resources.py`, `src/lython/browser.py`, `src/lython/__init__.py`.
3. Check `README.md` for the host-side one-shot response contract when
   diagnosing integration behavior.
4. Never invent HTTP endpoints, API keys, base URLs, or new command names.
   Preserve the `{cmd, data}` wire payloads.

## What's in the package

| Resource | Covers |
| --- | --- |
| `lython.chat` | Final chat completions, inference engines, history, sessions, scheduled messages |
| `lython.characters` | List, image, create/update (Character Card V2) |
| `lython.classifier` | Sentiment scores |
| `lython.images` | Generation models, final-only image generation and reference editing |
| `lython.nightmare_mobile` | WAN model catalog and final-only video generation |
| `lython.memories` | List, top memories, create/update |
| `lython.personas` | Global or per-character persona |
| `lython.tts` | Voices, speak, speak-to-file, stop |
| `lython.utils` | Save/read private files (base64) |
| `lython.contextual` | One-shot execution context |
| `lython.page` | Host-owned WebView automation (Playwright-like) |
| `lython.notify` | Fire-and-forget host notification |

## Pick a calling style

**Package-level resources** — the default for ordinary embedded scripts:

```python
import lython

characters = lython.characters.list()
persona = lython.personas.get()
```

**`_async` counterpart** — inside an asyncio workflow. Every host-calling
synchronous method has one; it runs the blocking native request on a worker
thread:

```python
characters = await lython.characters.list_async(timeout=60)
```

**`LythonClient`** — only to inject a transport for tests or set a finite
default timeout:

```python
from lython import LythonClient, LythonTransport

client = LythonClient(LythonTransport(default_timeout=120))
history = client.chat.get_chat_history("session-id")
```

### Reference editing and Nightmare Mobile video

Use `lython.images.generate_image(..., reference_images=[image_data_uri])` for
native reference editing. References are a keyword-only sequence of complete
base64 image data URIs, preserving order; they may be combined with
`img2img_base64`. `None` omits the field, `[]` sends an empty list. On supported
hosts, a non-empty list with an unsupported image model raises `LythonHostError`.
Older hosts may ignore reference images.

Use `lython.nightmare_mobile.get_models()` to list IDs, download state, and
advisory UI capabilities. `generate_video(model_id, prompt, *, width=None,
height=None, frames=None, fps=None, ...)` generates a WAN MP4. Both have `_async`
counterparts. Choose a downloaded model for generation.

```python
video = lython.nightmare_mobile.generate_video(
    "wan22_ti2v_turbo", "An apple gently turns on a wooden table",
    width=512, height=320, frames=25, fps=24, seed=42,
    image_data_base64=source_image_data_uri, timeout=900,
)
print(video["model_id"], video["seed"], video["frame_count"])
```

The host applies supplied controls over the latest UI-saved `sdcpp.json`.
Omitted options, including saved images and previews, are inherited. Capability
limits are advisory: do not reject API values based on them. Expose no duration,
aspect-ratio, LoRA, sampler, step, CFG, or sigma options. Image inputs and the MP4
output include their data URI prefixes. The returned seed is a decimal string;
large Python integer seeds are encoded as strings to preserve 64-bit precision
across the JavaScript host. See `references/api.md` for all fields and options.

Video generation is final-only, with no progress callbacks/events. Async
cancellation does not cancel native generation. The host must implement the
two `nightmaremobile_*` commands.

### Timeouts

- Resource calls **wait indefinitely** by default. Pass a finite `timeout`
  (seconds) to impose a native deadline.
- Cancelling an awaiting task does **not** cancel the underlying native request.
  Only an explicit native timeout bounds the worker thread.
- WebView timeouts are separate: milliseconds, with their own host watchdog
  (see below).

## Keep output executor-friendly

Layla's executor and the calling LLM consume **stdout as the result channel**.

- **stdout** — print the final successful result only, in a concise
  self-contained form (JSON or clearly labeled Markdown).
- **`lython.notify(message)`** — progress updates, selector diagnostics, debug.
- **stderr** — genuine errors that prevented a result.

**Never call `sys.exit()`, `exit()`, or raise `SystemExit`.** The executor
treats `SystemExit` — including `SystemExit(0)` — as a failure and can discard a
successful stdout result. On an expected failure, print an actionable message to
stderr and return normally. Let an unexpected exception propagate only when the
caller should see the run as failed.

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

## Chat is final-only

Call only `lython.chat.completions.create(...)` / `create_async(...)`. It
returns an OpenAI-shaped `chat.completion` dict:

```python
completion = lython.chat.completions.create(
    messages=[{"role": "user", "content": "Give me one chess tip."}]
)
text = completion["choices"][0]["message"]["content"]
reasoning = completion["choices"][0]["message"].get("reasoning")
```

- **Reject `stream=True`** (it raises `LythonError`) and never emulate a
  streaming iterator. The host consolidates tokens into the terminal
  `on_message_end` response; Lython never sees token events.
- Preserve OpenAI content-part input for images: at most **one** base64 image
  data URL per message (PNG/JPEG/GIF/WebP; remote URLs rejected).

## Automate the WebView

`lython.page` drives Layla's single host-owned automation WebView. Do not start
a browser process, use Playwright itself, call `lython_native`, or build raw
`{cmd, data}` messages when the high-level API covers the operation.

**Prefer `Page`/`Locator` helpers** for common operations:

```python
lython.page.fill("input[name=email]", "user@example.com")
lython.page.click("button[type=submit]")
lython.page.wait_for_selector(".result", state="visible", timeout=10_000)

items = lython.page.locator(".result-item")
texts = items.all_text_contents()
```

Helpers cover navigation, URL/load-state waits, HTML/title reads, clicks, key
presses, fills, text/HTML reads, attributes, input values, visibility, counts,
selector waits, function waits, and timeout waits. Each has an `_async`
counterpart. Locators re-query their CSS selector on every call.

**Prefer direct navigation** when a search or filter maps to a stable GET URL.
Encode parameters instead of concatenating user input, then use locator actions
only for state that must be selected in the page:

```python
from urllib.parse import urlencode

search_url = "https://www.google.com/search?" + urlencode({"hl": "en", "q": query})
lython.page.goto(search_url, timeout=30_000)
lython.page.locator('a[href*="tbm=nws"], a[href*="udm=5"]').click(timeout=30_000)
```

Don't fill and submit a form just to reach the same deterministic URL. If the
site exposes no stable URL parameters, use `fill()` + `click()`/`press()`.

**Use `evaluate()` for custom DOM logic.** Its form matches Playwright's
`page.evaluate(expression, arg)`:

```python
text = lython.page.evaluate(
    "selector => document.querySelector(selector)?.textContent",
    ".result",
)
```

- An omitted argument differs from explicit `None` (`None` becomes JS `null`).
- The expression may return a Promise; the host awaits it.
- Arguments and results must be JSON-serializable; JS `undefined` becomes Python
  `None`. Project DOM nodes, functions, and other JS objects to plain data
  inside the expression — Lython exposes no remote handles.

**Navigation and waits:**

- `evaluate()` is navigation-unaware. Locator `click()`/`press()` arm the host
  navigation watcher unless `no_wait_after=True`. Use `wait_for_url()` when the
  destination matters.
- Selector and function waits retry across document replacement within their
  original overall timeout, and run as Promises inside the WebView. Do not add
  Python- or React Native-side polling. Never replay arbitrary evaluations to
  wait — they may have side effects.
- Browser timeouts are **milliseconds** (Playwright convention), unlike
  resource timeouts (seconds). An omitted browser timeout uses the host watchdog
  (currently 30 s); `0` disables it. A configured native transport timeout stays
  independent.

See [examples/google_news_search.py](../../../examples/google_news_search.py)
for a complete WebView automation script.

## Respect the one-shot boundary

Layla's embedded APIs are request/response only — there are no event streams or
callbacks. Do not try to add them.

- Image and video generation are final-only; no progress callbacks or events.
- Use `lython.contextual.get_execution_context`; there are no contextual
  `on`/`off` subscriptions.
- `lython.notify(message)` is the intentional fire-and-forget path. It calls
  `lython_native.send()` directly, so it has no timeout and no `_async` form.
- Do not expose background-audio controls (fire-and-forget, event-driven).
- Return the documented dicts and lists; do not swap in incompatible model
  classes.
- Keep the public Python API **snake_case only**. No camelCase aliases.

## Handle errors

All SDK exceptions inherit from `LythonError`:

```text
LythonError
├── LythonProtocolError
├── LythonHostError
└── LythonTransportError
    ├── LythonNativeUnavailableError   # running outside Layla
    ├── LythonTimeoutError             # native timeout elapsed
    └── LythonExecutionError
```

Catch the narrowest exception the situation needs. Do not hide protocol errors
or silently fall back to mock results in production code.

## Verify changes

When changing SDK usage, exercise the relevant response shape. When changing
this package or its skill, run the tests:

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m unittest discover -s tests -v
```

For tests outside Layla, inject a fake native module through `LythonTransport`
(`LythonClient(LythonTransport(native_module=fake))`). Do not import or
monkey-patch the private `lython_native` module globally.
