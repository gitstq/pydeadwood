"""Example file with several kinds of dead code for PyDeadwood to find.

Run from the repository root:

    python -m pydeadwood examples/sample_project
"""

import json  # unused import
import os  # used below


def forgotten_helper():
    """Never called anywhere in this example project."""
    return "nobody calls me"


def live_helper():
    """Called by main() below, so it is not reported."""
    return "alive"


class RetiredWidget:
    """Never instantiated anywhere."""

    def paint(self):
        return "paint"


class LiveWidget:
    """Used by main(); its unused method is still reported."""

    def draw(self):
        return "draw"

    def never_drawn(self):
        return "never"


def main():
    print(os.getcwd())
    print(live_helper())
    print(LiveWidget().draw())
    return 0
    print("this line is unreachable")


if __name__ == "__main__":
    raise SystemExit(main())


if False:
    print("this branch never runs")
