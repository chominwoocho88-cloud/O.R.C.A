"""Static checks for the ORCA import-structure refactor."""

from __future__ import annotations

import ast
import importlib
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TARGET_FILES = [
    ROOT / "orca" / "analysis.py",
    ROOT / "orca" / "data.py",
    ROOT / "orca" / "notify.py",
]


def _function_local_imports(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    imports = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        current = parents.get(node)
        owner = None
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = current.name
                break
            current = parents.get(current)
        if owner:
            imports.append((node.lineno, owner))
    return imports


def _install_stub_modules() -> None:
    anthropic = types.ModuleType("anthropic")

    class DummyAnthropic:
        def __init__(self, api_key=None):
            self.api_key = api_key

    anthropic.Anthropic = DummyAnthropic

    httpx = types.ModuleType("httpx")
    httpx.post = lambda *args, **kwargs: None
    httpx.get = lambda *args, **kwargs: None

    rich = types.ModuleType("rich")
    rich_console = types.ModuleType("rich.console")

    class DummyConsole:
        def print(self, *args, **kwargs):
            return None

    rich_console.Console = DummyConsole
    rich.console = rich_console

    sys.modules["anthropic"] = anthropic
    sys.modules["httpx"] = httpx
    sys.modules["rich"] = rich
    sys.modules["rich.console"] = rich_console


class ImportStructureTests(unittest.TestCase):
    def test_analysis_data_notify_have_no_function_scoped_imports(self):
        for path in TARGET_FILES:
            with self.subTest(path=path.name):
                imports = _function_local_imports(path)
                self.assertEqual(
                    imports,
                    [],
                    f"{path.name} still has function-scoped imports: {imports}",
                )

    def test_analysis_data_notify_import_at_module_level(self):
        _install_stub_modules()
        for module_name in ("orca.analysis", "orca.data", "orca.notify"):
            sys.modules.pop(module_name, None)

        analysis = importlib.import_module("orca.analysis")
        data = importlib.import_module("orca.data")
        notify = importlib.import_module("orca.notify")

        self.assertTrue(callable(analysis.load_lessons))
        self.assertTrue(callable(data.load_market_data))
        self.assertTrue(callable(notify.send_message))


if __name__ == "__main__":
    unittest.main()
