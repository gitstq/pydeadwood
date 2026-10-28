"""Core analysis engine for PyDeadwood.

Analysis is deliberately conservative: a name is only reported as unused
when it is never referenced anywhere in the scanned project. That keeps
false positives low at the cost of occasionally missing dead code that
shares a name with live code. PyDeadwood reports; it never deletes code.

Scope of one analysis run
-------------------------
* Unused imports (``import x`` / ``from m import y``, including aliases).
  Star imports (``from m import *``) are never reported: their names
  cannot be known from the importing file alone.
* Unused top-level functions and classes.
* Unused methods (a method counts as used when its name is ever used
  as an attribute, e.g. ``obj.method()`` or ``self.method``).
* Unreachable statements after ``return`` / ``raise`` / ``break`` /
  ``continue`` in the same block.
* Constant dead branches: ``if False: ...``, the ``else`` of
  ``if True: ...``, and ``while False: ...``.
* Files that fail to parse, reported as ``parse-error`` findings so a
  broken file never silently disappears from the report.

Exemptions (never reported)
----------------------------
* Names listed in the same file's ``__all__`` (public re-exports).
* Dunder names (``__init__``, ``__str__``, ...), ``main`` entry points,
  and unittest-style lifecycle methods (``setUp``, ``tearDown``, ...).
* Test functions (``test_*``) and test classes (``Test*``), unless
  ``include_tests`` is set: a test runner calls them without any
  textual reference in the scanned code.
* Names matching an ``ignore_names`` glob pattern.
"""

from __future__ import annotations

import ast
import fnmatch
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

__all__ = ["Finding", "analyze", "collect_py_files", "summarize"]

# Directories that are never scanned, even when given explicitly as a
# sub-path is not special-cased: these are build / environment artefacts.
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    ".eggs",
}

LIFECYCLE_METHODS = {
    "setUp",
    "tearDown",
    "setUpClass",
    "tearDownClass",
    "setUpModule",
    "tearDownModule",
}

SEVERITY = {
    "unused-import": "warning",
    "unused-function": "warning",
    "unused-class": "warning",
    "unused-method": "warning",
    "unreachable-code": "error",
    "dead-branch": "error",
    "parse-error": "error",
}


@dataclass(frozen=True)
class Finding:
    """One dead-code finding."""

    kind: str
    file: str
    line: int
    name: str
    message: str
    severity: str = "warning"

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class _Definition:
    kind: str  # "function" | "class" | "method"
    name: str
    line: int
    class_name: str | None = None


@dataclass
class _Import:
    name: str
    line: int
    display: str  # e.g. "os" or "from pathlib import Path"


@dataclass
class _FileFacts:
    path: Path
    display: str
    tree: ast.AST | None
    parse_error: str | None
    definitions: list[_Definition]
    imports: list[_Import]
    public_names: set[str]
    name_uses: set[str]
    attribute_uses: set[str]


def _is_test_name(name: str, kind: str) -> bool:
    if kind in ("function", "method") and name.startswith("test_"):
        return True
    if kind == "class" and name.startswith("Test"):
        return True
    return False


def _iter_blocks(node: ast.AST) -> Iterator[list[ast.stmt]]:
    """Yield every statement list in a tree (bodies, else, finally...)."""
    for child in ast.walk(node):
        for attr in ("body", "orelse", "finalbody"):
            value = getattr(child, attr, None)
            if isinstance(value, list) and value and all(
                isinstance(item, ast.stmt) for item in value
            ):
                yield value
        # ExceptHandler bodies are covered by the walk itself, since
        # ast.walk visits handler nodes and their "body" attribute.


