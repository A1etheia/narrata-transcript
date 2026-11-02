import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

import transcript
from transcript.__main__ import main

REPO_ROOT = Path(__file__).resolve().parent.parent


def run(*argv: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class SmokeTest(unittest.TestCase):
    def test_package_exposes_a_version(self) -> None:
        self.assertTrue(transcript.__version__)

    def test_help_exits_successfully(self) -> None:
        stdout = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            self.assertRaises(SystemExit) as caught,
        ):
            main(["--help"])

        self.assertEqual(caught.exception.code, 0)
        self.assertIn("usage: transcript", stdout.getvalue())

    def test_no_command_still_prints_help(self) -> None:
        code, stdout, _ = run()

        self.assertEqual(code, 0)
        self.assertIn("usage: transcript", stdout)


class ConfigCommandTest(unittest.TestCase):
    def test_shows_values_from_the_example_file(self) -> None:
        code, stdout, _ = run(
            "config", "--config", str(REPO_ROOT / "config" / "example.yaml")
        )

        self.assertEqual(code, 0)
        self.assertIn("language: de", stdout)

    def test_missing_required_value_is_reported_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("language: de\n", encoding="utf-8")

            code, stdout, stderr = run("config", "--config", str(path))

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("missing required key: paths.root", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_missing_default_file_points_to_the_example(self) -> None:
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                code, _, stderr = run("config")
            finally:
                os.chdir(previous)

        self.assertEqual(code, 2)
        self.assertIn("config/example.yaml", stderr)


if __name__ == "__main__":
    unittest.main()
