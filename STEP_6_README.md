# DevPilot AI — Step 6: Bounded repair loop

## What this adds

This is an **additive update** to Step 5. It introduces one read-only-to-original repair loop for a **single existing Python source file**:

1. Start from a previously saved Step 5 patch (`*.json`).
2. Stage the patch into a disposable copy and run the pytest suite in Docker, without network access.
3. If pytest reports actual test failures (exit code 1), ask the human **REPAIR** before any Groq request.
4. Supply bounded error output plus a source excerpt to the existing Groq/LangGraph focused patch agent.
5. Retry **at most 2 times**, then stop if nothing passes.
6. When Docker passes, show a **diff against the untouched original** and save the candidate to `.venv/devpilot_proposals/repaired_*.json`.
7. Ask for explicit **APPLY** before modifying the original Python file; recheck the source hash and store a backup.

The repaired manifest is a *proposal*, not a permanent attestation of passing tests. If applying later, re-run Docker verification with Step 5. The demo here intentionally uses an incorrect initial patch so the repair behavior is visible.

## Installation (PowerShell, Windows)

Run within `D:\0 Resume Projects\DevPilot AI` (your existing working virtual environment):

```powershell
Expand-Archive -Path "C:\Users\rohit\Downloads\DevPilot_AI_Step6_Repair_Loop.zip" -DestinationPath "D:\0 Resume Projects\DevPilot AI" -Force
python -m pytest -q tests --basetemp=.\pytest_temp
```

This ZIP adds only three files: `app/agent/repair_pipeline.py`, `app/step6_cli.py`, `tests/test_step6_repair_loop.py`, plus this guide. Existing Step 5 code is not overwritten.

## First, create a SAFE test scenario (no API, no changes to real code)

```powershell
python -m app.step6_cli demo
```

This creates `.venv/devpilot_demos/calculator/` containing an `add` function, two real tests, and an **intentionally wrong** proposed change: `return abs(a - b)` instead of addition. Because this directory is under `.venv`, it stays outside your Git commits by default.

**The demo cannot be created twice at the same path**, to avoid silently replacing earlier work. To retry it, delete only `.venv/devpilot_demos/calculator/` after checking it has no work you want to keep.

## Launch the repair loop

```powershell
python -m app.step6_cli --repo ".\.venv\devpilot_demos\calculator" run --proposal ".venv/devpilot_proposals/initial.json" --max-repairs 2
```

- Type **TEST** to run the first broken patch in Docker. The two calculator tests should fail.
- Then type **REPAIR** to authorize up to two Groq repair rounds. Each repair uses at most three model calls (may hit free-tier token limits).
- If a repair passes tests, inspect the full diff against the unchanged original.
- Type **APPLY** only if you are happy with it, or anything else to decline. A saved candidate is retained for review.

Sample success path (the LLM may or may not repair on the first attempt):

```
[Trial 1] ... FAIL
Tests failed. Type REPAIR ...: REPAIR
[Repair 1/2] ...
[Trial 2] ... PASS
Final candidate diff ...
Type APPLY ...: APPLY
```

No Docker image rebuild is necessary if your `devpilot-test-runner:local` image still exists.

## General usage on a NEW bug fix

First use the existing Step 5 `generate` command to save a fresh proposal for an existing, authorized Python target. Then use:

```powershell
python -m app.step6_cli --repo . run --proposal ".venv/devpilot_proposals/latest.json" --max-repairs 2
```

The earlier `path.stat()` Step 5 demo has **already been applied**. Its old manifest is stale, so do not reuse it as the Step 6 test case.

## Safety and limitations

- The repair model can only propose a correction to the *same Python file*; no shell execution or writes to real source are exposed to it.
- Docker restricts network access, memory, CPU, capabilities, and uses read-only mounts. This reduces risk, but it is not a guarantee against every malicious workload or a substitute for strong VM isolation. Work only on repositories you own or trust.
- Step 6 interprets pytest exit code 1 as a test failure. Container/pytest infrastructure errors (including Docker exit 125 and pytest no-tests exit 5) stop immediately and do not trigger an LLM call.
- A passing test suite is not proof a patch is correct. You must review the code and its test coverage before approval.
- The project is intentionally restricted to one existing `.py` file at a time. New-file generation, multi-file repair, generating regression tests, and GitHub PRs are later milestones.
- Only **existing tests** are run in Step 6; it does not automatically generate new regression tests yet.
- On Groq rate limits or other API errors, the process stops. You can retry after limits reset.

## Offline regression test status

The 14 newly included regression tests were run locally with pytest. LangGraph/Groq integration and actual Docker execution must be verified in your Windows environment. Expected in your environment if all prior 38 pass: **52 passing tests**, though dependencies/environment can affect outcomes.
