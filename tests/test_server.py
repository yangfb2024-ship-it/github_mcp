'''Unit tests for server assembly and environment loading.'''

import os

from github_mcp.server import _load_dotenv, _strip_quotes, create_server


class TestStripQuotes:
    def test_double_quotes(self):
        assert _strip_quotes('"abc"') == "abc"

    def test_single_quotes(self):
        assert _strip_quotes("'abc'") == "abc"

    def test_unquoted_unchanged(self):
        assert _strip_quotes("abc") == "abc"

    def test_mismatched_quotes_unchanged(self):
        assert _strip_quotes('"abc\'') == '"abc\''


class TestLoadDotenv:
    def test_strips_quotes_and_skips_comments(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text('GITHUB_TOKEN="abc123"\nPLAIN=value\n# comment\n\nBROKEN\n')
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("PLAIN", raising=False)
        _load_dotenv(str(env))
        assert os.environ["GITHUB_TOKEN"] == "abc123"
        assert os.environ["PLAIN"] == "value"

    def test_does_not_override_existing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "existing")
        env = tmp_path / ".env"
        env.write_text("GITHUB_TOKEN=new\n")
        _load_dotenv(str(env))
        assert os.environ["GITHUB_TOKEN"] == "existing"

    def test_missing_file_is_noop(self, tmp_path):
        _load_dotenv(str(tmp_path / "nope.env"))  # must not raise

    def test_export_prefix_accepted(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text('export GITHUB_TOKEN="tok123"\nexport PLAIN=value\n')
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("PLAIN", raising=False)
        _load_dotenv(str(env))
        assert os.environ["GITHUB_TOKEN"] == "tok123"
        assert os.environ["PLAIN"] == "value"


class TestCreateServer:
    def test_registers_all_tools(self):
        import asyncio

        mcp = create_server()
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
        assert names == {
            "github_search_repos",
            "github_search_code",
            "github_search_issues",
            "github_search_commits",
            "github_search_users",
            "github_search_topics",
            "github_search_labels",
            "github_get_repo",
            "github_get_repo_readme",
            "github_get_file_content",
            "github_get_issue",
        }

    def test_import_has_no_env_side_effect(self, monkeypatch):
        # create_server must not require GITHUB_TOKEN or read .env by itself.
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        mcp = create_server()
        assert mcp.name == "github_mcp"
