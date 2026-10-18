# DevPilot AI — Step 3: LangGraph + Groq agent

This is an ADD-ON to Step 2. It deliberately **does not replace** your existing `app/tools/repo_tools.py`, `app/repo_cli.py`, `.env`, or `test_llm.py`.

## Install into existing Windows project

Run PowerShell from `D:\0 Resume Projects\DevPilot AI` with your virtualenv active.

```powershell
python -m pip install -U langgraph langchain-groq python-dotenv
```

Extract the contents of `DevPilot_AI_Step3_LangGraph.zip` **directly into the project root** (not into an extra nested folder). You should see `app/agent/graph.py` and `app/agent_cli.py` next to your existing `app/repo_cli.py`.

To extract using PowerShell, if the ZIP is in your Downloads directory:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\DevPilot_AI_Step3_LangGraph.zip" -DestinationPath . -Force
```

Keep `.env` in the root with `GROQ_API_KEY=...`. Do not share or commit `.env`.

## Run local tests without API calls

```powershell
python -m pytest -q tests --basetemp=.\pytest_temp
```

Expect 10 passing tests (the original 7 plus 3 new ones), assuming all dependencies are installed and the Step 2 files remain present.

## Run the agent (Groq API)

```powershell
python -m app.agent_cli --repo . --question "Summarize this repository and cite relevant files" --verbose
```

Or investigate a specific file:

```powershell
python -m app.agent_cli --repo . --question "Inspect app/tools/repo_tools.py and identify two possible edge cases. Cite files and line numbers." --verbose
```

Optional: set `GROQ_MODEL=openai/gpt-oss-120b` in `.env` to choose the model. By default, this is the selected model. The tool-calling run can consume multiple model requests, so keep prompts specific and monitor Groq's free-tier rate limits.

## Features and limits

- Read-only tools: list, search, read, Python AST symbols
- Repository root chosen by the user in `--repo`, not by LLM
- Secret-file/path-traversal guards inherited from Step 2
- Max 6 Groq calls/run by default, adjustable with `--max-calls` (max 12)
- No code edits, terminal execution, Docker tests, Git pushes, or PR creation **yet**
- The agent **may** report false-positive bugs: no execution occurs, so findings are hypotheses

## Troubleshooting

- `ModuleNotFoundError: langchain_groq` → run the install command in the active `.venv`.
- `No module named app.agent_cli` → ZIP was extracted to the wrong directory. Move `app` and `tests` into the existing project root.
- `GROQ_API_KEY was not found` → ensure `.env` exists in the current project root.
- Groq rate limit / quota → try again after limits reset; keep `--max-calls` low.
- The graph may stop at its call limit before producing a complete report. Ask a narrower question or raise `--max-calls` carefully.

### Security note

Only inspect repositories you trust and are authorized to access. Repository code may contain confidential information; the selected code snippets are sent to Groq when the agent reads them. `.env` and common credential formats are blocked, but static filename filters cannot catch every possible secret embedded in source files. Avoid using this stage on sensitive, private repositories.
