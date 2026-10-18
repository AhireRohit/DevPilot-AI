"""Issue #1 acceptance checks, injected into a disposable Docker test stage.

This test is intentionally *not* collected by the main project test suite
until the implementation is fixed. Copy it into the eventual PR branch's
normal tests directory before merging.
"""
from app.tools.repo_tools import RepositoryExplorer


def test_nested_functions_classes_and_methods(tmp_path):
    source = '''def outer():
    def inner():
        return 1
    class Inner:
        def method(self):
            def helper():
                return 2
            return helper()
    return Inner()

class Container:
    class Nested:
        def run(self):
            return 3

    async def execute(self):
        async def action():
            return 4
        return await action()
'''
    (tmp_path / 'nested.py').write_text(source, encoding='utf-8')
    symbols = RepositoryExplorer(tmp_path).python_symbols('nested.py')
    items = {(s['kind'], s['name'], s['line']) for s in symbols}
    expected = {
        ('function', 'outer', 1),
        ('function', 'outer.inner', 2),
        ('class', 'outer.Inner', 4),
        ('method', 'outer.Inner.method', 5),
        ('function', 'outer.Inner.method.helper', 6),
        ('class', 'Container', 11),
        ('class', 'Container.Nested', 12),
        ('method', 'Container.Nested.run', 13),
        ('method', 'Container.execute', 16),
        ('function', 'Container.execute.action', 17),
    }
    assert expected <= items


def test_original_top_level_shape_unchanged(tmp_path):
    (tmp_path / 'classic.py').write_text(
        'class Calc:\n    def div(self, a, b):\n        return a / b\n', encoding='utf-8')
    assert RepositoryExplorer(tmp_path).python_symbols('classic.py') == [
        {'kind': 'class', 'name': 'Calc', 'line': 1},
        {'kind': 'method', 'name': 'Calc.div', 'line': 2},
    ]
