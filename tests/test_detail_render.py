'''Unit tests for the detail-tool markdown renderers.'''

from github_mcp.tools.detail import (
    _render_dir_md,
    _render_file_md,
    _render_readme_md,
    _render_repo_md,
)


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
