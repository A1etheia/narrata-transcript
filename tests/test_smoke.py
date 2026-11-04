import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from media import mp4_with_audio, needs_media, sine, synth, video

import transcript
from transcript import audio_tools
from transcript.__main__ import main
from transcript.audio_tools import AudioToolError, AudioTools, ToolInfo
from transcript.session import SessionKey, SessionPaths

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


class DoctorCommandTest(unittest.TestCase):
    def test_prints_each_tool_with_version_and_path(self) -> None:
        tools = AudioTools(
            ffmpeg=ToolInfo("ffmpeg", Path("/bin/ffmpeg"), "6.1.1"),
            ffprobe=ToolInfo("ffprobe", Path("/bin/ffprobe"), "6.1.1"),
        )
        with mock.patch.object(audio_tools, "check_audio_tools", return_value=tools):
            code, stdout, _ = run("doctor")

        self.assertEqual(code, 0)
        self.assertIn("ffmpeg 6.1.1 (/bin/ffmpeg)", stdout)
        self.assertIn("ffprobe 6.1.1 (/bin/ffprobe)", stdout)

    def test_missing_tool_is_reported_without_traceback(self) -> None:
        error = AudioToolError("ffprobe not found on PATH; install with: sudo apt …")
        with mock.patch.object(audio_tools, "check_audio_tools", side_effect=error):
            code, stdout, stderr = run("doctor")

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("error: ffprobe not found", stderr)
        self.assertNotIn("Traceback", stderr)


class ExtractCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / "config.yaml"
        self.config.write_text(
            f"language: de\npaths:\n  root: {self.root}\n", encoding="utf-8"
        )
        self.paths = SessionPaths(SessionKey("beispielgruppe", 1), self.root)
        self.input = self.paths.input_dir
        self.input.mkdir(parents=True)

    def extract(self, *extra: str) -> tuple[int, str, str]:
        return run("extract", "beispielgruppe/1", "--config", str(self.config), *extra)

    @needs_media
    def test_extracts_the_session_recording(self) -> None:
        synth(self.input / "talk.mp4", *mp4_with_audio())

        code, stdout, stderr = self.extract()

        self.assertEqual(code, 0, stderr)
        self.assertIn("audio stream 0 of 1 (aac), video ignored", stdout)
        self.assertTrue(self.paths.audio_wav.is_file())
        self.assertTrue(self.paths.audio_metadata.is_file())
        self.assertIn("ffmpeg", stderr)
        self.assertNotIn("talk.mp4", stderr)

    def test_empty_input_directory_is_reported(self) -> None:
        code, stdout, stderr = self.extract()

        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("error: ", stderr)
        self.assertIn("expected one recording, found 0", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_two_recordings_are_reported(self) -> None:
        (self.input / "a.mp4").write_bytes(b"")
        (self.input / "b.mp4").write_bytes(b"")

        code, _, stderr = self.extract()

        self.assertEqual(code, 2)
        self.assertIn("expected one recording, found 2", stderr)

    def test_hidden_and_windows_zone_files_are_not_recordings(self) -> None:
        (self.input / ".DS_Store").write_bytes(b"")
        (self.input / "talk.mp3:Zone.Identifier").write_bytes(b"")

        code, _, stderr = self.extract()

        self.assertEqual(code, 2)
        self.assertIn("expected one recording, found 0", stderr)

    def test_invalid_session_key_is_reported(self) -> None:
        code, _, stderr = run("extract", "Beispiel", "--config", str(self.config))

        self.assertEqual(code, 2)
        self.assertIn("invalid session key", stderr)

    @needs_media
    def test_recording_without_audio_is_reported(self) -> None:
        synth(self.input / "silent.mp4", *video())

        code, _, stderr = self.extract()

        self.assertEqual(code, 2)
        self.assertIn("error: silent.mp4: no audio stream", stderr)
        self.assertNotIn("Traceback", stderr)

    @needs_media
    def test_missing_stream_is_reported(self) -> None:
        synth(self.input / "talk.wav", *sine())

        code, _, stderr = self.extract("--stream", "1")

        self.assertEqual(code, 2)
        self.assertIn("no audio stream 1", stderr)


if __name__ == "__main__":
    unittest.main()
