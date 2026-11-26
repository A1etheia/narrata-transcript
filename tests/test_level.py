"""The level filter against tones synthesized at runtime (see tests/media.py)."""

import array
import dataclasses
import json
import tempfile
import unittest
import wave
from pathlib import Path

from media import TOOLS, needs_media, sine, synth
from test_audio import failing_ffmpeg

from transcript import level
from transcript.audio import AudioError
from transcript.audio_tools import AudioTools, ToolInfo
from transcript.config import LEVEL_FILTERS, Config
from transcript.session import SessionKey

RATE = 16000
SECONDS = 5
FRAMES = RATE * SECONDS


def tone(volume: float = 0.05) -> list[str]:
    """A quiet mono tone as the extraction would write it."""
    return [*sine(SECONDS, rate=RATE), "-af", f"volume={volume}", "-c:a", "pcm_s16le"]


def peak(path: Path) -> int:
    with wave.open(str(path), "rb") as source:
        samples = array.array("h", source.readframes(source.getnframes()))
    return max(abs(sample) for sample in samples)


class SettingsTest(unittest.TestCase):
    def test_the_filter_is_the_one_the_config_can_switch_on(self) -> None:
        self.assertEqual(LEVEL_FILTERS, ("none", level.FILTER))
        self.assertFalse(Config(language="de", root=Path("/data")).asr_levels)
        on = Config(language="de", root=Path("/data"), asr_level_filter=level.FILTER)
        self.assertTrue(on.asr_levels)

    def test_settings_name_chain_and_ffmpeg_version(self) -> None:
        tool = ToolInfo("ffmpeg", Path("ffmpeg"), "6.1.1")

        found = level.settings(AudioTools(ffmpeg=tool, ffprobe=tool))

        self.assertEqual(
            found, {"chain": "loudnorm=I=-16:TP=-1.5:LRA=11", "ffmpeg": "6.1.1"}
        )


