'''Unit tests for input models.'''

import pytest
from pydantic import ValidationError

from github_mcp.models import (
    FileContentInput,
    IssueDetailInput,
    LabelSearchInput,
    ReadmeInput,
    RepoInput,
    RepoSearchInput,
    ResponseFormat,
)


class TestRepoInput:
    def test_valid_repo(self):
        params = RepoInput(repo="facebook/react")
        assert params.repo == "facebook/react"
        assert params.response_format is ResponseFormat.MARKDOWN

    def test_invalid_repo_without_slash(self):
        with pytest.raises(ValidationError):
            RepoInput(repo="justaname")

    def test_invalid_repo_with_at(self):
        with pytest.raises(ValidationError):
            RepoInput(repo="owner@name/repo")

    def test_repo_strips_whitespace(self):
        params = RepoInput(repo="  facebook/react  ")
        assert params.repo == "facebook/react"

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            RepoInput(repo="a/b", bogus=1)

    def test_dot_only_segments_rejected(self):
        # ".." segments could otherwise traverse the API path after URL
        # normalization; real names containing dots (".github") stay valid.
        with pytest.raises(ValidationError):
            RepoInput(repo="a/..")
        with pytest.raises(ValidationError):
            RepoInput(repo="../b")
        assert RepoInput(repo="a/.github").repo == "a/.github"


class TestSearchInput:
    def test_valid_query(self):
        params = RepoSearchInput(q="fastmcp language:python", sort="stars", per_page=5)
        assert params.q == "fastmcp language:python"
        assert params.sort == "stars"

    def test_query_whitespace_rejected(self):
        with pytest.raises(ValidationError):
            RepoSearchInput(q="   ")

    def test_query_too_long(self):
        with pytest.raises(ValidationError):
            RepoSearchInput(q="a" * 300)

    def test_invalid_sort_rejected(self):
        with pytest.raises(ValidationError):
            RepoSearchInput(q="x", sort="created_at")

    def test_per_page_bounds(self):
        with pytest.raises(ValidationError):
            RepoSearchInput(q="x", per_page=0)
        with pytest.raises(ValidationError):
            RepoSearchInput(q="x", per_page=101)

    def test_json_format(self):
        params = RepoSearchInput(q="x", response_format="json")
        assert params.response_format is ResponseFormat.JSON


class TestDetailInputs:
    def test_readme_input(self):
        params = ReadmeInput(repo="a/b", ref="main")
        assert params.ref == "main"

    def test_label_search_requires_repository_id(self):
        with pytest.raises(ValidationError):
            LabelSearchInput(q="bug")
        params = LabelSearchInput(q="bug", repository_id=1362490)
        assert params.repository_id == 1362490

    def test_file_content_input(self):
        params = FileContentInput(repo="a/b", path="src/server.py")
        assert params.path == "src/server.py"

    def test_file_content_path_required(self):
        with pytest.raises(ValidationError):
            FileContentInput(repo="a/b")

    def test_issue_number_ge1(self):
        with pytest.raises(ValidationError):
            IssueDetailInput(repo="a/b", issue_number=0)
        params = IssueDetailInput(repo="a/b", issue_number=1)
        assert params.issue_number == 1
