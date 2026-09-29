'''Shared helpers: error mapping, pagination metadata and markdown rendering.'''

from __future__ import annotations

import html
import json
import re
import time
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.fastmcp import Context

from github_mcp.client import GitHubAPIError, GitHubClient

MAX_SEARCH_RESULTS = 1000
MAX_OUTPUT_CHARS = 25_000

READ_ONLY_TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}


def get_github_client(ctx: Context) -> GitHubClient:
    '''Fetch the shared GitHub client from the server lifespan state.'''
    return ctx.request_context.lifespan_context["github"]


def truncate_output(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    '''Cap output size to protect LLM context; appends a note when truncating.'''
    if len(text) <= limit:
        return text
    return (
        text[:limit].rstrip()
        + f"\n\n> [Output truncated at {limit} characters. "
        "Refine the query or lower per_page for more focused results.]"
    )


def handle_api_error(e: Exception, endpoint: str = "", hint: str = "") -> str:
    '''Map exceptions to actionable, non-revealing error messages.'''
    if isinstance(e, GitHubAPIError):
        status = e.status_code
        if status == 401:
            return (
                "Error: GitHub authentication failed (401). "
                "Set a valid GITHUB_TOKEN in the server environment. "
                "Code search and some private resources require authentication."
            )
        if status == 403:
            raw_ts = e.reset_ts if e.reset_ts and str(e.reset_ts).isdigit() else None
            when = (
                f" It resets at {time.strftime('%H:%M:%S UTC', time.gmtime(int(raw_ts)))}."
                if raw_ts
                else ""
            )
            return (
                f"Error: Forbidden or rate limit exceeded (403): {e.message}.{when} "
                "Authenticate with GITHUB_TOKEN to raise the limit, or wait for the "
                "rate-limit window to reset before retrying."
            )
        if status == 404:
            return (
                f"Error: Resource not found (404) for '{endpoint}'. "
                "Check that the repository is in 'owner/name' format and is public "
                "or accessible with the configured token."
            )
        if status == 422:
            extra = f" {hint}" if hint else ""
            return (
                "Error: Query validation failed (422). "
                "Check qualifier syntax (e.g. repo:, language:, state:), ensure the query "
                f"is under 256 characters and uses at most 5 boolean operators.{extra}"
            )
        if status == 503:
            return "Error: GitHub is temporarily unavailable (503). Please try again shortly."
        return f"Error: GitHub API request failed ({status}): {e.message}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Please try again."
    if isinstance(e, httpx.HTTPError):
        return f"Error: Network request failed: {type(e).__name__}. Please check connectivity."
    return f"Error: Unexpected error: {type(e).__name__}: {e}"


def _pagination(total_count: int, per_page: int, page: int, returned: int) -> Dict[str, Any]:
    '''Build consistent pagination metadata.'''
    offset = (page - 1) * per_page
    # GitHub only serves the first MAX_SEARCH_RESULTS hits, but paging within
    # that window is still possible even when total_count exceeds it.
    reachable = min(total_count, MAX_SEARCH_RESULTS)
    has_more = offset + returned < reachable
    return {
        "total_count": total_count,
        "count": returned,
        "page": page,
        "per_page": per_page,
        "has_more": has_more,
        "next_page": page + 1 if has_more else None,
    }


def build_search_response(
    data: Dict[str, Any],
    items_key: str,
    render_md,
    per_page: int,
    page: int,
    response_format,
    rate_limit_remaining: Optional[str],
) -> str:
    '''Turn a raw GitHub search response into markdown or JSON.'''
    items: List[Dict[str, Any]] = list(data.get(items_key, []))
    total_count = int(data.get("total_count", 0))
    meta = _pagination(total_count, per_page, page, len(items))
    if rate_limit_remaining is not None:
        meta["rate_limit_remaining"] = rate_limit_remaining
    if "incomplete_results" in data:
        meta["incomplete_results"] = data["incomplete_results"]

    if response_format.value == "json":
        # Trim items until the payload fits the output budget, keeping the
        # document valid JSON and flagging the truncation explicitly. Fewer
        # items always means a smaller payload, so a binary search finds the
        # largest fitting prefix in O(log n) serializations.
        def _serialize(kept: List[Dict[str, Any]], truncated: bool) -> str:
            meta["count"] = len(kept)
            payload = {"items": kept, **meta}
            if truncated:
                payload["truncated"] = True
            return json.dumps(payload, indent=2, ensure_ascii=False)

        out = _serialize(items, truncated=False)
        if len(out) > MAX_OUTPUT_CHARS:
            lo, hi = 0, len(items) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if len(_serialize(items[:mid], truncated=True)) <= MAX_OUTPUT_CHARS:
                    lo = mid
                else:
                    hi = mid - 1
            out = _serialize(items[:lo], truncated=True)
        return out

    if not items:
        return f"No results found for query. Total matches: {total_count}."

    lines = [
        f"# Search Results: {total_count} total (showing {len(items)})",
        "",
    ]
    for item in items:
        lines.extend(render_md(item))
        lines.append("")
    if meta["has_more"]:
        lines.append(f"> More results available (page {meta['next_page']}). Use page={meta['next_page']} to continue.")
    if meta.get("incomplete_results"):
        lines.append("> Note: GitHub reports incomplete results (search timed out). Retry or narrow the query.")
    if rate_limit_remaining is not None:
        lines.append(f"> API rate limit remaining: {rate_limit_remaining}")
    return truncate_output("\n".join(lines))


def _render_text_matches(item: Dict[str, Any]) -> List[str]:
    '''Extract GitHub text-match fragments as readable bullet points.'''
    matches = item.get("text_matches") or []
    lines: List[str] = []
    for m in matches[:3]:
        fragment = (m.get("fragment") or "").strip()
        if fragment:
            lines.append(f"  - Match in `{m.get('property', '')}`: {fragment}")
    return lines


# --- Search item renderers -------------------------------------------------

def render_repo(item: Dict[str, Any]) -> List[str]:
    owner = (item.get("owner") or {}).get("login", "?")
    full_name = item.get("full_name") or f"{owner}/{item.get('name', '?')}"
    stars = item.get("stargazers_count", 0)
    lines = [f"## {full_name} (★ {stars})"]
    attrs = []
    if item.get("language"):
        attrs.append(f"Language: {item['language']}")
    attrs.append(f"Forks: {item.get('forks_count', 0)}")
    license_name = (item.get("license") or {}).get("name")
    if license_name:
        attrs.append(f"License: {license_name}")
    if item.get("fork"):
        attrs.append("forked")
    if attrs:
        lines.append(f"- **{' | '.join(attrs)}**")
    if item.get("description"):
        lines.append(f"- {item['description']}")
    if item.get("topics"):
        lines.append(f"- Topics: {', '.join(item['topics'][:8])}")
    lines.append(f"- URL: {item.get('html_url', '')}")
    lines.extend(_render_text_matches(item))
    return lines


def render_code(item: Dict[str, Any]) -> List[str]:
    repo_full = (item.get("repository") or {}).get("full_name") or _repo_from_url(item.get("repository_url"))
    path = item.get("path", "?")
    lines = [f"## {repo_full}:{path}"]
    if item.get("language"):
        lines.append(f"- **Language**: {item['language']}")
    lines.append(f"- URL: {item.get('html_url', '')}")
    lines.extend(_render_text_matches(item))
    return lines


def _repo_from_url(repository_url: Optional[str]) -> str:
    '''Extract 'owner/name' from an API repository_url like .../repos/psf/requests.'''
    if not repository_url:
        return "?"
    parts = repository_url.rstrip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else repository_url


def render_issue(item: Dict[str, Any]) -> List[str]:
    repo_full = (item.get("repository") or {}).get("full_name") or _repo_from_url(item.get("repository_url"))
    number = item.get("number", "?")
    title = item.get("title", "(no title)")
    state = item.get("state", "?")
    lines = [f"## {repo_full}#{number}: {title} [{state}]"]
    labels = ", ".join(l.get("name", "") for l in item.get("labels", []) if l.get("name"))
    if labels:
        lines.append(f"- **Labels**: {labels}")
    user = (item.get("user") or {}).get("login", "?")
    created = (item.get("created_at") or "")[:10]
    lines.append(f"- **By {user} on {created} | Comments: {item.get('comments', 0)}**")
    if item.get("pull_request"):
        lines.append("- *(Pull request)*")
    body = (item.get("body") or "").strip().splitlines()
    if body:
        preview = " ".join(body[0].split())[:160]
        lines.append(f"- {preview}")
    lines.append(f"- URL: {item.get('html_url', '')}")
    lines.extend(_render_text_matches(item))
    return lines


def render_commit(item: Dict[str, Any]) -> List[str]:
    commit = item.get("commit") or {}
    sha = item.get("sha", "?")[:7]
    message = (commit.get("message") or "").splitlines()[0] if commit.get("message") else "(no message)"
    author = (commit.get("author") or {})
    author_name = author.get("name", "?")
    author_date = (author.get("date") or "")[:10]
    repo_full = (item.get("repository") or {}).get("full_name") or _repo_from_url(item.get("repository_url"))
    lines = [
        f"## {sha}: {message}",
        f"- **{author_name} on {author_date} | repo: {repo_full}**",
        f"- URL: {item.get('html_url', '')}",
    ]
    lines.extend(_render_text_matches(item))
    return lines


def render_user(item: Dict[str, Any]) -> List[str]:
    # The search API only returns login/type/score (followers, bio and name
    # are exclusive to the user detail endpoint), so don't render fields that
    # would show misleading placeholders like "Followers: 0".
    login = item.get("login", "?")
    name = item.get("name") or ""
    lines = [f"## {login} {f'({name})' if name else ''}"]
    lines.append(f"- **Type: {item.get('type', '?')} | Score: {item.get('score', 0)}**")
    lines.append(f"- URL: {item.get('html_url', '')}")
    lines.extend(_render_text_matches(item))
    return lines


def _strip_html(value: Optional[str]) -> str:
    '''Remove HTML tags and unescape entities (topics descriptions come as HTML).'''
    if not value:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def render_topic(item: Dict[str, Any]) -> List[str]:
    lines = [f"## {item.get('name', '?')}"]
    description = _strip_html(item.get("description"))
    if description:
        lines.append(f"- {description}")
    if item.get("curated"):
        lines.append("- Curated topic")
    lines.append(f"- Score: {item.get('score', 0)}")
    return lines


def render_label(item: Dict[str, Any]) -> List[str]:
    lines = [f"## {item.get('name', '?')}"]
    if item.get("description"):
        lines.append(f"- {item['description']}")
    lines.append(f"- Color: #{item.get('color', '')} | Default: {bool(item.get('default'))}")
    return lines
