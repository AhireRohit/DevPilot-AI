"""Local CLI to validate repository exploration tools before agent integration."""

import argparse
import json

from app.tools.repo_tools import RepositoryExplorer


def main() -> None:
    parser = argparse.ArgumentParser(description="DevPilot read-only repository explorer")
    parser.add_argument("--repo", default=".", help="Local folder to inspect (default: current)")
    commands = parser.add_subparsers(dest="command", required=True)

    tree_cmd = commands.add_parser("tree", help="List files")
    tree_cmd.add_argument("--limit", type=int, default=120)

    search_cmd = commands.add_parser("search", help="Search text inside source files")
    search_cmd.add_argument("query", help="Literal text to find")
    search_cmd.add_argument("--limit", type=int, default=30)

    read_cmd = commands.add_parser("read", help="Read numbered lines from a file")
    read_cmd.add_argument("file")
    read_cmd.add_argument("--start", type=int, default=1)
    read_cmd.add_argument("--end", type=int, default=80)

    symbols_cmd = commands.add_parser("symbols", help="List Python classes/functions")
    symbols_cmd.add_argument("file")

    args = parser.parse_args()
    explorer = RepositoryExplorer(args.repo)

    try:
        if args.command == "tree":
            result = explorer.list_files(args.limit)
        elif args.command == "search":
            result = explorer.search_code(args.query, args.limit)
        elif args.command == "read":
            result = explorer.read_file(args.file, args.start, args.end)
        else:
            result = explorer.python_symbols(args.file)
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"Error: {exc}\n")

    if isinstance(result, str):
        print(result or "(No lines in requested range)")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
