'''Unit tests for error mapping, pagination and markdown rendering.'''

import httpx
import pytest

from github_mcp.client import GitHubAPIError
from github_mcp.models import ResponseFormat
from github_mcp.utils import (
    MAX_OUTPUT_CHARS,
    _pagination,
    build_search_response,
    handle_api_error,
    render_commit,
    render_issue,
    render_repo,
    render_topic,
    render_user,
    truncate_output,
)


class TestErrorMapping:
    def test_401(self):
        msg = handle_api_error(GitHubAPIError("Bad credentials", 401))
        assert "GITHUB_TOKEN" in msg

    def test_403_includes_reset_time(self):
        msg = handle_api_error(GitHubAPIError("rate limit", 403, reset_ts="2000000000"))
        assert "403" in msg
        assert "resets at" in msg

    def test_403_malformed_reset_ts_does_not_crash(self):
        msg = handle_api_error(GitHubAPIError("rate limit", 403, reset_ts="not-a-number"))
        assert "403" in msg
        assert "resets at" not in msg

    def test_404(self):
        msg = handle_api_error(GitHubAPIError("Not Found", 404), "foo/bar")
        assert "404" in msg
        assert "owner/name" in msg

    def test_422(self):
        msg = handle_api_error(GitHubAPIError("Validation Failed", 422))
        assert "qualifier" in msg

    def test_422_with_hint(self):
        msg = handle_api_error(
            GitHubAPIError("Validation Failed", 422),
            "issues",
            hint="With a GITHUB_TOKEN, GitHub requires 'is:issue' or 'is:pull-request' in the query.",
        )
        assert "is:issue" in msg

    def test_503(self):
        msg = handle_api_error(GitHubAPIError("Service Unavailable", 503))
        assert "503" in msg

    def test_timeout(self):
        msg = handle_api_error(httpx.TimeoutException("slow"))
        assert "timed out" in msg

    def test_unknown(self):
        msg = handle_api_error(RuntimeError("boom"))
        assert "RuntimeError" in msg


class TestPagination:
    def test_has_more(self):
        meta = _pagination(total_count=50, per_page=20, page=1, returned=20)
        assert meta["has_more"] is True
        assert meta["next_page"] == 2

    def test_no_more(self):
        meta = _pagination(total_count=20, per_page=20, page=1, returned=20)
        assert meta["has_more"] is False
        assert meta["next_page"] is None

    def test_search_cap_1000(self):
        meta = _pagination(total_count=5000, per_page=100, page=10, returned=100)
        assert meta["has_more"] is False

    def test_paging_allowed_within_first_1000(self):
        meta = _pagination(total_count=5000, per_page=20, page=1, returned=20)
        assert meta["has_more"] is True
        assert meta["next_page"] == 2

    def test_paging_stops_at_1000_boundary(self):
        meta = _pagination(total_count=5000, per_page=20, page=50, returned=20)
        assert meta["has_more"] is False


