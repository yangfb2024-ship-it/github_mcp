'''Unit tests for the detail-tool markdown renderers.'''

from github_mcp.tools.detail import (
    _render_dir_md,
    _render_file_md,
    _render_issue_md,
    _render_readme_md,
    _render_repo_md,
)
from github_mcp.utils import MAX_OUTPUT_CHARS


class TestRepoMd:
    def test_full(self):
        data = {
            "full_name": "fastapi/fastapi",
            "description": "FastAPI framework",
            "language": "Python",
            "stargazers_count": 70000,
            "forks_count": 6000,
            "watchers_count": 70000,
            "open_issues_count": 12,
            "license": {"name": "MIT License"},
            "topics": ["fastapi", "python"],
            "default_branch": "master",
            "homepage": "https://fastapi.tiangolo.com",
            "created_at": "2018-12-04T00:00:00Z",
            "pushed_at": "2024-01-01T00:00:00Z",
            "html_url": "https://github.com/fastapi/fastapi",
        }
        out = _render_repo_md(data)
        assert "# fastapi/fastapi" in out
        assert "Language: Python" in out
        assert "Stars: 70000" in out
        assert "MIT License" in out
        assert "https://github.com/fastapi/fastapi" in out

    def test_archived_note(self):
        data = {"full_name": "a/b", "archived": True}
        assert "archived" in _render_repo_md(data)

    def test_minimal(self):
        data = {"full_name": "a/b"}
        out = _render_repo_md(data)
        assert "# a/b" in out
        assert "No description" in out


class TestReadmeMd:
    def test_readme(self):
        out = _render_readme_md("README.md", "# Hello", "https://github.com/a/b")
        assert "# README: README.md" in out
        assert "# Hello" in out

    def test_fence_widened_when_content_has_backticks(self):
        out = _render_readme_md("README.md", "```python\ncode\n```", "u")
        assert "````markdown" in out
        assert "```python\ncode\n```" in out


class TestFileMd:
    def test_base64_decoded(self):
        import base64

        content = base64.b64encode("print('hi')".encode()).decode()
        data = {"path": "main.py", "size": 11, "encoding": "base64", "html_url": "u"}
        out = _render_file_md(data, content)
        assert "print('hi')" in out

    def test_empty_is_binary(self):
        data = {"path": "logo.png", "size": 5, "html_url": "u"}
        out = _render_file_md(data, "")
        assert "(binary file)" in out

    def test_zero_size_is_empty_not_binary(self):
        data = {"path": "empty.txt", "size": 0, "html_url": "u"}
        out = _render_file_md(data, "")
        assert "(empty file)" in out

    def test_encoding_none_reports_omitted(self):
        data = {"path": "big.bin", "size": 1_500_000, "encoding": "none", "html_url": "u"}
        out = _render_file_md(data, "")
        assert "omitted" in out

    def test_binary_base64_detected_by_nul(self):
        import base64

        content = base64.b64encode(b"\x89PNG\x00\x0d\x0a").decode()
        data = {"path": "logo.png", "size": 7, "encoding": "base64", "html_url": "u"}
        out = _render_file_md(data, content)
        assert "(binary file)" in out


class TestJsonBudget:
    def test_oversized_content_dropped(self):
        from github_mcp.tools.detail import _to_json

        data = {"path": "big.py", "content": "x" * (MAX_OUTPUT_CHARS * 2)}
        out = _to_json(data)
        assert len(out) <= MAX_OUTPUT_CHARS
        assert '"content": null' in out
        assert '"truncated": true' in out

    def test_small_payload_unchanged(self):
        from github_mcp.tools.detail import _to_json

        out = _to_json({"a": 1})
        assert '"a": 1' in out


class TestDirMd:
    def test_dirs_first(self):
        entries = [
            {"type": "file", "name": "b.py", "size": 3},
            {"type": "dir", "name": "src", "size": 0},
            {"type": "file", "name": "a.py", "size": 1},
        ]
        out = _render_dir_md(entries, "pkg")
        assert "# Directory: pkg" in out
        assert out.index("dir/` src") < out.index("file` a.py")
        assert "file` b.py" in out


class TestIssueMd:
    def _issue(self, **overrides):
        data = {
            "title": "Fix thing",
            "state": "closed",
            "labels": [{"name": "bug"}],
            "user": {"login": "octocat"},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "comments": 3,
            "html_url": "https://github.com/a/b/issues/1",
            "body": "Body text",
        }
        data.update(overrides)
        return data

    def test_plain_issue(self):
        out = _render_issue_md(self._issue(), "a/b", 1)
        assert "# a/b#1: Fix thing" in out
        assert "State: closed" in out
        assert "Pull request" not in out

    def test_pr_merged_at_from_nested_pull_request(self):
        issue = self._issue(pull_request={"merged_at": "2024-02-01T00:00:00Z"})
        out = _render_issue_md(issue, "a/b", 1, pr_data={"merge_commit_sha": "abc123"})
        assert "*(Pull request)*" in out
        assert "**Merged** on 2024-02-01" in out
        assert "Merge commit: abc123" in out

    def test_pr_without_merge_info(self):
        issue = self._issue(pull_request={"merged_at": None})
        out = _render_issue_md(issue, "a/b", 1)
        assert "*(Pull request)*" in out
        assert "Merged" not in out
        assert "Merge commit" not in out
