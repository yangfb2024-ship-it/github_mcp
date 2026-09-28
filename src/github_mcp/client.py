'''Shared GitHub API client with authentication, rate-limit awareness and error mapping.'''

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from github_mcp import __version__

API_BASE_URL = "https://api.github.com"
API_VERSION = "2022-11-28"
REQUEST_TIMEOUT = 30.0

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
    quota to the agent.
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
            GitHubAPIError: On any non-2xx response.
            httpx.TimeoutException: On request timeout.
        '''
        headers = self._base_headers()
        if text_match:
            headers["Accept"] = "application/vnd.github.text-match+json"

        try:
            response = await self._client.request(
                method, path, params=params, headers=headers
            )
        except httpx.HTTPStatusError as e:  # pragma: no cover - defensive
            raise GitHubAPIError(str(e), getattr(e.response, "status_code", None))

        self._record_rate_limit(response)

        if response.is_error:
            raise self._build_error(response)

        if not response.content:
            return {}
        return response.json()

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
