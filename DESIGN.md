# PyDeadwood Design Notes

## Goal

Give Python projects a fast, safe, zero-dependency way to find dead
code, usable as a CI gate, without ever executing the scanned code.

## Why AST-only analysis

Executing code to prove reachability is slow, needs the project's full
dependency environment, and is unsafe on untrusted code. AST analysis
is fast, offline, and safe. The trade-off is accepted explicitly: names
that are only reachable dynamically (reflection, plugins, string-built
names) are invisible, so the tool is conservative — a name referenced
anywhere counts as used.

## Pipeline

1. **Collect** — expand paths to `.py` files, skipping environment and
   build directories (`.git`, `__pycache__`, `venv`, `build`, `dist`…).
2. **Parse** — one `ast.parse` per file. A file that fails to parse
   becomes a `parse-error` finding instead of disappearing silently.
3. **Gather facts per file** — top-level functions/classes, methods,
   imports (with aliases), `__all__` re-exports, and every `Name` /
   `Attribute` reference.
4. **Decide project-wide** — unused imports use file-local references;
   unused functions/classes/methods use project-wide reference sets, so
   cross-file use counts.
5. **Scan blocks** — every statement list is checked for statements
   after a terminating statement, and every `If`/`While` node is
   checked for a constant boolean test.
6. **Sort** — findings are sorted by file, line, kind, and name, so
   output is deterministic across runs.

## Exemption policy

Exemptions exist to keep the false-positive rate low where static
analysis structurally cannot see the call:

- `__all__` names: the author explicitly declared them public.
- Dunder methods and `main`: called by the runtime or by convention.
- Test functions/classes and lifecycle methods: called by test runners.
- Star imports and `__future__` imports: not inferable / compiler
  directives.
- Methods of an unused class: the class finding already covers them.

## What is deliberately out of scope for v1.0

- Unused module-level variables and unused parameters (planned, off
  by default, because both are noisier).
- Any automatic fixing or deletion.
- Type-aware or data-flow analysis; names are matched textually.
