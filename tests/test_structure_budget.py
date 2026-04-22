"""Structure budget tests: prevent architectural drift.

These tests guard the repository structure after the P2 refactors:
- No new module-level import cycles across orca/ and jackal/
- Explicit file-size budgets for known large modules
- Default budget for new modules
- Critical import-direction constraints stay intact

If any test fails, a structural invariant has drifted and needs
explicit review before more code is added.

Reference: docs/analysis/2026-04-22_repository_review.md Section 6 P3-3
"""

from __future__ import annotations

import ast
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


FILE_SIZE_BUDGET = {
    # large by design
    "orca/state.py": 3900,
    "orca/backtest.py": 3200,
    "jackal/scanner.py": 1900,
    "jackal/hunter.py": 2050,
    "jackal/evolution.py": 1250,
    # post-refactor budgets
    "orca/analysis.py": 300,
    "orca/analysis_market.py": 520,
    "orca/analysis_review.py": 650,
    "orca/analysis_lessons.py": 450,
    "orca/analysis_patterns.py": 120,
    "orca/analysis_verification.py": 600,
    "orca/_analysis_common.py": 80,
    "jackal/quality_engine.py": 500,
    # default for all other source modules
    "__default__": 1000,
}


FORBIDDEN_IMPORT_PREFIXES = {
    "orca/analysis_market.py": ("orca.notify", "orca.analysis"),
    "orca/analysis_review.py": ("orca.notify", "orca.analysis"),
    "orca/analysis_lessons.py": ("orca.notify", "orca.analysis"),
    "orca/analysis_patterns.py": ("orca.notify", "orca.analysis"),
    "orca/analysis_verification.py": ("orca.notify", "orca.analysis"),
    "jackal/quality_engine.py": ("jackal.scanner",),
}


