"""Safe, read-only repository exploration functions.

No network/API calls, shell execution, or file modification.
The caller must provide the local path of an authorized repository.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "node_modules", "dist", "build",
    ".next", ".tox", "site-packages", ".idea", ".vscode",
    "pytest_temp",
}
PRIVATE_NAMES = {".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519"}
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"}
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json",
    ".ini", ".cfg", ".rst", ".html", ".css", ".js", ".ts",
    ".tsx", ".jsx", ".sh", ".ps1", ".sql", ".xml",
}
MAX_BYTES = 256_000


class RepositoryExplorer:
    """Inspect a local repository without allowing reads outside its root."""

    def __init__(self, repo_path: str | Path):
        self.root = Path(repo_path).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError(f"Not a directory: {self.root}")

    @staticmethod
    def _private_name(filename: str) -> bool:
        name = filename.lower()
        return (
            name in PRIVATE_NAMES
            or (name.startswith(".env.") and name != ".env.example")
            or Path(name).suffix in PRIVATE_SUFFIXES
        )

    def _safe_file(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve(strict=True)
        try:
            parts = candidate.relative_to(self.root).parts
        except ValueError as exc:
            raise ValueError("Path is outside the selected repository") from exc
        if any(part.lower() in EXCLUDED_DIRS for part in parts[:-1]):
            raise ValueError("Cannot read ignored directories")
        if self._private_name(candidate.name):
            raise ValueError("Reading secret or credential files is disabled")
        if not candidate.is_file():
            raise ValueError("The requested path is not a regular file")
        if candidate.stat().st_size > MAX_BYTES:
            raise ValueError(f"File exceeds {MAX_BYTES:,} byte limit")
        return candidate

    def _files(self):
        """Yield eligible files, excluding common dependencies and sensitive files."""
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(
                d for d in dirs
                if d.lower() not in EXCLUDED_DIRS
                and not (Path(directory) / d).is_symlink()
            )
            for filename in sorted(files):
                path = Path(directory) / filename
                if path.is_symlink() or self._private_name(filename):
                    continue
                if path.suffix.lower() not in TEXT_SUFFIXES and filename not in {
                    "Dockerfile", "Makefile", ".gitignore", ".env.example"
                }:
                    continue
                try:
                    if path.stat().st_size > MAX_BYTES:
                        continue
                except OSError:
                    continue
                yield path

    def list_files(self, limit: int = 120) -> list[str]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        result = []
        for path in self._files():
            result.append(path.relative_to(self.root).as_posix())
            if len(result) >= limit:
                break
        return result

    def search_code(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        if not query.strip():
            raise ValueError("Search query cannot be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        matches = []
        term = query.casefold()
        for path in self._files():
            try:
                with path.open("r", encoding="utf-8") as stream:
                    for number, line in enumerate(stream, 1):
                        if term in line.casefold():
                            matches.append({
                                "file": path.relative_to(self.root).as_posix(),
                                "line": number,
                                "text": line.rstrip()[:240],
                            })
                            if len(matches) >= limit:
                                return matches
            except (UnicodeError, OSError):
                continue
        return matches

    def read_file(self, relative_path: str, start: int = 1, end: int = 120) -> str:
        if start < 1 or end < start or end - start + 1 > 160:
            raise ValueError("Request 1–160 lines with valid start/end numbers")
        path = self._safe_file(relative_path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeError as exc:
            raise ValueError("File is not valid UTF-8 text") from exc
        selection = lines[start - 1:end]
        return "\n".join(f"{i:>4} | {line}" for i, line in enumerate(selection, start))

    def python_symbols(self, relative_path: str) -> list[dict[str, Any]]:
        path = self._safe_file(relative_path)
        if path.suffix.lower() != ".py":
            raise ValueError("Symbol extraction is available for Python files only")
        try:
            syntax = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeError) as exc:
            raise ValueError(f"Could not parse Python file: {exc}") from exc
        symbols = []
        for node in syntax.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({"kind": "function", "name": node.name, "line": node.lineno})
            elif isinstance(node, ast.ClassDef):
                symbols.append({"kind": "class", "name": node.name, "line": node.lineno})
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append({
                            "kind": "method", "name": f"{node.name}.{child.name}",
                            "line": child.lineno,
                        })
        return symbols
