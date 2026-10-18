"""DevPilot Step 5: save proposals, verify in Docker, and approve a single patch."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
import shutil

from app.agent.patches import PatchSession
from app.agent.review_pipeline import (
    apply_tested_patch, diff_for, docker_test, load_proposal, save_proposal,
    stage_repository,
)
from app.tools.repo_tools import RepositoryExplorer


def demo_patch(repo: Path, output: Path):
    """Recreate the precise earlier AI proposal, without making another API call."""
    sess = PatchSession(RepositoryExplorer(repo))
    patch = sess.propose(
        path="app/tools/repo_tools.py",
        old_text="                if path.stat().st_size > MAX_BYTES:\n                    continue",
        new_text=(
            "                try:\n"
            "                    if path.stat().st_size > MAX_BYTES:\n"
            "                        continue\n"
            "                except OSError:\n"
            "                    continue"
        ),
        explanation="Skip unreadable metadata rather than aborting repository enumeration.",
    )
    save_proposal(patch, output)
    print(f"Saved the previously reviewed stat() fix to: {output}")
    print("No Groq call. No repository source files changed.")
    print(patch.diff)


def generate_patch(args, repo: Path, output: Path):
    """Optional bridge from the existing Groq agent to Step 5, for future fixes."""
    import os
    from dotenv import load_dotenv
    from langchain_core.messages import HumanMessage
    from app.agent.focus import focused_source_excerpt
    from app.agent.patch_graph import make_patch_agent

    load_dotenv(repo / ".env")
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY missing in .env")
    excerpt = focused_source_excerpt(
        RepositoryExplorer(repo), path=args.target, needle=args.needle, radius=22
    )
    prompt = (f"TASK: {args.task}\n\n{excerpt}\n\n"
              "The source has already been read. Propose exactly one minimal patch using submit_patch.")
    graph, session = make_patch_agent(repo, max_model_calls=args.max_calls, focused=True)
    graph.invoke({"messages": [HumanMessage(content=prompt)]},
                 config={"recursion_limit": 3 * args.max_calls + 8})
    if session.proposal is None:
        print("Agent could not produce a valid patch; no proposal saved.")
        return
    save_proposal(session.proposal, output)
    print(f"Saved Groq-generated patch to: {output}")
    print(session.proposal.diff)
    print("No source files changed.")


def verify(repo: Path, proposal_file: Path):
    proposal, original_path, original = load_proposal(repo, proposal_file)
    print("\n=== Patch for human review ===")
    print("Target:", proposal.path)
    print("Reason:", proposal.explanation)
    print(diff_for(original, proposal))
    print("Original source is unchanged.")
    if input("Type TEST to run this patch in an isolated Docker container: ").strip() != "TEST":
        print("Cancelled. No source changes.")
        return
    stage_root = repo / ".venv" / "devpilot_stage"
    stage_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stage-", dir=stage_root) as directory:
        stage = Path(directory) / "repo"
        count = stage_repository(repo, stage, proposal)
        if proposal.path == "app/tools/repo_tools.py" and "except OSError" in proposal.proposed_source:
            regression = repo / "devpilot_runner" / "regressions" / "test_stat_oserror.py"
            if not regression.is_file():
                raise ValueError("Required stat() regression test is missing")
            shutil.copyfile(regression, stage / "tests" / "test_stat_oserror.py")
            print("Included dedicated stat() permission-error regression test in Docker run.")
        print(f"Staged {count} text files. Running tests offline in Docker...")
        result = docker_test(stage)
        print("\n=== Docker pytest output ===")
        print(result.stdout[-12000:])
        if result.stderr.strip():
            print("Docker stderr (truncated):\n", result.stderr[-3000:])
        if result.returncode != 0:
            print(f"Tests failed (exit {result.returncode}); original source NOT changed.")
            return
        print("Docker tests PASSED. No code has been applied yet.")
    if input("Type APPLY to replace the original Python file (backup saved): ").strip() != "APPLY":
        print("Declined. Original source unchanged.")
        return
    # No re-running models or executing host project code after approval.
    backup = apply_tested_patch(repo, proposal, original, tests_passed=True)
    print(f"Applied approved patch to: {original_path}")
    print(f"Backup: {backup}")
    print("Review the diff in Git and keep the tests in your next commit.")


def main():
    p = argparse.ArgumentParser(description="DevPilot safe review + Docker tests")
    p.add_argument("--repo", default=".", help="Authorized repository root")
    sub = p.add_subparsers(dest="mode", required=True)
    demo = sub.add_parser("demo", help="Recreate previously reviewed stat() fix with no API call")
    demo.add_argument("--output", default=".venv/devpilot_proposals/stat_oserror.json")
    gen = sub.add_parser("generate", help="Ask Groq to generate and persist a NEW patch")
    gen.add_argument("--target", required=True)
    gen.add_argument("--needle", required=True)
    gen.add_argument("--task", required=True)
    gen.add_argument("--max-calls", type=int, default=3)
    gen.add_argument("--output", default=".venv/devpilot_proposals/latest.json")
    run = sub.add_parser("verify", help="Review, Docker-test, and optionally apply a saved patch")
    run.add_argument("--proposal", default=".venv/devpilot_proposals/stat_oserror.json")
    args = p.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        p.error("Repository does not exist")
    try:
        if args.mode == "demo":
            demo_patch(repo, repo / args.output)
        elif args.mode == "generate":
            generate_patch(args, repo, repo / args.output)
        else:
            verify(repo, repo / args.proposal)
    except (ValueError, OSError, RuntimeError, SyntaxError) as exc:
        print(f"Step 5 stopped safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
