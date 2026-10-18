"""Offline tests for the bounded Step 6 Docker repair loop (never call Groq)."""
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.agent.patches import PatchSession
from app.agent.repair_pipeline import (
    check_repair_source, changed_source_excerpt, feedback_text, run_repair_loop,
)
from app.agent.review_pipeline import SavedPatch, fingerprint
from app.tools.repo_tools import RepositoryExplorer


def example(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_calculator.py").write_text(
        "from src.calculator import add\ndef test_add():\n    assert add(4,3) == 7\n",
        encoding="utf-8",
    )
    session = PatchSession(RepositoryExplorer(tmp_path))
    initial = session.propose(
        path="src/calculator.py", old_text="    return a - b",
        new_text="    return abs(a - b)", explanation="Intentionally wrong",
    )
    return SavedPatch(initial.path, initial.explanation,
                      fingerprint(initial.original), initial.proposed)


def fake_runner(stage):
    source = (stage / "src" / "calculator.py").read_text(encoding="utf-8")
    if "return a + b" in source:
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")
    return SimpleNamespace(returncode=1, stdout="1 failed\nassert 1 == 7", stderr="")


def test_fail_then_repair_passes_and_original_stays_unchanged(tmp_path):
    p = example(tmp_path)
    requests = []

    def fake_repair(stage, proposal, failure, attempt):
        requests.append((proposal.path, attempt, failure))
        assert (stage / "src" / "calculator.py").read_text() == p.proposed_source
        return "def add(a, b):\n    return a + b\n"

    output = run_repair_loop(tmp_path, p, runner=fake_runner, repairer=fake_repair,
                             allow_repair=lambda: True, log=lambda _: None)
    assert output.status == "passed"
    assert len(output.trials) == 2
    assert output.repairs_used == 1
    assert requests[0][:2] == ("src/calculator.py", 1)
    assert output.proposal.original_hash == p.original_hash
    assert "return a + b" in output.proposal.proposed_source
    assert "return a - b" in (tmp_path / "src" / "calculator.py").read_text()


def test_refusal_no_api_call(tmp_path):
    p = example(tmp_path)
    def forbidden(*args):
        raise AssertionError("Groq was called without approval")
    outcome = run_repair_loop(tmp_path, p, runner=fake_runner,
                              repairer=forbidden, allow_repair=lambda: False,
                              log=lambda _: None)
    assert outcome.status == "failed"
    assert outcome.repairs_used == 0
    assert len(outcome.trials) == 1


def test_repair_limit_cannot_exceed_two(tmp_path):
    p = example(tmp_path)
    with pytest.raises(ValueError, match="max_repairs"):
        run_repair_loop(tmp_path, p, max_repairs=3, runner=fake_runner)


def test_one_retry_not_indefinite(tmp_path):
    p = example(tmp_path)
    calls = []
    def ineffective(stage, proposal, feedback, attempt):
        calls.append(attempt)
        return "def add(a, b):\n    return a * b\n"
    outcome = run_repair_loop(tmp_path, p, max_repairs=1, runner=fake_runner,
                              repairer=ineffective, allow_repair=lambda: True,
                              log=lambda _: None)
    assert outcome.status == "failed"
    assert len(outcome.trials) == 2
    assert calls == [1]


def test_container_error_is_not_a_bug_fix(tmp_path):
    p = example(tmp_path)
    def runner(stage):
        return SimpleNamespace(returncode=125, stdout="", stderr="Docker daemon unavailable")
    with pytest.raises(RuntimeError, match="Test environment failed"):
        run_repair_loop(tmp_path, p, runner=runner, repairer=lambda *_: "", 
                        allow_repair=lambda: True, log=lambda _: None)


def test_no_tests_is_not_a_success(tmp_path):
    p = example(tmp_path)
    def runner(stage):
        return SimpleNamespace(returncode=5, stdout="no tests ran", stderr="")
    with pytest.raises(RuntimeError, match="exit 5"):
        run_repair_loop(tmp_path, p, runner=runner, log=lambda _: None)


def test_reject_invalid_syntax_and_unchanged_source(tmp_path):
    p = example(tmp_path)
    with pytest.raises(SyntaxError):
        check_repair_source(p, p, "def add(:\n")
    with pytest.raises(ValueError, match="did not modify"):
        check_repair_source(p, p, p.proposed_source)


