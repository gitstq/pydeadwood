"""Command-line interface for PyDeadwood.

Exit codes
----------
* ``0`` -- no findings at or above the ``--fail-on`` threshold.
* ``1`` -- findings were found.
* ``2`` -- usage error, e.g. a scanned path does not exist.

PyDeadwood only reports; it never modifies or deletes scanned code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import analyze, summarize

FAIL_ON_KINDS = {
    "any": None,  # any finding fails
    "unused": {
        "unused-import",
        "unused-function",
        "unused-class",
        "unused-method",
    },
    "unreachable": {"unreachable-code", "dead-branch"},
    "none": set(),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pydeadwood",
        description=(
            "Find dead code in Python projects (unused imports, "
            "functions, classes and methods, unreachable code, "
            "constant dead branches) without running the code."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="files or directories to scan (default: current directory)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="skip files/directories matching this glob (repeatable)",
    )
    parser.add_argument(
        "--ignore-names",
        action="append",
        default=[],
        metavar="PATTERN",
        help="never report names matching this glob (repeatable)",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="also report test functions/classes (excluded by default)",
    )
    parser.add_argument(
        "--fail-on",
        choices=sorted(FAIL_ON_KINDS),
        default="any",
        help="which finding kinds make the exit code 1 (default: any)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def _render_text(findings) -> str:
    if not findings:
        return "No dead code found."
    lines: list[str] = []
    current_file = None
    for finding in findings:
        if finding.file != current_file:
            current_file = finding.file
            lines.append(f"\n{current_file}")
        name = f" {finding.name}" if finding.name else ""
        lines.append(
            f"  {finding.line}:{finding.severity} "
            f"{finding.kind}{name} -- {finding.message}"
        )
    summary = summarize(findings)
    breakdown = ", ".join(
        f"{count} {kind}" for kind, count in sorted(summary["by_kind"].items())
    )
    lines.append(f"\nFound {summary['total']} finding(s): {breakdown}")
    return "\n".join(lines)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    missing = [p for p in args.paths if not Path(p).exists()]
    if missing:
        print(
            f"pydeadwood: path not found: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    findings = analyze(
        args.paths,
        exclude=args.exclude,
        ignore_names=args.ignore_names,
        include_tests=args.include_tests,
    )
    if args.format == "json":
        payload = {
            "summary": summarize(findings),
            "findings": [finding.to_dict() for finding in findings],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_render_text(findings))
    failing_kinds = FAIL_ON_KINDS[args.fail_on]
    if failing_kinds is None:
        failed = bool(findings)
    else:
        failed = any(f.kind in failing_kinds for f in findings)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
