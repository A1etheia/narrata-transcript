import tempfile
import unittest
from pathlib import Path

from transcript.narrata_client import NarrataClientError, read_token

TOKEN = "12|made-up-token"  # stands in for a real token that must not leak


class ReadTokenTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dotenv = Path(directory.name) / ".env"

    def write(self, text: str) -> None:
        self.dotenv.write_text(text, encoding="utf-8")

    def assert_fails(self, expected: str, environ: dict[str, str]) -> None:
        with self.assertRaises(NarrataClientError) as caught:
            read_token(environ, self.dotenv)
        self.assertIn(expected, str(caught.exception))
        self.assertNotIn("made-up", str(caught.exception))

    def test_environment_wins_over_dotenv(self) -> None:
        self.write("NARRATA_TOKEN=from-file\n")

        self.assertEqual(read_token({"NARRATA_TOKEN": TOKEN}, self.dotenv), TOKEN)

    def test_dotenv_is_read_when_the_environment_has_none(self) -> None:
        for text in (
            f"NARRATA_TOKEN={TOKEN}\n",
            f"# comment\n\nOTHER=x\nexport NARRATA_TOKEN = {TOKEN}  \n",
            f'NARRATA_TOKEN="{TOKEN}"\n',
            f"NARRATA_TOKEN='{TOKEN}'\n",
        ):
            with self.subTest(text=text):
                self.write(text)

                self.assertEqual(read_token({"NARRATA_TOKEN": ""}, self.dotenv), TOKEN)

    def test_missing_token_points_to_the_example(self) -> None:
        for text in (None, "NARRATA_TOKEN=\n", "OTHER=x\n"):
            with self.subTest(text=text):
                if text is not None:
                    self.write(text)

                self.assert_fails("NARRATA_TOKEN is not set", {})
                self.assert_fails(".env.example", {})

    def test_malformed_line_is_named_by_number_only(self) -> None:
        self.write(f"OTHER=x\n{TOKEN}\n")

        self.assert_fails("line 2 is not KEY=VALUE", {})

    def test_example_file_holds_no_token(self) -> None:
        example = Path(__file__).resolve().parent.parent / ".env.example"

        with self.assertRaises(NarrataClientError) as caught:
            read_token({}, example)

        self.assertIn("NARRATA_TOKEN is not set", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
