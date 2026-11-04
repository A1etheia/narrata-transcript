"""Probe and extraction against media synthesized at runtime (see tests/media.py)."""

import array
import dataclasses
import hashlib
import itertools
import json
import tempfile
import unittest
import wave
from pathlib import Path

from media import TOOLS, mp4_with_audio, needs_media, sine, synth, video
from test_audio_tools import write_stub

from transcript.audio import (
    MP4_CONTAINER,
    AudioError,
    AudioInfo,
    ExtractedSegment,
    extract,
    probe,
)
from transcript.audio_tools import AudioTools, ToolInfo
from transcript.config import Config
from transcript.session import SessionKey


@needs_media
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

    def extract_one(self, info: AudioInfo, **kwargs: object) -> ExtractedSegment:
        (segment,) = extract([info], self.paths, self.config, self.tools, **kwargs)
        return segment

    def test_mp4_audio_becomes_16_khz_mono_wav(self) -> None:
        source = synth(self.dir / "talk.mp4", *mp4_with_audio())
        info = probe(source, self.tools)

        segment = self.extract_one(info)

        with wave.open(str(self.paths.segment_wav(1)), "rb") as wav:
            self.assertEqual(wav.getframerate(), 16000)
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getnframes(), segment.frames)
        self.assertAlmostEqual(segment.duration_ms, info.duration * 1000, delta=500)

        metadata = self.metadata()
        self.assertEqual(metadata["format_version"], 2)
        self.assertEqual(metadata["output_format"]["sample_rate"], 16000)
        self.assertEqual(metadata["tools"]["ffmpeg"], self.tools.ffmpeg.version)
        (entry,) = metadata["segments"]
        self.assertEqual(entry["index"], 1)
        self.assertEqual(entry["file"], "segment-01.wav")
        self.assertEqual(entry["frames"], segment.frames)
        self.assertTrue(entry["source"]["has_video"])
        self.assertEqual(entry["source"]["file"], "talk.mp4")
        self.assertEqual(
            entry["source"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest()
        )
        self.assertEqual(
            entry["selected_stream"], {"audio_index": 0, "stream_index": 1}
        )

    def test_recordings_become_segments_in_the_given_order(self) -> None:
        first = synth(self.dir / "part 1.wav", *sine(seconds=1))
        second = synth(self.dir / "part 2.mp3", *sine(seconds=2))
        infos = [probe(first, self.tools), probe(second, self.tools)]

        segments = extract(infos, self.paths, self.config, self.tools)

        self.assertEqual([segment.index for segment in segments], [1, 2])
        self.assertAlmostEqual(segments[0].duration_ms, 1000, delta=50)
        self.assertAlmostEqual(segments[1].duration_ms, 2000, delta=100)
        entries = self.metadata()["segments"]
        self.assertEqual(
            [entry["source"]["file"] for entry in entries], ["part 1.wav", "part 2.mp3"]
        )
        self.assertEqual(
            [entry["source"]["sha256"] for entry in entries],
            [hashlib.sha256(path.read_bytes()).hexdigest() for path in (first, second)],
        )
        self.assertTrue(self.paths.segment_wav(2).is_file())

    def test_fewer_recordings_remove_stale_segments(self) -> None:
        first = probe(synth(self.dir / "a.wav", *sine(seconds=1)), self.tools)
        second = probe(synth(self.dir / "b.wav", *sine(seconds=1)), self.tools)
        extract([first, second], self.paths, self.config, self.tools)

        extract([first], self.paths, self.config, self.tools)

        self.assertEqual(
            sorted(path.name for path in self.paths.audio_dir.iterdir()),
            ["audio.json", "segment-01.wav"],
        )

    def test_configured_format_is_used(self) -> None:
        config = dataclasses.replace(
            self.config, audio_sample_rate=22050, audio_channels=2
        )
        info = probe(synth(self.dir / "talk.wav", *sine()), self.tools)

        extract([info], self.paths, config, self.tools)

        with wave.open(str(self.paths.segment_wav(1)), "rb") as wav:
            self.assertEqual((wav.getframerate(), wav.getnchannels()), (22050, 2))

    def test_supported_formats_extract(self) -> None:
        for name, args in (
            ("talk.m4a", [*sine(), "-c:a", "aac"]),
            ("talk.mp3", sine()),
            ("talk.wav", sine()),
        ):
            with self.subTest(name=name):
                info = probe(synth(self.dir / name, *args), self.tools)

                segment = self.extract_one(info)

                self.assertAlmostEqual(segment.duration_ms, 2000, delta=100)

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

        self.extract_one(info)
        default_frequency = frequency(self.paths.segment_wav(1))
        self.extract_one(info, stream=1)

        self.assertAlmostEqual(default_frequency, 440, delta=20)
        self.assertAlmostEqual(frequency(self.paths.segment_wav(1)), 880, delta=20)
        self.assertEqual(
            self.metadata()["segments"][0]["selected_stream"],
            {"audio_index": 1, "stream_index": 1},
        )

    def test_missing_stream_is_rejected(self) -> None:
        info = probe(synth(self.dir / "talk.wav", *sine()), self.tools)

        with self.assertRaises(AudioError) as caught:
            self.extract_one(info, stream=1)

        self.assertIn("no audio stream 1; the recording has 1", str(caught.exception))

    def test_source_is_not_modified(self) -> None:
        source = synth(self.dir / "talk.mp4", *mp4_with_audio())
        before = hashlib.sha256(source.read_bytes()).hexdigest()

        self.extract_one(probe(source, self.tools))

        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)

    def test_failing_ffmpeg_leaves_no_files(self) -> None:
        info = probe(synth(self.dir / "talk.wav", *sine()), self.tools)
        tools = self.failing_ffmpeg("exit 1")

        with self.assertRaises(AudioError) as caught:
            extract([info], self.paths, self.config, tools)

        self.assertIn("extraction failed (boom: Invalid data)", str(caught.exception))
        self.assertEqual(list(self.paths.audio_dir.iterdir()), [])

    def test_failure_in_a_later_recording_keeps_the_previous_state(self) -> None:
        first = probe(synth(self.dir / "a.wav", *sine(seconds=1)), self.tools)
        second = probe(synth(self.dir / "b.wav", *sine(seconds=1)), self.tools)
        self.extract_one(first)
        before = {
            path.name: path.read_bytes() for path in self.paths.audio_dir.iterdir()
        }
        # The stub passes the first recording on to the real ffmpeg.
        tools = self.failing_ffmpeg(
            f'case "$*" in *b.wav*) exit 1;; esac\nexec "{self.tools.ffmpeg.path}" "$@"'
        )

        with self.assertRaises(AudioError) as caught:
            extract([first, second], self.paths, self.config, tools)

        self.assertIn("b.wav: extraction failed", str(caught.exception))

        after = {
            path.name: path.read_bytes() for path in self.paths.audio_dir.iterdir()
        }
        self.assertEqual(after, before)

    def test_duration_mismatch_is_rejected_and_leaves_no_files(self) -> None:
        info = probe(synth(self.dir / "talk.wav", *sine()), self.tools)
        stream = dataclasses.replace(info.audio_streams[0], duration=10.0)
        claims_ten_seconds = dataclasses.replace(info, audio_streams=(stream,))

        with self.assertRaises(AudioError) as caught:
            self.extract_one(claims_ten_seconds)

        self.assertIn("may be damaged", str(caught.exception))
        self.assertEqual(list(self.paths.audio_dir.iterdir()), [])

    def failing_ffmpeg(self, body: str) -> AudioTools:
        """ffmpeg stub that prints an error line and runs `body`."""
        write_stub(self.dir, "ffmpeg", f"echo 'boom: Invalid data' >&2\n{body}")
        stub = ToolInfo("ffmpeg", self.dir / "ffmpeg", "x")
        return dataclasses.replace(self.tools, ffmpeg=stub)


def frequency(path: Path) -> float:
    """Frequency of a mono sine in Hz; a sine crosses zero twice per period."""
    with wave.open(str(path), "rb") as wav:
        samples = array.array("h", wav.readframes(wav.getnframes()))
        seconds = wav.getnframes() / wav.getframerate()
    crossings = sum(1 for a, b in itertools.pairwise(samples) if (a < 0) != (b < 0))
    return crossings / 2 / seconds


if __name__ == "__main__":
    unittest.main()
