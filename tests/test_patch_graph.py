"""Offline graph integration tests. Skips only if LangGraph is unavailable."""
import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage, HumanMessage
from app.agent.patch_graph import make_patch_agent


class FakePatchModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{
                "name": "read_repository_file",
                "args": {"path": "sample.py", "start": 1, "end": 10},
                "id": "read_one", "type": "tool_call",
            }])
        return AIMessage(content="", tool_calls=[{
            "name": "submit_patch",
            "args": {
                "path": "sample.py", "old_text": "    return 1",
                "new_text": "    return 2", "explanation": "Fix returned value",
            },
            "id": "patch_one", "type": "tool_call",
        }])


def test_agent_inspects_then_proposes_without_writing(tmp_path):
    file = tmp_path / "sample.py"
    code = "def answer():\n    return 1\n"
    file.write_text(code, encoding="utf-8")
    fake = FakePatchModel()
    graph, session = make_patch_agent(tmp_path, model=fake, max_model_calls=4)
    response = graph.invoke({"messages": [HumanMessage(content="Fix answer function")]},
                            config={"recursion_limit": 22})
    assert fake.calls == 2
    assert session.proposal is not None
    assert "+    return 2" in session.proposal.diff
    assert file.read_text(encoding="utf-8") == code
    assert "not been applied" in response["messages"][-1].content
