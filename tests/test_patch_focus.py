"""Regression tests for the bounded context supplied to the coding agent."""
from pathlib import Path
import pytest

from app.tools.repo_tools import RepositoryExplorer
from app.agent.focus import focused_source_excerpt


def test_focus_contains_target_once_and_preserves_indentation(tmp_path: Path):
    (tmp_path / "sample.py").write_text(
        "def example():\n    value = 1\n    return value\n", encoding="utf-8"
    )
    context = focused_source_excerpt(
        RepositoryExplorer(tmp_path), path="sample.py", needle="value = 1"
    )
    assert "AUTHORIZED TARGET: sample.py" in context
    assert "   2 |     value = 1" in context
    assert "omit them" in context


def test_focus_requires_unique_needle(tmp_path: Path):
    (tmp_path / "sample.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="appears 2 times"):
        focused_source_excerpt(RepositoryExplorer(tmp_path), path="sample.py", needle="x = 1")


def test_focus_rejects_private_and_traversal(tmp_path: Path):
    (tmp_path / ".env").write_text("private\n", encoding="utf-8")
    (tmp_path / "sample.py").write_text("safe = True\n", encoding="utf-8")
    explorer = RepositoryExplorer(tmp_path)
    with pytest.raises(ValueError):
        focused_source_excerpt(explorer, path=".env", needle="private")
    with pytest.raises(ValueError):
        focused_source_excerpt(explorer, path="../sample.py", needle="safe")


def test_focus_rejects_missing_needle(tmp_path: Path):
    (tmp_path / "sample.py").write_text("safe = True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not found"):
        focused_source_excerpt(RepositoryExplorer(tmp_path), path="sample.py", needle="missing")


def test_focused_agent_exposes_only_submit_patch(tmp_path: Path):
    pytest.importorskip("langgraph")
    pytest.importorskip("langchain_core")
    from langchain_core.messages import AIMessage, HumanMessage
    from app.agent.patch_graph import make_patch_agent

    (tmp_path / "sample.py").write_text("def value():\n    return 1\n", encoding="utf-8")

    class FakeModel:
        def __init__(self):
            self.calls = 0
            self.tool_names = []
        def bind_tools(self, tools):
            self.tool_names = [tool.name for tool in tools]
            return self
        def invoke(self, messages):
            self.calls += 1
            return AIMessage(content="", tool_calls=[{
                "name": "submit_patch",
                "args": {
                    "path": "sample.py", "old_text": "    return 1",
                    "new_text": "    return 2", "explanation": "Fix value",
                },
                "id": f"patch_{self.calls}", "type": "tool_call",
            }])

    fake = FakeModel()
    graph, session = make_patch_agent(tmp_path, model=fake, max_model_calls=3, focused=True)
    result = graph.invoke({"messages": [HumanMessage(content="Fix sample.py")]})
    assert fake.tool_names == ["submit_patch"]
    assert fake.calls == 1
    assert session.proposal is not None
    assert "+    return 2" in session.proposal.diff
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "def value():\n    return 1\n"
