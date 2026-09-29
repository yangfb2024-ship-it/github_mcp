'''GitHub search tools: repositories, code, issues, commits, users, topics, labels.'''

from __future__ import annotations

from typing import Annotated, Any, Callable, Dict, Optional

from mcp.server.fastmcp import Context, FastMCP

from github_mcp.client import GitHubClient
from github_mcp.models import (
    CODE_SORT_FIELD,
    COMMIT_SORT_FIELD,
    ISSUE_SORT_FIELD,
    LABEL_SORT_FIELD,
    ORDER_FIELD,
    PAGE_FIELD,
    PER_PAGE_FIELD,
    Q_FIELD,
    REPOSITORY_ID_FIELD,
    REPO_SORT_FIELD,
    RESPONSE_FORMAT_FIELD,
    TOPIC_SORT_FIELD,
    USER_SORT_FIELD,
    CodeSort,
    CommitSort,
    IssueSort,
    LabelSort,
    RepoSort,
    ResponseFormat,
    SortValues,
    TopicSort,
    UserSort,
)
from github_mcp.utils import (
    READ_ONLY_TOOL_ANNOTATIONS,
    build_search_response,
    get_github_client,
    handle_api_error,
    render_code,
    render_commit,
    render_issue,
    render_label,
    render_repo,
    render_topic,
    render_user,
)


async def _search(
    ctx: Context,
    endpoint: str,
    renderer: Callable[[Dict[str, Any]], list],
    *,
    q: str,
    sort: Optional[str],
    order: str,
    per_page: int,
    page: int,
    response_format: ResponseFormat,
    text_match: bool = False,
    repository_id: Optional[int] = None,
    error_hint: str = "",
) -> str:
    '''Shared search implementation used by all seven search tools.'''
    client: GitHubClient = get_github_client(ctx)
    query_params: Dict[str, Any] = {
        "q": q,
        "per_page": per_page,
        "page": page,
    }
    if repository_id is not None:
        query_params["repository_id"] = repository_id
    if sort:
        query_params["sort"] = sort
        query_params["order"] = order

    try:
        data = await client.search(endpoint, query_params, text_match=text_match)
    except Exception as e:
        return handle_api_error(e, endpoint, hint=error_hint)

    return build_search_response(
        data,
        "items",
        renderer,
        per_page,
        page,
        response_format,
        client.rate_limit_remaining,
    )


