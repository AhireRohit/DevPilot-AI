"""Offline, zero-cost security/correctness tests of review-only patch proposals."""
from __future__ import annotations

import pytest

from app.agent.patches import PatchSession
from app.tools.repo_tools import RepositoryExplorer


def make_session(tmp_path, code="def answer():\n    return 1\n"):
    file = tmp_path / "sample.py"
    file.write_text(code, encoding="utf-8")
    return PatchSession(RepositoryExplorer(tmp_path)), file


def propose(session, path="sample.py", old="    return 1", new="    return 2"):
    return session.propose(path=path, old_text=old, new_text=new,
                           explanation="Fix the return value")


def test_review_only_diff_does_not_write(tmp_path):
    session, file = make_session(tmp_path)
    before = file.read_bytes()
    patch = propose(session)
    assert file.read_bytes() == before
    assert "-    return 1" in patch.diff
    assert "+    return 2" in patch.diff
    assert "a/sample.py" in patch.diff
    assert patch.proposed.endswith("return 2\n")


def test_requires_exact_match(tmp_path):
    session, _ = make_session(tmp_path)
    with pytest.raises(ValueError, match="not found exactly"):
        propose(session, old="    return 999")


def test_requires_unique_match(tmp_path):
    session, _ = make_session(tmp_path, "def a():\n    return 1\ndef b():\n    return 1\n")
    with pytest.raises(ValueError, match="multiple locations"):
        propose(session)


def test_rejects_invalid_python(tmp_path):
    session, file = make_session(tmp_path)
    with pytest.raises(ValueError, match="invalid syntax"):
        propose(session, new="    return (")
    assert file.read_text(encoding="utf-8") == "def answer():\n    return 1\n"


def test_rejects_traversal_absolute_and_windows_paths(tmp_path):
    session, _ = make_session(tmp_path)
    for path in ("../outside.py", "/tmp/outside.py", "C:/Users/a.py", "..\\outside.py"):
        with pytest.raises(ValueError):
            propose(session, path=path)


def test_rejects_private_files(tmp_path):
    session, _ = make_session(tmp_path)
    (tmp_path / ".env.py").write_text("SECRET=1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="secret"):
        propose(session, path=".env.py", old="SECRET=1", new="SECRET=2")


def test_rejects_symlink(tmp_path):
    session, _ = make_session(tmp_path)
    target = tmp_path / "linked.py"
    try:
        target.symlink_to(tmp_path / "sample.py")
    except (OSError, NotImplementedError):
        pytest.skip("Platform does not allow creating test symlinks")
    with pytest.raises(ValueError, match="symlink"):
        propose(session, path="linked.py")


def test_rejects_non_python_target(tmp_path):
    session, _ = make_session(tmp_path)
    (tmp_path / "notes.md").write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\.py"):
        propose(session, path="notes.md", old="hello", new="goodbye")


def test_cannot_submit_second_patch(tmp_path):
    session, _ = make_session(tmp_path)
    propose(session)
    with pytest.raises(ValueError, match="already been proposed"):
        propose(session)


def test_rejects_unchanged_replacement(tmp_path):
    session, _ = make_session(tmp_path)
    with pytest.raises(ValueError, match="would not change"):
        propose(session, new="    return 1")


def test_rejects_excessive_code(tmp_path):
    session, _ = make_session(tmp_path)
    with pytest.raises(ValueError, match="too large"):
        propose(session, new="x" * 4001)


def test_patch_stat_bug_with_exact_excerpt(tmp_path):
    code = ('from pathlib import Path\n'
            'def visit(path: Path):\n'
            '    if path.stat().st_size > 10:\n'
            '        return False\n'
            '    return True\n')
    session, file = make_session(tmp_path, code)
    patch = session.propose(
        path="sample.py",
        old_text="    if path.stat().st_size > 10:\n        return False",
        new_text=("    try:\n        if path.stat().st_size > 10:\n"
                  "            return False\n    except OSError:\n        return False"),
        explanation="Skip files whose metadata cannot be read",
    )
    assert "except OSError" in patch.diff
    assert file.read_text(encoding="utf-8") == code
