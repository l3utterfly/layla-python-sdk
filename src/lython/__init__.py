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
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    ErrorPayload,
    ResponseEnvelope,
    decode_layla_event,
    decode_layla_request,
    decode_request_envelope,
    decode_response_envelope,
    encode_error_response,
    encode_layla_request,
    encode_request_envelope,
    encode_success_response,
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
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "ErrorPayload",
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
    "ResponseEnvelope",
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
    "decode_request_envelope",
    "decode_response_envelope",
    "encode_error_response",
    "encode_layla_request",
    "encode_request_envelope",
    "encode_success_response",
    "images",
    "memories",
    "personas",
    "tts",
    "utils",
]