def test_no_extra_call_when_tests_pass(tmp_path):
    p = example(tmp_path)
    def success(stage):
        return SimpleNamespace(returncode=0, stdout="2 passed", stderr="")
    def forbidden(*args):
        raise AssertionError("No repair should run if tests pass")
    result = run_repair_loop(tmp_path, p, runner=success, repairer=forbidden,
                             allow_repair=lambda: True, log=lambda _: None)
    assert result.status == "passed"
    assert result.repairs_used == 0


def test_bound_failure_output():
    fake = SimpleNamespace(stdout="z" * 9999 + "\x1b[31m", stderr="error!")
    feedback = feedback_text(fake)
    assert len(feedback) <= 5000
    assert "error!" in feedback
    assert "\x1b" not in feedback


def test_excerpt_around_changed_lines():
    before = "def add(a,b):\n    return a - b\n"
    after = "def add(a,b):\n    return abs(a - b)\n"
    snippet = changed_source_excerpt(before, after, "src/calculator.py")
    assert "TARGET FILE: src/calculator.py" in snippet
    assert "return abs(a - b)" in snippet
    assert "UNTRUSTED SOURCE" in snippet


def test_staging_never_copies_env_to_test_runner(tmp_path):
    p = example(tmp_path)
    (tmp_path / ".env").write_text("GROQ_API_KEY=secret", encoding="utf-8")
    def runner(stage):
        assert not (stage / ".env").exists()
        return fake_runner(stage)
    result = run_repair_loop(tmp_path, p, runner=runner, log=lambda _: None)
    assert result.status == "failed"


def test_demo_is_untracked_and_patch_is_saved(tmp_path):
    from app.step6_cli import create_demo
    (tmp_path / ".venv").mkdir()
    create_demo(tmp_path)
    demo = tmp_path / ".venv" / "devpilot_demos" / "calculator"
    assert (demo / "src" / "calculator.py").exists()
    assert (demo / ".venv" / "devpilot_proposals" / "initial.json").exists()
    with pytest.raises(FileExistsError):
        create_demo(tmp_path)


def test_cli_refusal_to_apply_preserves_original_and_saves_candidate(tmp_path, monkeypatch):
    from app import step6_cli as cli
    from app.agent.repair_pipeline import RepairOutcome, Trial
    create_demo = cli.create_demo
    create_demo(tmp_path)
    demo = tmp_path / ".venv" / "devpilot_demos" / "calculator"
    path = demo / "src" / "calculator.py"
    manifest = demo / ".venv" / "devpilot_proposals" / "initial.json"
    source = path.read_text(encoding="utf-8")
    saved, _, _ = cli.load_proposal(demo, manifest)
    final = SavedPatch(saved.path, saved.explanation, saved.original_hash,
                       "def add(a, b):\n    return a + b\n")
    monkeypatch.setattr(cli, "run_repair_loop", lambda *a, **kw:
                        RepairOutcome("passed", final, (Trial(1, True, 0, "2 passed"),), 1))
    answers = iter(["TEST", "NO"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    cli.run_demo(demo, manifest, 2)
    assert path.read_text(encoding="utf-8") == source
    repaired_manifests = list((demo / ".venv" / "devpilot_proposals").glob("repaired_*.json"))
    assert len(repaired_manifests) == 1
    candidate, _, _ = cli.load_proposal(demo, repaired_manifests[0])
    assert "return a + b" in candidate.proposed_source


def test_cli_requires_explicit_test_confirmation(tmp_path, monkeypatch):
    from app import step6_cli as cli
    cli.create_demo(tmp_path)
    demo = tmp_path / ".venv" / "devpilot_demos" / "calculator"
    manifest = demo / ".venv" / "devpilot_proposals" / "initial.json"
    monkeypatch.setattr("builtins.input", lambda *_: "NO")
    monkeypatch.setattr(cli, "run_repair_loop", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("Docker run without TEST")))
    cli.run_demo(demo, manifest, 2)
    assert "return a - b" in (demo / "src" / "calculator.py").read_text()
