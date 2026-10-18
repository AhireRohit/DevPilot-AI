# DevPilot AI — Step 3.1 hotfix

Your Step 3 reported `10 passed`, then Groq requested 200-line file reads (maximum is 100), listed `pytest_temp/` fixtures and exhausted the default 6 model calls.

This patch changes **only**:

- `app/tools/repo_tools.py`: ignore `pytest_temp` during repository listing and searches.
- `app/agent/tools.py`: automatically cap requested file reads to 100 lines instead of returning a tool error, with explicit guidance in its schema.
- `tests/test_agent_tool_bounds.py`: 2 additional offline regression tests.

## Installation on Windows

Open PowerShell in `D:\0 Resume Projects\DevPilot AI` with `.venv` active and extract `DevPilot_AI_Step3_1_Hotfix.zip` into the main project directory (not a nested folder):

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\DevPilot_AI_Step3_1_Hotfix.zip" -DestinationPath . -Force
python -m pytest -q tests --basetemp=.\pytest_temp
```

With the original 10 tests and the two new ones, expect 12 passing tests.

Then try a specific, bounded task with a few more model calls:

```powershell
python -m app.agent_cli --repo . --max-calls 10 --verbose --question "Inspect app/tools/repo_tools.py only. Read lines 1 to 100, then relevant later lines if necessary. Identify at most two potential edge cases, referencing exact line numbers, and give a concise final report."
```

The max-calls safeguard still applies. Full-repository analysis may take more calls; precise prompts are more reliable on a free API. The system is still read-only.