@needs_media
class EnsureTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        assert TOOLS is not None
        self.tools = TOOLS
        config = Config(language="de", root=self.dir)
        self.paths = config.session_paths(SessionKey("beispielgruppe", 1))
        self.paths.audio_dir.mkdir(parents=True)
        self.raw = synth(self.paths.segment_wav(1), *tone())

    def ensure(self, tools: AudioTools | None = None) -> level.Levelled:
        return level.ensure(self.paths, 1, FRAMES, tools or self.tools)

    def files(self) -> list[str]:
        return sorted(path.name for path in self.paths.level_dir.iterdir())

    def record(self) -> dict:
        return json.loads(self.paths.level_record(1).read_text(encoding="utf-8"))

    def test_filtered_copy_keeps_the_length_and_raises_the_level(self) -> None:
        before = self.raw.read_bytes()

        found = self.ensure()

        self.assertEqual(found.path, self.paths.level_wav(1))
        self.assertFalse(found.reused)
        with wave.open(str(found.path), "rb") as source:
            shape = (source.getnframes(), source.getframerate(), source.getnchannels())
        self.assertEqual(shape, (FRAMES, RATE, 1))
        self.assertGreater(peak(found.path), 2 * peak(self.raw))
        self.assertEqual(self.files(), ["segment-01.json", "segment-01.wav"])
        self.assertEqual(self.raw.read_bytes(), before)  # the raw WAV is only read

    def test_record_names_chain_version_input_and_measurements(self) -> None:
        found = self.ensure()

        record = self.record()
        self.assertEqual(record["format_version"], level.RECORD_FORMAT_VERSION)
        self.assertEqual(record["chain"], level.CHAIN)
        self.assertEqual(record["ffmpeg"], self.tools.ffmpeg.version)
        self.assertEqual((record["frames"], record["sample_rate"]), (FRAMES, RATE))
        self.assertEqual(len(record["raw_sha256"]), 64)
        self.assertEqual(
            sorted(record["measured"]),
            ["input_i", "input_lra", "input_thresh", "input_tp", "target_offset"],
        )
        self.assertLess(record["measured"]["input_i"], level.TARGET["I"])
        self.assertIs(record["linear_expected"], True)
        self.assertEqual(record["filter_seconds"], found.seconds)

    def test_a_fitting_copy_is_reused_without_ffmpeg(self) -> None:
        first = self.ensure()
        before = first.path.read_bytes()

        again = self.ensure(self.stub("exit 1", version=self.tools.ffmpeg.version))

        self.assertTrue(again.reused)
        self.assertEqual(again.path.read_bytes(), before)

    def test_changed_raw_wav_is_filtered_again(self) -> None:
        self.ensure()
        synth(self.raw, *tone(volume=0.2))

        self.assertFalse(self.ensure().reused)

    def test_other_ffmpeg_version_is_filtered_again(self) -> None:
        self.ensure()
        other = ToolInfo("ffmpeg", self.tools.ffmpeg.path, "0.0-other")

        found = self.ensure(dataclasses.replace(self.tools, ffmpeg=other))

        self.assertFalse(found.reused)
        self.assertEqual(self.record()["ffmpeg"], "0.0-other")

    def test_copy_without_a_record_is_filtered_again(self) -> None:
        self.ensure()
        self.paths.level_record(1).unlink()

        self.assertFalse(self.ensure().reused)

    def test_unreadable_record_is_filtered_again(self) -> None:
        self.ensure()
        self.paths.level_record(1).write_text("{", encoding="utf-8")

        self.assertFalse(self.ensure().reused)

    def test_unknown_record_version_is_filtered_again(self) -> None:
        self.ensure()
        changed = {**self.record(), "format_version": 99}
        self.paths.level_record(1).write_text(json.dumps(changed), encoding="utf-8")

        self.assertFalse(self.ensure().reused)

    def test_failing_measurement_leaves_no_files(self) -> None:
        with self.assertRaises(AudioError) as caught:
            self.ensure(self.stub("exit 1"))

        message = str(caught.exception)
        self.assertIn("segment-01.wav: level measurement failed", message)
        self.assertNotIn(str(self.dir), message)
        self.assertEqual(self.files(), [])

    def test_failing_filter_pass_leaves_no_files(self) -> None:
        with self.assertRaises(AudioError) as caught:
            self.ensure(self.second_pass_fails())

        self.assertIn("level filter failed (boom: Invalid data)", str(caught.exception))
        self.assertEqual(self.files(), [])

    def test_failure_keeps_the_copy_of_an_earlier_run(self) -> None:
        self.ensure()
        before = {p.name: p.read_bytes() for p in self.paths.level_dir.iterdir()}
        synth(self.raw, *tone(volume=0.2))

        with self.assertRaises(AudioError):
            self.ensure(self.second_pass_fails())

        after = {p.name: p.read_bytes() for p in self.paths.level_dir.iterdir()}
        self.assertEqual(after, before)

    def test_silence_cannot_be_measured(self) -> None:
        silence = f"anullsrc=sample_rate={RATE}:channel_layout=mono"
        synth(self.raw, "-f", "lavfi", "-i", silence, "-t", str(SECONDS))

        with self.assertRaises(AudioError) as caught:
            self.ensure()

        self.assertIn("level cannot be measured", str(caught.exception))
        self.assertEqual(self.files(), [])

    def test_length_other_than_the_manifest_is_rejected(self) -> None:
        with self.assertRaises(AudioError) as caught:
            level.ensure(self.paths, 1, FRAMES + 1, self.tools)

        self.assertIn("the manifest has", str(caught.exception))
        self.assertFalse(self.paths.level_dir.exists())

    def test_missing_raw_wav_is_rejected(self) -> None:
        self.raw.unlink()

        with self.assertRaises(AudioError) as caught:
            self.ensure()

        self.assertIn("WAV is unreadable", str(caught.exception))

    def stub(self, body: str, version: str = "x") -> AudioTools:
        return failing_ffmpeg(self.dir, self.tools, body, version)

    def second_pass_fails(self) -> AudioTools:
        """The measuring pass goes on to the real ffmpeg, the filter pass fails."""
        real = self.tools.ffmpeg.path
        return self.stub(
            f'case "$*" in *print_format=json*) exec "{real}" "$@";; esac\nexit 1',
            version=self.tools.ffmpeg.version,
        )


if __name__ == "__main__":
    unittest.main()
