"""Run an end-to-end diagnostic of every unique Lython one-shot API.

This script is intended to run inside Layla's embedded Python runtime.  It
tests each underlying SDK operation once.  Async counterparts and camelCase
aliases are intentionally not repeated because they route to the same host
commands.

Detailed results are printed to stdout.  Concise start, per-API progress, and
final-summary messages are also sent to the host with ``lython.notify()``.

Some APIs necessarily have side effects.  The runner updates existing
characters/chat messages/memories without changing their values when suitable
records exist.  If there is no chat message or memory to update, it creates a
clearly marked diagnostic record because the corresponding create/update API
cannot otherwise be exercised.  The scheduled message is cancelled during the
same run.  The first listed inference engine is selected, which may change the
current engine.  There is no delete API for the small private diagnostic file.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import lython
from lython import (
    LythonExecutionError,
    LythonHostError,
    LythonNativeUnavailableError,
    LythonProtocolError,
    LythonTimeoutError,
    LythonTransportError,
)


# Increase these if the device/model is slow.  Every request remains bounded.
DEFAULT_TIMEOUT_SECONDS = 60.0
GENERATION_TIMEOUT_SECONDS = 300.0
TTS_TIMEOUT_SECONDS = 180.0
EXPECTED_API_COUNT = 26

# Set this to True when using the script from a test harness that relies on a
# non-zero exit code.  False is friendlier to Layla's interactive runner.
FAIL_PROCESS_ON_ERROR = False

DIAGNOSTIC_FILE = "lython_sdk_api_diagnostic.txt"
MARKER = "[Lython SDK API diagnostic]"

LOG = logging.getLogger("lython-api-diagnostics")
MISSING = object()


class SkipAPI(Exception):
    """Raised when an API cannot be called without a missing prerequisite."""


class APIReportedFailure(RuntimeError):
    """Raised when a valid API response explicitly reports success=false."""


@dataclass
class TestResult:
    name: str
    status: str
    seconds: float
    detail: str


RESULTS: list[TestResult] = []
NOTIFICATIONS_ENABLED = True


def notify_progress(message: str) -> None:
    """Notify the host without allowing progress reporting to stop the run."""

    global NOTIFICATIONS_ENABLED
    if not NOTIFICATIONS_ENABLED:
        return

    try:
        lython.notify(f"{MARKER} {message}")
    except Exception as exc:
        NOTIFICATIONS_ENABLED = False
        LOG.warning(
            "Host progress notifications disabled after notify failed: %s: %s",
            type(exc).__name__,
            exc,
        )


def _json_default(value: Any) -> str:
    return f"<{type(value).__name__}: {value!s}>"


def _compact(value: Any, *, depth: int = 0) -> Any:
    """Make results readable without printing entire images/audio or huge data."""
    if depth >= 5:
        return f"<{type(value).__name__}: maximum display depth reached>"
    if isinstance(value, str):
        if value.startswith("data:") and ";base64," in value:
            header, encoded = value.split(",", 1)
            return f"<{header},...; {len(encoded)} base64 chars>"
        if len(value) > 500:
            return value[:500] + f"... <{len(value) - 500} chars omitted>"
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _compact(item, depth=depth + 1)
            for key, item in list(value.items())[:30]
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        shown = [_compact(item, depth=depth + 1) for item in value[:10]]
        if len(value) > 10:
            shown.append(f"<{len(value) - 10} more items omitted>")
        return shown
    if isinstance(value, (bytes, bytearray)):
        return f"<{type(value).__name__}: {len(value)} bytes>"
    return value


def _format(value: Any) -> str:
    return json.dumps(
        _compact(value),
        default=_json_default,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _failure_details(exc: Exception) -> dict[str, Any]:
    details: dict[str, Any] = {
        "exception_type": type(exc).__name__,
        "message": str(exc) or "<exception had no message>",
    }
    if isinstance(exc, LythonHostError):
        details.update(
            host_code=exc.code,
            host_details=exc.details,
            retryable=exc.retryable,
            raw_host_message=exc.raw_message,
            likely_cause=(
                "Layla received the request but its host handler rejected or "
                "could not complete it. Inspect host_code, host_details, and "
                "raw_host_message above."
            ),
        )
    elif isinstance(exc, LythonTimeoutError):
        details["likely_cause"] = (
            "The native request did not receive its expected terminal event "
            "before the configured timeout. The feature may be slow, its host "
            "handler may not emit the expected event, or the operation may be stuck."
        )
    elif isinstance(exc, LythonNativeUnavailableError):
        details["likely_cause"] = (
            "The script is not running inside Layla's embedded runtime, or "
            "lython_native was not injected into this execution."
        )
    elif isinstance(exc, LythonExecutionError):
        details["likely_cause"] = (
            "The embedded Python execution closed or became unavailable while "
            "the native request was active."
        )
    elif isinstance(exc, LythonProtocolError):
        details["likely_cause"] = (
            "Layla returned a response whose terminal event or data shape did "
            "not match the SDK contract."
        )
    elif isinstance(exc, LythonTransportError):
        details["likely_cause"] = (
            "The Python-to-Layla native transport failed before a valid host "
            "response could be decoded."
        )
    elif isinstance(exc, APIReportedFailure):
        details["likely_cause"] = (
            "The API call returned normally, but its response explicitly "
            "contained success=false."
        )
    else:
        details["likely_cause"] = (
            "A Python exception occurred while preparing the request, validating "
            "the response, or extracting a prerequisite."
        )
    return details


def run_api(
    name: str,
    call: Callable[[], Any],
    *,
    purpose: str,
    validate: Callable[[Any], None] | None = None,
) -> Any:
    position = len(RESULTS) + 1
    notify_progress(f"Running {position}/{EXPECTED_API_COUNT}: {name}")
    LOG.info("RUN  %-42s | %s", name, purpose)
    started = time.monotonic()
    try:
        value = call()
        if validate is not None:
            validate(value)
    except SkipAPI as exc:
        elapsed = time.monotonic() - started
        reason = str(exc)
        RESULTS.append(TestResult(name, "SKIP", elapsed, reason))
        LOG.warning("SKIP %-42s | %.3fs | %s", name, elapsed, reason)
        return MISSING
    except Exception as exc:
        elapsed = time.monotonic() - started
        details = _failure_details(exc)
        RESULTS.append(TestResult(name, "FAIL", elapsed, details["message"]))
        LOG.error("FAIL %-42s | %.3fs\n%s", name, elapsed, _format(details))
        LOG.error("Traceback for %s:\n%s", name, traceback.format_exc().rstrip())
        return MISSING

    elapsed = time.monotonic() - started
    RESULTS.append(TestResult(name, "PASS", elapsed, ""))
    LOG.info("PASS %-42s | %.3fs | result=%s", name, elapsed, _format(value))
    return value


def require(value: Any, reason: str) -> Any:
    if value is MISSING or value is None:
        raise SkipAPI(reason)
    return value


def require_nonempty_string(value: Any, description: str) -> None:
    if not isinstance(value, str) or not value:
        raise APIReportedFailure(f"{description} was empty or not a string: {_format(value)}")


def require_success(value: Any) -> None:
    if isinstance(value, Mapping) and value.get("success") is False:
        raise APIReportedFailure(f"API response reported failure: {_format(value)}")


def require_success_true(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("success") is not True:
        raise APIReportedFailure(
            f"API response did not report success=true: {_format(value)}"
        )


def require_result_id(value: Any) -> None:
    require_success(value)
    if get_id(value, "id") is None:
        raise APIReportedFailure(f"API response did not contain an ID: {_format(value)}")


def require_nonempty_list(value: Any, description: str) -> None:
    if not isinstance(value, list) or not value:
        raise APIReportedFailure(f"{description} was empty or not a list: {_format(value)}")


def require_data_uri(value: Any, media_type: str, description: str) -> None:
    require_nonempty_string(value, description)
    if not value.startswith(f"data:{media_type}") or ";base64," not in value:
        raise APIReportedFailure(
            f"{description} was not a base64 {media_type} data URI: {_format(value)}"
        )


def require_chat_completion(value: Any) -> None:
    try:
        if value.get("object") != "chat.completion":
            raise KeyError("object")
        message = value["choices"][0]["message"]
        content = message["content"]
        if not isinstance(content, str):
            raise TypeError("completion content was not a string")
    except (AttributeError, KeyError, IndexError, TypeError) as exc:
        raise APIReportedFailure(
            f"Response was not a usable final chat completion: {_format(value)}"
        ) from exc


def require_voice_file(value: Any) -> None:
    require_success_true(value)
    audio = value.get("audio_data_base64")
    require_data_uri(audio, "audio/", "Generated audio")


def require_saved_file(value: Any) -> None:
    require_success_true(value)
    require_nonempty_string(value.get("filename"), "Saved filename")


def require_read_file(value: Any) -> None:
    require_success(value)
    if not isinstance(value, Mapping):
        raise APIReportedFailure(f"Read-file result was not an object: {_format(value)}")
    require_data_uri(value.get("content_base64"), "", "Read file content")


def first_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            if isinstance(item, Mapping):
                return item
    return None


def get_id(value: Any, *keys: str) -> Any:
    if isinstance(value, Mapping):
        for key in keys:
            candidate = value.get(key)
            if candidate is not None and candidate != "":
                return candidate
    return None


def find_character(context: Any, characters: Any) -> tuple[str | None, Mapping[str, Any] | None]:
    context_character = context.get("character") if isinstance(context, Mapping) else None
    candidates: list[Mapping[str, Any]] = []
    if isinstance(context_character, Mapping):
        candidates.append(context_character)
    if isinstance(characters, Sequence) and not isinstance(characters, (str, bytes, bytearray)):
        candidates.extend(item for item in characters if isinstance(item, Mapping))

    for character in candidates:
        character_id = get_id(character, "id", "character_id", "characterId")
        if character_id is not None:
            return str(character_id), character
    return None, None


def find_session_id(context: Any, sessions: Any) -> str | None:
    context_session = get_id(context, "session_id", "sessionId")
    if context_session is not None:
        return str(context_session)
    if isinstance(sessions, Mapping):
        session_items = sessions.get("sessions", [])
        if isinstance(session_items, Sequence):
            for session in session_items:
                session_id = get_id(session, "session_id", "sessionId", "id")
                if session_id is not None:
                    return str(session_id)
    return None


def select_string_id(items: Any) -> str | None:
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        return None
    for item in items:
        if isinstance(item, str) and item:
            return item
        candidate = get_id(item, "id", "name")
        if candidate is not None:
            return str(candidate)
    return None


def main() -> int:
    global NOTIFICATIONS_ENABLED
    RESULTS.clear()
    NOTIFICATIONS_ENABLED = True
    LOG.info("Lython SDK API diagnostic started")
    LOG.info(
        "SDK wire format=direct Layla messages | Python=%s",
        sys.version.replace("\n", " "),
    )
    LOG.warning(
        "This full diagnostic invokes state-changing and media APIs. See the "
        "module docstring for the side-effect policy."
    )
    notify_progress(f"Started; running {EXPECTED_API_COUNT} API checks")

    context = run_api(
        "contextual.get_execution_context",
        lambda: lython.contextual.get_execution_context(timeout=DEFAULT_TIMEOUT_SECONDS),
        purpose="Discover the active Layla execution, character, and session.",
    )
    characters = run_api(
        "characters.list",
        lambda: lython.characters.list(offset=0, range=10, timeout=DEFAULT_TIMEOUT_SECONDS),
        purpose="List the first ten available characters.",
    )
    character_id, character = find_character(context, characters)
    LOG.info("Selected character_id=%r", character_id)

    run_api(
        "characters.get_image",
        lambda: lython.characters.get_image(
            require(character_id, "No character ID was available."),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ),
        purpose="Fetch the selected character's image (None is valid if it has none).",
    )

    def update_character() -> Any:
        selected = require(character, "No character record was available to update safely.")
        if "id" not in selected or "data" not in selected:
            raise SkipAPI(
                "The selected character did not contain both 'id' and 'data'; "
                "creating a new Character Card would be an excessive test side effect."
            )
        return lython.characters.update(dict(selected), timeout=DEFAULT_TIMEOUT_SECONDS)

    run_api(
        "characters.update",
        update_character,
        purpose="Write the selected character back unchanged.",
        validate=lambda value: require_nonempty_string(value, "Updated character ID"),
    )

    run_api(
        "classifier.get_sentiment",
        lambda: lython.classifier.get_sentiment(
            "I am happy that this diagnostic is working.", timeout=DEFAULT_TIMEOUT_SECONDS
        ),
        purpose="Run the local sentiment classifier.",
    )

    engines = run_api(
        "chat.get_inference_engines",
        lambda: lython.chat.get_inference_engines(timeout=DEFAULT_TIMEOUT_SECONDS),
        purpose="List installed inference engines.",
    )
    engine_name = select_string_id(engines)
    run_api(
        "chat.set_inference_engine",
        lambda: lython.chat.set_inference_engine(
            require(engine_name, "No inference engine was returned by the listing API."),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ),
        purpose=f"Select the first listed engine ({engine_name!r}).",
        validate=require_success_true,
    )

    sessions = run_api(
        "chat.get_chat_sessions",
        lambda: lython.chat.get_chat_sessions(
            require(character_id, "No character ID was available."),
            offset=0,
            range=10,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ),
        purpose="List recent sessions for the selected character.",
    )
    session_id = find_session_id(context, sessions)
    LOG.info("Selected session_id=%r", session_id)

    history = run_api(
        "chat.get_chat_history",
        lambda: lython.chat.get_chat_history(
            require(session_id, "No active or listed chat session ID was available."),
            offset=0,
            range=10,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ),
        purpose="Read recent messages from the selected session.",
    )

    def save_chat_message() -> Any:
        existing = first_mapping(history)
        if existing is not None:
            payload = dict(existing)
            action = "updating an existing message unchanged"
        else:
            payload = {
                "id": 0,
                "role": "user",
                "content": f"{MARKER} save_chat_message test",
                "character_id": require(character_id, "No character ID was available."),
                "session_id": require(session_id, "No chat session ID was available."),
                "timestamp": int(time.time() * 1000),
            }
            action = "creating a marked diagnostic message because history was empty"
        LOG.warning("chat.save_chat_message is %s", action)
        return lython.chat.save_chat_message(payload, timeout=DEFAULT_TIMEOUT_SECONDS)

    run_api(
        "chat.save_chat_message",
        save_chat_message,
        purpose="Update an existing message unchanged, or create one diagnostic record.",
        validate=require_result_id,
    )

    scheduled_id: int | None = None

    def schedule_message() -> Any:
        payload = {
            "id": 0,
            "character_id": require(character_id, "No character ID was available."),
            "session_id": session_id,
            # Far enough ahead that the following cancellation should happen first.
            "timestamp": int((time.time() + 24 * 60 * 60) * 1000),
            "message": f"{MARKER} scheduled-message test; this should be cancelled",
        }
        return lython.chat.schedule_chat_message(payload, timeout=DEFAULT_TIMEOUT_SECONDS)

    scheduled = run_api(
        "chat.schedule_chat_message",
        schedule_message,
        purpose="Create a marked message one day ahead; it is cancelled below.",
        validate=require_result_id,
    )
    candidate_scheduled_id = get_id(scheduled, "id")
    if isinstance(candidate_scheduled_id, int):
        scheduled_id = candidate_scheduled_id

    run_api(
        "chat.get_scheduled_chat_messages",
        lambda: lython.chat.get_scheduled_chat_messages(timeout=DEFAULT_TIMEOUT_SECONDS),
        purpose="List scheduled messages after creating the diagnostic fixture.",
    )
    run_api(
        "chat.cancel_scheduled_chat_message",
        lambda: lython.chat.cancel_scheduled_chat_message(
            require(scheduled_id, "The schedule response did not contain an integer ID."),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ),
        purpose="Cancel the diagnostic scheduled message.",
        validate=require_success_true,
    )

    memories = run_api(
        "memories.list",
        lambda: lython.memories.list(
            require(character_id, "No character ID was available."),
            offset=0,
            range=10,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ),
        purpose="List recent memories for the selected character.",
    )
    run_api(
        "memories.get_top_memories",
        lambda: lython.memories.get_top_memories(
            require(character_id, "No character ID was available."),
            limit=10,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ),
        purpose="Retrieve the character's highest-ranked memories.",
    )

    def create_or_update_memory() -> Any:
        existing = first_mapping(memories)
        if existing is not None:
            payload = dict(existing)
            action = "updating an existing memory unchanged"
        else:
            payload = {
                "id": 0,
                "character_id": require(character_id, "No character ID was available."),
                "session_id": session_id,
                "rawText": f"{MARKER} create_or_update memory test",
                "timestamp": int(time.time() * 1000),
                "summary": "Lython SDK diagnostic fixture",
                "knowledgeGraphJSON": None,
            }
            action = "creating a marked diagnostic memory because none was listed"
        LOG.warning("memories.create_or_update is %s", action)
        return lython.memories.create_or_update([payload], timeout=DEFAULT_TIMEOUT_SECONDS)

    run_api(
        "memories.create_or_update",
        create_or_update_memory,
        purpose="Update an existing memory unchanged, or create one diagnostic record.",
        validate=lambda value: require_nonempty_list(value, "Saved memories result"),
    )

    run_api(
        "personas.get",
        lambda: lython.personas.get(character_id, timeout=DEFAULT_TIMEOUT_SECONDS),
        purpose="Read the active persona, optionally scoped to the selected character.",
    )

    image_models = run_api(
        "images.get_image_generation_models",
        lambda: lython.images.get_image_generation_models(timeout=DEFAULT_TIMEOUT_SECONDS),
        purpose="List installed image-generation models.",
    )
    image_model_id = select_string_id(image_models)
    run_api(
        "images.generate_image",
        lambda: lython.images.generate_image(
            f"{MARKER} A simple small blue circle on a white background",
            model_id=image_model_id,
            timeout=GENERATION_TIMEOUT_SECONDS,
        ),
        purpose=f"Generate one diagnostic image with model {image_model_id!r}.",
        validate=lambda value: require_data_uri(
            value, "image/", "Generated image data URI"
        ),
    )

    completion = run_api(
        "chat.completions.create",
        lambda: lython.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Lython SDK diagnostic: reply with exactly the word OK and "
                        "nothing else."
                    ),
                }
            ],
            model="layla",
            timeout=GENERATION_TIMEOUT_SECONDS,
        ),
        purpose="Request one final-only chat completion.",
        validate=require_chat_completion,
    )
    if completion is not MISSING:
        try:
            content = completion["choices"][0]["message"]["content"]
            LOG.info("Chat completion extracted content=%r", content)
        except (KeyError, IndexError, TypeError):
            LOG.error("Chat completion passed SDK validation but content extraction failed.")

    voices = run_api(
        "tts.get_voices",
        lambda: lython.tts.get_voices(timeout=DEFAULT_TIMEOUT_SECONDS),
        purpose="List installed TTS voices.",
    )
    voice_id = select_string_id(voices)
    LOG.info("Selected tts_voice_id=%r (None means Layla's global default)", voice_id)
    run_api(
        "tts.generate_voice",
        lambda: lython.tts.generate_voice(
            voice_id,
            "Lython SDK text to speech diagnostic.",
            timeout=TTS_TIMEOUT_SECONDS,
        ),
        purpose="Speak a short diagnostic phrase.",
    )
    run_api(
        "tts.stop_speaking",
        lambda: lython.tts.stop_speaking(timeout=DEFAULT_TIMEOUT_SECONDS),
        purpose="Exercise the foreground speech stop API.",
    )
    run_api(
        "tts.generate_voice_to_file",
        lambda: lython.tts.generate_voice_to_file(
            voice_id,
            "Lython SDK voice file diagnostic.",
            save=False,
            timeout=TTS_TIMEOUT_SECONDS,
        ),
        purpose="Generate audio data without saving it to shared storage.",
        validate=require_voice_file,
    )

    file_bytes = (
        f"{MARKER}\nUTC timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
    ).encode("utf-8")
    saved_file = run_api(
        "utils.save_file",
        lambda: lython.utils.save_file(
            DIAGNOSTIC_FILE,
            base64.b64encode(file_bytes).decode("ascii"),
            share=False,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ),
        purpose=f"Write a small private diagnostic file named {DIAGNOSTIC_FILE!r}.",
        validate=require_saved_file,
    )
    returned_filename = get_id(saved_file, "filename") or DIAGNOSTIC_FILE

    def validate_read_file(value: Any) -> None:
        require_read_file(value)
        encoded = value["content_base64"].split(",", 1)[1]
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise APIReportedFailure("Read file content contained invalid base64.") from exc
        if decoded != file_bytes:
            raise APIReportedFailure(
                "Read file bytes did not match the bytes passed to utils.save_file."
            )

    run_api(
        "utils.read_file",
        lambda: lython.utils.read_file(
            str(returned_filename), timeout=DEFAULT_TIMEOUT_SECONDS
        ),
        purpose="Read back the private diagnostic file.",
        validate=validate_read_file,
    )

    passed = sum(result.status == "PASS" for result in RESULTS)
    failed = sum(result.status == "FAIL" for result in RESULTS)
    skipped = sum(result.status == "SKIP" for result in RESULTS)
    total_seconds = sum(result.seconds for result in RESULTS)

    LOG.info("=" * 88)
    LOG.info("FINAL SUMMARY: %d PASS | %d FAIL | %d SKIP | %d TOTAL | %.3fs", passed, failed, skipped, len(RESULTS), total_seconds)
    for result in RESULTS:
        suffix = f" | {result.detail}" if result.detail else ""
        LOG.info("%-4s %-42s %8.3fs%s", result.status, result.name, result.seconds, suffix)
    LOG.info("=" * 88)

    if len(RESULTS) != EXPECTED_API_COUNT:
        LOG.error(
            "Internal runner error: expected %d API results, recorded %d",
            EXPECTED_API_COUNT,
            len(RESULTS),
        )
        failed += 1
    notify_progress(
        f"Complete: {passed} PASS, {failed} FAIL, {skipped} SKIP, "
        f"{len(RESULTS)} TOTAL"
    )
    if failed:
        LOG.error("Diagnostic completed with failures. Search above for 'FAIL'.")
    elif skipped:
        LOG.warning("Diagnostic had no failures, but some APIs were skipped due to missing prerequisites.")
    else:
        LOG.info(
            "All %d unique Lython one-shot APIs completed successfully.",
            EXPECTED_API_COUNT,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03dZ %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    logging.Formatter.converter = time.gmtime
    exit_code = main()
    if FAIL_PROCESS_ON_ERROR:
        raise SystemExit(exit_code)
