# Contributing to PyDeadwood

## Workflow

1. Fork the repository and create a feature branch.
2. Make your change, keeping the project zero-dependency.
3. Run the full test suite: `python -m unittest discover -s tests -v`
4. Run the self-check: `python -m pydeadwood pydeadwood`
5. Open a pull request with a clear description of the behaviour change.

## Rules for new detection rules

- Every new rule needs a positive test (a case that must be reported)
  and a negative test (a case that must not be reported).
- Prefer a false negative over a false positive: when in doubt, do not
  report.
- Never add code that imports, executes, or modifies the scanned
  project. PyDeadwood reports only.

## Commit convention

Follow the Angular convention: `feat:`, `fix:`, `docs:`, `refactor:`,
`test:`, `chore:`, followed by a short imperative description, e.g.
`feat: add unused argument detection`.
