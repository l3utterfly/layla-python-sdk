"""Layla's standard-library-only SDK for the embedded Lython runtime."""

from .errors import (
    LythonError,
    LythonExecutionError,
    LythonHostError,
    LythonNativeUnavailableError,
    LythonProtocolError,
    LythonTimeoutError,
    LythonTransportError,
)
from .protocol import (
    decode_layla_event,
    decode_layla_request,
    encode_layla_request,
)
from .request import OneShotRequestTemplate
from .resources import (
    Chat,
    Characters,
    Classifier,
    Contextual,
    Images,
    LythonClient,
    Memories,
    Personas,
    TTS,
    Utils,
)
from .transport import LythonTransport, OneShotResponse

_client = LythonClient()

chat = _client.chat
characters = _client.characters
images = _client.images
classifier = _client.classifier
utils = _client.utils
memories = _client.memories
personas = _client.personas
tts = _client.tts
contextual = _client.contextual

__all__ = [
    "LythonError",
    "LythonExecutionError",
    "LythonHostError",
    "LythonClient",
    "LythonNativeUnavailableError",
    "LythonProtocolError",
    "LythonTimeoutError",
    "LythonTransport",
    "LythonTransportError",
    "OneShotRequestTemplate",
    "OneShotResponse",
    "Chat",
    "Characters",
    "Classifier",
    "Contextual",
    "Images",
    "Memories",
    "Personas",
    "TTS",
    "Utils",
    "chat",
    "characters",
    "classifier",
    "contextual",
    "decode_layla_event",
    "decode_layla_request",
    "encode_layla_request",
    "images",
    "memories",
    "personas",
    "tts",
    "utils",
]
