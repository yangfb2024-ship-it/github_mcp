'''Pydantic input models for all GitHub MCP tools.'''

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

REPO_PATTERN = r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$"


class ResponseFormat(str, Enum):
    '''Output format for tool responses.'''
    MARKDOWN = "markdown"
    JSON = "json"


class SearchInput(BaseModel):
    '''Base input model shared by all search tools.'''
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    q: str = Field(
        ...,
        description=(
            "Search query containing keywords and qualifiers. "
            "Examples: 'fastmcp language:python', 'bug label:bug state:open', "
            "'chromium repo:facebook/react'. Max 256 characters, at most 5 boolean operators."
        ),
        min_length=1,
        max_length=256,
    )
    order: Literal["desc", "asc"] = Field(
        default="desc",
        description="Sort order. Ignored unless sort is provided.",
    )
    per_page: int = Field(
        default=20,
        description="Number of results per page (1-100, default 20).",
        ge=1,
        le=100,
    )
    page: int = Field(
        default=1,
        description="Page number of results to fetch (starts at 1).",
        ge=1,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable.",
    )

    @field_validator("q")
    @classmethod
    def _validate_query(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace only.")
        return v.strip()


class RepoSearchInput(SearchInput):
    '''Input for repository search.'''
    sort: Optional[Literal["stars", "forks", "help-wanted-issues", "updated"]] = Field(
        default=None,
        description="Sort by stars, forks, help-wanted-issues, or updated. Default: best match.",
    )


class CodeSearchInput(SearchInput):
    '''Input for code search (requires authentication).'''
    sort: Optional[Literal["indexed"]] = Field(
        default=None,
        description="Only 'indexed' is supported for code search. Default: best match.",
    )


class IssueSearchInput(SearchInput):
    '''Input for issues/pull-requests search.'''
    sort: Optional[Literal[
        "comments", "reactions", "reactions-+1", "reactions--1", "reactions-smile",
        "reactions-thinking_face", "reactions-heart", "reactions-tada",
        "interactions", "created", "updated",
    ]] = Field(
        default=None,
        description="Sort by comments, reactions, interactions, created, or updated. Default: best match.",
    )


class CommitSearchInput(SearchInput):
    '''Input for commit search.'''
    sort: Optional[Literal["author-date", "committer-date"]] = Field(
        default=None,
        description="Sort by author-date or committer-date. Default: best match.",
    )


class UserSearchInput(SearchInput):
    '''Input for user search.'''
    sort: Optional[Literal["followers", "repositories", "joined"]] = Field(
        default=None,
        description="Sort by followers, repositories, or joined. Default: best match.",
    )


class TopicSearchInput(SearchInput):
    '''Input for topic search.'''
    sort: Optional[Literal["created", "updated"]] = Field(
        default=None,
        description="Sort by created or updated. Default: best match.",
    )


class LabelSearchInput(SearchInput):
    '''Input for label search.'''
    repository_id: int = Field(
        ...,
        description=(
            "Numeric ID of the repository to search labels in, as returned by "
            "github_get_repo's 'id' field (e.g. 1362490 for psf/requests). "
            "Required by the GitHub label search endpoint."
        ),
        ge=1,
    )
    sort: Optional[Literal["created", "updated"]] = Field(
        default=None,
        description="Sort by created or updated. Default: best match.",
    )


class RepoInput(BaseModel):
    '''Input for tools addressing a single repository.'''
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    repo: str = Field(
        ...,
        description="Repository in 'owner/name' format, e.g. 'facebook/react'.",
        pattern=REPO_PATTERN,
        min_length=3,
        max_length=200,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable or 'json' for machine-readable.",
    )


class ReadmeInput(RepoInput):
    '''Input for fetching a repository README.'''
    ref: Optional[str] = Field(
        default=None,
        description="The name of the commit/branch/tag to fetch the README from (default: default branch).",
        max_length=100,
    )


class FileContentInput(RepoInput):
    '''Input for fetching a file or directory from a repository.'''
    path: str = Field(
        ...,
        description="File or directory path relative to the repo root, e.g. 'src/server.py' or 'docs'.",
        min_length=1,
        max_length=500,
    )
    ref: Optional[str] = Field(
        default=None,
        description="The name of the commit/branch/tag to fetch the content from (default: default branch).",
        max_length=100,
    )


class IssueDetailInput(RepoInput):
    '''Input for fetching a single issue or pull request.'''
    issue_number: int = Field(
        ...,
        description="Issue or pull request number, e.g. 123.",
        ge=1,
    )


# --- Field descriptors & type aliases for flattened tool signatures ---------
# FastMCP builds a tool's input schema from the function signature, so these
# Field descriptors are shared via Annotated[...] metadata. The BaseModel
# classes above remain the single source of truth: field constraints (pattern,
# min/max, Literal choices) flow into the tool schemas, and the models
# themselves are unit-tested directly. Sort aliases are derived from the model
# field annotations to avoid declaring the Literal choices twice.

SortValues = Literal["desc", "asc"]
RepoSort = RepoSearchInput.model_fields["sort"].annotation
CodeSort = CodeSearchInput.model_fields["sort"].annotation
IssueSort = IssueSearchInput.model_fields["sort"].annotation
CommitSort = CommitSearchInput.model_fields["sort"].annotation
UserSort = UserSearchInput.model_fields["sort"].annotation
TopicSort = TopicSearchInput.model_fields["sort"].annotation
LabelSort = LabelSearchInput.model_fields["sort"].annotation

Q_FIELD = SearchInput.model_fields["q"]
ORDER_FIELD = SearchInput.model_fields["order"]
PER_PAGE_FIELD = SearchInput.model_fields["per_page"]
PAGE_FIELD = SearchInput.model_fields["page"]
RESPONSE_FORMAT_FIELD = SearchInput.model_fields["response_format"]

REPO_FIELD = RepoInput.model_fields["repo"]
RESPONSE_FORMAT_DETAIL_FIELD = RepoInput.model_fields["response_format"]
REF_FIELD = ReadmeInput.model_fields["ref"]
PATH_FIELD = FileContentInput.model_fields["path"]
ISSUE_NUMBER_FIELD = IssueDetailInput.model_fields["issue_number"]

REPO_SORT_FIELD = RepoSearchInput.model_fields["sort"]
CODE_SORT_FIELD = CodeSearchInput.model_fields["sort"]
ISSUE_SORT_FIELD = IssueSearchInput.model_fields["sort"]
COMMIT_SORT_FIELD = CommitSearchInput.model_fields["sort"]
USER_SORT_FIELD = UserSearchInput.model_fields["sort"]
TOPIC_SORT_FIELD = TopicSearchInput.model_fields["sort"]
LABEL_SORT_FIELD = LabelSearchInput.model_fields["sort"]
REPOSITORY_ID_FIELD = LabelSearchInput.model_fields["repository_id"]
