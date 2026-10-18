"""DevPilot Step 6: Docker-verified patch repair with explicit approval."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from uuid import uuid4

from app.agent.patches import PatchProposal, PatchSession
from app.agent.repair_pipeline import groq_repair, run_repair_loop
from app.agent.review_pipeline import (
    apply_tested_patch, diff_for, load_proposal, save_proposal,
)
from app.tools.repo_tools import RepositoryExplorer


def create_demo(repo: Path) -> None:
    """A disposable deliberately wrong initial patch to demonstrate failing tests."""
    demo = repo / ".venv" / "devpilot_demos" / "calculator"
    target = demo / "src" / "calculator.py"
    if demo.exists():
        raise FileExistsError("Demo already exists; keep existing data or remove it manually")
    target.parent.mkdir(parents=True)
    (demo / "tests").mkdir()
    (demo / "src" / "__init__.py").write_text("", encoding="utf-8")
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (demo / "tests" / "test_calculator.py").write_text(
        "from src.calculator import add\n\n"
        "def test_positive():\n    assert add(4, 3) == 7\n\n"
        "def test_negative():\n    assert add(-2, 3) == 1\n",
        encoding="utf-8",
    )
    session = PatchSession(RepositoryExplorer(demo))
    patch = session.propose(
        path="src/calculator.py",
        old_text="    return a - b",
        new_text="    return abs(a - b)",
        explanation="Intentionally incorrect first proposal to demonstrate repair retries",
    )
    location = demo / ".venv" / "devpilot_proposals" / "initial.json"
    save_proposal(patch, location)
    print(f"Created isolated demo: {demo}")
    print("The first patch is intentionally WRONG so the Docker tests fail.")
    print("Run:\n  python -m app.step6_cli --repo .\\.venv\\devpilot_demos\\calculator "
          "run --proposal .venv/devpilot_proposals/initial.json")
    print("No real DevPilot files changed. No Groq API call made.")


def run_demo(repo: Path, proposal_location: Path, max_repairs: int) -> None:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")  # reuse existing DevPilot key; no new key needed
    saved, target_path, original = load_proposal(repo, proposal_location)
    print("\n=== Initial proposal ===")
    print("Target:", saved.path)
    print(diff_for(original, saved))
    print("Original source unchanged. Only authorized repositories should be tested.")
    if input("Type TEST to start Docker verification: ").strip() != "TEST":
        print("Cancelled before test execution.")
        return

    def approve_repair():
        return input(
            "Tests failed. Type REPAIR to authorize up to "
            f"{max_repairs} Groq repair attempts (free-tier limits apply): "
        ).strip() == "REPAIR"

    def repairer(stage, proposal, failure, attempt):
        print(f"[Repair {attempt}/{max_repairs}] Requesting targeted correction from Groq...")
        return groq_repair(stage, proposal, failure, attempt, original_source=original)

    outcome = run_repair_loop(
        repo, saved, max_repairs=max_repairs,
        repairer=repairer if max_repairs else None,
        allow_repair=approve_repair if max_repairs else None,
    )
    print("\n=== Verification summary ===")
    for t in outcome.trials:
        print(f"Trial {t.attempt}: {'PASSED' if t.passed else 'FAILED'} (exit {t.exit_code})")
        if not t.passed:
            print(t.output[-1600:])
    if outcome.status != "passed":
        print("Verification FAILED; no original source files changed.")
        return
    print(f"Docker verification PASSED after {outcome.repairs_used} repair attempts.")
    print("\n=== Final candidate diff against original ===")
    final_diff = diff_for(original, outcome.proposal)
    print(final_diff)
    # Persist as an *unverified* proposal; the Step 5 verifier must re-test it.
    # The in-memory outcome was verified by Docker, but that evidence cannot be
    # assumed valid later because other files could change in the meantime.
    saved_path = repo / ".venv" / "devpilot_proposals" / f"repaired_{uuid4().hex[:12]}.json"
    save_proposal(PatchProposal(
        path=outcome.proposal.path, explanation=outcome.proposal.explanation,
        diff=final_diff, original=original, proposed=outcome.proposal.proposed_source,
    ), saved_path)
    print("Saved reviewable candidate:", saved_path)
    if input("Type APPLY to approve replacing the original file: ").strip() != "APPLY":
        print("Declined. Original source unchanged.")
        return
    # Safety: re-check the source hash and active path prior to applying.
    backup = apply_tested_patch(repo, outcome.proposal, original, tests_passed=True)
    print(f"Applied approved patch to: {target_path}")
    print(f"Backup stored at: {backup}")


def main():
    parser = argparse.ArgumentParser(description="DevPilot Step 6 repair runner")
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("demo", help="Create an isolated failing example with no API call")
    run = sub.add_parser("run", help="Docker-test and optionally repair a saved patch")
    run.add_argument("--proposal", default=".venv/devpilot_proposals/latest.json")
    run.add_argument("--max-repairs", type=int, default=2)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        parser.error("Repository root does not exist")
    try:
        if args.mode == "demo":
            create_demo(repo)
        else:
            run_demo(repo, repo / args.proposal, args.max_repairs)
    except (ValueError, OSError, RuntimeError, SyntaxError) as exc:
        print(f"Step 6 stopped safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        # Includes provider RateLimitError; do not dump credentials or sensitive
        # HTTP headers into the terminal on unanticipated API exceptions.
        print(f"Step 6 stopped safely: {type(exc).__name__}. "
              "Check Groq limits or the Python traceback with debugging tools.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
