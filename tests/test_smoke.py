import contextlib
import dataclasses
import io
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from media import mp4_with_audio, needs_media, sine, synth, video
from test_diarization import FakeDiarizer
from test_narrata import (
    ALIAS,
    CHARACTER,
    NAME,
    PLACE,
    SUMMARY,
    VARIANT,
    context,
    encoded,
    glossary_entry,
    participant,
)
from test_narrata_client import TOKEN, start_fake_narrata
from test_reference import KEY, MANIFEST, SECRET, SEGMENT, minimal
from test_transcription import MANIFEST_3, FailingLoad, session_backend

import transcript
from transcript import __main__ as transcript_main
from transcript import audio_tools, jsonfile, retry
from transcript import manifest as manifest_module
from transcript.__main__ import main
from transcript.asr import AudioInputError, BackendUnavailableError, ResourceError
from transcript.asr.fake import FakeBackend
from transcript.audio_tools import AudioToolError, AudioTools, ToolInfo
from transcript.reference import Passage, Word, update_reference
from transcript.session import SessionKey, SessionPaths

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_LOAD_MANIFEST = manifest_module.load_manifest  # before any test patches it


def run(*argv: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def failing_diarizer(test: Any, error: Exception) -> Any:
    """Patch the diarizer factory so every diarizer `test` gets raises `error`."""

    def broken(config: Any) -> FakeDiarizer:
        diarizer = test.diarizer(config)
        diarizer.diarize = mock.Mock(side_effect=error)
        return diarizer

    return mock.patch.object(
        transcript_main.PyannoteDiarizer, "from_config", side_effect=broken
    )


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
        self.assertIn("1 recording(s) in this order", stdout)
        self.assertIn("1. talk.mp4: ", stdout)
        self.assertIn("audio stream 0 of 1 (aac), video ignored", stdout)
        self.assertIn("-> segment-01.wav", stdout)
        self.assertTrue(self.paths.segment_wav(1).is_file())
        self.assertTrue(self.paths.audio_metadata.is_file())
        self.assertIn("ffmpeg", stderr)
        self.assertNotIn("talk.mp4", stderr)

    def test_empty_input_directory_is_reported(self) -> None:
        code, stdout, stderr = self.extract()

        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("error: ", stderr)
        self.assertIn("no recording found", stderr)
        self.assertNotIn("Traceback", stderr)

    @needs_media
    def test_recordings_are_listed_in_session_order(self) -> None:
        synth(self.input / "teil 2.mp3", *sine(seconds=1))
        synth(self.input / "teil 1.mp3", *sine(seconds=1))

        code, stdout, stderr = self.extract()

        self.assertEqual(code, 0, stderr)
        self.assertIn("2 recording(s) in this order", stdout)
        self.assertLess(stdout.index("1. teil 1.mp3"), stdout.index("2. teil 2.mp3"))
        self.assertTrue(self.paths.segment_wav(2).is_file())

    def test_hidden_and_windows_zone_files_are_not_recordings(self) -> None:
        (self.input / ".DS_Store").write_bytes(b"")
        (self.input / "talk.mp3:Zone.Identifier").write_bytes(b"")

        code, _, stderr = self.extract()

        self.assertEqual(code, 2)
        self.assertIn("no recording found", stderr)

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


class ManifestCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / "config.yaml"
        self.config.write_text(
            f"language: de\npaths:\n  root: {self.root}\n", encoding="utf-8"
        )
        self.paths = SessionPaths(SessionKey("beispielgruppe", 1), self.root)
        self.paths.input_dir.mkdir(parents=True)

    def manifest(self, *extra: str) -> tuple[int, str, str]:
        return run("manifest", "beispielgruppe/1", "--config", str(self.config), *extra)

    def write_context(self) -> None:
        """Store the context the way a user does: `transcript context --from-file`."""
        saved = self.root / "saved-context.json"
        saved.write_bytes(encoded(context(ordinal=1)))
        code, _, stderr = run(
            "context",
            "beispielgruppe/1",
            "--from-file",
            str(saved),
            "--config",
            str(self.config),
        )
        self.assertEqual(code, 0, stderr)

    @needs_media
    def test_two_recordings_get_a_gapless_timeline(self) -> None:
        synth(self.paths.input_dir / "teil 1.mp3", *sine(seconds=1))
        synth(self.paths.input_dir / "teil 2.wav", *sine(seconds=2))
        code, _, stderr = run(
            "extract", "beispielgruppe/1", "--config", str(self.config)
        )
        self.assertEqual(code, 0, stderr)
        self.write_context()

        code, stdout, stderr = self.manifest("--consent")

        self.assertEqual(code, 0, stderr)
        self.assertIn("play session 4711, 2026-10-30, 2 segment(s)", stdout)
        lines = [line for line in stdout.splitlines() if line.startswith("  ")]
        first_end = lines[0].split()[3]
        second_start = lines[1].split()[1]
        self.assertEqual(lines[0].split()[1], "00:00:00.000")
        self.assertEqual(first_end, second_start)
        self.assertIn("consent noted at", stdout)
        self.assertNotIn("warning", stderr)
        self.assertTrue(self.paths.manifest.is_file())

    def test_missing_context_is_reported(self) -> None:
        code, stdout, stderr = self.manifest()

        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("Narrata transcription context not found", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_missing_extraction_points_to_extract(self) -> None:
        self.write_context()

        code, _, stderr = self.manifest()

        self.assertEqual(code, 2)
        self.assertIn("run transcript extract first", stderr)

    @needs_media
    def test_missing_consent_warns(self) -> None:
        synth(self.paths.input_dir / "teil 1.mp3", *sine(seconds=1))
        run("extract", "beispielgruppe/1", "--config", str(self.config))
        self.write_context()

        code, _, stderr = self.manifest()

        self.assertEqual(code, 0, stderr)
        self.assertIn("warning: no consent note", stderr)


class ContextCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.narrata = start_fake_narrata(self)
        self.narrata.body = encoded(context())
        self.config = self.root / "config.yaml"
        self.write_config(self.narrata.url)
        self.paths = SessionPaths(KEY, self.root)
        for patcher in (
            mock.patch.dict(os.environ, {"NARRATA_TOKEN": TOKEN}),
            mock.patch.object(transcript_main, "_DOTENV", self.root / ".env"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write_config(self, url: str | None) -> None:
        self.config.write_text(
            f"language: de\npaths:\n  root: {self.root}\nnarrata:\n"
            + ("" if url is None else f"  url: '{url}'\n")
            + "  groups:\n    beispielgruppe: 12\n"
            + "  recent_sessions: 5\n  archive_limit: 40\n",
            encoding="utf-8",
        )

    def context(self, *extra: str) -> tuple[int, str, str]:
        return run("context", str(KEY), "--config", str(self.config), *extra)

    def test_fetched_context_is_stored_and_summarized_without_names(self) -> None:
        code, stdout, stderr = self.context()

        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.paths.narrata_context.read_bytes(), self.narrata.body)
        [(path, headers)] = self.narrata.requests
        self.assertEqual(
            path,
            "/api/groups/12/play-sessions/42/transcription-context"
            "?n=5&archive_limit=40",
        )
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
        self.assertIn(
            "beispielgruppe/042: play session 4711, 2026-10-30, contract 1.1", stdout
        )
        self.assertIn("  1 participant(s) (0 gm, 0 former), 0 character(s)\n", stdout)
        self.assertIn(
            "  0 glossary entries (0 pc, 0 session, 0 recent, 0 archive), "
            "archive tier 0 of 0, 0 asr ambiguities",
            stdout,
        )
        self.assertIn(f"wrote {self.paths.narrata_context}", stdout)
        self.assertNotIn(NAME, stdout + stderr)
        self.assertNotIn(TOKEN, stdout + stderr)

    def test_saved_response_takes_the_same_path_without_narrata(self) -> None:
        saved = self.root / "saved.json"
        saved.write_bytes(self.narrata.body)
        self.write_config(None)  # no narrata.url: the file needs no connection

        code, stdout, stderr = self.context("--from-file", str(saved))

        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.paths.narrata_context.read_bytes(), saved.read_bytes())
        self.assertIn("1 participant(s)", stdout)
        self.assertEqual(self.narrata.requests, [])

    def test_unsupported_version_is_not_stored(self) -> None:
        self.narrata.body = encoded(context("2.0"))

        code, stdout, stderr = self.context()

        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("contract_version 2.0 is not supported", stderr)
        self.assertFalse(self.paths.narrata_context.exists())

    def test_participants_are_counted_without_names(self) -> None:
        self.narrata.body = encoded(
            context(
                participants=[
                    participant(user_id=7, role="gm"),
                    participant(
                        is_former=True,
                        characters=[
                            {"person_id": 18, "name": CHARACTER, "aliases": []},
                            {"person_id": 19, "name": "Ilse Erdacht", "aliases": []},
                        ],
                    ),
                ]
            )
        )

        code, stdout, stderr = self.context()

        self.assertEqual(code, 0, stderr)
        self.assertIn("2 participant(s) (1 gm, 1 former), 2 character(s)", stdout)
        self.assertNotIn(NAME, stdout + stderr)
        self.assertNotIn(CHARACTER, stdout + stderr)

    def test_invalid_participants_keep_the_stored_file(self) -> None:
        code, _, stderr = self.context()
        self.assertEqual(code, 0, stderr)
        good = self.paths.narrata_context.read_bytes()
        self.narrata.body = encoded(context(participants=[participant(role=NAME)]))

        code, stdout, stderr = self.context()

        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("participants[0].role missing or invalid", stderr)
        self.assertNotIn(NAME, stderr)
        self.assertEqual(self.paths.narrata_context.read_bytes(), good)

    def test_glossary_is_counted_without_names(self) -> None:
        data = context()
        data["glossary"] = [
            glossary_entry(type="person", id=18, name=CHARACTER, relevance="pc"),
            glossary_entry(),
            glossary_entry(id=6, name="Nebelsee", relevance="archive"),
        ]
        data["glossary_meta"] = {"archive_total": 40, "archive_returned": 1}
        data["asr_ambiguities"] = [
            {
                "variant": VARIANT,
                "entries": [{"type": "place", "id": 5}, {"type": "place", "id": 6}],
            }
        ]
        self.narrata.body = encoded(data)

        code, stdout, stderr = self.context()

        self.assertEqual(code, 0, stderr)
        self.assertIn(
            "  3 glossary entries (1 pc, 1 session, 0 recent, 1 archive), "
            "archive tier 1 of 40, 1 asr ambiguities",
            stdout,
        )
        for value in (CHARACTER, PLACE, ALIAS, VARIANT, SUMMARY, "Nebelsee"):
            self.assertNotIn(value, stdout + stderr)

    def test_invalid_glossary_keeps_the_stored_file(self) -> None:
        code, _, stderr = self.context()
        self.assertEqual(code, 0, stderr)
        good = self.paths.narrata_context.read_bytes()
        data = context()
        data["glossary"] = [glossary_entry(relevance=PLACE)]
        self.narrata.body = encoded(data)

        code, stdout, stderr = self.context()

        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("glossary[0].relevance missing or not a known value", stderr)
        self.assertNotIn(PLACE, stderr)
        self.assertEqual(self.paths.narrata_context.read_bytes(), good)

    def test_rejected_token_is_reported_without_its_value(self) -> None:
        self.narrata.status = 401

        code, _, stderr = self.context()

        self.assertEqual(code, 2)
        self.assertIn("NARRATA_TOKEN is missing or expired", stderr)
        self.assertNotIn(TOKEN, stderr)
        self.assertNotIn("Traceback", stderr)

    def test_missing_settings_name_their_source(self) -> None:
        with mock.patch.dict(os.environ, {"NARRATA_TOKEN": ""}):
            code, _, stderr = self.context()
        self.assertEqual(code, 2)
        self.assertIn("NARRATA_TOKEN is not set", stderr)

        code, _, stderr = run("context", "andere-runde/1", "--config", str(self.config))
        self.assertEqual(code, 2)
        self.assertIn("narrata.groups has no group id for andere-runde", stderr)

        self.write_config(None)
        code, _, stderr = self.context()
        self.assertEqual(code, 2)
        self.assertIn("narrata.url is not set", stderr)

        code, _, stderr = self.context("--from-file", str(self.root / "missing.json"))
        self.assertEqual(code, 2)
        self.assertIn("missing.json: cannot read file", stderr)
        self.assertEqual(self.narrata.requests, [])


class TranscribeCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / "config.yaml"
        self.config.write_text(
            f"language: de\npaths:\n  root: {self.root}\nasr:\n  device: cpu\n",
            encoding="utf-8",
        )
        self.paths = SessionPaths(KEY, self.root)
        self.paths.audio_dir.mkdir(parents=True)
        for segment in MANIFEST_3.segments:
            self.paths.segment_wav(segment.index).write_bytes(b"audio")
        self.backend = session_backend()
        self.diarizers: list[FakeDiarizer] = []
        for patcher in (
            mock.patch.object(retry, "RETRY_DELAY_S", 0),
            mock.patch.object(
                transcript_main.manifest, "load_manifest", return_value=MANIFEST_3
            ),
            mock.patch.object(
                transcript_main.WhisperBackend, "from_config", side_effect=self.created
            ),
            mock.patch.object(
                transcript_main.PyannoteDiarizer,
                "from_config",
                side_effect=self.diarizer,
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def created(self, config: Any) -> FakeBackend:
        self.assertEqual(config.asr_device, "cpu")
        return self.backend

    def diarizer(self, config: Any) -> FakeDiarizer:
        backend = self.backend

        class AfterAsr(FakeDiarizer):
            def load(self) -> None:
                assert not backend.loaded, "diarizer loaded next to Whisper"
                super().load()

        self.diarizers.append(AfterAsr())
        return self.diarizers[-1]

    def transcribe(self, *extra: str) -> tuple[int, str, str]:
        return run("transcribe", str(KEY), "--config", str(self.config), *extra)

    def test_whole_session_prints_counts_per_segment_but_no_text(self) -> None:
        code, stdout, stderr = self.transcribe("--no-diarize")

        self.assertEqual(code, 0, stderr)
        self.assertIn("beispielgruppe/042: 3 segment(s)", stdout)
        self.assertRegex(
            stdout,
            r"  2\. transcribed in \d+\.\d s: 1 passage\(s\), 0 word\(s\), "
            r"0 with confidence, language de",
        )
        self.assertIn(
            "beispielgruppe/042: 3 transcribed, 0 reused, 0 failed, 0 open "
            "with fake fake (rev1)",
            stdout,
        )
        self.assertIn(f"wrote {self.paths.asr_dir}", stdout)
        self.assertEqual(self.backend.load_calls, 1)
        self.assertEqual(self.backend.requests[0].keywords, ())
        self.assertEqual(self.diarizers, [])
        self.assertNotIn(SECRET, stdout + stderr)

    def test_unsupported_contract_version_stops_before_the_asr(self) -> None:
        jsonfile.write_atomic(self.paths.manifest, manifest_module._to_json(MANIFEST_3))
        jsonfile.write_atomic(
            self.paths.narrata_context,
            {"contract_version": "2.0", "session": {"ordinal": KEY.ordinal}},
        )

        # MANIFEST_3 is a made-up timeline with gaps; only the context check counts.
        with (
            mock.patch.object(
                transcript_main.manifest, "load_manifest", REAL_LOAD_MANIFEST
            ),
            mock.patch.object(manifest_module, "_check_timeline"),
        ):
            code, stdout, stderr = self.transcribe()

        self.assertEqual(code, 2)
        self.assertIn("contract_version 2.0 is not supported", stderr)
        self.assertEqual(stdout, "")
        self.assertEqual(self.backend.load_calls, 0)
        self.assertEqual(self.diarizers, [])

    def test_second_run_reuses_without_loading(self) -> None:
        self.transcribe("--no-diarize")
        self.backend = session_backend()

        code, stdout, _ = self.transcribe("--no-diarize")

        self.assertEqual(code, 0)
        self.assertIn("  1. reused: 1 passage(s)", stdout)
        self.assertIn("0 transcribed, 3 reused", stdout)
        self.assertEqual(self.backend.load_calls, 0)

        _, stdout, _ = self.transcribe("--no-diarize", "--force")
        self.assertIn("3 transcribed, 0 reused", stdout)

    def test_segment_option_selects_one_segment(self) -> None:
        code, stdout, _ = self.transcribe("--no-diarize", "--segment", "2")

        self.assertEqual(code, 0)
        self.assertIn("1 transcribed, 0 reused", stdout)
        self.assertEqual(
            [request.audio.name for request in self.backend.requests],
            ["segment-02.wav"],
        )

    def test_failed_segment_gives_exit_1_and_the_run_goes_on(self) -> None:
        self.backend = session_backend(fail_on=2)

        code, stdout, stderr = self.transcribe("--no-diarize")

        self.assertEqual(code, 1)
        self.assertIn(
            "  2. failed after 3 attempt(s): ResourceError (retryable): "
            "fake: out of memory",
            stdout,
        )
        self.assertIn("2 transcribed, 0 reused, 1 failed, 0 open", stdout)
        self.assertIn(
            "WARNING beispielgruppe/042 segment 2: fake: attempt 3/3 failed: "
            "ResourceError: fake: out of memory; giving up",
            stderr,
        )
        self.assertNotIn(SECRET, stdout + stderr)

    def test_passing_failure_is_retried_with_exit_0(self) -> None:
        self.backend = session_backend(errors={2: [ResourceError("fake: oom")]})

        code, stdout, stderr = self.transcribe("--no-diarize")

        self.assertEqual(code, 0)
        self.assertIn("3 transcribed, 0 reused, 0 failed, 0 open", stdout)
        self.assertIn("segment 2: fake: attempt 1/3 failed", stderr)
        self.assertIn("retrying in 0 s", stderr)

    def test_retries_come_from_the_configuration(self) -> None:
        self.config.write_text(
            self.config.read_text(encoding="utf-8") + "  retries: 0\n",
            encoding="utf-8",
        )
        self.backend = session_backend(fail_on=2)

        _, stdout, _ = self.transcribe("--no-diarize")

        self.assertIn("  2. failed after 1 attempt(s)", stdout)

    def test_failed_diarization_gives_exit_1(self) -> None:
        with failing_diarizer(self, AudioInputError("fake-diar: bad audio")):
            code, stdout, stderr = self.transcribe()

        self.assertEqual(code, 1)
        self.assertIn("3 transcribed, 0 reused, 0 failed, 0 open", stdout)
        self.assertIn(
            "  1. failed after 1 attempt(s): AudioInputError (not retryable): "
            "fake-diar: bad audio",
            stdout,
        )
        self.assertIn("segment 1: fake-diar: attempt 1/3 failed", stderr)

    def test_load_failure_leaves_segments_open_with_exit_1(self) -> None:
        self.backend = FailingLoad()

        code, stdout, stderr = self.transcribe("--no-diarize")

        self.assertEqual(code, 1)
        self.assertIn("  3. open", stdout)
        self.assertIn("0 transcribed, 0 reused, 0 failed, 3 open", stdout)
        self.assertEqual(stderr, "error: fake: model not in the local cache\n")

    def test_problems_before_the_run_give_exit_2(self) -> None:
        code, _, stderr = self.transcribe("--no-diarize", "--segment", "4")
        self.assertEqual(code, 2)
        self.assertIn("error: segment 4 not in the manifest", stderr)

        with mock.patch.object(
            FakeDiarizer,
            "identity",
            side_effect=BackendUnavailableError("pyannote: runtime missing"),
        ):
            code, stdout, stderr = self.transcribe()
        self.assertEqual((code, stdout), (2, ""))
        self.assertEqual(stderr, "error: pyannote: runtime missing\n")
        self.assertEqual(self.backend.load_calls, 0)

    def test_diarization_follows_once_whisper_is_closed(self) -> None:
        code, stdout, stderr = self.transcribe("--num-speakers", "2")

        self.assertEqual(code, 0, stderr)
        self.assertIn("beispielgruppe/042: diarization", stdout)
        self.assertRegex(stdout, r"  3\. diarized in \d+\.\d s: 2 label\(s\)")
        self.assertIn(
            f"wrote {self.paths.asr_dir} and {self.paths.diarization_dir}", stdout
        )
        diarizer = self.diarizers[0]
        self.assertEqual(diarizer.load_calls, 1)
        self.assertEqual([call[2] for call in diarizer.diarized], [2, 2, 2])
        for secret in (SECRET, "SPEAKER_"):
            self.assertNotIn(secret, stdout + stderr)


class DiarizeCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / "config.yaml"
        self.config.write_text(
            f"language: de\npaths:\n  root: {self.root}\ndiarization:\n  device: cpu\n",
            encoding="utf-8",
        )
        self.paths = SessionPaths(KEY, self.root)
        self.paths.audio_dir.mkdir(parents=True)
        self.paths.segment_wav(1).write_bytes(b"audio")
        update_reference(
            self.paths,
            minimal(
                passages=(
                    Passage(
                        index=1,
                        text=f" Zum {SECRET}.",
                        words=(Word("Zum", 0, 400), Word(SECRET, 400, 1500)),
                    ),
                )
            ),
        )
        self.manifest = dataclasses.replace(
            MANIFEST, segments=(dataclasses.replace(SEGMENT, index=1),)
        )
        self.diarizers: list[FakeDiarizer] = []
        for patcher in (
            mock.patch.object(retry, "RETRY_DELAY_S", 0),
            mock.patch.object(
                transcript_main.manifest, "load_manifest", return_value=self.manifest
            ),
            mock.patch.object(
                transcript_main.PyannoteDiarizer,
                "from_config",
                side_effect=self.diarizer,
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def diarizer(self, config: Any) -> FakeDiarizer:
        self.assertEqual(config.diarization_device, "cpu")
        self.diarizers.append(FakeDiarizer())
        return self.diarizers[-1]

    def diarize(self, *extra: str) -> tuple[int, str, str]:
        return run("diarize", str(KEY), "--config", str(self.config), *extra)

    def test_prints_counts_and_times_but_no_labels_or_text(self) -> None:
        code, stdout, stderr = self.diarize("--num-speakers", "2")

        self.assertEqual(code, 0, stderr)
        self.assertIn("beispielgruppe/042: 1 segment(s)", stdout)
        self.assertRegex(
            stdout,
            r"1\. diarized in \d+\.\d s: 2 label\(s\), 2 turn\(s\), "
            r"1/2 words labelled",  # the second word lies between turns
        )
        self.assertEqual(self.diarizers[0].diarized[0][2], 2)
        for secret in (SECRET, "SPEAKER_"):
            self.assertNotIn(secret, stdout + stderr)

    def test_second_run_reuses_and_force_diarizes_again(self) -> None:
        self.diarize()

        _, stdout, _ = self.diarize()
        self.assertIn("1. reused stored diarization", stdout)

        _, stdout, _ = self.diarize("--force")
        self.assertIn("1. diarized in", stdout)

    def test_failed_segment_gives_exit_1(self) -> None:
        with failing_diarizer(self, ResourceError("fake-diar: out of memory")):
            code, stdout, stderr = self.diarize()

        self.assertEqual(code, 1)
        self.assertIn(
            "1. failed after 3 attempt(s): ResourceError (retryable): "
            "fake-diar: out of memory",
            stdout,
        )
        self.assertEqual(stderr.count("WARNING beispielgruppe/042 segment 1"), 3)
        self.assertEqual(self.diarizers[0].close_calls, 1)

    def test_invalid_speaker_count_is_rejected_by_argparse(self) -> None:
        with (
            self.assertRaises(SystemExit) as caught,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.diarize("--num-speakers", "0")
        self.assertEqual(caught.exception.code, 2)

    def test_backend_errors_are_reported_without_traceback(self) -> None:
        with mock.patch.object(
            FakeDiarizer,
            "identity",
            side_effect=BackendUnavailableError(
                "pyannote: model not in the local cache"
            ),
        ):
            code, stdout, stderr = self.diarize()

        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("error: pyannote: model not in the local cache", stderr)


if __name__ == "__main__":
    unittest.main()
