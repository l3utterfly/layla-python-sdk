# Layla Python SDK

<table>
  <tr>
    <td>
      <img src="assets/layla.png" alt="Layla butterfly logo" width="160">
    </td>
    <td>
      <code>layla-python-sdk</code> is the standard-library-only Python SDK distribution for code running inside Layla's embedded Python runtime. It is imported as <code>lython</code> and communicates with the Layla host through the private <code>lython_native</code> string transport, exposing one-shot APIs for characters, chat completions, inference engines, chat history and sessions, scheduled chat messages, sentiment classification, image generation and reference editing, Nightmare Mobile video generation, memories, personas, TTS, private files, execution context, and Playwright-style WebView automation.
    </td>
  </tr>
</table>

`layla-python-sdk` is the standard-library-only Python SDK distribution for
code running inside Layla's embedded Python runtime. It is imported as
`lython` and communicates with the Layla host through the private
`lython_native` string transport.

Real API calls only work inside an active Layla embedded Python execution.
There is no HTTP endpoint, API key, or base URL. The package requires Python
3.14 or newer and has no third-party runtime dependencies.

## Contents

- [Installation](#installation)
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
- [Nightmare Mobile video generation](#nightmare-mobile-video-generation)
- [Memories](#memories)
- [Personas](#personas)
- [Text to speech](#text-to-speech)
- [Private files](#private-files)
- [Execution context](#execution-context)
- [WebView automation](#webview-automation)
- [Notifications](#notifications)
- [Explicit clients and timeouts](#explicit-clients-and-timeouts)
- [Low-level APIs](#low-level-apis)
- [Errors](#errors)
- [Runtime limitations](#runtime-limitations)
- [Host integration](#host-integration)
- [Development and releases](#development-and-releases)

## Installation

Install the `layla-python-sdk` distribution from PyPI:

```console
pip install layla-python-sdk
```

The distribution is imported in Python as `lython`.

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
`memories`, `personas`, `tts`, `utils`, `contextual`, and `page`.

Every ordinary one-shot resource method:

- is synchronous by default;
- accepts a keyword-only `timeout: float | None` argument;
- has an async counterpart with an `_async` suffix; and
- returns ordinary dictionaries, lists, strings, or `None`.

Ordinary Layla API timeouts are measured in seconds. `page` and `locator`
timeouts use Playwright's millisecond convention.

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
| `nightmare_mobile` | `get_models_async`, `generate_video_async` |
| `memories` | `list_async`, `get_top_memories_async`, `create_or_update_async` |
| `personas` | `get_async` |
| `tts` | `get_voices_async`, `generate_voice_async`, `generate_voice_to_file_async`, `stop_speaking_async` |
| `utils` | `save_file_async`, `read_file_async` |
| `contextual` | `get_execution_context_async` |
| `page` | `goto_async`, `evaluate_async`, `evaluate_all_frames_async`, `frames_content_async`, `content_async`, `title_async`, `wait_for_url_async`, `wait_for_load_state_async`, `wait_for_function_async`, `wait_for_function_all_frames_async`, `wait_for_timeout_async`, `wait_for_selector_async`, `click_async`, `press_async`, `fill_async`, `text_content_async`, `inner_text_async`, `inner_html_async`, `get_attribute_async`, `is_visible_async` |
| `locator` | `wait_for_async`, `click_async`, `press_async`, `fill_async`, `text_content_async`, `inner_text_async`, `inner_html_async`, `get_attribute_async`, `input_value_async`, `is_visible_async`, `count_async`, `all_text_contents_async` |

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
| `nightmare_mobile` | `get_models`, `generate_video` | WAN model catalog or final MP4 data URI and metadata |
| `memories` | `list`, `get_top_memories`, `create_or_update` | Memory dictionaries |
| `personas` | `get` | Persona dictionary |
| `tts` | `get_voices`, `generate_voice`, `generate_voice_to_file`, `stop_speaking` | Voice data, file result, or `None` |
| `utils` | `save_file`, `read_file` | Private-file result |
| `contextual` | `get_execution_context` | Execution context or `None` |
| `page` | `goto`, `evaluate`, `content`, `title`, waits, and selector helpers | JSON values and page data |
| `locator` | waits, actions, text, attributes, visibility, and counts | JSON-compatible element data |
| Package/client | `notify` | `None` (fire-and-forget) |

The sections below document the high-level operations. Add `_async` to a
host-calling method name and `await` it to use its async counterpart. `notify`
is the exception because it does not wait for a response.

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

With the keyword form, OpenAI options can be passed directly:

```python
completion = lython.chat.completions.create(
    messages=messages, tools=tools, tool_choice="auto", temperature=0.2,
)
```

Final replies decode `<think>` and `<tool_call>` markup. Tool calls appear in
`choices[0]["message"]["tool_calls"]`, with JSON-string `function.arguments` and
`finish_reason: "tool_calls"`. Visible content excludes the markup. Arguments
can be incomplete or invalid JSON: parse and validate them before use. Every
constructed completion includes `message.refusal: None` and `choice.logprobs:
None`. Already structured host completions are preserved.


### Image input

Chat accepts OpenAI-style content parts, including multiple base64 image data
URIs per message on Layla 7.5 and newer:

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

On Layla 7.5 and newer, the complete OpenAI request body is forwarded unchanged
except for the host-internal `stream` flag. Tools, tool result IDs, sampling and
response-format options, optional assistant content, and multiple image parts
are preserved. The host decides which model features it supports.

The SDK probes the host version once per client, with a maximum two-second
deadline, and falls back to legacy chat when the probe fails or the host is
older. Legacy translation maps `developer` to `system`, keeps one PNG/JPEG/GIF/
WebP base64 image per message, joins text parts with newlines, and warns when
unsupported images, content parts, or tool/function messages are ignored.

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

For native reference-image editing, pass `reference_images` as a keyword-only
sequence of complete base64 image data URIs. References preserve their order
and can be combined with the img2img base image:

```python
edited_image = lython.images.generate_image(
    "Turn the red apple green, keeping the composition unchanged",
    model_id="qwen-image-2.1-turbo-htp",
    reference_images=[source_image_data_uri],
    timeout=600,
)
```

Omit the argument or pass `None` to keep it off the wire; `[]` sends an empty
reference list. Raw base64 and remote URLs are not accepted by the host. A
non-empty list with an unsupported model raises `LythonHostError`. This needs
a host build implementing `generate_image.reference_images`; older hosts may
ignore it. `generate_image_async` accepts the same arguments. Existing
positional `prompt`, `img2img_base64`, and `model_id` calls remain compatible.

## Nightmare Mobile video generation

### `nightmare_mobile.get_models`

```python
models = lython.nightmare_mobile.get_models(timeout=30)
model = next((item for item in models if item["downloaded"]), None)
if model is None:
    raise RuntimeError("Download a WAN model in Nightmare Mobile first")
```

The catalog includes undownloaded models and follows the host's content
visibility settings. Entries contain `id`, `name`, `description`, `downloaded`,
`start_image`, `end_image`, `size_presets`, `size_multiple`, `min_size`,
`max_size`, `max_area`, `trained_fps`, `max_duration`, `frame_options`, and
`fps_options`. These capabilities and limits describe the UI and are advisory;
API inputs are not constrained by them.

### `nightmare_mobile.generate_video`

```python
video = lython.nightmare_mobile.generate_video(
    "wan22_ti2v_turbo",
    "The apple gently turns on a wooden table, fixed camera",
    width=512,
    height=320,
    frames=25,
    fps=24,
    seed=42,
    image_data_base64=source_image_data_uri,
    timeout=900,
)
print(video["model_id"], video["seed"], video["frame_count"])
```

`model_id` and `prompt` are required. All remaining arguments are keyword-only:
`negative_prompt`, `width`, `height`, `frames`, `fps`, `seed`,
`image_data_base64`, `end_image_data_base64`, `denoise_strength`, and `timeout`.
Options passed as `None` are omitted. Zero seeds/strength and empty negative
prompts are sent unchanged. Images must be complete base64 image data URIs.

The host reads the latest UI-saved `sdcpp.json` for every run and overrides only
supplied options. Omitted settings, including saved start/end images and
preview settings, are inherited. LoRAs, samplers, steps, CFG, and sigmas stay in
that saved configuration. Use `width`/`height` and `frames`/`fps`; there are no
aspect-ratio or duration request options. The host applies basic input checks,
while the engine determines what can run beyond the advisory model limits.

The returned mapping contains `model_id`, `video_data_base64` (a complete
`data:video/mp4;base64,` URI), `seed` (a decimal string), `width`, `height`,
`frame_count`, `fps`, `duration_ms`, and `generation_time_ms`. Python integer
seeds outside JavaScript's safe integer range are sent as decimal strings to
preserve precision; callers may also pass decimal strings directly. The
generated clip remains in the host's Nightmare Mobile history.

Both methods have `_async` counterparts with the same arguments and return
shapes. Python receives only the terminal response, with no progress callbacks
or events. Async cancellation does not stop native generation. Host failures
raise `LythonHostError`; native deadlines raise `LythonTimeoutError`. This
requires a Layla host implementing both `nightmaremobile_*` commands.

The repository's `lython_api_diagnostics.py` includes the reference-image
variant and WAN model-list/generation checks. It uses the pinned Qwen and WAN
model IDs above, skips them if unavailable, and reuses its generated image as
the reference/start image instead of requiring a separate image file.

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

## WebView automation

`lython.page` controls the WebView owned by the active Layla Python screen. It
implements a JSON-only subset of Playwright's synchronous `Page` and `Locator`
APIs; it does not create a browser process or expose remote element handles.

### Navigation and raw evaluation

```python
import lython
from urllib.parse import urlencode

final_url = lython.page.goto("https://example.com", timeout=30_000)
title = lython.page.evaluate("() => document.title")

search_url = "https://example.com/search?" + urlencode({"q": "Layla"})
lython.page.goto(search_url, timeout=30_000)
lython.page.locator('a[href*="section=news"]').click(timeout=30_000)
```

`evaluate(expression, arg)` follows Playwright's calling form. If the
expression evaluates to a function, the host invokes it with `arg` and awaits
its result. Omitting `arg` is distinct from explicitly passing `None`. Arguments
and results must be JSON serializable; JavaScript `undefined` returns `None`.
Browser timeouts are milliseconds. Omitting one uses the host controller's
default watchdog (currently 30 seconds); zero disables that host watchdog.
Raw `evaluate()` deliberately does not infer or wait for navigation.

`wait_for_url()` accepts Playwright-style `*`, `**`, and `?` glob patterns and
is race-safe: it checks the current loaded URL before waiting for a future
top-frame load. `wait_for_load_state()` currently supports the WebView's
observable `"load"` state.

When a search or filter has a stable GET-style URL, construct that URL with
`urllib.parse.urlencode()` and call `goto()` instead of filling a form and
submitting it. This removes an unnecessary interaction and its associated
navigation race. Use locator actions for state that is only reachable from the
loaded page, such as selecting a results vertical or tab.

### Page and locator helpers

```python
lython.page.fill("input[name=email]", "user@example.com")
lython.page.click("button[type=submit]")
lython.page.wait_for_selector(".result", state="visible", timeout=10_000)
print(lython.page.text_content(".result"))

items = lython.page.locator(".result-item")
print(items.count())
print(items.all_text_contents())
```

Page helpers include `content`, `title`, `wait_for_url`, `wait_for_load_state`,
`wait_for_function`, `wait_for_timeout`, `wait_for_selector`, `click`, `press`,
`fill`, `text_content`, `inner_text`, `inner_html`, `get_attribute`, and
`is_visible`. A locator adds `wait_for`, `input_value`, `count`, and
`all_text_contents`. Locator operations re-query their CSS selector each time.

Locator `click()` and `press()` arm a top-frame navigation watcher before the
action and wait for any navigation they initiate. Pass `no_wait_after=True` to
opt out. Selector/function waits are retried after a document replacement while
preserving their original overall timeout; arbitrary evaluations are never
replayed because they may have side effects.

Selector waits execute inside the WebView with page-side timers; React Native
does not poll across the bridge. Supported states are `attached`, `detached`,
`visible`, and `hidden`. Every operation has an `_async` counterpart.

`wait_for_timeout`, by contrast, sleeps on the host (like Playwright's
driver-side wait) rather than in the page — the WebView keeps running while it
waits. A page-side timer would be broadcast to every frame and could be inflated
or timed out by an unresponsive frame.

### All-frames helpers

`evaluate()` and the locator/selector helpers observe only the **top document**.
For content that lives inside a nested (often cross-origin) iframe — which the
top frame cannot reach through the DOM — use the all-frames helpers, which fan
the evaluation out across every frame and return one result per frame:

```python
# One result per frame (top document first, then every nested iframe).
for frame in lython.page.frames_content():
    print(frame.url, len(frame.content or ""))

results = lython.page.evaluate_all_frames("() => document.title")

# Poll a probe across all frames until one frame returns a truthy value. The
# probe must return immediately (it is polled from the host side), which is what
# lets it observe conditions inside iframes the top frame cannot see.
lython.page.wait_for_function_all_frames(
    "() => { const i = document.getElementById('resultImgEl');"
    " return i && (i.src || '').startsWith('data:image') ? i.src.length : 0; }",
    polling_ms=1_000,
    timeout=180_000,
)
```

Each result is a `FrameResult(url, content, error)`; `content` is `None` and
`error` is populated when that frame's evaluation raised (e.g. a sandboxed
iframe). `wait_for_function_all_frames` raises `LythonTimeoutError` if no frame
matches before the timeout. All three have `_async` counterparts.

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

The WebView controller has its own independent watchdog as described in
[WebView automation](#webview-automation).

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

## Additional one-shot public APIs

These methods mirror the public TypeScript SDK using Python snake_case names,
without streaming, event subscriptions, progress callbacks, or abort signals.
Every method below also has an `_async` counterpart and accepts keyword-only
`timeout` in seconds. Async calls still return one final result. Optional
`None` controls are omitted; `False`, zero and empty strings are preserved.

### Image tags

```python
lython.images.get_tag_dictionaries() -> list
lython.images.get_tags(dictionary_filename, *, offset=0, limit=50, category=None) -> dict
lython.images.get_tag(dictionary_filename, english) -> dict | None
lython.images.upsert_tag(dictionary_filename, tag, replacing=None) -> dict
lython.images.delete_tag(dictionary_filename, english) -> bool
lython.images.search_tags(dictionary_filename, query, *, mode=None, offset=0, limit=50, category=None) -> dict
lython.images.suggest_tags(dictionary_filename, query, *, limit=40) -> list
```

Use the dictionary filename returned by discovery. Tags and pages retain the
host's documented fields (`english`, aliases, translations, category, counts,
pagination). `get_tag` returns `None` when absent; `delete_tag` returns `False`
when already absent. `replacing` identifies the exact existing name to rename.
Search mode is `"name"` or `"prefix"`; a zero limit is forwarded to the host.

### NeoDragon video

```python
lython.neodragon.generate_video(
    image_data_base64, prompt, *, seed=None, upscale=None, fps=None,
    cinematic_prompt=None, crop=None,
) -> dict
```

The source is a complete base64 image data URI. `crop` has normalized `x`, `y`,
`width`, and `height`. The returned mapping contains `video_data_base64` (an MP4
data URI), seed, dimensions, frame count, FPS, duration and generation time.
Omitted controls use host defaults; `seed=0` and `upscale=False` remain valid.

### Ace-Step music and raw passes

```python
lython.acestep.get_models() -> list
lython.acestep.generate_music(prompt, lyrics=None, duration=None, *, model_id=None) -> str | None
lython.acestep.lm(request, *, model_id=None, use_gpu=None) -> list
lython.acestep.synth(request, *, model_id=None, use_gpu=None, use_flash_attn=None, vae_tile_size=None) -> dict
lython.acestep.understand(source, *, model_id=None, request=None, return_latents=None, use_gpu=None, use_flash_attn=None, vae_tile_size=None) -> dict
lython.acestep.vae_encode(audio_base64, *, model_id=None, request=None, use_gpu=None, vae_tile_size=None) -> dict
lython.acestep.vae_decode(latents_base64, *, model_id=None, request=None, use_gpu=None, vae_tile_size=None) -> dict
```

Choose a model with `ready_for_use: True`. `generate_music` returns an audio data
URI; duration is in seconds. The raw request mapping retains every model field,
including unknown fields, so LM/analysis results can be passed to `synth`.
Generation and raw passes queue within a client so the shared music engine
never runs overlapping passes. Chat completions likewise queue within a client.
Raw `request` keys match the engine contract (for example `caption`,
`audio_codes`, `output_format`, and `lm_temperature`). The synth result includes
inline audio, the resolved seed, and the resolved request.

`understand` takes exactly one source: `{"audio_base64": audio}` or
`{"latents_base64": latents}`. Audio may include a data URI prefix. Encoded
latents are base64 raw f32 `[T, 64]` bytes; they can be decoded or reused for
analysis. `return_latents=True` returns latents with audio-source analysis.
VAE results retain the host's audio/latents and metadata. No raw-pass output is
saved to private storage automatically. Use `utils.save_file` to keep it.

### Files, notifications, SQL and Cloud

```python
lython.utils.list_dir(path) -> list
lython.utils.delete_file_or_dir(path) -> None
lython.utils.schedule_notification(notification) -> dict
lython.utils.get_scheduled_notifications() -> list
lython.utils.cancel_scheduled_notification(id) -> dict
lython.db.execute_sql(query, params=None) -> dict
lython.cloud.login() -> str | None
```

File paths are relative to the calling app's private workspace. Pass `""` to
list its root; entries have `path` and `is_dir`. Deletion is recursive and waits
for acknowledgement. Private files and SQL require a host-provided workspace.

A notification mapping has `message`, a future Unix-millisecond `timestamp`,
and an optional relative `icon` path. Omitted/`None` icons use the default.
The result includes the host-assigned ID needed for cancellation. Listing
returns pending notifications belonging to the calling app.

SQL accepts bound parameters, e.g. `execute_sql("SELECT ?", [42])`. Results
retain `rows`, `rowsAffected`, and `insertId`. Cloud login returns the account's
access token or `None`; use it as a Bearer token in your own HTTP requests.

### Contextual questions and speech recognition controls

```python
lython.contextual.send_out_of_band_message(message, *, image_base64=None, json_schema=None) -> str
lython.stt.start_listening() -> None
lython.stt.stop_listening() -> None
```

An out-of-band question uses the current conversation without entering its
history. The optional image includes its data URI prefix; `json_schema` is a
schema mapping enforced only by engines that support constrained decoding.
The result is the host's final reply text.

STT controls only acknowledge starting/stopping the recognizer. Python does
not receive transcript events. Background-audio controls are excluded because
they have no terminal host response. No event or progress APIs are exposed.

The new resource classes `AceStep`, `NeoDragon`, `DB`, `Cloud`, and `STT`, and
their package instances, are exported from `lython` and available on explicit
`LythonClient` instances.

## Runtime limitations

- Chat completions are final-only; no streaming iterator is exposed.
- Image generation is final-only; no progress callbacks are exposed.
- Context lookup and out-of-band questions are one-shot; contextual `on`/`off` subscriptions are absent.
- Background-audio controls are absent because they are fire-and-forget and
  event-driven.
- WebView evaluation is JSON-only. DOM nodes, functions, cyclic objects, and
  other remote JavaScript handles cannot cross the bridge.
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

## Layla App

Visit the official Layla website: https://www.layla-network.ai/

Download the Layla app:

<p>
  <a href="https://play.google.com/store/apps/details?id=com.layla">
    <img src="./assets/google_badge.png" alt="Get it on Google Play" height="60">
  </a>
  &nbsp;&nbsp;
  <a href="https://apps.apple.com/us/app/layla/id6456886656">
    <img src="./assets/apple_badge.png" alt="Download on the App Store" height="60">
  </a>
</p>

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
