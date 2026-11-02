import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from transcript.config import Config
from transcript.debug_log import transcript_logger
from transcript.session import SessionKey

KEY = SessionKey("beispielgruppe", 42)
TEXT = "synthetischer Beispielsatz"


class TranscriptLoggerTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.debug_log = self.config(debug=True).session_paths(KEY).debug_log

    def config(self, *, debug: bool) -> Config:
        return Config(language="de", root=self.root, debug=debug)

    def log(self, *, debug: bool) -> str:
        """Log one line and return what reached stderr."""
        logger = transcript_logger(self.config(debug=debug), KEY)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            logger.info(TEXT)
        for handler in logger.handlers:
            handler.close()
        return stderr.getvalue()

    def test_debug_mode_writes_text_to_the_file_only(self) -> None:
        stderr = self.log(debug=True)

        self.assertIn(TEXT, self.debug_log.read_text(encoding="utf-8"))
        self.assertEqual(stderr, "")

    def test_repeated_setup_does_not_duplicate_lines(self) -> None:
        self.log(debug=True)
        self.log(debug=True)

        lines = self.debug_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)

    def test_without_debug_mode_nothing_is_written(self) -> None:
        stderr = self.log(debug=False)

        self.assertEqual(stderr, "")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_root_logger_never_receives_the_text(self) -> None:
        for debug in (True, False):
            with self.subTest(debug=debug), self.assertNoLogs():
                self.log(debug=debug)


if __name__ == "__main__":
    unittest.main()
