import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from media import sine, synth
from test_audio_tools import write_stub

from transcript import speaker_player
from transcript.audio import sha256_file
from transcript.config import SUGGESTED_PLAYBACK_FILTER
from transcript.speaker_player import (
    MAX_SAMPLE_MS,
    command,
    find_player,
    play,
    sample_ms,
    usable_filter,
)

PLAYER = Path("/opt/fake/ffplay")
WAV = Path("work/beispielgruppe/042/audio/segment-001.wav")


class CommandTest(unittest.TestCase):
    def test_the_sample_starts_at_the_local_time_and_lasts_the_passage(self) -> None:
        argv = command(PLAYER, WAV, 83_250, sample_ms(83_250, 87_000))

        self.assertEqual(argv[0], str(PLAYER))
        self.assertEqual(argv[argv.index("-ss") + 1], "83.250")
        self.assertEqual(argv[argv.index("-t") + 1], "3.750")
        self.assertEqual(argv[-1], str(WAV))
        self.assertIn("-nodisp", argv)
        self.assertIn("-autoexit", argv)

    def test_a_filter_goes_before_the_input(self) -> None:
        argv = command(PLAYER, WAV, 0, 1_000, "highpass=f=80,afftdn")

        self.assertEqual(argv[argv.index("-af") + 1], "highpass=f=80,afftdn")
        self.assertLess(argv.index("-af"), argv.index(str(WAV)))

    def test_without_a_filter_the_raw_signal_plays(self) -> None:
        self.assertNotIn("-af", command(PLAYER, WAV, 0, 1_000))

    def test_a_long_or_open_passage_is_cut_to_the_cap(self) -> None:
        self.assertEqual(sample_ms(0, 60_000), MAX_SAMPLE_MS)
        self.assertEqual(sample_ms(5_000, None), MAX_SAMPLE_MS)
        self.assertEqual(sample_ms(5_000, 5_000), MAX_SAMPLE_MS)


class PlayTest(unittest.TestCase):
    def run_with(self, **result: object) -> tuple[str, mock.MagicMock]:
        with mock.patch.object(speaker_player.subprocess, "run") as run:
            if "error" in result:
                run.side_effect = result["error"]
            else:
                run.return_value = subprocess.CompletedProcess([], result["code"])
            return play(PLAYER, WAV, 1_000, 3_000), run

    def test_a_played_sample_drops_the_player_output(self) -> None:
        played, run = self.run_with(code=0)

        self.assertEqual(played, "played")
        (argv,), options = run.call_args
        self.assertEqual(argv, command(PLAYER, WAV, 1_000, 2_000))
        self.assertEqual(options["stdout"], subprocess.DEVNULL)
        self.assertEqual(options["stderr"], subprocess.DEVNULL)
        self.assertGreater(options["timeout"], 2)

    def test_failures_are_reported_not_raised(self) -> None:
        cases = {
            "exit code": {"code": 1},
            "cannot run": {"error": OSError("no audio")},
            "hangs": {"error": subprocess.TimeoutExpired("ffplay", 12)},
        }
        for name, result in cases.items():
            with self.subTest(name):
                self.assertEqual(self.run_with(**result)[0], "failed")

    def test_ctrl_c_stops_the_sample_only(self) -> None:
        played, _ = self.run_with(error=KeyboardInterrupt())

        self.assertEqual(played, "stopped")

    def test_keys_typed_while_playing_are_dropped(self) -> None:
        with (
            mock.patch.object(speaker_player.sys.stdin, "isatty", return_value=True),
            mock.patch.object(speaker_player.termios, "tcflush") as flush,
        ):
            self.run_with(code=0)

        flush.assert_called_once_with(
            speaker_player.sys.stdin, speaker_player.termios.TCIFLUSH
        )

    def test_without_player_nothing_runs(self) -> None:
        with mock.patch.object(speaker_player.subprocess, "run") as run:
            self.assertEqual(play(None, WAV, 0, 1_000), "missing")
        run.assert_not_called()


class UsableFilterTest(unittest.TestCase):
    CHAIN = "highpass=f=80,afftdn=nf=-25"

    def with_ffmpeg(self, body: str | None) -> str | None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            if body is not None:
                write_stub(folder, "ffmpeg", body)
            return usable_filter(self.CHAIN, str(folder))

    def test_a_chain_ffmpeg_builds_is_used(self) -> None:
        self.assertEqual(self.with_ffmpeg("exit 0"), self.CHAIN)

    def test_a_chain_ffmpeg_rejects_plays_unfiltered(self) -> None:
        self.assertIsNone(self.with_ffmpeg("exit 1"))

    def test_without_ffmpeg_samples_play_unfiltered(self) -> None:
        self.assertIsNone(self.with_ffmpeg(None))

    @unittest.skipIf(shutil.which("ffmpeg") is None, "ffmpeg not installed")
    def test_real_ffmpeg_accepts_the_default_and_rejects_unknown_filters(
        self,
    ) -> None:
        self.assertEqual(
            usable_filter(SUGGESTED_PLAYBACK_FILTER), SUGGESTED_PLAYBACK_FILTER
        )
        self.assertIsNone(usable_filter("nosuchfilter"))
        self.assertIsNone(usable_filter("afftdn=nosuchoption=1"))


class FilteredPlaybackTest(unittest.TestCase):
    @unittest.skipIf(shutil.which("ffplay") is None, "ffplay not installed")
    def test_playing_through_the_filter_leaves_the_wav_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wav = Path(directory) / "segment-001.wav"
            synth(wav, *sine(seconds=0.5, rate=16_000), "-ac", "1")
            before = sha256_file(wav)

            # dummy audio driver: ffplay decodes and filters, nothing is heard
            with mock.patch.dict(os.environ, {"SDL_AUDIODRIVER": "dummy"}):
                played = play(find_player(), wav, 0, 300, SUGGESTED_PLAYBACK_FILTER)

            self.assertEqual(played, "played")
            self.assertEqual(sha256_file(wav), before)


class FindPlayerTest(unittest.TestCase):
    def test_finds_ffplay_on_the_search_path_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.assertIsNone(find_player(str(folder)))
            write_stub(folder, "ffplay", "exit 0")
            self.assertEqual(find_player(str(folder)), folder / "ffplay")


if __name__ == "__main__":
    unittest.main()
