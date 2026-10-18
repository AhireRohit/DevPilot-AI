"""Run DevPilot's read-only repository investigation agent.

Examples:
    python -m app.agent_cli --repo . --question "Summarize this codebase"
    python -m app.agent_cli --repo . --question "Find possible bugs in repo_tools.py" --verbose
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import make_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="DevPilot read-only LangGraph agent")
    parser.add_argument("--repo", default=".", help="Local repository directory")
    parser.add_argument("--question", required=True, help="Your investigation task")
    parser.add_argument("--max-calls", type=int, default=6,
                        help="Maximum Groq model calls per run (default 6; range 1–12)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print tool requests and limited tool outputs")
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("GROQ_API_KEY"):
        parser.exit(2, "Error: GROQ_API_KEY was not found in .env\n")

    try:
        graph = make_agent(args.repo, max_model_calls=args.max_calls)
        result = graph.invoke(
            {"messages": [HumanMessage(content=args.question)]},
            config={"recursion_limit": 3 * args.max_calls + 5},
        )
    except Exception as exc:
        # Never print API keys or complete request bodies in exceptions.
        print(f"Agent execution failed ({type(exc).__name__}).", file=sys.stderr)
        print("Check your Groq quota, network connection, and selected repo.", file=sys.stderr)
        raise SystemExit(1) from None

    for message in result["messages"]:
        if args.verbose and isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                print(f"\n[Tool request] {call['name']}({call['args']})")
        if args.verbose and isinstance(message, ToolMessage):
            print(f"[Tool result] {str(message.content)[:1000]}")

    responses = [
        message for message in result["messages"]
        if isinstance(message, AIMessage) and not message.tool_calls
    ]
    print("\n=== DevPilot Report ===")
    print(responses[-1].content if responses else "No final response was generated.")


if __name__ == "__main__":
    main()
