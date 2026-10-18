"""Tool exposing safe in-memory patch proposals to the LLM."""
from __future__ import annotations

from langchain_core.tools import tool

from app.agent.patches import PatchSession


def make_patch_tool(session: PatchSession):
    @tool
    def submit_patch(path: str, old_text: str, new_text: str, explanation: str) -> str:
        """Propose ONE minimal code change in an existing .py file; never writes it.

        path: relative repository path such as app/tools/repo_tools.py.
        old_text: exact text copied from the file, WITHOUT line-number prefixes.
        new_text: the replacement snippet, with matching indentation.
        explanation: brief justification for the change.

        A successful proposal is syntax-checked and will be shown as a diff to the user.
        First read the targeted code to obtain an exact, unique old_text excerpt.
        """
        try:
            proposal = session.propose(
                path=path, old_text=old_text,
                new_text=new_text, explanation=explanation,
            )
            return (
                f"Patch proposal recorded for {proposal.path}; Python syntax valid. "
                "No source files changed. Stop requesting tools and summarize the proposal."
            )
        except ValueError as exc:
            return f"Patch rejected: {exc}"
        except (OSError, UnicodeError):
            return "Patch rejected: target file could not be read"

    return submit_patch
