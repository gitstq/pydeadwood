# PyDeadwood Test Report (2026-10-28)

## Result

- Command: `python -m unittest discover -s tests -v`
- Result: **28 tests passed, 0 failed**
- Self-check: `python -m pydeadwood pydeadwood` → `No dead code found.`
- Example check: `python -m pydeadwood examples/sample_project` →
  6 findings, one of each kind (`unused-import`, `unused-function`,
  `unused-class`, `unused-method`, `unreachable-code`, `dead-branch`),
  exit code 1 as designed.

## Coverage by area

| Area | Tests |
| --- | --- |
| Unused imports (plain, alias, from-import, star, `__future__`, `__all__` re-export) | 6 |
| Unused definitions (top-level, cross-file, class/method suppression, dunder/`main`, tests, lifecycle, `__all__`) | 9 |
| Unreachable code and constant dead branches | 4 |
| Robustness and options (parse error, exclude, ignore-names, summary) | 4 |
| CLI (clean exit 0, findings exit 1, JSON output, `--fail-on none`, missing path exit 2) | 5 |

## Notes

- Every test builds its own throwaway project in a temporary
  directory, so the suite never depends on the repository it lives in.
- One issue was found and fixed during development: `from __future__
  import annotations` was initially reported as an unused import.
  `__future__` imports are now exempt, with a dedicated regression
  test.
- A test-helper naming collision was also fixed: the helper was
  renamed from `run` to `scan` because `unittest.TestCase` already
  defines `run`.
