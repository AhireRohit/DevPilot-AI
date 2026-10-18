"""Regression test: unreadable file metadata must not abort repository scanning."""
from pathlib import Path

from app.tools.repo_tools import RepositoryExplorer


def test_unreadable_stat_is_skipped(tmp_path, monkeypatch):
    (tmp_path / "good.py").write_text("def okay():\n    return True\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("def nope():\n    return False\n", encoding="utf-8")
    original_stat = Path.stat

    def sometimes_denied(self, *args, **kwargs):
        if self.name == "broken.py" and kwargs.get("follow_symlinks", True):
            raise PermissionError("simulated Windows access-denied error")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", sometimes_denied)
    files = RepositoryExplorer(tmp_path).list_files()
    assert "good.py" in files
    assert "broken.py" not in files
