"""Offline tests: the actual Groq API is never called."""
import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import make_agent
from app.agent.tools import make_repository_tools
from app.tools.repo_tools import RepositoryExplorer


class FakeToolCallingModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{
                    "name": "list_repository_files",
                    "args": {"limit": 20},
                    "id": "call_test_01",
                    "type": "tool_call",
                }],
            )
        return AIMessage(content="Found sample.py in the repository.")


def test_model_can_request_and_use_tool(tmp_path):
    (tmp_path / "sample.py").write_text("def sample():\n    return 42\n", encoding="utf8")
    model = FakeToolCallingModel()
    graph = make_agent(tmp_path, model=model)
    result = graph.invoke(
        {"messages": [HumanMessage(content="What files are there?")]},
        config={"recursion_limit": 15},
    )
    assert model.calls == 2
    tool_outputs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_outputs) == 1
    assert "sample.py" in tool_outputs[0].content
    assert "Found sample.py" in result["messages"][-1].content


def test_secret_file_remains_blocked(tmp_path):
    (tmp_path / ".env").write_text("GROQ_API_KEY=PRIVATE_KEY", encoding="utf8")
    tools = make_repository_tools(RepositoryExplorer(tmp_path))
    read = next(t for t in tools if t.name == "read_repository_file")
    result = read.invoke({"path": ".env", "start": 1, "end": 2})
    assert "Tool error" in result
    assert "PRIVATE_KEY" not in result


def test_model_call_limit(tmp_path):
    (tmp_path / "sample.py").write_text("print('ok')\n", encoding="utf8")
    model = FakeToolCallingModel()
    graph = make_agent(tmp_path, model=model, max_model_calls=1)
    result = graph.invoke(
        {"messages": [HumanMessage(content="What files exist?")]},
        config={"recursion_limit": 12},
    )
    assert model.calls == 1
    assert "limit" in result["messages"][-1].content.lower()
