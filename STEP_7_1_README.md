# Step 7.1 — GitHub Issue → Saved AI Patch (no source edits)

This small addon fills the gap between the current Step 4 patch generator (in-memory only) and Step 7's GitHub publishing CLI (requires a saved patch JSON file). It reads issue #1 from GitHub with your local token, shows the model a bounded excerpt of `python_symbols()`, and saves a reviewable, **unapplied** patch.

Before continuing: confirm `.env` contains both `GROQ_API_KEY` and `GITHUB_TOKEN`; do not paste them into chats. Keep Git `main` clean. Step 7.1 never sends tokens to the model. Your source excerpt and GitHub issue body are sent to Groq.

## Install and test

Extract ZIP directly into your DevPilot AI project root. From the venv:

```powershell
python -m pytest -q tests --basetemp=.\pytest_temp
```

Expected: 71 tests, if the earlier 66 still pass.

**Commit the addon before generating the issue proposal** (Step 7 requires a clean tree):

```powershell
git add STEP_7_1_README.md app/step7_1_cli.py devpilot_runner/regressions/test_nested_symbols.py tests/test_step7_1_issue_proposals.py
git diff --cached --check
git commit -m "feat: connect GitHub issues to saved patch proposals"
git push
```

## Propose a fix using Groq

```powershell
python -m app.step7_1_cli --repo . propose --github AhireRohit/DevPilot-AI --issue 1 --target app/tools/repo_tools.py --needle "def python_symbols(" --max-calls 5
```

Expected: a readable diff + `.venv/devpilot_proposals/issue_1.json`, without modifying source files. If Groq fails due to quota, wait for the retry window and try again. If it generates an invalid proposal, add `--output issue_1_v2.json` and adjust the instruction later; never overwrite an earlier proposal silently.

## Verify the issue-specific acceptance test (offline Docker)

```powershell
python -m app.step7_1_cli --repo . verify --proposal .venv/devpilot_proposals/issue_1.json
```

This creates a disposable staged copy, injects two nested-symbol acceptance tests, and runs all tests in Docker offline. If tests fail, DON'T publish; inspect the failures and revise the patch. Your main working directory is unaffected.

## Publish a verified patch, after your approval

```powershell
python -m app.step7_cli --repo . review --github AhireRohit/DevPilot-AI --issue 1 --proposal .venv/devpilot_proposals/issue_1.json
```

Type `TEST` to rerun ordinary Docker suite. Then inspect the approval prompt: typing the **exact** `PUBLISH AhireRohit/DevPilot-AI#1` will push a separate branch and open a **draft PR**. Declining leaves GitHub unchanged. The source on `main` remains unchanged. The draft is not merged.

**Current Step 7 limitation**: it publishes one Python source file only. The dedicated regression tests used for verification live under `devpilot_runner/regressions/` on `main`, **not in the draft PR's standard pytest suite**. Before marking the PR ready or merging it, add those regression tests to the PR branch under `tests/` and verify CI. Multi-file PR patches are the next improvement to DevPilot.
