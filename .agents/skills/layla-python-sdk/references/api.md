# Lython one-shot API reference

This reference describes the embedded Python API. Methods are synchronous
unless suffixed with `_async`. Ordinary resource methods accept keyword-only
`timeout: float | None`; every host-calling synchronous method has an `_async`
counterpart. The public API uses snake_case exclusively and provides no
camelCase aliases. Requests wait indefinitely by default; pass a finite timeout
to impose a native deadline.

## Contents

- [Characters](#characters)
- [Chat](#chat)
- [Classifier and images](#classifier-and-images)
- [Nightmare Mobile video](#nightmare-mobile-video)
- [Memories and personas](#memories-and-personas)
- [TTS and files](#tts-and-files)
- [Execution context](#execution-context)
- [WebView automation](#webview-automation)
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
    prompt, img2img_base64=None, model_id=None, *, reference_images=None, timeout=None
) -> str | None
```

Image models have `id`, `name`, and `description`. Generated images and
`img2img_base64` use complete data URIs. Generation is final-only; progress
events are intentionally unavailable.

`reference_images` accepts a sequence of complete base64 image data URIs and
sends the `reference_images` wire field in order. It can be combined with the
img2img base. `None` omits it; `[]` sends an empty list. The host rejects raw
base64/remote URLs and unsupported image models with `LythonHostError`. Reference
editing requires host support; older hosts may ignore the field. The same
keyword is available on `generate_image_async`.

## Nightmare Mobile video

```python
lython.nightmare_mobile.get_models(*, timeout=None) -> list[dict]
lython.nightmare_mobile.generate_video(
    model_id, prompt, *, negative_prompt=None, width=None, height=None,
    frames=None, fps=None, seed=None, image_data_base64=None,
    end_image_data_base64=None, denoise_strength=None, timeout=None
) -> dict
```

The resource class `NightmareMobile` and the package-level `nightmare_mobile`
instance are exported from `lython`. Explicit `LythonClient` instances have the
same resource. Methods also have `get_models_async` and `generate_video_async`
forms. The commands are `nightmaremobile_get_models` (data is `None`) and
`nightmaremobile_generate_video`; they wait for their respective
`on_nightmaremobile_*_response` terminal events. No progress events or callbacks
are exposed to Python.

Catalog entries include missing/downloading models (`downloaded: False`) and
follow content visibility settings. Fields: `id`, `name`, `description`,
`downloaded`, `start_image` (`none`/`optional`/`required`), `end_image`,
`size_presets` (width/height mappings), `size_multiple`, `min_size`, `max_size`,
`max_area`, `trained_fps`, `max_duration`, `frame_options`, `fps_options`.
Capabilities/limits describe the mini-app UI and are advisory for API callers.

Only supplied generation controls override the latest UI-saved `sdcpp.json`.
`None` is omitted; empty negative prompts and zero seeds/strength are preserved.
Omitted start/end images and previews are inherited. LoRAs and sampling remain
in the saved config. There are no duration, aspect-ratio, sampler, steps, CFG,
sigma, or LoRA arguments. The host applies basic type/value validation and lets
the engine determine capability support.

Image inputs are complete base64 image data URIs. `width`/`height` and `frames`
are positive integers; `fps` is a positive finite number. `seed` takes `-1` for
random or an unsigned 64-bit integer/decimal string. Python integers outside
JavaScript's safe integer range are encoded as decimal strings. Results contain
`model_id`, `video_data_base64` (with `data:video/mp4;base64,`), a string `seed`,
`width`, `height`, `frame_count`, `fps`, `duration_ms`, `generation_time_ms`.
The clip also stays in Nightmare Mobile history.

Calls wait indefinitely by default; supply a finite native `timeout` for a
deadline. Async cancellation does not stop native generation. Errors use the
existing `LythonHostError` / `LythonTimeoutError` handling. Requires a Layla host
implementing both Nightmare Mobile commands.

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

## WebView automation

The package-level `lython.page` and `LythonClient.page` control Layla's single
host-owned WebView. Browser API timeouts use milliseconds, matching Playwright.
An omitted timeout uses the host's default watchdog (currently 30 seconds), and
zero disables the host watchdog. A separately configured native transport
timeout can still end the request.

```python
lython.page.goto(url, timeout=None) -> str
lython.page.wait_for_url(url, wait_until="load", timeout=None) -> None
lython.page.wait_for_load_state(state="load", timeout=None) -> None
lython.page.evaluate(expression, arg=<omitted>, timeout=None) -> JSON value
lython.page.content(timeout=None) -> str
lython.page.title(timeout=None) -> str
lython.page.wait_for_function(
    expression, arg=<omitted>, polling="raf", timeout=None
) -> JSON value
lython.page.wait_for_timeout(timeout) -> None
lython.page.wait_for_selector(
    selector, state="visible", timeout=None
) -> Locator | None
lython.page.locator(selector) -> Locator
```

Page selector helpers are `click`, `press`, `fill`, `text_content`, `inner_text`,
`inner_html`, `get_attribute`, and `is_visible`. Locators provide `wait_for`,
the same action/read helpers, plus `input_value`, `count`, and
`all_text_contents`. `click` and `press` accept `no_wait_after: bool | None` and
wait for navigation by default. Every host-calling method has an `_async`
counterpart.

`evaluate` uses Playwright's expression-and-argument form. An omitted argument
invokes a function with no argument; explicit `None` becomes JavaScript `null`.
The expression may return a Promise. Arguments and results must be JSON values,
and JavaScript `undefined` is normalized to `None`. DOM nodes and other remote
handles must be projected to plain data within the expression.

`wait_for_url` accepts `*`, `**`, and `?` glob patterns and checks the current
loaded URL before observing future top-frame loads. `wait_for_load_state`
currently supports `"load"`. Raw `evaluate` does not wait for navigation.

`wait_for_selector` and locator actions wait inside the WebView rather than
polling through React Native. Supported states are `attached`, `detached`,
`visible`, and `hidden`. Selector and function waits retry after a document is
replaced while preserving the original overall timeout.

For a stable GET-style search or filter endpoint, build the URL with
`urllib.parse.urlencode()` and navigate directly instead of filling and
submitting a form. Use locator actions for page-only state such as a results tab.

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
