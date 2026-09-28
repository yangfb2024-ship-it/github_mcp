'''GitHub detail-retrieval tools: repo, README, file content, issue.'''

from __future__ import annotations

import base64
import json
from typing import Annotated, Any, Dict, Optional

from mcp.server.fastmcp import Context, FastMCP

from github_mcp.client import GitHubClient
from github_mcp.models import (
    ISSUE_NUMBER_FIELD,
    PATH_FIELD,
    REF_FIELD,
    REPO_FIELD,
    RESPONSE_FORMAT_DETAIL_FIELD,
    ResponseFormat,
)
from github_mcp.utils import (
    READ_ONLY_TOOL_ANNOTATIONS,
    get_github_client,
    handle_api_error,
    truncate_output,
)

MAX_INLINE_FILE_SIZE = 2_000_000


def _client(ctx: Context) -> GitHubClient:
    return get_github_client(ctx)


def _to_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _render_repo_md(data: Dict[str, Any]) -> str:
    full_name = data.get("full_name", "?")
    lines = [
        f"# {full_name}",
        f"- **{data.get('description') or 'No description'}**",
        "",
    ]
    attrs = []
    if data.get("language"):
        attrs.append(f"Language: {data['language']}")
    attrs.append(f"Stars: {data.get('stargazers_count', 0)}")
    attrs.append(f"Forks: {data.get('forks_count', 0)}")
    attrs.append(f"Watchers: {data.get('watchers_count', 0)}")
    attrs.append(f"Open issues: {data.get('open_issues_count', 0)}")
    if data.get("license"):
        attrs.append(f"License: {data['license'].get('name', '?')}")
    lines.append(f"- **{' | '.join(attrs)}**")
    if data.get("topics"):
        lines.append(f"- Topics: {', '.join(data['topics'][:12])}")
    lines.append(f"- Default branch: {data.get('default_branch', '?')}")
    if data.get("homepage"):
        lines.append(f"- Homepage: {data['homepage']}")
    lines.append(f"- Created: {(data.get('created_at') or '')[:10]} | Last push: {(data.get('pushed_at') or '')[:10]}")
    lines.append(f"- URL: {data.get('html_url', '')}")
    if data.get("archived"):
        lines.append("- **Note: this repository is archived (read-only).**")
    return "\n".join(lines)


def _render_readme_md(path: str, content: str, html_url: str) -> str:
    return (
        f"# README: {path}\n"
        f"Source: {html_url}\n\n"
        f"```markdown\n{content}\n```"
    )


def _render_file_md(data: Dict[str, Any], content: str) -> str:
    path = data.get("path", "?")
    size = data.get("size", 0)
    if data.get("encoding") == "base64":
        content = base64.b64decode(content).decode("utf-8", errors="replace")
    elif not content:
        content = "(binary file)"
    return (
        f"# File: {path} ({size} bytes)\n"
        f"URL: {data.get('html_url', '')}\n\n"
        f"```\n{content}\n```"
    )


def _render_dir_md(data: Any, path: str) -> str:
    lines = [f"# Directory: {path}", ""]
    for entry in sorted(data, key=lambda e: (e.get("type") != "dir", e.get("name", ""))):
        kind = "dir/" if entry.get("type") == "dir" else "file"
        size = f" ({entry.get('size', 0)} bytes)" if kind == "file" else ""
        lines.append(f"- `{kind}` {entry.get('name', '?')}{size}")
    return "\n".join(lines)


def _render_issue_md(
    data: Dict[str, Any],
    repo: str,
    issue_number: int,
    pr_data: Optional[Dict[str, Any]] = None,
) -> str:
    '''Render an issue/PR payload as markdown.

    The issues API nests PR info under 'pull_request' (merged_at lives there)
    and never exposes merge_commit_sha; that field comes from the pulls API,
    passed in via pr_data on a best-effort basis.
    '''
    title = data.get("title", "(no title)")
    state = data.get("state", "?")
    labels = ", ".join(l.get("name", "") for l in data.get("labels", []) if l.get("name"))
    author = (data.get("user") or {}).get("login", "?")
    lines = [
        f"# {repo}#{issue_number}: {title}",
        f"- **State: {state}** | Labels: {labels or 'none'}",
        f"- By **{author}** | Created: {(data.get('created_at') or '')[:10]} | "
        f"Updated: {(data.get('updated_at') or '')[:10]} | Comments: {data.get('comments', 0)}",
    ]
    if data.get("assignees"):
        lines.append(f"- Assignees: {', '.join(u.get('login', '?') for u in data['assignees'])}")
    pr = data.get("pull_request")
    if pr:
        lines.append("- *(Pull request)*")
        merged_at = pr.get("merged_at")
        if merged_at:
            lines.append(f"- **Merged** on {merged_at[:10]}")
        merge_sha = (pr_data or {}).get("merge_commit_sha")
        if merge_sha:
            lines.append(f"- Merge commit: {merge_sha}")
    lines.append(f"- URL: {data.get('html_url', '')}")
    body = data.get("body") or "(no body)"
    lines += ["", "---", "", "## Body", "", body]
    return "\n".join(lines)


