'''Unit tests for the GitHub API client error handling.'''

import httpx

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
