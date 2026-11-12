import tempfile
import unittest
from pathlib import Path

from test_reference import KEY
from test_smoke import _ExportableSession, run

from transcript import status
from transcript.session import SessionKey, SessionPaths


def fresh(key: SessionKey, overall: str = "not_started") -> str:
    """The closing line of a session nothing has run on yet."""
    return f"{key}: {overall}; next: extract with transcript process {key}"


class StatusCommandTest(unittest.TestCase):
    """Sessions with stand-in recordings; status opens no recording."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / "config.yaml"
        self.config.write_text(
            f"language: de\npaths:\n  root: {self.root}\n", encoding="utf-8"
        )

    def status(self, *session: str) -> tuple[int, str, str]:
        return run("status", *session, "--config", str(self.config))

    def recording(self, key: SessionKey) -> None:
        directory = SessionPaths(key, self.root).input_dir
        directory.mkdir(parents=True)
        (directory / "aufnahme.mp3").write_bytes(b"not read")

    def test_a_session_shows_every_step_and_how_it_goes_on(self) -> None:
        self.recording(KEY)

        code, stdout, stderr = self.status(str(KEY))

        self.assertEqual(code, 0, stderr)
        lines = stdout.splitlines()
        self.assertEqual([line.split()[1] for line in lines[:-1]], list(status.STEPS))
        self.assertTrue(all(line.split()[2] == "pending" for line in lines[:-1]))
        self.assertEqual(lines[-1], fresh(KEY))

    def test_without_a_session_every_session_gets_one_line(self) -> None:
        other = SessionKey("zweite-gruppe", 7)
        self.recording(KEY)
        self.recording(other)
        for odd in ("beispielgruppe/42", "Gross/001", "beispielgruppe/abc"):
            (self.root / "input" / odd).mkdir(parents=True)
        (self.root / "input" / "beispielgruppe" / "043").write_text("a file")

        code, stdout, stderr = self.status()

        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout.splitlines(), [fresh(KEY), fresh(other)])

    def test_a_session_without_recordings_has_failed(self) -> None:
        (self.root / "input" / str(KEY)).mkdir(parents=True)

        code, stdout, _ = self.status()

        self.assertEqual(code, 0)
        self.assertEqual(stdout, fresh(KEY, "failed") + "\n")

    def test_without_sessions_it_says_so(self) -> None:
        code, stdout, _ = self.status()

        self.assertEqual(code, 0)
        self.assertEqual(stdout, f"no session under {self.root / 'input'}\n")

    def test_an_invalid_key_or_configuration_is_an_error(self) -> None:
        code, _, stderr = self.status("beispielgruppe")
        self.assertEqual(code, 2)
        self.assertIn("invalid session key", stderr)

        self.config.write_text("language: de\n", encoding="utf-8")
        code, _, stderr = self.status(str(KEY))
        self.assertEqual(code, 2)
        self.assertIn("paths.root", stderr)

    def test_writes_nothing(self) -> None:
        self.recording(KEY)
        before = sorted(self.root.rglob("*"))

        self.status(str(KEY))
        self.status()

        self.assertEqual(sorted(self.root.rglob("*")), before)


class StatusOutputTest(_ExportableSession):
    """A diarized session with names and text that must not reach the console."""

    def test_names_no_participant_label_or_text(self) -> None:
        self.speakers()

        code, stdout, stderr = run("status", str(KEY), "--config", str(self.config))

        self.assertEqual(code, 0, stderr)
        self.assert_nothing_secret(stdout + stderr)
        self.assertIn(f"{KEY}: speakers    waiting", stdout)
        self.assertIn(f"fill in {self.paths.speaker_assignment}", stdout)


if __name__ == "__main__":
    unittest.main()
