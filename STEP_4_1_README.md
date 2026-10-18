# DevPilot — Step 4.1 Focused Patch Mode

Your tests passed, but GPT-OSS-120B repeatedly requested `read_repository_file`
instead of submitting a patch. This optional **focused mode** supplies a bounded
snippet before the first model call and gives the LLM only the `submit_patch`
tool. It avoids repeated repository browsing and can complete in one API call.

Extract this ZIP directly into the existing `DevPilot AI` project root. It
updates `app/patch_cli.py` and `app/agent/patch_graph.py`, and adds
`app/agent/focus.py` plus `tests/test_patch_focus.py`. Existing Step 4 mode
without `--target/--needle` is unchanged.

```powershell
cd "D:\0 Resume Projects\DevPilot AI"
python -m pytest -q tests --basetemp=.\pytest_temp
python -m app.patch_cli --repo . --max-calls 3 --target app/tools/repo_tools.py --needle "for filename in sorted(files):" --task "Propose a minimal fix so path.stat() raising OSError inside _files causes that file to be skipped. Only propose a diff; do not modify files." --verbose
```

`--needle` **must occur on exactly one line** of the selected file. Use
`--radius 22` (default) to control the source excerpt size; valid 5–40.
If GPT-OSS-120B needs more context, increase to 30, not your API call budget.

**Security:** This is still a review-only proposal. It does not write the file,
run tests, push code, or create a PR. It sends the selected code excerpt to
Groq, so choose an authorized, nonsensitive repository. Validate correctness
and add regression tests before applying anything later.
