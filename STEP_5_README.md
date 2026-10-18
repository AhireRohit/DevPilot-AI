# DevPilot AI — Step 5: Human-approved patches & Docker tests

## What this adds
- **No additional Groq usage required for the previously successful `path.stat()` patch**: `demo` reproduces the exact diff you already reviewed using existing code, without asking a model to regenerate it.
- Persist a validated proposal to `.venv/devpilot_proposals/` (excluded from Repository Explorer and Git by virtue of `.venv`).
- Verify the proposal's original-source SHA-256 against the file before testing and again immediately before applying.
- Copy a bounded subset of repository text files to a disposable staging directory under `.venv/devpilot_stage/`; `.env`, private keys, `.git`, `pytest_temp` are excluded.
- Inject a dedicated test for the observed `path.stat()` failure into the *staged copy only*. This test demonstrably fails before the change and passes with it.
- Run Pytest inside a restricted Docker container (`--network none`, read-only file mount, no capabilities, non-root user, resource limits, no secrets mounted).
- Require **two approvals**: `TEST` to run the Docker suite and then `APPLY` to replace the original file, only when tests pass.
- Create a backup under `.venv/devpilot_backups/` before replacing source.

## 1. Install files in existing project root

Extract `DevPilot_AI_Step5_Docker_Approval.zip` straight into `D:\0 Resume Projects\DevPilot AI` (not inside another subfolder).

```powershell
cd "D:\0 Resume Projects\DevPilot AI"
Expand-Archive -Path "C:\Users\rohit\Downloads\DevPilot_AI_Step5_Docker_Approval.zip" -DestinationPath . -Force
python -m pytest -q tests --basetemp=.\pytest_temp
```

Expected: **38 passed**, as long as your previous 30 tests remain unchanged.

## 2. Install/start Docker Desktop and build the trusted testing runner

Run `docker version` to make sure Docker Desktop is running. Then build **our** test-runner image. The Docker build needs internet once to download Python packages. This is not a billable LLM/API operation.

```powershell
docker build -t devpilot-test-runner:local -f .\devpilot_runner\Dockerfile .\devpilot_runner
```

No repository source or secrets are sent as the image-build context: it is `devpilot_runner/` only. Do not use an analyzed repo's Dockerfile for the test runner.

## 3. Recreate the same proposal offline (0 Groq calls)

```powershell
python -m app.step5_cli --repo . demo
```

This writes `.venv/devpilot_proposals/stat_oserror.json` and shows the diff. It does **not** touch `app/tools/repo_tools.py`. If you already applied the fix, this demo will reject the duplicate.

## 4. Docker-test, then choose whether to apply

```powershell
python -m app.step5_cli --repo . verify
```

Review the displayed diff. Type `TEST` (uppercase) to stage the patched code and run tests in Docker. A new regression test is included in the staged suite. On successful tests, type `APPLY` (uppercase) to replace the original Python file and save a backup. Any other answer declines. On Docker errors, missing daemon/image, test failure or timeout, the original file stays unchanged.

**After applying:** Add the permanent regression test to your source tree and rerun local tests:

```powershell
Copy-Item .\devpilot_runner\regressions\test_stat_oserror.py .\tests\test_stat_oserror.py
python -m pytest -q tests --basetemp=.\pytest_temp
```

The final expected count is **39 passed** if the 38 existing tests remain successful.

## 5. For future tasks (uses Groq only when you deliberately request it)

```powershell
python -m app.step5_cli --repo . generate --target app/tools/repo_tools.py --needle "for node in syntax.body:" --task "Improve nested symbol discovery" --output .venv/devpilot_proposals/symbols.json
python -m app.step5_cli --repo . verify --proposal .venv/devpilot_proposals/symbols.json
```

Do not run `generate` for a new task until Step 5 is working for the known patch.

## Scope and cautions
- Python `.py` files only, one file per proposed patch. Changes do not get committed, pushed, or merged.
- No automated repair loop yet. That's Step 6, after we can reproduce and diagnose failing container tests.
- Docker isolation lowers risk but is not a hardened boundary against malicious code; do not test unknown adversarial repositories on your personal workstation.
- Tests passing is necessary, not sufficient: review code semantics, not just syntax and green tests.
- If Docker Desktop or image creation fails, provide the exact error; do not bypass the isolated execution by running unfamiliar code on the host.
