# 🪵 PyDeadwood — Python Dead Code Scanner

> Find the parts of your code nobody uses, without running your code.

English · [繁體中文](README.zh-TW.md) · [简体中文](README.md)

PyDeadwood is a zero-dependency Python dead code scanner. It parses code
with the standard library `ast` module and **never imports or executes
the code it scans**, so it is safe to run even on untrusted code. It
finds unused imports, functions, classes, and methods, unreachable code
after `return`, and constant dead branches such as `if False:`, and
reports them as human-readable text or JSON for CI.

## ✨ Key Features

- 🔍 **Unused import detection**: `import` / `from … import`, including
  aliases; star imports are never falsely reported
- 🧩 **Unused definition detection**: top-level functions, classes, and
  methods, with cross-file references counted as "used"
- 🚫 **Unreachable code detection**: statements after `return` /
  `raise` / `break` / `continue` in the same block
- 🌿 **Constant dead branch detection**: `if False:`, the `else` of
  `if True:`, and `while False:`
- 🛡️ **Report only, never delete**: no file is modified; deleting code
  is always a human decision
- 🧪 **Low false-positive exemptions**: `__all__` re-exports, dunder
  methods, `main`, test functions, and lifecycle methods such as
  `setUp`/`tearDown` are excluded by default
- 📄 **Two output formats**: readable text and machine-readable JSON,
  with exit codes suitable for CI gates
- 🪶 **Zero dependencies**: standard library only, Python ≥ 3.9

## 🚀 Quick Start

```bash
# No third-party dependencies to install
git clone https://github.com/gitstq/pydeadwood.git
cd pydeadwood

# Scan the current directory
python -m pydeadwood .

# Scan a project and output JSON
python -m pydeadwood path/to/your/project --format json

# Try the bundled example (expect 6 findings, one of each kind)
python -m pydeadwood examples/sample_project
```

Install as a command-line tool (optional):

```bash
pip install .
pydeadwood --help
```

## 📖 Detailed Usage Guide

### Basic usage

```bash
pydeadwood [paths ...] [options]
```

With no path, the current directory is scanned. Multiple files or
directories may be given; directories are scanned recursively, and
`.git`, `__pycache__`, `venv`, `.venv`, `build`, and `dist` are skipped
automatically.

### Options

| Option | Description |
| --- | --- |
| `--format text\|json` | Output format, default `text` |
| `--exclude PATTERN` | Skip files/directories matching this glob (repeatable) |
| `--ignore-names PATTERN` | Never report names matching this glob (repeatable) |
| `--include-tests` | Also report test functions/classes (excluded by default, since test runners do not call them through textual references) |
| `--fail-on any\|unused\|unreachable\|none` | Which findings make the exit code 1, default `any` |
| `--version` | Show the version |

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | No findings at or above the `--fail-on` threshold |
| `1` | Dead code was found |
| `2` | Usage error, e.g. a scanned path does not exist |

### CI examples

```bash
# Only unreachable code and dead branches fail the build;
# unused imports are reported but tolerated
pydeadwood src --fail-on unreachable

# Strict mode: any finding fails
pydeadwood src --fail-on any
```

### JSON output structure

```bash
pydeadwood src --format json
```

```json
{
  "summary": {
    "total": 2,
    "by_kind": {"unused-import": 1, "unused-function": 1},
    "by_severity": {"warning": 2}
  },
  "findings": [
    {
      "kind": "unused-import",
      "file": "src/a.py",
      "line": 1,
      "name": "os",
      "message": "unused import: import os",
      "severity": "warning"
    }
  ]
}
```

### Finding kinds and severities

| Kind | Severity | Meaning |
| --- | --- | --- |
| `unused-import` | warning | Import never used in its file |
| `unused-function` | warning | Top-level function never referenced in the project |
| `unused-class` | warning | Class never referenced in the project (its methods are not reported again) |
| `unused-method` | warning | Method never used as an attribute |
| `unreachable-code` | error | Statement in the same block after a terminating statement |
| `dead-branch` | error | Constant branch that can never run |
| `parse-error` | error | File that could not be parsed (never silently skipped) |

### Decision rules (deliberately conservative)

- A name referenced anywhere in the project counts as used. PyDeadwood
  prefers false negatives over false positives.
- A method counts as used when its name ever appears as an attribute
  (e.g. `obj.run()`, `self.run`).
- Methods of an unused class are not reported separately, to avoid
  duplicating one piece of dead code.
- `from … import *` and `from __future__ import …` are never reported:
  star-imported names cannot be inferred from the importing file, and
  `__future__` imports are compiler directives.
- Dynamic calls (`getattr`, reflection, plugin registration, names
  built from strings) are invisible to static analysis — exempt such
  names with `--ignore-names` or declare them in `__all__`.

## 🧠 Design Rationale and Iteration Plan

### Why static analysis only

Running target code would confirm whether something is called, but it
is slow and unsafe. PyDeadwood uses pure AST analysis instead: fast,
offline, and safe on untrusted code, at the deliberate cost of
conservative false negatives.

### Architecture

| Module | Responsibility |
| --- | --- |
| 🧠 `pydeadwood/core.py` | AST collection, cross-file reference counting, the seven finding rules, deterministic sorting |
| 💻 `pydeadwood/cli.py` | Argument parsing, text/JSON rendering, exit codes |
| 🧪 `tests/` | 28 unit tests, each building its own throwaway project in a temporary directory |

### Iteration plan

- [ ] v1.1: Report unused module-level variables and unused parameters
  (off by default, to avoid noise)
- [ ] v1.2: `--fix` that removes only unused imports (never functions
  or classes), printing a diff for confirmation first
- [ ] v1.3: Configuration in `pyproject.toml` under `[tool.pydeadwood]`
- [ ] v1.4: Per-file/directory summaries and a baseline file so only
  newly introduced dead code is reported

## 📦 Packaging and Deployment Guide

PyDeadwood is a tool/library project and therefore **ships without a
Release**. Install and use it as follows:

```bash
# Option 1: install from source
pip install .

# Option 2: run from source without installing
python -m pydeadwood <path>

# Option 3: use it as a library
python - <<'PY'
from pydeadwood import analyze
for finding in analyze(["src"]):
    print(finding.file, finding.line, finding.kind, finding.name)
PY
```

### Requirements

- Python ≥ 3.9
- No third-party dependencies
- macOS, Linux, and Windows are supported

### Local development and self-check

```bash
python -m unittest discover -s tests -v
python -m pydeadwood pydeadwood   # self-check, should print No dead code found.
```

## 🤝 Contributing Guide

Issues and pull requests are welcome:

1. Fork the repository and create a feature branch.
2. Make sure `python -m unittest discover -s tests -v` passes.
3. A new detection rule must come with both a positive test (should
   report) and a negative test (should not report).
4. Keep the zero-dependency and report-only principles.
5. Follow the Angular commit convention, e.g.
   `feat: add unused argument detection`.

## 📄 License

This project is licensed under the [MIT](LICENSE) license.
