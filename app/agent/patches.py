"""In-memory, review-only proposals for a single existing Python file.

No methods in this module write source files or execute repository code.
"""
from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.tools.repo_tools import RepositoryExplorer

MAX_OLD_TEXT = 4000
MAX_NEW_TEXT = 4000
MAX_FILE_BYTES = 64000


@dataclass(frozen=True)
class PatchProposal:
    path: str
    explanation: str
    diff: str
    original: str
    proposed: str


class PatchSession:
    """Hold at most one proposed patch for one explicitly selected repository."""

    def __init__(self, explorer: RepositoryExplorer):
        self.explorer = explorer
        self.proposal: PatchProposal | None = None

    def propose(self, *, path: str, old_text: str, new_text: str,
                explanation: str) -> PatchProposal:
        if self.proposal is not None:
            raise ValueError("A patch has already been proposed in this run")
        if not isinstance(path, str) or not path or "\\" in path or ":" in path:
            raise ValueError("Use a relative repository path with forward slashes")
        relative = PurePosixPath(path)
        if relative.is_absolute() or any(p in ("..", ".", "") for p in path.split("/")):
            raise ValueError("Absolute and traversal paths are not permitted")
        if relative.suffix.lower() != ".py":
            raise ValueError("Step 4 supports existing Python (.py) files only")
        if not old_text or not old_text.strip():
            raise ValueError("old_text must be a nonempty, exact source-code excerpt")
        if not isinstance(new_text, str):
            raise ValueError("new_text must be text")
        if len(old_text) > MAX_OLD_TEXT or len(new_text) > MAX_NEW_TEXT:
            raise ValueError("Replacement is too large; use a targeted edit")
        if not explanation or not explanation.strip():
            raise ValueError("Explain why the change is needed")

        # Reject symlinks in *any* path component before resolving the file.
        current = self.explorer.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Cannot propose edits through symlinks")

        source_path = self.explorer._safe_file(path)
        if source_path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("File too large for a Step 4 patch proposal")
        original = source_path.read_text(encoding="utf-8")
        count = original.count(old_text)
        if count == 0:
            raise ValueError("old_text was not found exactly; read the file again")
        if count != 1:
            raise ValueError("old_text matches multiple locations; make the excerpt unique")
        proposed = original.replace(old_text, new_text, 1)
        if proposed == original:
            raise ValueError("Replacement would not change the file")
        try:
            ast.parse(proposed, filename=path)
        except SyntaxError as exc:
            raise ValueError(f"Proposed Python has invalid syntax near line {exc.lineno}") from None

        diff = "".join(difflib.unified_diff(
            original.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=f"a/{relative.as_posix()}",
            tofile=f"b/{relative.as_posix()}",
            n=3,
        ))
        patch = PatchProposal(
            path=relative.as_posix(),
            explanation=explanation.strip()[:500],
            diff=diff,
            original=original,
            proposed=proposed,
        )
        self.proposal = patch
        return patch
