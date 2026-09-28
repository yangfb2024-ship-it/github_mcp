'''MCP server for GitHub data retrieval.'''

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("github_mcp")
except PackageNotFoundError:  # running from a bare checkout, not installed
    __version__ = "0.0.0"