def register_detail_tools(mcp: FastMCP) -> None:
    '''Register all detail-retrieval tools on the given server instance.'''

    @mcp.tool(
        name="github_get_repo",
        annotations={"title": "Get GitHub Repository Details", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_get_repo(
        repo: Annotated[str, REPO_FIELD],
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_DETAIL_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Fetch full details of a single repository.

        Returns language, star/fork/watch counts, open issues, license, topics,
        default branch, homepage, creation and last-push dates.

        Examples:
            - Use when: "How many stars does fastapi have" -> repo="fastapi/fastapi"
            - Use when: "What license does requests use" -> repo="psf/requests"
        '''
        client = _client(ctx)
        try:
            data = await client.get(f"/repos/{repo}")
        except Exception as e:
            return handle_api_error(e, repo)
        if response_format.value == "json":
            return _to_json(data)
        return _render_repo_md(data)

    @mcp.tool(
        name="github_get_repo_readme",
        annotations={"title": "Get Repository README", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_get_repo_readme(
        repo: Annotated[str, REPO_FIELD],
        ref: Annotated[Optional[str], REF_FIELD] = None,
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_DETAIL_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Fetch the README of a repository as raw markdown text.

        Useful for understanding project purpose, usage and quick-start docs.

        Examples:
            - Use when: "Summarize what fastapi is about" -> repo="fastapi/fastapi"
            - Use when: "What are the install steps for requests" -> repo="psf/requests"
        '''
        client = _client(ctx)
        params_ = {"ref": ref} if ref else None
        try:
            data = await client.get(f"/repos/{repo}/readme", params_)
        except Exception as e:
            return handle_api_error(e, repo)
        if response_format.value == "json":
            return _to_json(data)
        content = ""
        if data.get("encoding") == "base64" and data.get("content"):
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        elif data.get("size", 0) > 0:
            # README too large for the JSON payload (GitHub truncates content
            # above 1 MB); fall back to the raw media type.
            try:
                content = await client.get_raw(f"/repos/{repo}/readme", params_)
            except Exception:
                content = ""
        return truncate_output(_render_readme_md(data.get("path", "README"), content, data.get("html_url", "")))

    @mcp.tool(
        name="github_get_file_content",
        annotations={"title": "Get File or Directory Content", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_get_file_content(
        repo: Annotated[str, REPO_FIELD],
        path: Annotated[str, PATH_FIELD],
        ref: Annotated[Optional[str], REF_FIELD] = None,
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_DETAIL_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Fetch the content of a file or list a directory in a repository.

        For files, returns the decoded text (UTF-8). Files larger than 2 MB
        are not inlined; the response includes size and URL instead. If the
        path is a directory, returns a listing of its entries.

        Examples:
            - Use when: "Show me the setup.py of requests" -> repo="psf/requests" path="setup.py"
            - Use when: "What files are in the src folder of fastapi" -> repo="fastapi/fastapi" path="fastapi"
        '''
        client = _client(ctx)
        params_ = {"ref": ref} if ref else None
        try:
            data = await client.get(f"/repos/{repo}/contents/{path}", params_)
        except Exception as e:
            return handle_api_error(e, repo)
        if response_format.value == "json":
            return _to_json(data)

        if isinstance(data, list):
            return _render_dir_md(data, path)
        content = data.get("content") or ""
        if data.get("size", 0) > MAX_INLINE_FILE_SIZE:
            return (
                f"# File: {path}\n"
                f"File is {data.get('size')} bytes and is not inlined.\n"
                f"- Download: {data.get('download_url')}\n"
                f"- URL: {data.get('html_url', '')}"
            )
        return truncate_output(_render_file_md(data, content))

    @mcp.tool(
        name="github_get_issue",
        annotations={"title": "Get Issue or Pull Request Details", **READ_ONLY_TOOL_ANNOTATIONS},
    )
    async def github_get_issue(
        repo: Annotated[str, REPO_FIELD],
        issue_number: Annotated[int, ISSUE_NUMBER_FIELD],
        response_format: Annotated[ResponseFormat, RESPONSE_FORMAT_DETAIL_FIELD] = ResponseFormat.MARKDOWN,
        ctx: Context = None,
    ) -> str:
        '''Fetch a single issue or pull request with its full body.

        Includes title, state, labels, assignees, author, timestamps, body and
        comment count. PRs also expose the merged flag and merge commit SHA.

        Examples:
            - Use when: "Show me the body of issue #4312 in requests" -> repo="psf/requests" issue_number=4312
        '''
        client = _client(ctx)
        try:
            data = await client.get(f"/repos/{repo}/issues/{issue_number}")
        except Exception as e:
            return handle_api_error(e, repo)
        if response_format.value == "json":
            return _to_json(data)

        # merge_commit_sha is not part of the issues payload; fetch the PR
        # detail on a best-effort basis (merge info is nice-to-have).
        pr_data = None
        if data.get("pull_request"):
            try:
                pr_data = await client.get(f"/repos/{repo}/pulls/{issue_number}")
            except Exception:
                pr_data = None
        return truncate_output(_render_issue_md(data, repo, issue_number, pr_data))