def _collect_facts(path: Path, display: str) -> _FileFacts:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:  # unreadable file
        return _FileFacts(
            path=path,
            display=display,
            tree=None,
            parse_error=str(exc),
            definitions=[],
            imports=[],
            public_names=set(),
            name_uses=set(),
            attribute_uses=set(),
        )
    try:
        tree = ast.parse(source, filename=display)
    except SyntaxError as exc:
        return _FileFacts(
            path=path,
            display=display,
            tree=None,
            parse_error=f"{exc.msg} (line {exc.lineno})",
            definitions=[],
            imports=[],
            public_names=set(),
            name_uses=set(),
            attribute_uses=set(),
        )

    definitions: list[_Definition] = []
    imports: list[_Import] = []
    public_names: set[str] = set()
    name_uses: set[str] = set()
    attribute_uses: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            name_uses.add(node.id)
        elif isinstance(node, ast.Attribute):
            attribute_uses.add(node.attr)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions.append(
                _Definition("function", node.name, node.lineno)
            )
        elif isinstance(node, ast.ClassDef):
            definitions.append(_Definition("class", node.name, node.lineno))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    definitions.append(
                        _Definition(
                            "method", item.name, item.lineno, node.name
                        )
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                imports.append(
                    _Import(bound, node.lineno, f"import {alias.name}")
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue  # compiler directive, never "used" as a name
            if node.module is None and not node.names:
                continue
            if any(alias.name == "*" for alias in node.names):
                continue  # star import: names unknown, never reported
            for alias in node.names:
                bound = alias.asname or alias.name
                module = node.module or ""
                imports.append(
                    _Import(
                        bound,
                        node.lineno,
                        f"from {module} import {alias.name}",
                    )
                )
        elif isinstance(node, ast.Assign):
            # __all__ = ["name", ...] marks a public re-export.
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for element in node.value.elts:
                            if isinstance(element, ast.Constant) and isinstance(
                                element.value, str
                            ):
                                public_names.add(element.value)

    return _FileFacts(
        path=path,
        display=display,
        tree=tree,
        parse_error=None,
        definitions=definitions,
        imports=imports,
        public_names=public_names,
        name_uses=name_uses,
        attribute_uses=attribute_uses,
    )


def collect_py_files(paths: Iterable[str | os.PathLike]) -> list[Path]:
    """Expand paths to a sorted, de-duplicated list of ``.py`` files."""
    found: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        path = Path(raw)
        candidates: Iterator[Path]
        if path.is_dir():
            candidates = path.rglob("*.py")
        elif path.is_file():
            candidates = iter([path])
        else:
            continue  # missing paths are reported by the CLI layer
        for candidate in candidates:
            if any(part in SKIP_DIRS for part in candidate.parts):
                continue
            resolved = candidate.resolve()
            if resolved not in seen and candidate.suffix == ".py":
                seen.add(resolved)
                found.append(candidate)
    return sorted(found)


def _matches_any(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def _excluded(display: str, exclude: Sequence[str]) -> bool:
    if not exclude:
        return False
    parts = Path(display).parts
    return any(
        fnmatch.fnmatchcase(display, pattern)
        or any(fnmatch.fnmatchcase(part, pattern) for part in parts)
        for pattern in exclude
    )


def analyze(
    paths: Iterable[str | os.PathLike],
    *,
    exclude: Sequence[str] = (),
    ignore_names: Sequence[str] = (),
    include_tests: bool = False,
) -> list[Finding]:
    """Analyse the given files/directories and return sorted findings."""
    files = collect_py_files(paths)
    facts_list = []
    for path in files:
        display = str(path)
        if _excluded(display, exclude):
            continue
        facts_list.append(_collect_facts(path, display))

    all_name_uses: set[str] = set()
    all_attribute_uses: set[str] = set()
    for facts in facts_list:
        all_name_uses |= facts.name_uses
        all_attribute_uses |= facts.attribute_uses

    findings: list[Finding] = []
    for facts in facts_list:
        if facts.tree is None:
            findings.append(
                Finding(
                    kind="parse-error",
                    file=facts.display,
                    line=1,
                    name="",
                    message=f"could not parse file: {facts.parse_error}",
                    severity=SEVERITY["parse-error"],
                )
            )
            continue

        # --- unused imports (file-local reasoning) ---
        for imp in facts.imports:
            if imp.name in facts.public_names:
                continue
            if _matches_any(imp.name, ignore_names):
                continue
            if imp.name not in facts.name_uses:
                findings.append(
                    Finding(
                        kind="unused-import",
                        file=facts.display,
                        line=imp.line,
                        name=imp.name,
                        message=f"unused import: {imp.display}",
                        severity=SEVERITY["unused-import"],
                    )
                )

        # --- unused definitions (project-wide reasoning) ---
        unused_classes = {
            d.name
            for d in facts.definitions
            if d.kind == "class"
            and d.name not in all_name_uses
            and d.name not in facts.public_names
            and not d.name.startswith("__")
            and not _matches_any(d.name, ignore_names)
            and (include_tests or not _is_test_name(d.name, "class"))
        }
        for definition in facts.definitions:
            name = definition.name
            if _matches_any(name, ignore_names):
                continue
            if name in facts.public_names:
                continue
            if name.startswith("__") and name.endswith("__"):
                continue
            if name == "main":
                continue
            if not include_tests and _is_test_name(
                name, definition.kind
            ):
                continue
            if definition.kind == "function":
                if name not in all_name_uses:
                    findings.append(
                        Finding(
                            kind="unused-function",
                            file=facts.display,
                            line=definition.line,
                            name=name,
                            message=f"unused function: {name}()",
                            severity=SEVERITY["unused-function"],
                        )
                    )
            elif definition.kind == "class":
                if name in unused_classes:
                    findings.append(
                        Finding(
                            kind="unused-class",
                            file=facts.display,
                            line=definition.line,
                            name=name,
                            message=f"unused class: {name}",
                            severity=SEVERITY["unused-class"],
                        )
                    )
            elif definition.kind == "method":
                if definition.class_name in unused_classes:
                    continue  # the class finding already covers it
                if name in LIFECYCLE_METHODS:
                    continue
                if name not in all_attribute_uses:
                    findings.append(
                        Finding(
                            kind="unused-method",
                            file=facts.display,
                            line=definition.line,
                            name=name,
                            message=(
                                f"unused method: "
                                f"{definition.class_name}.{name}()"
                            ),
                            severity=SEVERITY["unused-method"],
                        )
                    )

        # --- unreachable code and constant dead branches ---
        assert facts.tree is not None
        for block in _iter_blocks(facts.tree):
            terminated = False
            for stmt in block:
                if terminated:
                    findings.append(
                        Finding(
                            kind="unreachable-code",
                            file=facts.display,
                            line=stmt.lineno,
                            name="",
                            message=(
                                "unreachable statement after "
                                "return/raise/break/continue"
                            ),
                            severity=SEVERITY["unreachable-code"],
                        )
                    )
                if isinstance(
                    stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)
                ):
                    terminated = True
        for node in ast.walk(facts.tree):
            if isinstance(node, ast.If) and isinstance(
                node.test, ast.Constant
            ):
                if node.test.value is False and node.body:
                    findings.append(
                        Finding(
                            kind="dead-branch",
                            file=facts.display,
                            line=node.lineno,
                            name="",
                            message="branch never runs: if False:",
                            severity=SEVERITY["dead-branch"],
                        )
                    )
                elif node.test.value is True and node.orelse:
                    findings.append(
                        Finding(
                            kind="dead-branch",
                            file=facts.display,
                            line=node.lineno,
                            name="",
                            message="branch never runs: else of if True:",
                            severity=SEVERITY["dead-branch"],
                        )
                    )
            elif isinstance(node, ast.While) and isinstance(
                node.test, ast.Constant
            ):
                if node.test.value is False and node.body:
                    findings.append(
                        Finding(
                            kind="dead-branch",
                            file=facts.display,
                            line=node.lineno,
                            name="",
                            message="branch never runs: while False:",
                            severity=SEVERITY["dead-branch"],
                        )
                    )

    findings.sort(key=lambda f: (f.file, f.line, f.kind, f.name))
    return findings


def summarize(findings: Sequence[Finding]) -> dict:
    """Return ``{"total": n, "by_kind": {...}, "by_severity": {...}}``."""
    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for finding in findings:
        by_kind[finding.kind] = by_kind.get(finding.kind, 0) + 1
        by_severity[finding.severity] = (
            by_severity.get(finding.severity, 0) + 1
        )
    return {
        "total": len(findings),
        "by_kind": by_kind,
        "by_severity": by_severity,
    }
