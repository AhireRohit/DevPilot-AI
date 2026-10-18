# DevPilot AI — Step 7: GitHub issue → draft PR

## What is new

This **additive** update introduces:

- Read an **open GitHub issue** through GitHub's REST API.
- Load a **previously saved** Step 5/6 patch (`*.json`), show the exact unified diff, and re-check it against the current source hash.
- Require `TEST`, then run the existing offline Docker pytest pipeline (no Groq calls).
- If Docker passes, require an exact `PUBLISH OWNER/REPO#NUMBER` authorization.
- Create a temporary Git worktree, new `devpilot/issue-…` branch, apply the tested patch **only to that worktree**, commit it, and push only that branch.
- Create a **draft** PR referencing the issue. Never push to `main`, auto-merge, or modify the original source tree.

**This is not yet an end-to-end issue-solving agent.** You must first save a proposed patch with Steps 4–6. The next milestone will connect issue understanding to automated patch selection and GitHub PRs.

## Installation (Windows PowerShell)

From `D:\0 Resume Projects\DevPilot AI` with `.venv` activated:

```powershell
Expand-Archive -Path "C:\Users\rohit\Downloads\DevPilot_AI_Step7_GitHub_Draft_PR.zip" -DestinationPath "D:\0 Resume Projects\DevPilot AI" -Force
python -m pytest -q tests --basetemp=.\pytest_temp
```

Expected if all previous 52 tests continue passing: **66 passed** (52 previous + 14 new tests). Platform-specific test skips may differ.

## 1. Check local Git readiness — NO network or API call

```powershell
python -m app.step7_cli --repo . status
```

If Git shows uncommitted changes from Step 6/7, commit them first:

```powershell
git status --short
git add app tests STEP_6_README.md STEP_7_README.md
git diff --cached --check
git commit -m "feat: add bounded repair and GitHub draft PR workflow"
git status
```

If `git add` reports missing paths (for instance if the README wasn't installed), stage only existing files. **Check that `.env`, `.venv`, and generated artifacts are not staged.** Do not commit secrets.

## 2. Set up a GitHub repository and issue

Create a **new empty** GitHub repository for DevPilot AI in your account (no auto-generated README or license, since you already have a Git history). Example if your GitHub username is `YOUR_USERNAME`:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/DevPilot-AI.git
git push -u origin main
```

If `origin` already exists, inspect it using `git remote -v` and confirm it points to the same repo you intend to use. Do not blindly overwrite it.

Then create a **new open issue** in that GitHub repository describing a small Python bug. Note its issue number, e.g., `1`.

Configure a **fine-grained personal access token** scoped only to that GitHub repository, with repository permissions **Issues: Read**, **Contents: Read and write**, and **Pull requests: Read and write**. Keep the token out of Git and screenshots. Add it to your existing ignored `.env`:

```env
GITHUB_TOKEN=github_pat_REPLACE_WITH_YOURS
```

The token authorizes GitHub's REST API; `git push` still requires Git credentials in Windows Git Credential Manager or SSH. A GitHub website sign-in or Docker sign-in alone does not guarantee that `git push` is authenticated.

Create fine-grained tokens: https://github.com/settings/personal-access-tokens/new

## 3. Save an UNAPPLIED patch proposal

Important: your old `path.stat()` patch is **already applied**, so its JSON manifest is stale and cannot be republished as a new diff.

Use your existing Step 4/5 code to generate a **fresh patch proposal** for a new issue. The proposed change must target an *existing tracked Python file*. **Do not APPLY the change to main**; Step 7 will create the patch in a separate temporary Git worktree instead.

For example, your Step 5 CLI may support `generate`; otherwise, use the reviewable JSON you saved from a Step 4/6 run before it was applied. Check `python -m app.step5_cli --help` for available commands. Keep the JSON under `.venv/devpilot_proposals/`.

## 4. Test and publish after TWO approvals

Replace placeholder values with your real GitHub owner, repo name, issue number, and saved (unapplied) proposal path:

```powershell
python -m app.step7_cli --repo . review --github YOUR_USERNAME/DevPilot-AI --issue 1 --proposal ".venv/devpilot_proposals/latest.json"
```

The CLI fetches the issue and prints the diff. Then:

1. Type `TEST` to validate the patch with offline Docker.
2. If Docker passes, review the printed scope. Type **exactly** `PUBLISH YOUR_USERNAME/DevPilot-AI#1` to authorize a new remote branch and draft PR.
3. Any other response stops without publishing.
4. Visit the draft PR URL and review it before merging. No automatic merge occurs.

### Important safeguards and limitations

- Step 7 checks the local repo is clean, checks that `origin` matches the exact GitHub `OWNER/REPO`, and rejects a changed commit/source hash before publication.
- It restricts the patch to one previously existing `.py` file and shows the diff before testing and publishing.
- Docker testing is sandboxed, offline, and explicitly authorized; GitHub is never accessed from inside Docker.
- It does **not** create a new regression test or modify multiple files. Passing existing tests is not proof the solution is correct.
- If `git push` succeeds but GitHub's PR API fails, a remote branch may remain. The tool will warn about its name so you can inspect it manually.
- GitHub public repos are public: review your tracked project files before pushing `main` for the first time.
- Running tests on untrusted repositories remains risky even with constrained Docker. Use repos you own or trust.

## Tests

The 14 new tests are fully offline, use a synthetic local bare Git repository for a branch/push check, mock GitHub HTTP requests, and never call Groq or the live GitHub API. They passed in the development container. The entire user project suite should be run in your Windows environment because it has LangChain/LangGraph and Docker available.
