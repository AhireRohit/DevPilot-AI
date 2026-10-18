"""Safe GitHub draft-PR publication for ONE verified DevPilot patch.

The production CLI requests separate TEST and PUBLISH authorizations.
This module NEVER merges PRs, force pushes, or edits the original working tree.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from app.agent.review_pipeline import SavedPatch, fingerprint

SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_RE = re.compile(r"^devpilot/issue-[1-9][0-9]*-[a-f0-9]{8}$")


def validate_slug(slug: str) -> str:
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise ValueError("GitHub repository must be OWNER/REPO")
    owner, name = slug.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."} or owner.startswith("-") or name.startswith("-"):
        raise ValueError("Invalid GitHub owner or repository")
    return slug


def validate_issue(number: int) -> int:
    if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 2_147_483_647:
        raise ValueError("Issue number must be a positive integer")
    return number


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:1600]


class GitHubClient:
    def __init__(self, token: str = "", opener=urlopen):
        self.token = token.strip()
        self.opener = opener

    def _request(self, method: str, route: str, payload: dict | None = None) -> dict:
        if not route.startswith("/repos/") or ".." in route or "?" in route:
            raise ValueError("Invalid GitHub API endpoint")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "DevPilot-AI-educational-agent",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request("https://api.github.com" + route, data=data, headers=headers, method=method)
        try:
            with self.opener(request, timeout=15) as response:
                answer = json.loads(response.read(150_000).decode("utf-8"))
        except HTTPError as exc:
            # Do not print error response body; provider may echo private contents.
            raise RuntimeError(f"GitHub API returned HTTP {exc.code} for {method}") from None
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Cannot reach GitHub API: {type(exc).__name__}") from None
        if not isinstance(answer, dict):
            raise RuntimeError("GitHub API response was not an object")
        return answer

    def get_issue(self, slug: str, number: int) -> dict:
        slug, number = validate_slug(slug), validate_issue(number)
        obj = self._request("GET", f"/repos/{slug}/issues/{number}")
        if "pull_request" in obj:
            raise ValueError("That number refers to a pull request, not an issue")
        if obj.get("state") != "open":
            raise ValueError("GitHub issue must be open")
        if not isinstance(obj.get("title"), str) or not obj["title"].strip():
            raise ValueError("GitHub issue title missing")
        return {
            "number": number,
            "title": obj["title"][:180],
            "url": obj.get("html_url", ""),
            "body": (obj.get("body") or "")[:4000],
        }

    def create_draft_pr(self, slug: str, *, title: str, head: str,
                        base: str, body: str) -> dict:
        validate_slug(slug)
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required to create a pull request")
        result = self._request("POST", f"/repos/{slug}/pulls", {
            "title": title[:240], "head": head, "base": base,
            "body": body[:3000], "draft": True,
        })
        if result.get("draft") is not True or not isinstance(result.get("html_url"), str):
            raise RuntimeError("GitHub did not confirm draft PR creation")
        return result


def git(repo: Path, *args: str, timeout: int = 45, hooks_dir: Path | None = None) -> str:
    command = ["git"]
    if hooks_dir is not None:
        command.extend(["-c", f"core.hooksPath={hooks_dir}", "-c", "commit.gpgsign=false"])
    command.extend(["-C", str(repo), *args])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Git command failed to run: {type(exc).__name__}") from None
    if result.returncode:
        # Avoid logging credential helper output, remote URLs or git-auth secrets.
        raise RuntimeError(f"Git command {args[0]!r} failed (exit {result.returncode}); check Git authentication, status, and configuration")
    return result.stdout.strip()


def github_origin_matches(remote_url: str, slug: str) -> bool:
    """Accept normal github HTTPS/SSH origins, never credential-embedded URLs."""
    validate_slug(slug)
    patterns = (
        r"https://github\.com/([^/?#]+/[^/?#]+)",
        r"git@github\.com:([^/?#]+/[^/?#]+)",
        r"ssh://git@github\.com/([^/?#]+/[^/?#]+)",
    )
    for pattern in patterns:
        m = re.fullmatch(pattern + r"(?:\.git)?/?", remote_url.strip(), re.IGNORECASE)
        if m and m.group(1).removesuffix(".git").lower() == slug.lower():
            return True
    return False


def check_clean_repo(repo: Path, slug: str | None = None) -> tuple[str, str | None]:
    root = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    if root != repo.resolve():
        raise ValueError("--repo must be the Git repository root")
    if git(repo, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Working tree is not clean; commit or stash changes first")
    head = git(repo, "rev-parse", "HEAD")
    origin: str | None
    try:
        origin = git(repo, "remote", "get-url", "origin")
    except RuntimeError:
        origin = None
    if slug is not None and not github_origin_matches(origin or "", slug):
        raise ValueError("Git origin must point to the exact GitHub OWNER/REPO you selected")
    return head, origin


def branch_name(issue: int, suffix: str | None = None) -> str:
    validate_issue(issue)
    suffix = suffix if suffix is not None else uuid4().hex[:8]
    name = f"devpilot/issue-{issue}-{suffix}"
    if not BRANCH_RE.fullmatch(name):
        raise ValueError("Invalid generated branch name")
    return name


def draft_title(issue: dict) -> str:
    return f"Fix #{issue['number']}: {issue['title']}"[:240]


def draft_body(issue: dict, proposal: SavedPatch) -> str:
    # Never insert untrusted issue body as procedural directions.
    return (
        f"Closes #{issue['number']}\n\n"
        "## DevPilot AI proposed change\n"
        f"- File: `{proposal.path}`\n"
        f"- Summary: {proposal.explanation[:500]}\n\n"
        "## Validation\n"
        "- A disposable Docker copy passed pytest immediately before publication.\n"
        "- Human approved publishing this **draft** PR.\n"
        "- Reviewer should inspect diff, CI results, and test coverage.\n\n"
        "*This is a draft; it has not been merged.*\n"
    )


def publish_draft(repo: Path, slug: str, issue: dict, proposal: SavedPatch,
                  *, original: str, expected_head: str, client: GitHubClient) -> dict:
    """Publish a tested patch on its own remote branch, never changing main worktree.

    The *caller* must get explicit PUBLISH permission; this method does not prompt.
    A push may succeed while PR API creation fails: the remote branch remains.
    """
    if not client.token:
        raise ValueError("GITHUB_TOKEN missing; cannot publish")
    head, _ = check_clean_repo(repo, slug)
    if head != expected_head:
        raise ValueError("HEAD changed since Docker verification")
    path = repo / proposal.path
    if not path.is_file() or path.is_symlink():
        raise ValueError("Patch target missing or symlinked")
    if fingerprint(path.read_text(encoding="utf-8")) != proposal.original_hash:
        raise ValueError("Patch target changed since verification")
    if original != path.read_text(encoding="utf-8"):
        raise ValueError("Patch baseline does not match")
    branch = branch_name(issue["number"])
    with TemporaryDirectory(prefix="devpilot-publish-") as scratch:
        worktree = Path(scratch) / "worktree"
        hooks = Path(scratch) / "empty_hooks"
        hooks.mkdir()
        worktree_added = False
        try:
            git(repo, "worktree", "add", "--detach", str(worktree), expected_head)
            worktree_added = True
            # Worktree is detached until the exact target is written and committed.
            git(worktree, "switch", "-c", branch)
            destination = worktree / proposal.path
            if not destination.is_file() or destination.is_symlink():
                raise ValueError("Target not present in Git-tracked checkout")
            destination.write_text(proposal.proposed_source, encoding="utf-8", newline="")
            git(worktree, "add", "--", proposal.path)
            if not git(worktree, "diff", "--cached", "--name-only").strip() == proposal.path:
                raise ValueError("Expected exactly one staged file")
            git(worktree, "commit", "-m", f"fix: resolve GitHub issue #{issue['number']}", hooks_dir=hooks)
            # Never force-push, never write to main branch.
            git(worktree, "push", "-u", "origin", branch, timeout=90)
            pr = client.create_draft_pr(
                slug, title=draft_title(issue), head=branch,
                base=git(repo, "symbolic-ref", "--quiet", "--short", "HEAD"),
                body=draft_body(issue, proposal),
            )
            return {"branch": branch, "url": pr["html_url"], "number": pr.get("number")}
        except Exception as exc:
            raise RuntimeError(f"Draft PR publication stopped; a remote branch named {branch} may exist: {exc}") from None
        finally:
            if worktree_added:
                try:
                    git(repo, "worktree", "remove", "--force", str(worktree))
                except RuntimeError:
                    pass
