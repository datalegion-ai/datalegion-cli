# Vendored from datalegion-shared v0.4.116 (src/datalegion_shared/testing/conventions.py). Do not edit: re-copy it; the upgrade sweep diffs it.
"""The test-suite conventions every Data Legion repo holds, checked from a repo's tracked files.

1. Every test can fail: it asserts, raises or expects a raise (``pytest.raises``/``warns``, a mock
   ``assert_*``, ``fail``), itself or through a helper anywhere in the tests (``conftest.py``
   included, followed transitively). A test whose whole claim is that valid input runs says so in
   its name (``..._does_not_raise`` / ``..._do_not_raise``) and can fail by raising.
2. No test swallows an exception with ``except ...: pass``: it passes whatever happened.
3. No two tests share a body (decorators included): the second name's behavior goes untested.

Standard library only, and nothing else from datalegion_shared imports this or is imported here:
a consumer's standardization caches fingerprint every shared module its code imports, so this
module must stay outside that closure. Repos that don't depend on datalegion-shared vendor a
byte-identical copy of this file; the upgrade sweep diffs the copies against this one.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

TEST_FILES = ("*test_*.py", "*_test.py")
HELPER_FILES = ("*tests/*.py", "*conftest.py")
NO_RAISE_SUFFIXES = ("_does_not_raise", "_do_not_raise")


def _tracked(root: Path, patterns: tuple[str, ...]) -> dict[str, ast.Module]:
    names = subprocess.run(
        ["git", "ls-files", *patterns], cwd=root, capture_output=True, text=True, check=True
    ).stdout.split()
    return {
        name: ast.parse((root / name).read_text(encoding="utf-8")) for name in sorted(set(names))
    }


def _functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


Test = tuple[tuple[ast.ClassDef, ...], ast.FunctionDef | ast.AsyncFunctionDef]


def _tests(tree: ast.Module) -> list[Test]:
    """Return the tests pytest collects, each with the classes it sits in.

    Module-level ``test*`` and ``test*`` methods of ``Test*`` classes, a ``Test*`` class nested in
    one included. A ``test*`` function nested in a fixture or another function (a route handler named
    ``test_endpoint``) is no test.
    """
    found: list[Test] = []

    def collect(body: list[ast.stmt], classes: tuple[ast.ClassDef, ...]) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                collect(node.body, (*classes, node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test"):
                    found.append((classes, node))

    collect(tree.body, ())
    return found


def _where(name: str, classes: tuple[ast.ClassDef, ...], fn: ast.AST) -> str:
    """``file::Class::test``, so two same-named methods in two classes can be told apart."""
    return "::".join([name, *(cls.name for cls in classes), fn.name])


def _checks_directly(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, (ast.Assert, ast.Raise)):
            return True
        if isinstance(node, (ast.With, ast.AsyncWith)) and any(
            re.search(r"\b(raises|warns)\(", ast.unparse(item.context_expr)) for item in node.items
        ):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr.startswith("assert") or node.func.attr == "fail":
                return True
    return False


def _called_names(fn: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def silent_tests(
    root: Path, tests: tuple[str, ...] = TEST_FILES, helpers: tuple[str, ...] = HELPER_FILES
) -> list[str]:
    """Return every test that can't fail: no assertion or raise, itself or through a helper."""
    trees = _tracked(root, tests)
    by_name = {
        fn.name: fn
        for tree in [*_tracked(root, helpers).values(), *trees.values()]
        for fn in _functions(tree)
        if not fn.name.startswith("test")
    }
    checking = {name for name, fn in by_name.items() if _checks_directly(fn)}
    while more := {n for n, fn in by_name.items() if _called_names(fn) & checking} - checking:
        checking |= more  # a helper calling a checking helper checks too
    return [
        _where(name, classes, fn)
        for name, tree in trees.items()
        for classes, fn in _tests(tree)
        if not _checks_directly(fn)
        and not (_called_names(fn) & checking)
        and not fn.name.endswith(NO_RAISE_SUFFIXES)
    ]


def swallowing_tests(root: Path, tests: tuple[str, ...] = TEST_FILES) -> list[str]:
    """Return every ``except ...: pass`` inside a test, as ``file::Class::test:line``."""
    found = []
    for name, tree in _tracked(root, tests).items():
        for classes, fn in _tests(tree):
            for node in ast.walk(fn):
                if isinstance(node, ast.Try) and any(
                    all(
                        isinstance(stmt, ast.Pass)
                        or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
                        for stmt in handler.body
                    )
                    for handler in node.handlers
                ):
                    found.append(f"{_where(name, classes, fn)}:{node.lineno}")
    return found


def _self_members_used(fn: ast.AST, cls: ast.ClassDef | None) -> list[ast.AST]:
    """Return the definitions of the ``self.X`` members a method uses, from its own class."""
    if cls is None:
        return []
    used = {
        n.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self"
    }
    members = []
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in used:
            members.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
            isinstance(t, ast.Name) and t.id in used
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
        ):
            members.append(node)
    return members


def duplicate_test_bodies(root: Path, tests: tuple[str, ...] = TEST_FILES) -> list[list[str]]:
    """Return groups of tests with one body (decorators included, docstrings ignored).

    A method's body includes the definitions of the ``self`` helpers it calls: twin person and
    company test classes share bodies but call their own ``self._slot``, so they test different
    code and are no duplicates.
    """
    by_body: dict[str, list[str]] = {}
    for name, tree in _tracked(root, tests).items():
        for classes, fn in _tests(tree):
            body = fn.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]
            used = _self_members_used(fn, classes[-1] if classes else None)
            key = ast.dump(ast.Module(body=[*fn.decorator_list, *body, *used], type_ignores=[]))
            by_body.setdefault(key, []).append(_where(name, classes, fn))
    return [names for names in by_body.values() if len(names) > 1]
