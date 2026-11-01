"""Bounded Vertex/Orthogonal transport; caller owns authorization and accounting.

No provider call is made on import or construction. Do not use without a
reviewed contract, one shared budget ledger and separately supplied credentials.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Optional

import httpx

_PROJECT = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_MODEL = 'gemini-3.8-flash'
_MAX_CAPTURE = 524_288
_MAX_REQUEST = 2_000_000
_TIMEOUT_SECONDS = 420.0

class TransportError(RuntimeError):
    """Sanitized error; caller treats post-start failure as uncertain."""

class OneShotTransport:
    """POST exactly once per invocation, with no redirects or HTTP retries.

    token_for(provider) supplies an in-memory bearer token. Calling code is
    responsible for credential refresh, billing, and operation admission.
    `http_transport` is for deterministic testing only; the production default
    constructs HTTPTransport(retries=0).
    """
    def __init__(self, project_id: str, token_for: Callable[[str], str], *,
                 http_transport: Optional[httpx.BaseTransport] = None):
        if not isinstance(project_id, str) or not _PROJECT.fullmatch(project_id):
            raise ValueError('invalid Google project identifier')
        if not callable(token_for):
            raise ValueError('credential callback required')
        if http_transport is not None and not isinstance(http_transport, httpx.BaseTransport):
            raise ValueError('invalid injected test transport')
        self._project_id = project_id
        self._token_for = token_for
        self._http_transport = http_transport

    def _url(self, provider: str, endpoint: str) -> str:
        if provider == 'vertex' and endpoint in ('countTokens', _MODEL + '@global'):
            action = 'countTokens' if endpoint == 'countTokens' else 'generateContent'
            return ('https://aiplatform.googleapis.com/v1/projects/' + self._project_id +
                    '/locations/global/publishers/google/models/' + _MODEL + ':' + action)
        if provider == 'orthogonal' and endpoint == '/v1/run':
            return 'https://api.orthogonal.com/v1/run'
        raise ValueError('provider or endpoint not admitted')

    def __call__(self, provider: str, endpoint: str, request_bytes: bytes) -> tuple[int, bytes]:
        url = self._url(provider, endpoint)  # rejects unsupported before credential acquisition
        if not isinstance(request_bytes, bytes) or not request_bytes or len(request_bytes) > _MAX_REQUEST:
            raise ValueError('request must be bounded nonempty bytes')
        try:
            token = self._token_for(provider)
        except Exception:
            raise TransportError('credential acquisition failed') from None
        if not isinstance(token, str) or not token or len(token) > 8192 or not token.isascii() or any(ord(x) <= 32 or ord(x) == 127 for x in token):
            raise TransportError('credential unavailable or malformed')
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                   'Accept-Encoding': 'identity'}
        # Never log headers, prompt bytes, provider bodies, or exception chains.
        try:
            engine = self._http_transport if self._http_transport is not None else httpx.HTTPTransport(retries=0)
            with httpx.Client(transport=engine, timeout=httpx.Timeout(_TIMEOUT_SECONDS),
                              follow_redirects=False, trust_env=False) as client:
                with client.stream('POST', url, headers=headers, content=request_bytes) as response:
                    chunks = bytearray()
                    for chunk in response.iter_raw():
                        if len(chunks) + len(chunk) > _MAX_CAPTURE:
                            raise TransportError('response exceeds capture limit')
                        chunks.extend(chunk)
                    return response.status_code, bytes(chunks)
        except TransportError:
            raise
        except Exception:
            # Endpoint/path/provider are public; exception text can include secrets.
            raise TransportError('request outcome or capture uncertain') from None
        finally:
            # This cannot guarantee memory erasure; it only drops local references.
            headers.clear()
            token = None
