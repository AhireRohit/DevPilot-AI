"""LangChain tool wrappers around the existing read-only RepositoryExplorer.

Repository paths are fixed by the CLI and cannot be selected by the LLM.
No shell commands, writes, git pushes, or network tools are exposed.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool

from app.tools.repo_tools import RepositoryExplorer


def make_repository_tools(explorer: RepositoryExplorer):
    """Create tools bound to a single user-selected repository root."""

    @tool
    def list_repository_files(limit: int = 60) -> str:
        """List source/documentation paths in the selected repository; begin here to discover files."""
        try:
            return json.dumps(explorer.list_files(limit=min(max(limit, 1), 100)))
        except (ValueError, OSError) as exc:
            return f"Tool error: {exc}"

    @tool
    def search_repository_code(query: str, limit: int = 15) -> str:
        """Search repository text for an exact word or phrase, returning file paths and line numbers."""
        try:
            if len(query) > 200:
                return "Tool error: Search query must be 200 characters or fewer"
            results = explorer.search_code(query, limit=min(max(limit, 1), 30))
            return json.dumps(results)
        except (ValueError, OSError) as exc:
            return f"Tool error: {exc}"

    @tool
    def read_repository_file(path: str, start: int = 1, end: int = 80) -> str:
        """Read numbered lines from a repository file. Read in blocks of at most 100 lines (e.g. start=1, end=100). Use relative paths from list/search. Avoid empty files."""
        try:
            if start < 1 or end < start:
                return "Tool error: Invalid line range (start must be >= 1, end >= start)"
            requested_end = end
            end = min(end, start + 99)
            content = explorer.read_file(path, start=start, end=end) or "(No lines in requested range)"
            if requested_end > end:
                return f"[Read capped at lines {start}-{end}; request more if needed.]\n{content}"
            return content
        except (ValueError, OSError) as exc:
            return f"Tool error: {exc}"

    @tool
    def inspect_python_symbols(path: str) -> str:
        """Find class/function/method declarations and line numbers in a Python source file."""
        try:
            return json.dumps(explorer.python_symbols(path))
        except (ValueError, OSError) as exc:
            return f"Tool error: {exc}"

    return [list_repository_files, search_repository_code, read_repository_file, inspect_python_symbols]
