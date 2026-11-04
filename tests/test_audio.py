"""Audio tests synthesize their media with ffmpeg at runtime; no audio lives in the repo."""

import array
import dataclasses
import hashlib
import itertools
import json
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from test_audio_tools import write_stub

from transcript.audio import MP4_CONTAINER, AudioError, extract, probe
from transcript.audio_tools import (
    AudioToolError,
    AudioTools,
    ToolInfo,
    check_audio_tools,
)
from transcript.config import Config
from transcript.session import SessionKey

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


class ExtractTest(MediaTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = Config(language="de", root=self.dir / "root")
        self.paths = self.config.session_paths(SessionKey("beispielgruppe", 1))

    def metadata(self) -> dict:
        return json.loads(self.paths.audio_metadata.read_text(encoding="utf-8"))

    def test_mp4_audio_becomes_16_khz_mono_wav(self) -> None:
        source = synth(self.dir / "talk.mp4", *mp4_with_audio())
        info = probe(source, self.tools)

        result = extract(info, self.paths, self.config, self.tools)

        with wave.open(str(self.paths.audio_wav), "rb") as wav:
            self.assertEqual(wav.getframerate(), 16000)
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
        self.assertAlmostEqual(result.duration, info.duration, delta=0.5)

        metadata = self.metadata()
        self.assertEqual(metadata["format_version"], 1)
        self.assertTrue(metadata["source"]["has_video"])
        self.assertEqual(metadata["source"]["file"], "talk.mp4")
        self.assertEqual(
            metadata["selected_stream"], {"audio_index": 0, "stream_index": 1}
        )
        self.assertEqual(metadata["output"]["file"], "audio.wav")
        self.assertEqual(metadata["output"]["sample_rate"], 16000)
        self.assertEqual(metadata["tools"]["ffmpeg"], self.tools.ffmpeg.version)

    def test_configured_format_is_used(self) -> None:
        config = dataclasses.replace(
            self.config, audio_sample_rate=22050, audio_channels=2
        )
        info = probe(synth(self.dir / "talk.wav", *sine()), self.tools)

        extract(info, self.paths, config, self.tools)

        with wave.open(str(self.paths.audio_wav), "rb") as wav:
            self.assertEqual((wav.getframerate(), wav.getnchannels()), (22050, 2))

    def test_supported_formats_extract(self) -> None:
        for name, args in (
            ("talk.m4a", [*sine(), "-c:a", "aac"]),
            ("talk.mp3", sine()),
            ("talk.wav", sine()),
        ):
            with self.subTest(name=name):
                info = probe(synth(self.dir / name, *args), self.tools)

                result = extract(info, self.paths, self.config, self.tools)

                self.assertAlmostEqual(result.duration, 2, delta=0.1)

    def test_stream_choice_is_deterministic_and_recorded(self) -> None:
        source = synth(
            self.dir / "two.mp4",
            *sine(frequency=440),
            *sine(frequency=880),
            "-map",
            "0",
            "-map",
            "1",
            "-c:a",
            "aac",
        )
        info = probe(source, self.tools)

        extract(info, self.paths, self.config, self.tools)
        default_frequency = frequency(self.paths.audio_wav)
        extract(info, self.paths, self.config, self.tools, stream=1)

        self.assertAlmostEqual(default_frequency, 440, delta=20)
        self.assertAlmostEqual(frequency(self.paths.audio_wav), 880, delta=20)
        self.assertEqual(
            self.metadata()["selected_stream"], {"audio_index": 1, "stream_index": 1}
        )

    def test_missing_stream_is_rejected(self) -> None:
        info = probe(synth(self.dir / "talk.wav", *sine()), self.tools)

        with self.assertRaises(AudioError) as caught:
            extract(info, self.paths, self.config, self.tools, stream=1)

        self.assertIn("no audio stream 1; the recording has 1", str(caught.exception))

    def test_source_is_not_modified(self) -> None:
        source = synth(self.dir / "talk.mp4", *mp4_with_audio())
        before = hashlib.sha256(source.read_bytes()).hexdigest()

        extract(probe(source, self.tools), self.paths, self.config, self.tools)

        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)

    def test_failing_ffmpeg_leaves_no_files(self) -> None:
        info = probe(synth(self.dir / "talk.wav", *sine()), self.tools)
        write_stub(self.dir, "ffmpeg", "echo 'boom: Invalid data' >&2\nexit 1")
        stub = ToolInfo("ffmpeg", self.dir / "ffmpeg", "x")
        tools = dataclasses.replace(self.tools, ffmpeg=stub)

        with self.assertRaises(AudioError) as caught:
            extract(info, self.paths, self.config, tools)

        self.assertIn("extraction failed (boom: Invalid data)", str(caught.exception))
        self.assertEqual(list(self.paths.audio_dir.iterdir()), [])

    def test_duration_mismatch_is_rejected_and_leaves_no_files(self) -> None:
        info = probe(synth(self.dir / "talk.wav", *sine()), self.tools)
        stream = dataclasses.replace(info.audio_streams[0], duration=10.0)
        claims_ten_seconds = dataclasses.replace(info, audio_streams=(stream,))

        with self.assertRaises(AudioError) as caught:
            extract(claims_ten_seconds, self.paths, self.config, self.tools)

        self.assertIn("may be damaged", str(caught.exception))
        self.assertEqual(list(self.paths.audio_dir.iterdir()), [])


def frequency(path: Path) -> float:
    """Frequency of a mono sine in Hz; a sine crosses zero twice per period."""
    with wave.open(str(path), "rb") as wav:
        samples = array.array("h", wav.readframes(wav.getnframes()))
        seconds = wav.getnframes() / wav.getframerate()
    crossings = sum(1 for a, b in itertools.pairwise(samples) if (a < 0) != (b < 0))
    return crossings / 2 / seconds


if __name__ == "__main__":
    unittest.main()
