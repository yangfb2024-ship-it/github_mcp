'''Unit tests for the GitHub API client error handling.'''

import asyncio

import httpx
import pytest

from github_mcp.client import GitHubAPIError, GitHubClient


def _fake_response(status_code: int, body: dict, headers: dict | None = None):
    return httpx.Response(status_code, json=body, headers=headers or {})


class TestClientErrorBuilding:
    def test_build_error_message_from_body(self):
        client = GitHubClient()
        response = _fake_response(422, {"message": "Validation Failed"})
        err = client._build_error(response)
        assert isinstance(err, GitHubAPIError)
        assert err.status_code == 422
        assert err.message == "Validation Failed"

    def test_build_error_falls_back_to_doc_url(self):
        client = GitHubClient()
        response = _fake_response(404, {"documentation_url": "https://docs.example.com"})
        err = client._build_error(response)
        assert err.message == "https://docs.example.com"

    def test_build_error_empty_body(self):
        client = GitHubClient()
        response = _fake_response(500, {})
        err = client._build_error(response)
        assert err.message == "Unknown GitHub API error"

    def test_record_rate_limit_headers(self):
        client = GitHubClient()
        response = _fake_response(
            200,
            {},
            {"X-RateLimit-Remaining": "3", "X-RateLimit-Limit": "10", "X-RateLimit-Reset": "2000000000"},
        )
        client._record_rate_limit(response)
        assert client.rate_limit_remaining == "3"
        assert client.rate_limit_total == "10"
        assert client.rate_limit_reset == "2000000000"


class TestRetry:
    '''Transient failures are retried with backoff; other errors surface once.'''

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        async def instant_sleep(_seconds):
            return None

        monkeypatch.setattr(asyncio, "sleep", instant_sleep)

    def _stub_responses(self, monkeypatch, client, responses):
        calls = {"n": 0}

        async def fake_request(*args, **kwargs):
            resp = responses[min(calls["n"], len(responses) - 1)]
            calls["n"] += 1
            if isinstance(resp, Exception):
                raise resp
            return resp

        monkeypatch.setattr(client._client, "request", fake_request)
        return calls

    @pytest.mark.asyncio
    async def test_retries_transient_503_then_succeeds(self, monkeypatch):
        client = GitHubClient()
        calls = self._stub_responses(
            monkeypatch, client, [_fake_response(503, {}), _fake_response(200, {"ok": True})]
        )
        out = await client.request("GET", "/x")
        assert out == {"ok": True}
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_gives_up_after_max_retries(self, monkeypatch):
        client = GitHubClient()
        calls = self._stub_responses(
            monkeypatch,
            client,
            [_fake_response(503, {"message": "down"})] * 5,
        )
        with pytest.raises(GitHubAPIError):
            await client.request("GET", "/x")
        assert calls["n"] == 3  # initial attempt + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_status_not_retried(self, monkeypatch):
        client = GitHubClient()
        calls = self._stub_responses(monkeypatch, client, [_fake_response(404, {"message": "nope"})])
        with pytest.raises(GitHubAPIError):
            await client.request("GET", "/x")
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_connect_error_retried(self, monkeypatch):
        client = GitHubClient()
        calls = self._stub_responses(
            monkeypatch,
            client,
            [httpx.ConnectError("boom"), _fake_response(200, {"ok": True})],
        )
        out = await client.request("GET", "/x")
        assert out == {"ok": True}
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_non_json_body_returns_empty_dict(self, monkeypatch):
        client = GitHubClient()
        self._stub_responses(
            monkeypatch, client, [httpx.Response(200, content=b"<html>oops</html>")]
        )
        assert await client.request("GET", "/x") == {}