def register_search_tools(mcp: FastMCP) -> None:
    '''Register all search tools on the given server instance.'''

    @mcp.tool(
        name="github_search_repos",
        annotations={"title": "Search GitHub Repositories", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_search_repos(
        q: Annotated[str, Q_FIELD],
        sort: Annotated[RepoSort, REPO_SORT_FIELD] = None,
        order: Annotated[SortValues, ORDER_FIELD] = "desc",
        per_page: Annotated[int, PER_PAGE_FIELD] = 20,
        page: Annotated[int, PAGE_FIELD] = 1,
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Search for repositories by keywords and qualifiers.

        Supports qualifiers such as language:, stars:, forks:, user:, org:, topics:,
        in:readme, is:fork, archived:true/false and more. Results are sorted by
        best match unless a sort option is given. When the user wants popular,
        high-quality, or most-starred repos, pass sort="stars" with order="desc".

        Examples:
            - Use when: "Find popular fastmcp servers in Python" -> q="fastmcp language:python" sort="stars"
            - Use when: "Show the most starred AI agent frameworks" -> q="agent framework" sort="stars"
            - Use when: "Show unmaintained forks of react" -> q="fork:true archived:true repo:facebook/react"
            - Don't use when: you need code snippets inside files (use github_search_code)
        '''
        return await _search(
            ctx, "repositories", render_repo,
            q=q, sort=sort, order=order, per_page=per_page, page=page,
            response_format=response_format,
        )

    @mcp.tool(
        name="github_search_code",
        annotations={"title": "Search GitHub Code", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_search_code(
        q: Annotated[str, Q_FIELD],
        sort: Annotated[CodeSort, CODE_SORT_FIELD] = None,
        order: Annotated[SortValues, ORDER_FIELD] = "desc",
        per_page: Annotated[int, PER_PAGE_FIELD] = 20,
        page: Annotated[int, PAGE_FIELD] = 1,
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Search for code inside files. Requires GITHUB_TOKEN (10 req/min).

        Only the default branch is searched; only files smaller than 384 KB are
        indexed. Always include at least one keyword (e.g. "addClass in:file
        language:js repo:jquery/jquery"). Returns text-match fragments showing
        why each file matched.

        Examples:
            - Use when: "Find where argparse is imported in fastapi" -> q="argparse language:python repo:fastapi/fastapi"
            - Use when: "Search implementation of sort in django" -> q="def sort language:python repo:django/django"
            - Don't use when: no GITHUB_TOKEN is configured (search will fail with 401)
        '''
        return await _search(
            ctx, "code", render_code,
            q=q, sort=sort, order=order, per_page=per_page, page=page,
            response_format=response_format, text_match=True,
        )

    @mcp.tool(
        name="github_search_issues",
        annotations={"title": "Search GitHub Issues and Pull Requests", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_search_issues(
        q: Annotated[str, Q_FIELD],
        sort: Annotated[IssueSort, ISSUE_SORT_FIELD] = None,
        order: Annotated[SortValues, ORDER_FIELD] = "desc",
        per_page: Annotated[int, PER_PAGE_FIELD] = 20,
        page: Annotated[int, PAGE_FIELD] = 1,
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Search issues and pull requests by keyword, labels, state, and more.

        Supports qualifiers: state:, label:, author:, assignee:, is:issue,
        is:pr, is:open, is:closed, milestone:, repo:, user:, org:, language:.
        Returns text-match fragments on titles/bodies.

        Note: when the server runs with a GITHUB_TOKEN, GitHub requires the
        query to include 'is:issue' or 'is:pull-request' to scope the search.

        Examples:
            - Use when: "List open bug issues in requests" -> q="repo:psf/requests label:bug state:open is:issue"
            - Use when: "Find merged PRs touching the client module" -> q="repo:psf/requests is:pr is:merged client"
        '''
        return await _search(
            ctx, "issues", render_issue,
            q=q, sort=sort, order=order, per_page=per_page, page=page,
            response_format=response_format, text_match=True,
            error_hint="With a GITHUB_TOKEN, GitHub requires 'is:issue' or 'is:pull-request' in the query.",
        )

    @mcp.tool(
        name="github_search_commits",
        annotations={"title": "Search GitHub Commits", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_search_commits(
        q: Annotated[str, Q_FIELD],
        sort: Annotated[CommitSort, COMMIT_SORT_FIELD] = None,
        order: Annotated[SortValues, ORDER_FIELD] = "desc",
        per_page: Annotated[int, PER_PAGE_FIELD] = 20,
        page: Annotated[int, PAGE_FIELD] = 1,
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Search commits on the default branch by message, author, or hash.

        Supports qualifiers: author:, committer:, author-name:, committer-name:
        and repo:. Use sort="author-date" or "committer-date" to order by time.

        Examples:
            - Use when: "Find recent commits mentioning security fix" -> q="security fix sort:committer-date"
        '''
        return await _search(
            ctx, "commits", render_commit,
            q=q, sort=sort, order=order, per_page=per_page, page=page,
            response_format=response_format, text_match=True,
        )

    @mcp.tool(
        name="github_search_users",
        annotations={"title": "Search GitHub Users", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_search_users(
        q: Annotated[str, Q_FIELD],
        sort: Annotated[UserSort, USER_SORT_FIELD] = None,
        order: Annotated[SortValues, ORDER_FIELD] = "desc",
        per_page: Annotated[int, PER_PAGE_FIELD] = 20,
        page: Annotated[int, PAGE_FIELD] = 1,
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Search GitHub users by name, login, location, or bio keywords.

        Supports qualifiers: type:user, type:org, in:login, in:name,
        followers:>, location:, repos:>, language:.

        Examples:
            - Use when: "Find the maintainer named Guido van Rossum" -> q="guido in:login type:user"
        '''
        return await _search(
            ctx, "users", render_user,
            q=q, sort=sort, order=order, per_page=per_page, page=page,
            response_format=response_format,
        )

    @mcp.tool(
        name="github_search_topics",
        annotations={"title": "Search GitHub Topics", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_search_topics(
        q: Annotated[str, Q_FIELD],
        sort: Annotated[TopicSort, TOPIC_SORT_FIELD] = None,
        order: Annotated[SortValues, ORDER_FIELD] = "desc",
        per_page: Annotated[int, PER_PAGE_FIELD] = 20,
        page: Annotated[int, PAGE_FIELD] = 1,
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Search repository topics (tags).

        Supports the qualifier is:featured for curated topics.

        Examples:
            - Use when: "What are the most used web framework topics" -> q="web framework"
        '''
        return await _search(
            ctx, "topics", render_topic,
            q=q, sort=sort, order=order, per_page=per_page, page=page,
            response_format=response_format,
        )

    @mcp.tool(
        name="github_search_labels",
        annotations={"title": "Search GitHub Labels", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_search_labels(
        q: Annotated[str, Q_FIELD],
        repository_id: Annotated[int, REPOSITORY_ID_FIELD],
        sort: Annotated[LabelSort, LABEL_SORT_FIELD] = None,
        order: Annotated[SortValues, ORDER_FIELD] = "desc",
        per_page: Annotated[int, PER_PAGE_FIELD] = 20,
        page: Annotated[int, PAGE_FIELD] = 1,
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Search repository labels by name or color. The GitHub API requires
        the numeric repository ID, which github_get_repo returns as 'id'.

        Examples:
            - Use when: "Find bug-related labels in requests" -> q="bug" repository_id=1362490
        '''
        return await _search(
            ctx, "labels", render_label,
            q=q, sort=sort, order=order, per_page=per_page, page=page,
            response_format=response_format, repository_id=repository_id,
        )
