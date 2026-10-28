"""Test suite for PyDeadwood.

Every test builds its own throwaway project in a temporary directory,
so the suite never depends on the repository it lives in.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydeadwood.cli import main as cli_main  # noqa: E402
from pydeadwood.core import analyze, summarize  # noqa: E402


def kinds(findings):
    return [(f.kind, f.name) for f in findings]


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def scan(self, **kwargs):
        return analyze([str(self.root)], **kwargs)


class TestUnusedImports(ProjectCase):
    def test_unused_import_reported(self):
        self.write("a.py", "import os\n\nx = 1\n")
        found = [f for f in self.scan() if f.kind == "unused-import"]
        self.assertEqual([(f.name, f.line) for f in found], [("os", 1)])

    def test_used_import_not_reported(self):
        self.write("a.py", "import os\n\nprint(os.getcwd())\n")
        self.assertEqual(
            [f for f in self.scan() if f.kind == "unused-import"], []
        )

    def test_alias_and_from_import(self):
        self.write(
            "a.py",
            "import os as operating\nfrom pathlib import Path, PurePath\n"
            "print(PurePath('.'))\n",
        )
        names = sorted(
            f.name for f in self.scan() if f.kind == "unused-import"
        )
        self.assertEqual(names, ["Path", "operating"])

    def test_future_import_never_reported(self):
        self.write("a.py", "from __future__ import annotations\n")
        self.assertEqual(
            [f for f in self.scan() if f.kind == "unused-import"], []
        )

    def test_star_import_never_reported(self):
        self.write("a.py", "from os import *\n")
        self.assertEqual(
            [f for f in self.scan() if f.kind == "unused-import"], []
        )

    def test_reexport_via_all_not_reported(self):
        self.write("a.py", 'from os import path\n__all__ = ["path"]\n')
        self.assertEqual(
            [f for f in self.scan() if f.kind == "unused-import"], []
        )


class TestUnusedDefinitions(ProjectCase):
    def test_unused_top_level_function(self):
        self.write("a.py", "def lonely():\n    return 1\n")
        self.assertIn(
            ("unused-function", "lonely"), kinds(self.scan())
        )

    def test_called_function_not_reported(self):
        self.write("a.py", "def helper():\n    return 1\n\nprint(helper())\n")
        self.assertNotIn(
            ("unused-function", "helper"), kinds(self.scan())
        )

    def test_cross_file_use_counts(self):
        self.write("a.py", "def shared():\n    return 1\n")
        self.write("b.py", "from a import shared\nprint(shared())\n")
        self.assertNotIn(
            ("unused-function", "shared"), kinds(self.scan())
        )

    def test_unused_class_and_its_methods_suppressed(self):
        self.write(
            "a.py",
            "class Orphan:\n    def do(self):\n        return 1\n",
        )
        found = kinds(self.scan())
        self.assertIn(("unused-class", "Orphan"), found)
        self.assertNotIn(("unused-method", "do"), found)

    def test_unused_method_of_used_class(self):
        self.write(
            "a.py",
            "class Worker:\n"
            "    def run(self):\n        return 1\n"
            "    def idle(self):\n        return 2\n"
            "\nprint(Worker().run())\n",
        )
        found = kinds(self.scan())
        self.assertIn(("unused-method", "idle"), found)
        self.assertNotIn(("unused-method", "run"), found)

    def test_dunder_and_main_exempt(self):
        self.write(
            "a.py",
            "class Thing:\n"
            "    def __str__(self):\n        return 'x'\n"
            "\ndef main():\n    pass\n",
        )
        # Thing itself is unused and reported; its dunder is not.
        found = kinds(self.scan())
        self.assertIn(("unused-class", "Thing"), found)
        self.assertNotIn(("unused-method", "__str__"), found)
        self.assertNotIn(("unused-function", "main"), found)

    def test_test_functions_exempt_by_default(self):
        self.write("test_a.py", "def test_something():\n    assert True\n")
        self.assertEqual(self.scan(), [])
        included = self.scan(include_tests=True)
        self.assertIn(("unused-function", "test_something"), kinds(included))

    def test_lifecycle_methods_exempt(self):
        self.write(
            "a.py",
            "import unittest\n"
            "class Suite(unittest.TestCase):\n"
            "    def setUp(self):\n        pass\n"
            "\nprint(Suite)\n",
        )
        self.assertNotIn(("unused-method", "setUp"), kinds(self.scan()))

    def test_all_exempts_public_function(self):
        self.write("a.py", 'def api():\n    return 1\n\n__all__ = ["api"]\n')
        self.assertNotIn(("unused-function", "api"), kinds(self.scan()))


class TestUnreachableAndDeadBranches(ProjectCase):
    def test_code_after_return(self):
        self.write(
            "a.py",
            "def f():\n    return 1\n    print('never')\n",
        )
        found = [f for f in self.scan() if f.kind == "unreachable-code"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].line, 3)

    def test_code_after_raise_and_break(self):
        self.write(
            "a.py",
            "def f():\n    raise ValueError()\n    x = 1\n"
            "while True:\n    break\n    y = 2\n",
        )
        found = [f for f in self.scan() if f.kind == "unreachable-code"]
        self.assertEqual(len(found), 2)

    def test_if_false_and_while_false(self):
        self.write(
            "a.py",
            "if False:\n    x = 1\n"
            "if True:\n    y = 2\nelse:\n    z = 3\n"
            "while False:\n    w = 4\n",
        )
        found = [f for f in self.scan() if f.kind == "dead-branch"]
        self.assertEqual(len(found), 3)

    def test_normal_branches_not_reported(self):
        self.write("a.py", "if x:\n    a = 1\nelse:\n    b = 2\n")
        self.assertEqual(
            [f for f in self.scan() if f.kind == "dead-branch"], []
        )


class TestRobustnessAndOptions(ProjectCase):
    def test_syntax_error_is_a_finding_not_a_crash(self):
        self.write("broken.py", "def broken(:\n")
        found = [f for f in self.scan() if f.kind == "parse-error"]
        self.assertEqual(len(found), 1)

    def test_exclude_pattern(self):
        self.write("gen/generated.py", "import os\n")
        self.write("keep.py", "import sys\n")
        found = self.scan(exclude=["gen"])
        self.assertEqual(
            [f.name for f in found if f.kind == "unused-import"], ["sys"]
        )

    def test_ignore_names_glob(self):
        self.write("a.py", "import os\nimport sys\n")
        found = self.scan(ignore_names=["o*"])
        self.assertEqual(
            [f.name for f in found if f.kind == "unused-import"], ["sys"]
        )

    def test_summary_counts(self):
        self.write("a.py", "import os\n\ndef lonely():\n    return 1\n")
        summary = summarize(self.scan())
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["by_kind"]["unused-import"], 1)
        self.assertEqual(summary["by_kind"]["unused-function"], 1)


class TestCli(ProjectCase):
    def _run_cli(self, *args):
        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli_main(list(args))
        return code, buffer.getvalue()

    def test_cli_clean_project_exits_zero(self):
        self.write("a.py", "import os\nprint(os.getcwd())\n")
        code, out = self._run_cli(str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("No dead code found", out)

    def test_cli_findings_exit_one(self):
        self.write("a.py", "import os\n")
        code, out = self._run_cli(str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("unused-import", out)

    def test_cli_json_output(self):
        self.write("a.py", "import os\n")
        code, out = self._run_cli(str(self.root), "--format", "json")
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["findings"][0]["kind"], "unused-import")

    def test_cli_fail_on_none_exits_zero(self):
        self.write("a.py", "import os\n")
        code, _ = self._run_cli(str(self.root), "--fail-on", "none")
        self.assertEqual(code, 0)

    def test_cli_missing_path_exits_two(self):
        code, _ = self._run_cli(str(self.root / "does-not-exist"))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