ALLOWED_LOCAL_IMPORTS = {
    "orca/_analysis_common.py": {"orca.paths"},
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _parse_module(path: Path) -> ast.Module:
    source = _read_text(path)
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise AssertionError(f"AST parse failed for {path.relative_to(ROOT).as_posix()}: {exc}") from exc


def _iter_source_files() -> list[Path]:
    files = []
    for pkg in ("orca", "jackal"):
        for path in (ROOT / pkg).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return sorted(files)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _module_name(path: Path) -> str:
    rel = _relative(path)
    if rel.endswith("/__init__.py"):
        return rel[:-12].replace("/", ".")
    return rel[:-3].replace("/", ".")


def _build_module_index() -> dict[str, dict]:
    index = {}
    for path in _iter_source_files():
        index[_module_name(path)] = {
            "path": path,
            "is_package": path.name == "__init__.py",
        }
    return index


def _iter_module_level_imports(tree: ast.AST):
    stack = [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def _resolve_from_base(module_name: str, is_package: bool, node: ast.ImportFrom) -> tuple[list[str], str]:
    package_parts = module_name.split(".") if is_package else module_name.split(".")[:-1]
    if node.level:
        drop = node.level - 1
        if drop > len(package_parts):
            return package_parts, ""
        package_parts = package_parts[: len(package_parts) - drop]
    base_parts = package_parts[:]
    if node.module:
        base_parts.extend(node.module.split("."))
    return package_parts, ".".join(base_parts)


def _collect_local_imports(path: Path, module_index: dict[str, dict]) -> set[str]:
    module_name = _module_name(path)
    is_package = module_index[module_name]["is_package"]
    tree = _parse_module(path)
    local_imports: set[str] = set()

    for node in _iter_module_level_imports(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported = alias.name
                if imported in module_index:
                    local_imports.add(imported)
        elif isinstance(node, ast.ImportFrom):
            _, base_module = _resolve_from_base(module_name, is_package, node)
            if base_module and base_module in module_index:
                local_imports.add(base_module)
            for alias in node.names:
                if alias.name == "*":
                    continue
                if base_module:
                    candidate = f"{base_module}.{alias.name}"
                else:
                    package_parts, _ = _resolve_from_base(module_name, is_package, node)
                    candidate = ".".join(package_parts + [alias.name])
                if candidate in module_index:
                    local_imports.add(candidate)

    return local_imports


def _build_import_graph(module_index: dict[str, dict]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for module_name, info in module_index.items():
        graph[module_name]
        for imported in _collect_local_imports(info["path"], module_index):
            graph[module_name].add(imported)
    return graph


def _canonical_cycle(cycle: list[str]) -> tuple[str, ...]:
    if cycle and cycle[0] == cycle[-1]:
        cycle = cycle[:-1]
    rotations = []
    for seq in (cycle, list(reversed(cycle))):
        for idx in range(len(seq)):
            rotations.append(tuple(seq[idx:] + seq[:idx]))
    return min(rotations)


def _find_cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    visited: set[str] = set()
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        visited.add(node)
        stack.append(node)
        on_stack.add(node)
        for neighbor in sorted(graph.get(node, ())):
            if neighbor not in visited:
                visit(neighbor)
            elif neighbor in on_stack:
                start = stack.index(neighbor)
                cycle = stack[start:] + [neighbor]
                canon = _canonical_cycle(cycle)
                if canon not in seen:
                    seen.add(canon)
                    cycles.append(canon)
        stack.pop()
        on_stack.remove(node)

    for node in sorted(graph):
        if node not in visited:
            visit(node)
    return cycles


class TestNoImportCycles(unittest.TestCase):
    def test_orca_and_jackal_have_no_module_level_cycles(self):
        module_index = _build_module_index()
        cycles = _find_cycles(_build_import_graph(module_index))
        rendered = [" -> ".join(cycle + (cycle[0],)) for cycle in cycles]
        self.assertEqual([], rendered, f"Import cycles detected:\n" + "\n".join(rendered))


class TestFileSizeBudget(unittest.TestCase):
    def test_explicit_budgets_cover_known_large_modules(self):
        violations = []
        default_budget = FILE_SIZE_BUDGET["__default__"]
        for path in _iter_source_files():
            rel = _relative(path)
            line_count = len(_read_text(path).splitlines())
            budget = FILE_SIZE_BUDGET.get(rel, default_budget)
            if line_count > budget:
                violations.append(f"{rel}: {line_count} > budget {budget}")
        self.assertEqual([], violations, "File size budget violations:\n" + "\n".join(violations))

    def test_new_or_unspecified_modules_stay_under_default_budget(self):
        default_budget = FILE_SIZE_BUDGET["__default__"]
        violations = []
        for path in _iter_source_files():
            rel = _relative(path)
            if rel in FILE_SIZE_BUDGET:
                continue
            line_count = len(_read_text(path).splitlines())
            if line_count > default_budget:
                violations.append(f"{rel}: {line_count} > default budget {default_budget}")
        self.assertEqual(
            [],
            violations,
            "New or unspecified modules exceeded the default budget:\n" + "\n".join(violations),
        )


class TestCriticalImportDirections(unittest.TestCase):
    def test_forbidden_import_prefixes_are_not_used(self):
        module_index = _build_module_index()
        violations = []
        for rel, forbidden_prefixes in FORBIDDEN_IMPORT_PREFIXES.items():
            path = ROOT / rel
            imported_modules = _collect_local_imports(path, module_index)
            for imported in sorted(imported_modules):
                for forbidden in forbidden_prefixes:
                    if imported == forbidden or imported.startswith(forbidden + "."):
                        violations.append(f"{rel}: imports {imported} (forbidden: {forbidden})")
        self.assertEqual([], violations, "Forbidden imports detected:\n" + "\n".join(violations))

    def test_analysis_common_stays_self_contained(self):
        module_index = _build_module_index()
        rel = "orca/_analysis_common.py"
        actual = _collect_local_imports(ROOT / rel, module_index)
        expected = ALLOWED_LOCAL_IMPORTS[rel]
        self.assertEqual(
            actual,
            expected,
            f"{rel} local imports drifted. Actual={sorted(actual)!r}, expected={sorted(expected)!r}",
        )


if __name__ == "__main__":
    unittest.main()
