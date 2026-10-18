"""Offline regression tests for bounded tool reads and ignored pytest fixtures."""
from app.tools.repo_tools import RepositoryExplorer


def test_pytest_temp_is_skipped(tmp_path):
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    excluded = tmp_path / "pytest_temp"
    excluded.mkdir()
    (excluded / "fake_bug.py").write_text("raise RuntimeError('fake')", encoding="utf-8")
    explorer = RepositoryExplorer(tmp_path)
    assert explorer.list_files() == ["app.py"]
    assert explorer.search_code("fake_bug") == []


def test_agent_read_clamps_to_100_lines(tmp_path):
    from app.agent.tools import make_repository_tools

    (tmp_path / "example.py").write_text(
        "\n".join(f"x_{i} = {i}" for i in range(1, 151)) + "\n",
        encoding="utf-8",
    )
    tools = make_repository_tools(RepositoryExplorer(tmp_path))
    reader = next(t for t in tools if t.name == "read_repository_file")
    result = reader.invoke({"path": "example.py", "start": 1, "end": 200})
    assert "Read capped" in result
    assert "100 | x_100" in result
    assert "101 | x_101" not in result
    assert "Tool error" not in result
