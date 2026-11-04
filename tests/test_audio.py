"""Audio tests synthesize their media with ffmpeg at runtime; no audio lives in the repo."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from transcript.audio import MP4_CONTAINER, AudioError, probe
from transcript.audio_tools import AudioToolError, AudioTools, check_audio_tools

try:
    TOOLS: AudioTools | None = check_audio_tools()
except AudioToolError:
    TOOLS = None


def synth(path: Path, *args: str) -> Path:
    """Run ffmpeg with lavfi sources, e.g. `synth(p, "-f", "lavfi", "-i", "sine")`."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", *args, str(path)], check=True
    )
    return path


def sine(seconds: float = 2, frequency: int = 440, rate: int = 44100) -> list[str]:
    source = f"sine=frequency={frequency}:duration={seconds}:sample_rate={rate}"
    return ["-f", "lavfi", "-i", source]


def video(seconds: float = 2) -> list[str]:
    return ["-f", "lavfi", "-i", f"testsrc=size=64x48:rate=5:duration={seconds}"]


def mp4_with_audio() -> list[str]:
    """Video plus 48 kHz stereo AAC, the shape of a typical session recording."""
    return [*video(), *sine(rate=48000), "-ac", "2", "-c:a", "aac", "-shortest"]


@unittest.skipIf(TOOLS is None, "ffmpeg and ffprobe are needed to synthesize media")
class MediaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        assert TOOLS is not None
        self.tools = TOOLS


class ProbeTest(MediaTestCase):
    def test_supported_formats_are_recognized(self) -> None:
        cases = (
            ("talk.mp4", mp4_with_audio(), MP4_CONTAINER),
            ("talk.m4a", [*sine(), "-c:a", "aac"], MP4_CONTAINER),
            ("talk.mp3", sine(), "mp3"),
            ("talk.wav", sine(), "wav"),
        )
        for name, args, container in cases:
            with self.subTest(name=name):
                info = probe(synth(self.dir / name, *args), self.tools)

                self.assertEqual(info.container, container)
                self.assertEqual(len(info.audio_streams), 1)
                self.assertAlmostEqual(info.duration, 2, delta=0.1)

    def test_mp4_reports_video_and_audio_details(self) -> None:
        path = synth(self.dir / "talk.mp4", *mp4_with_audio())

        info = probe(path, self.tools)

        self.assertTrue(info.has_video)
        stream = info.audio_streams[0]
        self.assertEqual(stream.index, 1)
        self.assertEqual(stream.codec, "aac")
        self.assertEqual((stream.channels, stream.sample_rate), (2, 48000))

    def test_extension_is_not_trusted(self) -> None:
        path = synth(self.dir / "talk.mp3", *sine(), "-f", "wav")

        self.assertEqual(probe(path, self.tools).container, "wav")

    def test_mp4_without_audio_is_rejected(self) -> None:
        path = synth(self.dir / "silent.mp4", *video())

        self.assert_rejected(path, "no audio stream")

    def test_damaged_file_is_rejected_with_a_readable_message(self) -> None:
        path = self.dir / "talk.mp3"
        path.write_text("not a media file\n" * 200, encoding="utf-8")

        message = self.assert_rejected(path, "damaged or not a media file")

        self.assertIn("talk.mp3", message)
        self.assertNotIn(str(self.dir), message)

    def test_unsupported_container_is_named(self) -> None:
        path = synth(self.dir / "talk.ogg", *sine(), "-c:a", "libopus")

        self.assert_rejected(path, "unsupported container ogg")

    def test_missing_file_names_the_path(self) -> None:
        path = self.dir / "missing.mp4"

        message = self.assert_rejected(path, "file not found")

        self.assertIn(str(path), message)

    def assert_rejected(self, path: Path, expected: str) -> str:
        with self.assertRaises(AudioError) as caught:
            probe(path, self.tools)
        message = str(caught.exception)
        self.assertIn(expected, message)
        return message


if __name__ == "__main__":
    unittest.main()
