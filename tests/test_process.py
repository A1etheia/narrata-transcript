"""`transcript process`: the steps wired to their commands, halts and reruns."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_reference import KEY
from test_smoke import _ExportableSession, run

from transcript import __main__ as transcript_main
from transcript import candidates, decisions, manifest
from transcript.session import SessionPaths

# the commands before the manual steps; they need models, ffmpeg or Narrata
EARLY = ("_doctor", "_extract", "_context", "_snapshot", "_manifest", "_transcribe")
LATER = ("_working", "_export", "_render", "_report")


class _Patched(unittest.TestCase):
    """Every command a mock returning 0; review and speakers wait to be filled."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / "config.yaml"
        self.config.write_text(
            f"language: de\npaths:\n  root: {self.root}\n", encoding="utf-8"
        )
        self.paths = SessionPaths(KEY, self.root)
        self.mocks: dict[str, mock.Mock] = {}
        for name in (*EARLY, *LATER):
            self.patch(name, 0)
        self.patch("_review_export", 0, writes=self.paths.review_sheet)
        self.patch("_speakers", 0, writes=self.paths.speaker_assignment)
        self.patch_reusable_extract(False)

    def patch(self, name: str, value: int, writes: Path | None = None) -> mock.Mock:
        """Replace the command `name`; it returns `value` and writes `writes`."""

        def command(*_: object, **__: object) -> int:
            if writes is not None:
                self.touch(writes)
            return value

        patcher = mock.patch.object(transcript_main, name, side_effect=command)
        self.mocks[name] = patcher.start()
        self.addCleanup(patcher.stop)
        return self.mocks[name]

    def patch_reusable_extract(self, value: bool) -> None:
        patcher = mock.patch.object(
            transcript_main.audio, "find_recordings", return_value=()
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.paths.audio_dir.mkdir(parents=True, exist_ok=True)
        if value:
            self.paths.audio_metadata.write_text("{}", encoding="utf-8")

    def process(self, *options: str) -> tuple[int, str, str]:
        return run("process", str(KEY), "--config", str(self.config), *options)

    def touch(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")


class WiringTest(_Patched):
    def test_a_new_session_halts_for_review_and_speakers(self) -> None:
        code, stdout, stderr = self.process()

        self.assertEqual(code, 3, stderr)
        for name in (*EARLY, "_review_export", "_speakers"):
            self.mocks[name].assert_called_once()
        for name in LATER:
            self.mocks[name].assert_not_called()
        self.assertIn("process: halted for manual steps", stdout)
        self.assertIn(
            f"review: fill in the decisions in {self.paths.review_sheet}", stdout
        )
        self.assertIn(
            f"speakers: assign the labels in {self.paths.speaker_assignment}", stdout
        )
        self.assertIn(f"then run transcript process {KEY} again", stdout)
        self.assertIn("review halted, speakers halted", stdout)

    def test_without_candidates_the_review_does_not_halt(self) -> None:
        self.patch("_review_export", 0)  # writes no sheet without rows

        code, stdout, _ = self.process()

        self.assertEqual(code, 3)  # the speakers still do
        self.assertTrue(self.mocks["_review_export"].call_args.kwargs["skip_empty"])
        self.assertIn("review ran, speakers halted", stdout)
        self.assertNotIn("review: fill in", stdout)

    def test_filled_files_are_read_and_the_run_goes_on(self) -> None:
        self.touch(self.paths.review_sheet)
        self.touch(self.paths.speaker_assignment)
        self.patch("_review_import", 0)

        code, _, stderr = self.process()

        self.assertEqual(code, 0, stderr)
        self.mocks["_review_import"].assert_called_once()
        self.mocks["_review_export"].assert_not_called()
        self.assertEqual(
            [c.args[2] for c in self.mocks["_render"].call_args_list], ["txt", "docx"]
        )
        self.mocks["_report"].assert_called_once()

    def test_a_gap_in_the_report_gives_exit_1(self) -> None:
        self.touch(self.paths.review_sheet)
        self.touch(self.paths.speaker_assignment)
        self.patch("_review_import", 0)
        self.patch("_report", 1)

        code, stdout, _ = self.process()

        self.assertEqual(code, 1)
        self.assertIn("report incomplete", stdout)

    def test_a_failed_step_is_named_and_stops_the_run(self) -> None:
        self.patch("_snapshot", 2)

        code, stdout, stderr = self.process()

        self.assertEqual(code, 2)
        self.assertIn("process: stopped at snapshot (exit 2)", stderr)
        self.assertIn("snapshot failed", stdout)
        self.mocks["_manifest"].assert_not_called()

    def test_an_incomplete_transcription_stops_before_the_review(self) -> None:
        self.patch("_transcribe", 1)

        code, _, stderr = self.process()

        self.assertEqual(code, 1)
        self.assertIn("process: stopped at transcribe (exit 1)", stderr)
        self.mocks["_review_export"].assert_not_called()

    def test_files_in_place_are_reused(self) -> None:
        self.patch_reusable_extract(True)
        self.touch(self.paths.narrata_context)
        self.touch(self.paths.manifest)

        _, stdout, _ = self.process()

        for name in ("_extract", "_context", "_manifest"):
            self.mocks[name].assert_not_called()
        self.assertIn("extract reused, context reused, snapshot ran", stdout)
        self.assertIn("manifest reused", stdout)

    def test_redo_forces_the_step_and_runs_the_later_ones(self) -> None:
        self.touch(self.paths.narrata_context)
        self.touch(self.paths.manifest)

        _, stdout, _ = self.process("--redo", "snapshot", "--num-speakers", "4")

        self.mocks["_context"].assert_not_called()
        self.assertTrue(self.mocks["_snapshot"].call_args.args[2])  # refresh
        self.mocks["_manifest"].assert_called_once()
        transcribe = self.mocks["_transcribe"].call_args
        self.assertFalse(transcribe.args[3])  # not forced
        self.assertEqual(transcribe.kwargs["num_speakers"], 4)
        self.assertIn("process: snapshot (redo)", stdout)

    def test_consent_renews_a_manifest_without_it(self) -> None:
        self.touch(self.paths.manifest)
        without = mock.Mock(consent=None)

        with mock.patch.object(manifest, "load_manifest", return_value=without):
            self.process("--consent")

        self.assertTrue(self.mocks["_manifest"].call_args.args[2])

    def test_an_invalid_session_key_is_an_error(self) -> None:
        code, _, stderr = run("process", "nonsense", "--config", str(self.config))

        self.assertEqual(code, 2)
        self.assertIn("error:", stderr)
        self.mocks["_doctor"].assert_not_called()


class RerunTest(_ExportableSession):
    """The real manual steps and everything after them, on a diarized session."""

    def setUp(self) -> None:
        super().setUp()
        candidates.session_candidates(self.paths, manifest.load_manifest(self.paths))
        for name in EARLY:
            patcher = mock.patch.object(transcript_main, name, return_value=0)
            patcher.start()
            self.addCleanup(patcher.stop)

    def process(self) -> tuple[int, str, str]:
        return run("process", str(KEY), "--config", str(self.with_groups))

    def test_halts_once_then_runs_to_the_report_with_everything_open(self) -> None:
        code, stdout, stderr = self.process()

        self.assertEqual(code, 3, stderr)
        self.assertTrue(self.paths.review_sheet.is_file())
        self.assertTrue(self.paths.speaker_assignment.is_file())
        self.assertFalse(self.paths.transcript_export.exists())
        self.assert_nothing_secret(stdout + stderr)

        code, stdout, stderr = self.process()

        self.assertEqual(code, 1, stderr)  # open passage and labels are gaps
        for path in (
            self.paths.transcript_export,
            self.paths.transcript_text,
            self.paths.transcript_document,
            self.paths.report_json,
        ):
            self.assertTrue(path.is_file(), path)
        self.assertIn("gap: open_speakers (segment 1)", stderr)
        self.assertIn("gap: open_passages (segment 1)", stderr)
        self.assertIn("report incomplete", stdout)
        self.assert_nothing_secret(stdout + stderr)

    def test_a_session_with_everything_decided_halts_for_the_speakers_only(
        self,
    ) -> None:
        found = candidates.load_candidates(self.paths)
        decisions.write_decisions(
            self.paths,
            decisions.decide(
                decisions.SessionDecisions(),
                found,
                found.candidates[0].id,
                "confirmed",
            ),
        )

        code, stdout, _ = self.process()

        self.assertEqual(code, 3)
        self.assertFalse(self.paths.review_sheet.exists())
        self.assertIn("review: no candidate to decide", stdout)
        self.assertIn("review ran, speakers halted", stdout)


if __name__ == "__main__":
    unittest.main()
