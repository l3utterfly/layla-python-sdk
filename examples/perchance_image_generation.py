"""Generate an image with Perchance's free AI image API from inside Layla.

This is a faithful port of the image-generation portion of the community
`perchance` library (https://github.com/eeemoon/perchance), which drives a
headless Playwright/Chromium browser. Here we drive Layla's single host-owned
automation WebView through ``lython.page`` instead. The network flow is
identical:

    1. goto  {BASE_URL}/verifyUser        -> the page issues a Perchance
                                             session cookie and embeds a
                                             short-lived ``userKey`` in its HTML.
    2. read  page.content()               -> scrape ``"userKey":"..."``.
    3. fetch {BASE_URL}/generate (POST)    -> run inside the page via
                                             page.evaluate() so the request
                                             carries the session cookie and a
                                             real browser origin. Returns the
                                             image metadata (imageId, etc.).
    4. fetch {BASE_URL}/downloadTemporary* -> again inside the page; read the
                                             image blob as base64 and hand it
                                             back to Python.

Why a WebView and not plain HTTP: Perchance ties ``generate``/``download`` to
the cookie the ``verifyUser`` page sets, and gates it behind browser-shaped
requests. Running ``fetch()`` inside the loaded page is what makes the calls
succeed -- a bare ``requests``/``urllib`` client is rejected.

The generated image is written to Python's temp directory and the function
returns a ``file://`` URI to it.

Run inside Layla's embedded Python runtime (``lython_native`` must be present).
"""

from __future__ import annotations

import base64
import random
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import lython

BASE_URL = "https://image-generation.perchance.org/api"

# Perchance's fixed shape -> resolution table.
_RESOLUTIONS: dict[str, str] = {
    "portrait": "512x768",
    "square": "768x768",
    "landscape": "768x512",
}

# Generation can take a while on the free tier; give the in-page fetch room.
_NAV_TIMEOUT_MS = 30_000
_GENERATE_TIMEOUT_MS = 180_000
_DOWNLOAD_TIMEOUT_MS = 60_000


class PerchanceError(RuntimeError):
    """Any expected failure from the Perchance flow."""


class _VerificationRequired(Exception):
    """Perchance has not verified this device/network yet.

    Not a hard error: the user just needs to generate one image manually in a
    browser on this network (verification is network-scoped and server-side).
    """

    def __init__(self, *, rate_limited: bool = False) -> None:
        super().__init__()
        self.rate_limited = rate_limited


def _find_proxy_download(value: Any) -> str | None:
    """Locate the proxy download path/token anywhere in the generate response.

    Ported verbatim from the reference library: newer Perchance responses hand
    back a ``v1.`` token or an already-formed ``downloadTemporaryImageViaProxy``
    path somewhere in the JSON.
    """
    if isinstance(value, str):
        if "downloadTemporaryImageViaProxy" in value:
            return value
        if value.startswith("v1.") and len(value) > 80:
            return f"/downloadTemporaryImageViaProxy?t={value}"
        return None
    if isinstance(value, dict):
        for item in value.values():
            found = _find_proxy_download(item)
            if found:
                return found
        return None
    if isinstance(value, list):
        for item in value:
            found = _find_proxy_download(item)
            if found:
                return found
    return None


def _verify_user_and_get_key() -> str:
    """Load ``verifyUser`` (sets the session cookie) and scrape the userKey."""
    lython.page.goto(
        f"{BASE_URL}/verifyUser?thread=0&__cacheBust={random.random()}",
        timeout=_NAV_TIMEOUT_MS,
    )
    content = lython.page.content(timeout=_NAV_TIMEOUT_MS)

    marker = '"userKey":"'
    start = content.find(marker)
    if start != -1:
        start += len(marker)
        end = content.find('"', start)
        if end != -1:
            return content[start:end]

    # No userKey in the page. verifyUser now gates the key behind a network
    # verification that only a real browser generation establishes, so a missing
    # key almost always means "this network isn't verified yet".
    if "too_many_requests" in content:
        raise _VerificationRequired(rate_limited=True)
    raise _VerificationRequired()


