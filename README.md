# Lython SDK

`lython` is the standard-library-only Python SDK for code running inside
Layla's embedded Python runtime. It wraps the private `lython_native` string
transport with a versioned, JSON-encoded one-shot request protocol.

This first version intentionally supports only one-shot requests. It does not
provide streaming responses, progress events, unsolicited events, or
fire-and-forget notifications.

## Protocol

The existing React Native WebView API messages remain unchanged. A request such
as:

```json
{"cmd":"get_characters","data":{"offset":0,"limit":10}}
```

is serialized once and stored verbatim in the Lython request envelope's
`message` field:

```json
{
  "protocol": "layla.lython",
  "version": 1,
  "type": "request",
  "message": "{\"cmd\":\"get_characters\",\"data\":{\"offset\":0,\"limit\":10}}"
}
```

The native request ID is passed separately to `lython_native.request()` and is
not duplicated in the JSON envelope.

A successful host response wraps the existing WebView event JSON in the same
way:

```json
{
  "protocol": "layla.lython",
  "version": 1,
  "type": "response",
  "ok": true,
  "message": "{\"event\":\"on_get_characters_response\",\"data\":[]}"
}
```

A failed host request uses a structured error:

```json
{
  "protocol": "layla.lython",
  "version": 1,
  "type": "response",
  "ok": false,
  "error": {
    "code": "host_error",
    "message": "Unable to load characters",
    "retryable": false
  }
}
```

An optional `message` may also be included in a failed response when the host
has an original `on_error` WebView event to preserve.

## Host integration

The React Native Lython request listener should:

1. Parse and validate the outer Lython request envelope.
2. Pass the inner `message` string directly to
   `RNWebviewApiService.handleLaylaApiMessage(message)`.
3. Capture the one terminal WebView API event for that command.
4. Encode that event as a JSON string in a success response envelope.
5. Call `Lython.respond(executionId, requestId, responseEnvelope)` exactly once.
6. Return an error envelope for malformed requests, unknown commands, handler
   errors, and `on_error` terminal events.

Commands that currently emit intermediate events must be adapted by the host
to produce a single terminal response. Intermediate chat tokens and image
generation progress are deliberately not part of this SDK.

## Request template

Future resource methods can share `OneShotRequestTemplate`, which binds an
existing WebView command name to its expected response event:

```python
from lython import LythonTransport, OneShotRequestTemplate

get_characters = OneShotRequestTemplate(
    command="get_characters",
    response_event="on_get_characters_response",
)

transport = LythonTransport(default_timeout=60.0)
characters = await get_characters.send_async(
    transport,
    {"offset": 0, "limit": 10},
)
```

`LythonTransport` lazily imports `lython_native`, so protocol code and tests can
run in an ordinary Python environment. Tests can inject a fake native module.

The async API uses `asyncio.to_thread()` because `lython_native.request()` is a
blocking native call. Cancelling the awaiting task does not cancel the native
request; the finite native timeout still bounds its lifetime.

## Development

The runtime package has no third-party dependencies. Tests use `unittest` from
the standard library:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

