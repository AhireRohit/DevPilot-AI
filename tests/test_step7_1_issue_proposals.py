"""Offline Step 7.1 CLI tests: no Groq API calls, Docker, or GitHub writes."""
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.step7_1_cli import make_issue_prompt, output_location, STAGED_TEST


def test_prompt_contains_issue_and_bounded_source():
    message = make_issue_prompt({'title': 'Nested AST', 'body': 'Find functions'}, ' 1 | def foo():')
    assert 'Nested AST' in message
    assert 'Find functions' in message
    assert 'submit_patch' in message
    assert ' 1 | def foo():' in message


def test_prompt_bounds_untrusted_issue_body():
    message = make_issue_prompt({'title': 'x', 'body': 'a' * 9000}, 'source')
    assert 'a' * 2400 in message
    assert 'a' * 2401 not in message


def test_proposal_destination_remains_ignored(tmp_path):
    dest = output_location(tmp_path, 1, None)
    assert dest == tmp_path / '.venv' / 'devpilot_proposals' / 'issue_1.json'
    assert STAGED_TEST.as_posix().startswith('tests/')


def test_proposal_name_rejects_path_escape_and_files(tmp_path):
    for filename in ('../escape.json', 'else.json', 'issue_1.txt', 'a/issue_1.json'):
        with pytest.raises(ValueError):
            output_location(tmp_path, 1, filename)
    dest = output_location(tmp_path, 1, 'issue_1.json')
    dest.write_text('{}')
    with pytest.raises(FileExistsError):
        output_location(tmp_path, 1, 'issue_1.json')


def test_prompt_bad_data_fails():
    with pytest.raises(ValueError):
        make_issue_prompt({'title': None, 'body': 'x'}, 'code')
    with pytest.raises(ValueError):
        make_issue_prompt({'title': 'x', 'body': 'x'}, 'y' * 20_001)
