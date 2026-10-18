"""Step 5 tests never invoke Groq or Docker; runner is contract-tested offline."""
from pathlib import Path
import json
import shutil
from types import SimpleNamespace

import pytest

from app.agent.patches import PatchSession
from app.agent.review_pipeline import (
    apply_tested_patch, diff_for, docker_test, fingerprint, load_proposal,
    save_proposal, stage_repository,
)
from app.tools.repo_tools import RepositoryExplorer


def fixture_patch(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sanity.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "app" / "sample.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    session = PatchSession(RepositoryExplorer(tmp_path))
    patch = session.propose(path="app/sample.py", old_text="    return 1", new_text="    return 2",
                            explanation="Correct logic")
    target = tmp_path / ".venv" / "devpilot_proposals" / "demo.json"
    save_proposal(patch, target)
    return patch, target


def test_round_trip_and_diff(tmp_path):
    _, manifest = fixture_patch(tmp_path)
    saved, source, original = load_proposal(tmp_path, manifest)
    assert saved.path == "app/sample.py"
    assert "+    return 2" in diff_for(original, saved)
    assert "return 1" in source.read_text(encoding="utf-8")


def test_manifest_disallows_overwrite(tmp_path):
    patch, manifest = fixture_patch(tmp_path)
    with pytest.raises(FileExistsError):
        save_proposal(patch, manifest)


def test_invalid_target_path_rejected(tmp_path):
    _, manifest = fixture_patch(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["path"] = "../outside.py"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="path"):
        load_proposal(tmp_path, manifest)


def test_stale_patch_rejected(tmp_path):
    _, manifest = fixture_patch(tmp_path)
    (tmp_path / "app" / "sample.py").write_text("def f():\n    return 3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        load_proposal(tmp_path, manifest)


def test_stage_source_and_exclude_secrets(tmp_path):
    _, manifest = fixture_patch(tmp_path)
    (tmp_path / ".env").write_text("GROQ_API_KEY=dont-copy", encoding="utf-8")
    (tmp_path / "tests" / "token.key").write_text("SECRET", encoding="utf-8")
    (tmp_path / "pytest_temp").mkdir()
    (tmp_path / "pytest_temp" / "bad.py").write_text("SECRET=1", encoding="utf-8")
    saved, _, _ = load_proposal(tmp_path, manifest)
    stage = tmp_path / "staging-out" / "repo"
    count = stage_repository(tmp_path, stage, saved)
    assert count >= 2
    assert "return 2" in (stage / "app" / "sample.py").read_text(encoding="utf-8")
    assert "return 1" in (tmp_path / "app" / "sample.py").read_text(encoding="utf-8")
    assert not (stage / ".env").exists()
    assert not (stage / "tests" / "token.key").exists()
    assert not (stage / "pytest_temp").exists()


def test_apply_requires_tests_and_backups(tmp_path):
    _, manifest = fixture_patch(tmp_path)
    saved, source, original = load_proposal(tmp_path, manifest)
    with pytest.raises(ValueError, match="untested"):
        apply_tested_patch(tmp_path, saved, original, tests_passed=False)
    assert "return 1" in source.read_text(encoding="utf-8")
    backup = apply_tested_patch(tmp_path, saved, original, tests_passed=True)
    assert "return 2" in source.read_text(encoding="utf-8")
    assert "return 1" in backup.read_text(encoding="utf-8")


def test_apply_detects_changed_source(tmp_path):
    _, manifest = fixture_patch(tmp_path)
    saved, _, original = load_proposal(tmp_path, manifest)
    (tmp_path / "app" / "sample.py").write_text("def f():\n    return 500\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        apply_tested_patch(tmp_path, saved, original, tests_passed=True)


def test_docker_command_is_constrained(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(shutil, "which", lambda _: "docker.exe")
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")
    from app.agent import review_pipeline as pipeline
    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    result = docker_test(tmp_path)
    assert result.returncode == 0
    for flag in ("--network", "none", "--read-only", "--cap-drop", "ALL", "--user", "65534:65534"):
        assert flag in captured["cmd"]
    assert "type=bind,source=" in " ".join(captured["cmd"])
    assert "readonly" in " ".join(captured["cmd"])
    assert captured["kwargs"]["timeout"] == 180
