"""Propose a review-only Python code patch using Groq and LangGraph.

Example:
python -m app.patch_cli --repo . --task "Make _files skip unreadable entries"
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.patch_graph import make_patch_agent
from app.agent.focus import focused_source_excerpt
from app.tools.repo_tools import RepositoryExplorer


def main():
    parser = argparse.ArgumentParser(description="DevPilot review-only patch proposer")
    parser.add_argument("--repo", default=".", help="Repository directory")
    parser.add_argument("--task", required=True, help="Specific bug or code change to propose")
    parser.add_argument("--max-calls", type=int, default=8, help="Groq calls, 1–15 (default 8)")
    parser.add_argument("--verbose", action="store_true", help="Print tool names and short outputs")
    parser.add_argument("--target", help="Exact relative Python file path for focused patch mode")
    parser.add_argument("--needle", help="Unique source line fragment to focus around (requires --target)")
    parser.add_argument("--radius", type=int, default=22, help="Context lines either side of --needle (5–40)")
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("GROQ_API_KEY"):
        parser.exit(2, "Error: GROQ_API_KEY was not found in .env\n")
    if bool(args.target) != bool(args.needle):
        parser.error("--target and --needle must be provided together")
    try:
        prompt = args.task
        if args.target:
            excerpt = focused_source_excerpt(
                RepositoryExplorer(args.repo),
                path=args.target, needle=args.needle, radius=args.radius,
            )
            prompt = (
                f"TASK: {args.task}\n\n{excerpt}\n\n"
                "The source has already been read. Propose a minimal repair "
                "with submit_patch, or explain precisely why this excerpt is insufficient."
            )
        graph, session = make_patch_agent(
            args.repo, max_model_calls=args.max_calls, focused=bool(args.target)
        )
        result = graph.invoke(
            {"messages": [HumanMessage(content=prompt)]},
            config={"recursion_limit": 3 * args.max_calls + 8},
        )
    except ValueError as exc:
        print(f"Patch target error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except Exception as exc:
        print(f"Patch agent failed ({type(exc).__name__}).", file=sys.stderr)
        response = getattr(exc, "response", None)
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                print(f"Groq retry-after: {retry_after}", file=sys.stderr)
        print("If this is a RateLimitError, wait for quota reset; otherwise inspect the error locally.", file=sys.stderr)
        raise SystemExit(1) from None

    if args.verbose:
        for msg in result["messages"]:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for call in msg.tool_calls:
                    args_summary = call.get("args", {})
                    # Do not dump replacement source or other potentially sensitive content.
                    path = args_summary.get("path", "")
                    label = f" path={path}" if path else ""
                    print(f"[Tool request] {call['name']}{label}")
            if isinstance(msg, ToolMessage):
                print(f"[Tool result] {str(msg.content)[:400]}")

    print("\n=== DevPilot — Step 4 ===")
    if session.proposal is None:
        responses = [m for m in result["messages"]
                     if isinstance(m, AIMessage) and not m.tool_calls]
        print(responses[-1].content if responses else "No patch was proposed.")
        print("No files changed.")
        return
    patch = session.proposal
    print(f"File: {patch.path}")
    print(f"Reason: {patch.explanation}")
    print("Validation: Python syntax passed; tests NOT run")
    print("Status: PROPOSAL ONLY — no files changed\n")
    print("=== Proposed Unified Diff ===")
    print(patch.diff)
    print("Review the change; automatic apply and test execution are intentionally disabled.")


if __name__ == "__main__":
    main()
