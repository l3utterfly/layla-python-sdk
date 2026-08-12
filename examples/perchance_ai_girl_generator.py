"""Drive Perchance's "AI girl generator" UI from inside Layla.

Unlike ``perchance_image_generation.py`` (which calls Perchance's HTTP API from
inside the page), this example drives the visible generator UI on
https://perchance.org/improved-ai-girl-generator: it clicks the on-page
"✨ generate" button and waits for the result image to appear, then reads the
image straight out of the DOM.

The catch that makes this interesting: the generator's button and its result
image live inside nested, cross-origin iframes that the top document cannot
reach through the DOM. So every read/click here goes through the all-frames
helpers, which fan out across every frame:

  - ``page.wait_for_function_all_frames(expr)`` polls ``expr`` in every frame
    from the host side until one frame returns a truthy value. We use it both to
    click the button once it appears and to wait for the result image — the
    generation time is variable, so a fixed sleep would be wrong.
  - ``page.evaluate_all_frames(expr)`` runs a read in every frame and returns one
    result per frame; we pick the frame that actually holds the image.

The result image is a ``data:image/...;base64,`` URL already in the DOM, so no
extra download is needed — we decode it, save it to the temp directory, and
return a ``file://`` URI (matching ``perchance_image_generation.py``).

Run inside Layla's embedded Python runtime (``lython_native`` must be present).
"""

from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path
from typing import Any

import lython

URL = "https://perchance.org/improved-ai-girl-generator"

_NAV_TIMEOUT_MS = 30_000
# Let the page (and its generator iframe) hydrate before we look for the button.
_SETTLE_TIMEOUT_MS = 5_000
# The generator iframe can take a moment to appear after load.
_BUTTON_TIMEOUT_MS = 30_000
# Generation time is highly variable on the free tier.
_GENERATE_TIMEOUT_MS = 180_000

# Locate the generate button by its stable id, falling back to a button whose
# text reads "generate" (the id/styles can change; the label does not).
_GENERATE_BUTTON_JS = """
() => {
  const byId = document.getElementById('generateButtonEl');
  const btn = byId || Array.from(document.querySelectorAll('button'))
    .find((b) => /generate/i.test(b.textContent || ''));
  if (!btn) return false;
  btn.scrollIntoView({ block: 'center', inline: 'center' });
  btn.click();
  return true;
}
"""

# Lightweight readiness probe: return the base64 length (truthy) once the result
# image carries a data URL. Returning the length, not the (multi-MB) data URL,
# keeps every poll cheap.
_IMAGE_READY_JS = """
() => {
  const img = document.getElementById('resultImgEl');
  if (!img) return 0;
  const src = img.src || '';
  return src.indexOf('data:image') === 0 ? src.length : 0;
}
"""

# One-shot full read, run only after the image is ready.
_IMAGE_FETCH_JS = """
() => {
  const img = document.getElementById('resultImgEl');
  if (!img) return null;
  const src = img.src || '';
  if (src.indexOf('data:image') !== 0) return null;
  return { src, title: img.title || '' };
}
"""


class PerchanceError(RuntimeError):
    """Any expected failure from the generator flow."""


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    """Split a ``data:image/<ext>;base64,<payload>`` URL into bytes + extension."""
    header, _, payload = data_url.partition(",")
    if not payload or not header.startswith("data:"):
        raise PerchanceError("result image was not a base64 data URL")
    mime = header[len("data:"):].split(";", 1)[0]
    extension = (mime.split("/", 1)[-1] or "jpeg").lower()
    try:
        # base64 raises binascii.Error, a ValueError subclass, on bad input.
        return base64.b64decode(payload, validate=False), extension
    except ValueError as error:
        raise PerchanceError(f"could not decode result image: {error}") from error


def _first_image(frames: list[lython.FrameResult]) -> dict[str, Any]:
    """Return the first frame result whose content is a populated image dict."""
    for frame in frames:
        content = frame.content
        if isinstance(content, dict) and content.get("src"):
            return content
    raise PerchanceError("result image was reported ready but no frame returned it")


def generate_to_file() -> str:
    """Run one generation on the page and save the result image to a temp file."""
    lython.notify(f"Loading {URL} ...")
    lython.page.goto(URL, timeout=_NAV_TIMEOUT_MS)
    lython.page.wait_for_load_state("load", timeout=_NAV_TIMEOUT_MS)
    lython.page.wait_for_timeout(_SETTLE_TIMEOUT_MS)

    # Wait-and-click in one step: the probe clicks the button and returns true the
    # first time it finds it, so polling stops after a single click.
    lython.notify("Clicking generate ...")
    clicked = lython.page.wait_for_function_all_frames(
        _GENERATE_BUTTON_JS,
        polling_ms=500,
        timeout=_BUTTON_TIMEOUT_MS,
    )
    if not any(frame.content is True for frame in clicked):
        raise PerchanceError("could not find the generate button in any frame")

    # Wait for the result image to carry its base64 data URL.
    lython.notify("Waiting for the image to generate ...")
    lython.page.wait_for_function_all_frames(
        _IMAGE_READY_JS,
        polling_ms=1_000,
        timeout=_GENERATE_TIMEOUT_MS,
    )

    # Read the full image out of whichever frame holds it (one multi-MB transfer).
    frames = lython.page.evaluate_all_frames(_IMAGE_FETCH_JS, timeout=_NAV_TIMEOUT_MS)
    image = _first_image(frames)
    image_bytes, extension = _decode_data_url(image["src"])

    lython.notify("Saving image ...")
    out_path = Path(tempfile.gettempdir()) / f"perchance_ai_girl.{extension}"
    out_path.write_bytes(image_bytes)
    return out_path.resolve().as_uri()


def main() -> None:
    try:
        file_uri = generate_to_file()
    except (PerchanceError, lython.LythonError) as error:
        print(f"Generation failed: {error}", file=sys.stderr, flush=True)
        return

    # Success: emit only the file:// URI so Layla can consume it.
    print(file_uri)


if __name__ == "__main__":
    main()
