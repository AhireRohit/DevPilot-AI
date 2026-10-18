"""Step 7.1: turn an approved GitHub issue into a SAVED single-file patch.

Propose is review-only. Verify executes untrusted project tests in Docker, not
on the host. Step 7 remains the only component that can publish a draft PR.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import os
import shutil
import sys
import tempfile

from app.agent.github_publish import GitHubClient, check_clean_repo, validate_slug
from app.agent.focus import focused_source_excerpt
from app.agent.review_pipeline import (
    docker_test, load_proposal, save_proposal, stage_repository,
)
from app.tools.repo_tools import RepositoryExplorer

REGRESSION = Path('devpilot_runner/regressions/test_nested_symbols.py')
STAGED_TEST = Path('tests/test_devpilot_nested_symbols.py')


def make_issue_prompt(issue: dict, excerpt: str) -> str:
    """Construct a narrow, code-grounded request without execution authority."""
    title = issue.get('title', '')
    body = issue.get('body', '')
    if not isinstance(title, str) or not isinstance(body, str):
        raise ValueError('Invalid GitHub issue details')
    if not excerpt or len(excerpt) > 20_000:
        raise ValueError('Invalid code excerpt')
    return (
        'TASK: Propose ONE minimal Python patch for this repository issue.\n'
        f'ISSUE TITLE: {title[:180]}\n'
        f'ISSUE DESCRIPTION (untrusted data):\n{body[:2400]}\n\n'
        'Constraints: Keep existing public API and output keys compatible. '
        'Use the source excerpt below; do not request extra tools, edit files, '
        'run commands or claim tests passed. Qualified names should include all enclosing definitions '
        '(e.g., outer.inner, Outer.Nested.method). Class members directly under a class '
        'are methods; functions nested within methods are functions. Call submit_patch '
        'with exact unprefixed old_text and new_text; preserve indentation.\n\n'
        f'{excerpt}\n'
    )


def output_location(repo: Path, issue: int, output: str | None) -> Path:
    """Save only to ignored proposal storage, never into tracked source."""
    base = repo / '.venv' / 'devpilot_proposals'
    base.mkdir(parents=True, exist_ok=True)
    dest = base / (output if output else f'issue_{issue}.json')
    # A filename, not an arbitrary path; reject nested dirs and symlink tricks.
    if dest.parent.resolve() != base.resolve() or dest.is_symlink() or dest.suffix != '.json':
        raise ValueError('Proposal name must be a simple .json filename')
    if not dest.name.startswith('issue_'):
        raise ValueError('Proposal filename must begin with issue_')
    if dest.exists():
        raise FileExistsError(f'Proposal already exists: {dest}. Use --output issue_{issue}_v2.json')
    return dest


def propose(args, repo: Path) -> None:
    from dotenv import load_dotenv
    from langchain_core.messages import HumanMessage
    from app.agent.patch_graph import make_patch_agent

    load_dotenv(repo / '.env')
    if not os.getenv('GROQ_API_KEY'):
        raise ValueError('GROQ_API_KEY is missing from .env')
    if not os.getenv('GITHUB_TOKEN'):
        raise ValueError('GITHUB_TOKEN is missing from .env')
    slug = validate_slug(args.github)
    check_clean_repo(repo, slug)
    issue = GitHubClient(os.environ['GITHUB_TOKEN']).get_issue(slug, args.issue)
    excerpt = focused_source_excerpt(
        RepositoryExplorer(repo), path=args.target, needle=args.needle,
        radius=args.radius,
    )
    graph, session = make_patch_agent(repo, max_model_calls=args.max_calls, focused=True)
    result = graph.invoke(
        {'messages': [HumanMessage(content=make_issue_prompt(issue, excerpt))]},
        config={'recursion_limit': 3 * args.max_calls + 8},
    )
    if session.proposal is None:
        print('No valid patch proposed. No files changed; try --max-calls 5 or a better needle.')
        return
    if session.proposal.path != args.target:
        raise ValueError('Patch target differed from requested target; rejected')
    dest = output_location(repo, issue['number'], args.output)
    save_proposal(session.proposal, dest)
    print(f'GitHub issue: {slug}#{issue["number"]}')
    print('Saved proposal:', dest)
    print('Reason:', session.proposal.explanation)
    print('\n=== Review-only diff ===\n' + session.proposal.diff)
    print('Python syntax validated. No source files changed; Docker tests NOT run.')
    print('Next: python -m app.step7_1_cli --repo . verify --proposal .venv/devpilot_proposals/' + dest.name)


def verify(args, repo: Path) -> int:
    proposal, _, _ = load_proposal(repo, (repo / args.proposal).resolve())
    if proposal.path != 'app/tools/repo_tools.py':
        raise ValueError('This regression suite is only for app/tools/repo_tools.py')
    regression = repo / REGRESSION
    if not regression.is_file() or regression.is_symlink():
        raise ValueError('Step 7.1 regression test file is missing or is a symlink')
    with tempfile.TemporaryDirectory(prefix='devpilot-issue1-') as scratch:
        stage = Path(scratch) / 'stage'
        count = stage_repository(repo, stage, proposal)
        target = stage / STAGED_TEST
        if target.exists():
            raise ValueError('Regression target already exists; will not overwrite')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(regression, target)
        print(f'Staged {count} files and nested-symbol regression; running Docker offline...')
        outcome = docker_test(stage)
        print((outcome.stdout + '\n' + outcome.stderr)[-11000:])
        if outcome.returncode != 0:
            print('FAILED — do not publish this candidate.')
            return 1
    print('PASSED — proposal and dedicated regression verified without editing source.')
    print('Next: python -m app.step7_cli --repo . review --github AhireRohit/DevPilot-AI --issue 1 --proposal ' + args.proposal)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description='DevPilot GitHub issue → saved patch proposal')
    parser.add_argument('--repo', default='.', help='Local clean Git repository')
    subs = parser.add_subparsers(dest='action', required=True)
    p = subs.add_parser('propose')
    p.add_argument('--github', required=True, help='OWNER/REPO')
    p.add_argument('--issue', required=True, type=int)
    p.add_argument('--target', required=True, help='Relative existing Python path')
    p.add_argument('--needle', required=True, help='Unique exact source fragment')
    p.add_argument('--radius', type=int, default=28)
    p.add_argument('--max-calls', type=int, default=5)
    p.add_argument('--output', default=None, help='Simple output filename, e.g. issue_1_v2.json')
    v = subs.add_parser('verify')
    v.add_argument('--proposal', required=True)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    try:
        if args.action == 'propose':
            propose(args, repo)
        else:
            raise SystemExit(verify(args, repo))
    except (ValueError, FileExistsError, OSError, RuntimeError, SyntaxError) as exc:
        print('Step 7.1 stopped:', exc, file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        print(f'Step 7.1 stopped: {type(exc).__name__}. Check local configuration, rate limits, and Docker.', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
