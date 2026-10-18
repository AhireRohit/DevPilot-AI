# DevPilot AI — Step 4: review-only patch proposals

Step 4 connects the existing Groq/LangGraph agent to a **single-file Python
patch proposal tool**. It never changes repository source files.

## Install into your EXISTING `DevPilot AI` root

Extract this ZIP directly into your existing project folder. It adds files
under `app/agent/`, `app/patch_cli.py`, and `tests/`. It does not replace the
working Step 3 repository explorer, Groq configuration, or existing tests.

The Python packages are already available if Step 3 worked. Run:

```powershell
cd "D:\0 Resume Projects\DevPilot AI"
python -m pytest -q tests --basetemp=.\pytest_temp
```

Then run the **first real, grounded patch task**:

```powershell
python -m app.patch_cli --repo . --max-calls 10 --task "Inspect app/tools/repo_tools.py and propose a minimal fix for _files raising an OSError if path.stat() fails. Only propose the patch; show the diff." --verbose
```

### Expected behavior

- Groq reads source files through the existing repository tools.
- It calls `submit_patch` using an exact excerpt of source text.
- A matching proposal is verified for valid Python **syntax only**.
- The CLI displays a unified diff with `--- a/...` and `+++ b/...`.
- Your existing `repo_tools.py` remains unchanged.

If Groq doesn't submit a patch within the limit, the CLI shows the agent's
response and tells you no files were changed. A syntax-valid proposal has **not**
been run through tests and may still be incorrect.

### Security / design limits

- Only existing `.py` files, exactly one patch per run.
- Blocks absolute/traversal paths, secret files, symlinks, and large files.
- Unique exact `old_text` matching required; no free-form path writes.
- No shell execution, test execution, file modification, commits, or GitHub push.
- Treat repo content as untrusted; only choose repos you own or are authorized to inspect.
- The inspected source snippets are sent to Groq, so avoid confidential repos.

**Step 5:** after reviewing a diff, add explicit user-approved apply + isolated
Docker tests and a bounded repair loop.