class TestSearchResponse:
    def test_json_format(self):
        data = {"total_count": 2, "items": [{"full_name": "a/b", "stargazers_count": 1}]}
        out = build_search_response(
            data, "items", render_repo, 20, 1, ResponseFormat.JSON, "30"
        )
        import json

        parsed = json.loads(out)
        assert parsed["total_count"] == 2
        assert parsed["rate_limit_remaining"] == "30"

    def test_markdown_empty(self):
        out = build_search_response(
            {"total_count": 0, "items": []}, "items", render_repo, 20, 1, ResponseFormat.MARKDOWN, None
        )
        assert "No results" in out

    def test_markdown_renders_repo(self):
        item = {
            "full_name": "octocat/Hello-World",
            "owner": {"login": "octocat"},
            "name": "Hello-World",
            "stargazers_count": 123,
            "forks_count": 4,
            "language": "Ruby",
            "license": {"name": "MIT"},
            "description": "My first repo",
            "html_url": "https://github.com/octocat/Hello-World",
            "topics": ["octocat"],
        }
        out = build_search_response(
            {"total_count": 1, "items": [item]}, "items", render_repo, 20, 1, ResponseFormat.MARKDOWN, None
        )
        assert "octocat/Hello-World" in out
        assert "★ 123" in out
        assert "Language: Ruby" in out

    def test_markdown_shows_rate_limit_and_incomplete(self):
        item = {"full_name": "a/b", "owner": {"login": "a"}, "html_url": "u"}
        data = {"total_count": 1, "items": [item], "incomplete_results": True}
        out = build_search_response(data, "items", render_repo, 20, 1, ResponseFormat.MARKDOWN, "5")
        assert "rate limit remaining: 5" in out
        assert "incomplete results" in out

    def test_json_trims_items_to_fit_budget(self):
        big = "x" * MAX_OUTPUT_CHARS
        items = [{"full_name": f"a/{i}", "owner": {"login": "a"}, "description": big} for i in range(3)]
        data = {"total_count": 3, "items": items}
        out = build_search_response(data, "items", render_repo, 20, 1, ResponseFormat.JSON, None)
        import json

        parsed = json.loads(out)
        assert parsed["truncated"] is True
        assert parsed["count"] == len(parsed["items"]) < 3
        assert len(out) <= MAX_OUTPUT_CHARS + 1


class TestTruncateOutput:
    def test_short_text_unchanged(self):
        assert truncate_output("hello") == "hello"

    def test_long_text_truncated_with_note(self):
        out = truncate_output("x" * (MAX_OUTPUT_CHARS + 100))
        assert "truncated" in out
        assert len(out) < MAX_OUTPUT_CHARS + 200


class TestRenderers:
    def test_render_issue_uses_repository_url(self):
        item = {
            "repository_url": "https://api.github.com/repos/psf/requests",
            "number": 6102,
            "title": "HTTPDigestAuth fails",
            "state": "open",
            "labels": [{"name": "Bug"}],
            "user": {"login": "ondratu"},
            "created_at": "2022-04-04T10:00:00Z",
            "comments": 9,
            "html_url": "https://github.com/psf/requests/issues/6102",
            "body": "There was an issue reported.",
        }
        lines = render_issue(item)
        joined = "\n".join(lines)
        assert "psf/requests#6102" in joined
        assert "[open]" in joined
        assert "Bug" in joined

    def test_render_issue_missing_repo_url(self):
        item = {"repository_url": None, "number": 1, "title": "x", "state": "open"}
        assert "?#1" in "\n".join(render_issue(item))

    def test_render_commit(self):
        item = {
            "sha": "abc123def456",
            "commit": {"message": "fix: handle empty body\n\nDetails.", "author": {"name": "Ada", "date": "2024-01-01T00:00:00Z"}},
            "repository_url": "https://api.github.com/repos/a/b",
            "html_url": "https://github.com/a/b/commit/abc123def456",
        }
        joined = "\n".join(render_commit(item))
        assert "abc123d" in joined
        assert "fix: handle empty body" in joined
        assert "Ada" in joined

    def test_render_user(self):
        item = {"login": "octocat", "name": "Mona Lisa", "type": "User", "score": 1.5, "html_url": "u"}
        joined = "\n".join(render_user(item))
        assert "octocat" in joined
        assert "Mona Lisa" in joined

    def test_render_user_has_no_fake_followers(self):
        # The search API does not return followers/bio; they must not render
        # as misleading placeholders.
        item = {"login": "octocat", "type": "User", "score": 1.0, "html_url": "u"}
        joined = "\n".join(render_user(item))
        assert "Followers" not in joined
        assert "Bio" not in joined

    def test_render_topic_strips_html(self):
        item = {
            "name": "machine-learning",
            "description": "<p>Machine <b>learning</b> is &amp; fun.</p>",
            "curated": True,
            "score": 1.0,
        }
        joined = "\n".join(render_topic(item))
        assert "<p>" not in joined
        assert "<b>" not in joined
        assert "Machine learning is & fun." in joined
        assert "Curated topic" in joined
