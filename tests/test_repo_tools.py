from pathlib import Path

import pytest

from app.tools.repo_tools import RepositoryExplorer


@pytest.fixture
def example_repo(tmp_path: Path):
    (tmp_path / "logic.py").write_text(
        "class Calculator:\n    def divide(self, a, b):\n        return a / b\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("Example Python project\n", encoding="utf-8")
    (tmp_path / ".env").write_text("GROQ_API_KEY=DO_NOT_EXPOSE\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "secret.py").write_text("api_key = 'private'\n", encoding="utf-8")
    return RepositoryExplorer(tmp_path)


def test_list_files_skips_secrets_and_venv(example_repo):
    listed = example_repo.list_files()
    assert "logic.py" in listed
    assert "README.md" in listed
    assert ".env" not in listed
    assert ".venv/secret.py" not in listed


def test_search_finds_code_but_no_secrets(example_repo):
    matches = example_repo.search_code("return a / b")
    assert matches == [{"file": "logic.py", "line": 3, "text": "        return a / b"}]
    assert example_repo.search_code("DO_NOT_EXPOSE") == []


def test_read_file_has_line_numbers(example_repo):
    result = example_repo.read_file("logic.py", 2, 3)
    assert "   2 |     def divide" in result
    assert "   3 |         return a / b" in result


def test_symbol_extraction(example_repo):
    assert example_repo.python_symbols("logic.py") == [
        {"kind": "class", "name": "Calculator", "line": 1},
        {"kind": "method", "name": "Calculator.divide", "line": 2},
    ]


def test_block_private_file(example_repo):
    with pytest.raises(ValueError, match="credential"):
        example_repo.read_file(".env")


def test_block_path_traversal(example_repo, tmp_path):
    (tmp_path.parent / "outside.py").write_text("not in repo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        example_repo.read_file("../outside.py")


def test_block_huge_read(example_repo):
    with pytest.raises(ValueError, match="1–160"):
        example_repo.read_file("logic.py", 1, 500)
