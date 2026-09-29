#!/usr/bin/env python3
'''MCP server for GitHub data retrieval.

Runs over streamable HTTP by default (remote/multi-client) or stdio for local use.
Set GITHUB_TOKEN in the environment to enable code search and raise rate limits.
'''

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from github_mcp.client import GitHubClient
from github_mcp.tools.detail import register_detail_tools
from github_mcp.tools.search import register_search_tools

logger = logging.getLogger(__name__)


def _strip_quotes(value: str) -> str:
    '''Remove one layer of matching surrounding quotes, if present.'''
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _load_dotenv(path: str = ".env") -> None:
    '''Load KEY=VALUE pairs from a .env file without overriding existing env vars.'''
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].lstrip()
                key, _, value = line.partition("=")
                key = key.strip()
                value = _strip_quotes(value.strip())
                if key and key not in os.environ:
                    os.environ[key] = value
        logger.info("Loaded environment from %s", path)
    except OSError as e:  # pragma: no cover
        logger.warning("Could not read %s: %s", path, e)


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    '''Create and tear down the shared GitHub API client.'''
    token = os.getenv("GITHUB_TOKEN", "").strip() or None
    if token:
        logger.info("GitHub client initialized with token (code search enabled, 30 req/min).")
    else:
        logger.warning(
            "GITHUB_TOKEN not set. Unauthenticated search limits apply (10 req/min) "
            "and code search is unavailable."
        )
    client = GitHubClient(token=token)
    try:
        yield {"github": client}
    finally:
        await client.aclose()


def create_server(host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    '''Build the FastMCP server instance with all tools registered.'''
    mcp = FastMCP(
        "github_mcp",
        host=host,
        port=port,
        lifespan=app_lifespan,
        instructions=(
            "GitHub data retrieval server. Use github_search_* tools to find "
            "repositories, code, issues, commits, users, topics and labels, then "
            "follow up with github_get_* tools to fetch full details. "
            "Search queries support GitHub qualifiers such as language:, repo:, "
            "label:, state:, stars: and is:."
        ),
    )
    register_search_tools(mcp)
    register_detail_tools(mcp)
    return mcp


def main() -> None:
    '''Entry point: run over streamable HTTP unless MCP_TRANSPORT=stdio.'''
    logging.basicConfig(level=logging.INFO)
    _load_dotenv()
    host = os.getenv("HOST", "127.0.0.1")
    try:
        port = int(os.getenv("PORT", "8000"))
    except ValueError:
        raise SystemExit(f"Invalid PORT {os.getenv('PORT')!r}: must be an integer.")
    mcp = create_server(host=host, port=port)
    transport = os.getenv("MCP_TRANSPORT", "streamable_http")
    if transport == "stdio":
        logger.info("Starting github_mcp over stdio.")
        mcp.run(transport="stdio")
    else:
        logger.info("Starting github_mcp over streamable HTTP on http://%s:%s", host, port)
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
