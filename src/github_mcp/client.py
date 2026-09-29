'''Shared GitHub API client with authentication, rate-limit awareness and error mapping.'''

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from github_mcp import __version__

API_BASE_URL = "https://api.github.com"
API_VERSION = "2022-11-28"
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 2
RETRY_BACKOFF = 0.5  # seconds; linear backoff (0.5s, 1.0s)
RETRYABLE_STATUSES = frozenset({500, 502, 503, 504})

TEXT_MATCH_ACCEPT = "application/vnd.github.text-match+json"
RAW_ACCEPT = "application/vnd.github.raw+json"

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    '''Raised when the GitHub API returns an error response.

    Attributes:
        message: Human-readable error detail from the API (if any).
        status_code: HTTP status code of the failed response.
        reset_ts: X-RateLimit-Reset header value (epoch seconds) when present.
    '''

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        reset_ts: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.reset_ts = reset_ts


class GitHubClient:
    '''Thin async wrapper around the GitHub REST API.

    All tools share a single instance via the server lifespan. The client
    tracks the latest rate-limit headers so tools can surface remaining
    quota to the agent. Transient failures (5xx, connection errors) are
    retried with linear backoff; all requests are read-only GETs, so
    retrying is safe.
    '''

    def __init__(self, token: Optional[str] = None) -> None:
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=API_BASE_URL,
            headers=self._base_headers(),
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        self.rate_limit_remaining: Optional[str] = None
        self.rate_limit_total: Optional[str] = None
        self.rate_limit_reset: Optional[str] = None

    def _base_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": f"github_mcp/{__version__}",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @property
    def authenticated(self) -> bool:
        return bool(self._token)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        text_match: bool = False,
    ) -> Dict[str, Any]:
        '''Send a request and return the decoded JSON body.

        Args:
            method: HTTP method (GET/POST/...).
            path: API path, e.g. "/search/repositories".
            params: Query parameters.
            text_match: Add the text-match media type to highlight matching terms.

        Raises:
            GitHubAPIError: On any non-2xx response (after retries).
            httpx.HTTPError: On network/timeout failures (after retries).
        '''
        headers = {"Accept": TEXT_MATCH_ACCEPT} if text_match else None
        response = await self._send(method, path, params, headers)

        self._record_rate_limit(response)
        if response.is_error:
            raise self._build_error(response)

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            logger.warning("Non-JSON body returned for %s %s", method, path)
            return {}

    async def get_raw(self, path: str, params: Optional[Dict[str, Any]] = None) -> str:
        '''GET returning the raw body (raw media type) instead of JSON metadata.

        Useful for README/file payloads that are too large for the JSON
        representation (which truncates content above 1 MB).
        '''
        response = await self._send("GET", path, params, {"Accept": RAW_ACCEPT})
        self._record_rate_limit(response)
        if response.is_error:
            raise self._build_error(response)
        return response.text

    async def _send(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]],
        headers: Optional[Dict[str, str]],
    ) -> httpx.Response:
        '''Send a request, retrying transient failures with linear backoff.

        Transport errors cover connection failures and timeouts; all requests
        are read-only GETs, so retrying them is safe.
        '''
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._client.request(
                    method, path, params=params, headers=headers
                )
            except httpx.TransportError:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                    continue
                raise
            if response.status_code in RETRYABLE_STATUSES and attempt < MAX_RETRIES:
                logger.warning(
                    "GitHub %s %s returned %s; retrying (%d/%d)",
                    method, path, response.status_code, attempt + 1, MAX_RETRIES,
                )
                await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                continue
            return response
        raise AssertionError("unreachable")  # pragma: no cover

    def _record_rate_limit(self, response: httpx.Response) -> None:
        self.rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
        self.rate_limit_total = response.headers.get("X-RateLimit-Limit")
        self.rate_limit_reset = response.headers.get("X-RateLimit-Reset")

    def _build_error(self, response: httpx.Response) -> GitHubAPIError:
        try:
            body = response.json()
        except ValueError:
            body = {}
        message = "Unknown GitHub API error"
        if isinstance(body, dict):
            message = body.get("message") or body.get("documentation_url") or message
        elif isinstance(body, str):
            message = body
        return GitHubAPIError(
            message,
            response.status_code,
            reset_ts=response.headers.get("X-RateLimit-Reset"),
        )

    async def search(
        self,
        endpoint: str,
        params: Dict[str, Any],
        *,
        text_match: bool = False,
    ) -> Dict[str, Any]:
        '''Run a search request against /search/<endpoint>.'''
        return await self.request("GET", f"/search/{endpoint}", params, text_match=text_match)

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        '''Convenience GET against an arbitrary API path.'''
        return await self.request("GET", path, params)
