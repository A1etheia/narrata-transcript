import contextlib
import io
import unittest

import transcript
from transcript.__main__ import main


class SmokeTest(unittest.TestCase):
    def test_package_exposes_a_version(self) -> None:
        self.assertTrue(transcript.__version__)

    def test_help_exits_successfully(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as caught:
            main(["--help"])

        self.assertEqual(caught.exception.code, 0)
        self.assertIn("usage: transcript", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