def _request_generation(key: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST the generate request from inside the page and return the JSON."""
    url = (
        f"{BASE_URL}/generate"
        f"?userKey={key}"
        f"&requestId=aiImageCompletion{random.randint(0, 2 ** 30)}"
        f"&__cacheBust={random.random()}"
    )
    response = lython.page.evaluate(
        """
        async ({ url, body }) => {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!response.ok) {
                return { __error: `${response.status} ${response.statusText}` };
            }
            return await response.json();
        }
        """,
        {"url": url, "body": body},
        timeout=_GENERATE_TIMEOUT_MS,
    )

    if not isinstance(response, dict):
        raise PerchanceError(f"Unexpected generate response: {response!r}")
    if response.get("__error"):
        raise PerchanceError(f"Generate request failed: {response['__error']}")
    if "imageId" not in response:
        raise PerchanceError(f"Generate response missing imageId: {response!r}")
    return response


def _download_image_base64(image_id: str, proxy_download: str | None) -> str:
    """Fetch the finished image inside the page and return raw base64.

    Mirrors the reference flow: re-load ``verifyUser`` so the download fetch
    runs with a valid session cookie, then try the proxy URL (if any) before
    the direct ``downloadTemporaryImage`` endpoint.
    """
    lython.page.goto(
        f"{BASE_URL}/verifyUser?thread=0&__cacheBust={random.random()}",
        timeout=_NAV_TIMEOUT_MS,
    )

    urls: list[str] = []
    if proxy_download:
        urls.append(urljoin(BASE_URL + "/", proxy_download))
    urls.append(f"{BASE_URL}/downloadTemporaryImage?imageId={image_id}")

    result = lython.page.evaluate(
        """
        async (urls) => {
            const failures = [];
            for (const url of urls) {
                const response = await fetch(url);
                if (!response.ok) {
                    failures.push(`${response.status} ${url}`);
                    continue;
                }
                const blob = await response.blob();
                const base64 = await new Promise(resolve => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result.split(',')[1]);
                    reader.readAsDataURL(blob);
                });
                return { ok: true, data: base64 };
            }
            return { ok: false, failures };
        }
        """,
        urls,
        timeout=_DOWNLOAD_TIMEOUT_MS,
    )

    if not isinstance(result, dict) or not result.get("ok"):
        failures = result.get("failures") if isinstance(result, dict) else result
        raise PerchanceError(f"Failed to download image: {failures}")
    return result["data"]


def generate_image_to_file(
    prompt: str,
    *,
    negative_prompt: str | None = None,
    seed: int = -1,
    shape: Literal["portrait", "square", "landscape"] = "square",
    guidance_scale: float = 7.0,
) -> str:
    """Generate an image with Perchance and save it to the temp directory.

    Returns a ``file://`` URI pointing at the saved image.
    """
    resolution = _RESOLUTIONS.get(shape)
    if resolution is None:
        raise ValueError(f"Invalid shape: {shape!r} (expected {list(_RESOLUTIONS)})")

    lython.notify("Verifying Perchance session...")
    key = _verify_user_and_get_key()

    body = {
        "generatorName": "ai-image-generator",
        "channel": "ai-text-to-image-generator",
        "subChannel": "public",
        "prompt": prompt,
        "negativePrompt": negative_prompt or "",
        "seed": seed,
        "resolution": resolution,
        "guidanceScale": guidance_scale,
    }

    lython.notify("Requesting image generation...")
    meta = _request_generation(key, body)

    image_id = meta["imageId"]
    file_extension = meta.get("fileExtension", "jpeg")

    lython.notify("Downloading generated image...")
    image_b64 = _download_image_base64(image_id, _find_proxy_download(meta))
    image_bytes = base64.b64decode(image_b64)

    out_path = Path(tempfile.gettempdir()) / f"perchance_{image_id}.{file_extension}"
    out_path.write_bytes(image_bytes)

    return out_path.resolve().as_uri()


def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "a serene mountain lake at sunrise"
    try:
        file_uri = generate_image_to_file(prompt, shape="landscape")
    except _VerificationRequired as needed:
        # Not a failure: Perchance just needs a one-time human verification on
        # this network. Emit an instruction for the calling LLM, then end
        # gracefully (no exit() / SystemExit — Layla treats that as a failure).
        if needed.rate_limited:
            print(
                "Perchance is temporarily rate-limiting this network. Tell the "
                "user to wait a minute, then ask for the image again."
            )
        else:
            print(
                "Perchance needs this device's network verified before it can "
                "generate images. Tell the user to open a Perchance image "
                "generator (for example "
                "https://perchance.org/ai-text-to-image-generator) in any web "
                "browser on this same Wi-Fi/network, generate one image manually, "
                "then ask for this image again."
            )
        return
    except (PerchanceError, lython.LythonError) as error:
        print(f"Image generation failed: {error}", file=sys.stderr, flush=True)
        return

    # Success: emit only the file:// URI and nothing else — Layla consumes it.
    print(file_uri)


if __name__ == "__main__":
    main()
