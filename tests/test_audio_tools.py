import stat
import tempfile
import unittest
from pathlib import Path

from transcript.audio_tools import AudioToolError, check_audio_tools


def write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def working_stub(directory: Path, name: str, version: str = "6.1.1") -> None:
    write_stub(directory, name, f'echo "{name} version {version} Copyright (c)"')


class CheckAudioToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.bin = Path(directory.name)

    def check(self):
        return check_audio_tools(search_path=str(self.bin))

    def test_detects_both_tools_and_logs_their_versions(self) -> None:
        working_stub(self.bin, "ffmpeg")
        working_stub(self.bin, "ffprobe")

        with self.assertLogs("transcript.audio_tools", level="INFO") as logs:
            tools = self.check()

        self.assertEqual(tools.ffmpeg.version, "6.1.1")
        self.assertEqual(tools.ffprobe.version, "6.1.1")
        self.assertEqual(tools.ffmpeg.path, self.bin / "ffmpeg")
        self.assertTrue(any("ffmpeg 6.1.1" in line for line in logs.output))

    def test_missing_ffprobe_alone_is_named(self) -> None:
        working_stub(self.bin, "ffmpeg")

        with self.assertRaises(AudioToolError) as caught:
            self.check()

        message = str(caught.exception)
        self.assertIn("ffprobe not found", message)
        self.assertNotIn("ffmpeg not found", message)
        self.assertIn("sudo apt install ffmpeg", message)

    def test_both_missing_are_named_in_one_error(self) -> None:
        with self.assertRaises(AudioToolError) as caught:
            self.check()

        message = str(caught.exception)
        self.assertIn("ffmpeg not found", message)
        self.assertIn("ffprobe not found", message)

    def test_failing_tool_is_reported_as_unusable(self) -> None:
        write_stub(self.bin, "ffmpeg", "exit 1")
        working_stub(self.bin, "ffprobe")

        with self.assertRaises(AudioToolError) as caught:
            self.check()

        message = str(caught.exception)
        self.assertIn("ffmpeg at", message)
        self.assertIn("exit code 1", message)

    def test_unknown_version_format_keeps_the_first_line(self) -> None:
        write_stub(self.bin, "ffmpeg", 'echo "custom build 2026"')
        working_stub(self.bin, "ffprobe")

        tools = self.check()

        self.assertEqual(tools.ffmpeg.version, "custom build 2026")


if __name__ == "__main__":
    unittest.main()
