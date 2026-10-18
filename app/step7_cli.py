"""DevPilot Step 7: read GitHub issue, verify saved patch, publish draft PR."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from app.agent.github_publish import (
    GitHubClient, check_clean_repo, validate_slug, publish_draft,
)
from app.agent.review_pipeline import diff_for, load_proposal
from app.agent.repair_pipeline import run_repair_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="DevPilot Step 7: safe GitHub draft-PR publication")
    parser.add_argument("--repo", default=".", help="Local Git repository root")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("status", help="Check local Git readiness without GitHub or Groq")
    review = commands.add_parser("review", help="Read GitHub issue, show patch, optionally publish")
    review.add_argument("--github", required=True, metavar="OWNER/REPO")
    review.add_argument("--issue", required=True, type=int)
    review.add_argument("--proposal", required=True, help="Saved Step 5/6 JSON patch")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    try:
        if args.action == "status":
            head, origin = check_clean_repo(repo)
            print("Git status: clean")
            print("HEAD:", head[:12])
            print("Origin:", ("Configured (credentials/URL hidden)" if origin else "Not configured (GitHub remote needed for Step 7)"))
            print("No network calls; no source files changed.")
            return

        slug = validate_slug(args.github)
        # Read .env without printing it. Git pushes authenticate using configured
        # Git credential manager/SSH. GITHUB_TOKEN is used only for GitHub API.
        from dotenv import load_dotenv
        load_dotenv(repo / ".env")
        client = GitHubClient(os.getenv("GITHUB_TOKEN", ""))
        head, origin = check_clean_repo(repo, slug)
        issue = client.get_issue(slug, args.issue)
        proposal, _, original = load_proposal(repo, (repo / args.proposal).resolve())
        print(f"GitHub issue: {slug}#{issue['number']}")
        print("Issue title:", issue["title"])
        print("Patch target:", proposal.path)
        print("Patch diff:\n" + diff_for(original, proposal))
        print("Issue descriptions are untrusted data. No GitHub code has been changed.")
        if input("Type TEST to verify this exact patch in offline Docker: ").strip() != "TEST":
            print("Cancelled; nothing changed.")
            return
        result = run_repair_loop(repo, proposal, max_repairs=0)
        if result.status != "passed":
            for trial in result.trials:
                print(trial.output[-2400:])
            print("Tests failed. Publishing blocked; no GitHub changes.")
            return
        print(f"Docker pytest PASSED ({len(result.trials)} trial).")
        # Permission is deliberately bound to this exact remote issue.
        phrase = f"PUBLISH {slug}#{issue['number']}"
        print("About to create a new remote branch and GitHub DRAFT PR (never merge).")
        if input(f"Type exactly '{phrase}' to authorize the push and PR: ").strip() != phrase:
            print("Declined. Local repository and GitHub unchanged.")
            return
        response = publish_draft(repo, slug, issue, result.proposal,
                                 original=original, expected_head=head, client=client)
        print("Created DRAFT pull request:", response["url"])
        print("Remote branch:", response["branch"])
        print("Original working tree unchanged; review the PR manually before merging.")
    except (ValueError, RuntimeError, OSError, SyntaxError) as exc:
        print(f"Step 7 stopped: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        print(f"Step 7 stopped safely: {type(exc).__name__} (details withheld to avoid exposing credentials)", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
