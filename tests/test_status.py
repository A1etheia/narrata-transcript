import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from media import TOOLS, needs_media, sine, synth
from test_narrata import CHARACTER, NAME, context, encoded
from test_narrata import participant as participant_json
from test_reference import KEY, SECRET, minimal
from test_review_sheet import parsed, save_rows
from test_smoke import _ExportableSession, run

from transcript import candidates, decisions, knowledge, manifest, review_sheet, status
from transcript.audio import extract, find_recordings, probe
from transcript.config import UncertaintyThresholds, load_config
from transcript.knowledge import build_snapshot, load_snapshot
from transcript.manifest import build_manifest
from transcript.narrata import store_context
from transcript.reference import (
    AsrInfo,
    Diarization,
    Failure,
    Passage,
    Processing,
    SegmentRef,
    Word,
    write_reference,
)
from transcript.session import SessionPaths
from transcript.uncertainty import assess_session


@needs_media
class StatusTestCase(unittest.TestCase):
    """Real ffmpeg for the recordings; Narrata context and names are made up."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config_path = self.root / "config.yaml"
        self.config_path.write_text(
            f"language: de\npaths:\n  root: {self.root}\n", encoding="utf-8"
        )
        self.config = load_config(self.config_path)
        self.paths = SessionPaths(KEY, self.root)

    def recording(self, name: str = "aufnahme 1.mp3", seconds: float = 1) -> Path:
        self.paths.input_dir.mkdir(parents=True, exist_ok=True)
        return synth(self.paths.input_dir / name, *sine(seconds))

    def store_context(self, **session: object) -> None:
        store_context(
            self.paths, encoded(context(participants=[participant_json()], **session))
        )

    def extract(self) -> None:
        assert TOOLS is not None
        infos = [probe(path, TOOLS) for path in find_recordings(self.paths)]
        extract(infos, self.paths, self.config, TOOLS)

    def prepared(self, recordings: int = 1) -> None:
        """Recordings, context, snapshot, extracted audio and the manifest."""
        for number in range(1, recordings + 1):
            self.recording(f"aufnahme {number}.mp3")
        self.store_context()
        build_snapshot(self.paths, self.config.keyword_budget)
        self.extract()
        build_manifest(self.paths, consent=True)

    def reference(
        self,
        index: int = 1,
        diarized: bool = True,
        processed_at: str = "2026-11-04T20:00:00+01:00",
        **changes: Any,
    ) -> None:
        """A transcribed segment as `transcribe` stores it, rated."""
        values: dict[str, Any] = {
            "segment": SegmentRef(index, f"segment-{index:02d}.wav", "ab" * 32),
            "asr": AsrInfo(
                backend_id="fake",
                model="fake",
                knowledge_snapshot_id=load_snapshot(self.paths).snapshot_id,
            ),
            "processing": Processing(
                pipeline_version="0.0.1", processed_at=processed_at
            ),
            "passages": (
                Passage(
                    index=1,
                    text=f" Zum {SECRET}.",
                    start_ms=0,
                    end_ms=900,
                    words=(Word(f" {SECRET}", 0, 900, 0.9, "SPEAKER_00"),),
                    speaker="SPEAKER_00",
                ),
            ),
        }
        if diarized:
            values["diarization"] = Diarization(
                backend_id="fake", model="fake", labels=("SPEAKER_00",)
            )
        else:
            values["passages"] = ()
        values.update(changes)
        write_reference(self.paths, minimal(**values), {})
        assess_session(self.paths, [index], UncertaintyThresholds())

    def failed(self, index: int = 1) -> None:
        write_reference(
            self.paths,
            minimal(
                segment=SegmentRef(index, f"segment-{index:02d}.wav", "ab" * 32),
                status="failed",
                error=Failure(category="ResourceError", retryable=True),
            ),
            None,
        )

    def statuses(self) -> dict[str, tuple[str, str]]:
        found = status.inspect(self.paths, self.config).steps
        for step in found:
            for secret in (SECRET, NAME, CHARACTER, "SPEAKER_"):
                self.assertNotIn(secret, step.detail)
        return {step.step: (step.state, step.detail) for step in found}

    def state(self, step: str) -> str:
        return self.statuses()[step][0]


class OrderTest(StatusTestCase):
    def test_lists_every_step_with_a_file_in_run_order(self) -> None:
        self.assertEqual(
            list(self.statuses()),
            [
                "extract",
                "context",
                "snapshot",
                "manifest",
                "transcribe",
                "review",
                "speakers",
                "working",
                "export",
                "txt",
                "docx",
                "report",
            ],
        )

    def test_a_prepared_session_has_nothing_transcribed(self) -> None:
        self.prepared()

        states = {step: state for step, (state, _) in self.statuses().items()}

        self.assertEqual(
            [step for step, state in states.items() if state != "pending"],
            ["extract", "context", "snapshot", "manifest"],
        )
        found = status.inspect(self.paths, self.config)
        self.assertEqual(found.overall, "open")
        self.assertEqual(found.last_done, "manifest")
        self.assertEqual(found.resume_from, "transcribe")
        self.assertEqual(found.command, f"transcript process {KEY}")


class ExtractTest(StatusTestCase):
    def test_without_recordings_it_fails(self) -> None:
        self.assertEqual(self.state("extract"), "failed")

    def test_a_recording_alone_is_pending(self) -> None:
        self.recording()

        self.assertEqual(self.state("extract"), "pending")

    def test_extracted_audio_is_done(self) -> None:
        self.recording()
        self.extract()

        self.assertEqual(self.statuses()["extract"], ("done", "1 recording(s)"))

    def test_a_changed_recording_makes_it_stale(self) -> None:
        self.recording()
        self.extract()
        self.recording(seconds=2)

        state, detail = self.statuses()["extract"]

        self.assertEqual(state, "stale")
        self.assertIn("does not match the recordings", detail)

    def test_a_missing_segment_wav_makes_it_stale(self) -> None:
        self.recording()
        self.extract()
        self.paths.segment_wav(1).unlink()

        self.assertEqual(self.state("extract"), "stale")


class ContextSnapshotManifestTest(StatusTestCase):
    def test_missing_files_are_pending(self) -> None:
        for step in ("context", "snapshot", "manifest"):
            self.assertEqual(self.state(step), "pending", step)

    def test_an_unreadable_context_is_stale(self) -> None:
        self.store_context()
        self.paths.narrata_context.write_text("{}", encoding="utf-8")

        self.assertEqual(self.state("context"), "stale")

    def test_a_snapshot_behind_the_context_is_still_done_with_a_note(self) -> None:
        self.store_context()
        build_snapshot(self.paths, self.config.keyword_budget)
        short = load_snapshot(self.paths).snapshot_id[: knowledge.SHORT_ID]
        self.assertEqual(self.statuses()["snapshot"], ("done", f"snapshot {short}"))

        self.store_context(session_date="2026-11-05")

        state, detail = self.statuses()["snapshot"]
        self.assertEqual(state, "done")
        self.assertIn(knowledge.BEHIND_CONTEXT, detail)

    def test_an_unreadable_snapshot_is_stale(self) -> None:
        self.store_context()
        build_snapshot(self.paths, self.config.keyword_budget)
        self.paths.knowledge_snapshot.write_text("{}", encoding="utf-8")

        self.assertEqual(self.state("snapshot"), "stale")

    def test_the_manifest_counts_segments_and_names_a_missing_consent(self) -> None:
        self.prepared()
        self.assertEqual(self.statuses()["manifest"], ("done", "1 segment(s)"))

        data = json.loads(self.paths.manifest.read_text(encoding="utf-8"))
        data["consent"] = None
        self.paths.manifest.write_text(json.dumps(data), encoding="utf-8")

        self.assertEqual(
            self.statuses()["manifest"], ("done", "1 segment(s), no consent note")
        )

    def test_an_unreadable_manifest_is_stale(self) -> None:
        self.prepared()
        self.paths.manifest.write_text("{}", encoding="utf-8")

        self.assertEqual(self.state("manifest"), "stale")
        self.assertEqual(self.state("transcribe"), "stale")


class TranscribeTest(StatusTestCase):
    def test_without_a_manifest_it_waits_for_it(self) -> None:
        self.assertEqual(
            self.statuses()["transcribe"], ("pending", "needs the manifest")
        )

    def test_a_rated_and_diarized_segment_is_done(self) -> None:
        self.prepared()
        self.reference()

        self.assertEqual(
            self.statuses()["transcribe"],
            ("done", "1 of 1 segment(s) transcribed"),
        )

    def test_a_segment_without_speaker_labels_is_partial(self) -> None:
        self.prepared()
        self.reference(diarized=False)

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "partial")
        self.assertIn("no speaker labels: 1", detail)

    def test_a_missing_segment_among_transcribed_ones_is_partial(self) -> None:
        self.prepared(recordings=2)
        self.reference(index=1)

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "partial")
        self.assertIn("1 of 2 segment(s) transcribed", detail)
        self.assertIn("missing: 2", detail)

    def test_a_failed_segment_fails_the_step(self) -> None:
        self.prepared(recordings=2)
        self.reference(index=1)
        self.failed(index=2)

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "failed")
        self.assertIn("failed: 2", detail)

    def test_a_transcript_of_another_snapshot_is_stale(self) -> None:
        self.prepared()
        self.reference()
        self.store_context(session_date="2026-11-05")
        build_snapshot(self.paths, self.config.keyword_budget)

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "stale")
        self.assertIn("other snapshot: 1", detail)

    def test_a_rating_of_an_earlier_transcript_is_stale(self) -> None:
        self.prepared()
        self.reference()
        assessment = self.paths.review_uncertainty(1).read_bytes()
        self.reference(processed_at="2026-11-05T20:00:00+01:00")
        self.paths.review_uncertainty(1).write_bytes(assessment)

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "stale")
        self.assertIn("rating outdated: 1", detail)

    def test_a_missing_rating_is_stale(self) -> None:
        self.prepared()
        self.reference()
        self.paths.review_uncertainty(1).unlink()

        self.assertEqual(self.state("transcribe"), "stale")

    def test_an_unreadable_transcript_is_stale(self) -> None:
        self.prepared()
        self.reference()
        self.paths.reference(1).write_text("{}", encoding="utf-8")

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "stale")
        self.assertIn("unreadable: 1", detail)


class LaterStepsTest(_ExportableSession):
    """A diarized, rated session; the later steps run as their commands."""

    def setUp(self) -> None:
        super().setUp()
        self.found = candidates.session_candidates(
            self.paths, manifest.load_manifest(self.paths)
        )
        self.loaded = load_config(self.with_groups)

    def cli(self, command: str) -> int:
        code, _, stderr = run(command, str(KEY), "--config", str(self.with_groups))
        self.assertIn(code, (0, 1), stderr)
        return code

    def statuses(self) -> dict[str, tuple[str, str]]:
        found = status.inspect(self.paths, self.loaded).steps
        self.assert_nothing_secret(" ".join(step.detail for step in found))
        return {step.step: (step.state, step.detail) for step in found}

    def state(self, step: str) -> str:
        return self.statuses()[step][0]

    def decide_all(self) -> None:
        made = decisions.SessionDecisions()
        for candidate in self.found.candidates:
            made = decisions.decide(made, self.found, candidate.id, "confirmed")
        decisions.write_decisions(self.paths, made)

    def assignment(self) -> dict[str, Any]:
        return json.loads(self.paths.speaker_assignment.read_text(encoding="utf-8"))

    def save_assignment(self, data: dict[str, Any]) -> None:
        self.paths.speaker_assignment.write_text(json.dumps(data), encoding="utf-8")

    def produce(self) -> None:
        """Every file from the working version to the report, from the inputs."""
        for command in ("working", "export", "txt", "docx", "report"):
            self.cli(command)

    def test_review_without_a_sheet_is_pending_while_candidates_are_open(
        self,
    ) -> None:
        self.assertTrue(self.found.candidates)

        state, detail = self.statuses()["review"]

        self.assertEqual(state, "pending")
        self.assertIn(f"{len(self.found.candidates)} open", detail)

    def test_an_untouched_sheet_waits_for_a_person(self) -> None:
        self.cli("review-export")

        state, detail = self.statuses()["review"]

        self.assertEqual(state, "waiting")
        self.assertIn(f"fill in {self.paths.review_sheet}", detail)

    def test_a_filled_sheet_waits_until_it_is_imported(self) -> None:
        self.cli("review-export")
        rows = parsed(
            review_sheet.review_sheet(self.found, decisions.load_decisions(self.paths))
        )
        for row in rows:
            row["status"] = "confirmed"
        save_rows(self.paths.review_sheet, rows)

        state, detail = self.statuses()["review"]
        self.assertEqual(state, "waiting")
        self.assertIn("not imported yet", detail)

        self.cli("review-import")

        self.assertEqual(self.statuses()["review"], ("done", self.counts(0)))

    def counts(self, still_open: int) -> str:
        return f"{len(self.found.candidates)} candidate(s), {still_open} open"

    def test_every_candidate_decided_is_done_without_a_sheet(self) -> None:
        self.decide_all()

        self.assertEqual(self.statuses()["review"], ("done", self.counts(0)))

    def test_an_untouched_template_waits_for_a_person(self) -> None:
        self.assertEqual(self.state("speakers"), "pending")
        self.speakers()

        state, detail = self.statuses()["speakers"]

        self.assertEqual(state, "waiting")
        self.assertIn("2 label(s)", detail)
        self.assertIn("2 open", detail)

    def test_some_labels_open_is_partial_all_settled_is_done(self) -> None:
        self.speakers()
        data = self.assignment()
        data["entries"][0].update(assigned="unknown")
        self.save_assignment(data)

        self.assertEqual(self.state("speakers"), "partial")

        self.assign_all()

        self.assertEqual(self.state("speakers"), "done")

    def test_an_entry_that_does_not_apply_fails(self) -> None:
        self.assign_all()
        data = self.assignment()
        data["entries"][0].update(segment=99)
        self.save_assignment(data)

        state, detail = self.statuses()["speakers"]

        self.assertEqual(state, "failed")
        self.assertIn("1 entry(ies) not applied", detail)

    def test_files_built_from_the_current_inputs_are_done(self) -> None:
        self.decide_all()
        self.assign_all()
        for step in ("working", "export", "txt", "docx", "report"):
            self.assertEqual(self.state(step), "pending", step)

        self.produce()

        found = self.statuses()
        for step in ("review", "speakers", "working", "export", "txt", "docx"):
            self.assertEqual(found[step][0], "done", (step, found[step]))
        self.assertEqual(found["report"][0], "done", found["report"])

    def test_a_changed_input_makes_every_later_file_stale(self) -> None:
        self.decide_all()
        self.assign_all()
        self.produce()
        data = self.assignment()
        data["entries"][0].update(assigned="open")
        self.save_assignment(data)

        found = self.statuses()

        for step in ("working", "export", "txt", "docx", "report"):
            self.assertEqual(found[step][0], "stale", (step, found[step]))

    def test_a_file_edited_by_hand_is_stale(self) -> None:
        self.decide_all()
        self.assign_all()
        self.produce()
        for path in (self.paths.transcript_text, self.paths.report_markdown):
            path.write_text("edited\n", encoding="utf-8")

        found = self.statuses()

        self.assertEqual(found["export"][0], "done")
        self.assertEqual(found["txt"][0], "stale")
        self.assertEqual(found["report"][0], "stale")

    def test_gaps_make_the_export_and_report_partial(self) -> None:
        self.assign_all()
        self.produce()  # the candidate stays open

        found = self.statuses()

        self.assertEqual(found["export"][0], "partial")
        self.assertIn("gaps: open_passages (1)", found["export"][1])
        self.assertEqual(found["report"][0], "partial")
        self.assertIn("open_passages (1)", found["report"][1])


def _steps(**states: str) -> tuple[status.StepStatus, ...]:
    """Every step done unless named; `redo_<step>` marks the step for `--redo`."""
    return tuple(
        status.StepStatus(name, states.get(name, "done"), redo=f"redo_{name}" in states)
        for name in status.STEPS
    )


class SummarizeTest(unittest.TestCase):
    paths = SessionPaths(KEY, Path("/nonexistent"))

    def summary(self, **states: str) -> status.SessionStatus:
        return status.summarize(self.paths, _steps(**states))

    def test_every_step_pending_is_not_started(self) -> None:
        names = {name: "pending" for name in status.STEPS}

        found = self.summary(**names)

        self.assertEqual(found.overall, "not_started")
        self.assertIsNone(found.last_done)
        self.assertEqual(found.resume_from, "extract")
        self.assertEqual(found.command, f"transcript process {KEY}")

    def test_everything_done_is_complete_with_nothing_to_resume(self) -> None:
        found = self.summary()

        self.assertEqual(found.overall, "complete")
        self.assertEqual(found.last_done, "report")
        self.assertIsNone(found.resume_from)
        self.assertIsNone(found.command)

    def test_a_gap_is_partial_and_needs_no_run(self) -> None:
        found = self.summary(report="partial", speakers="partial")

        self.assertEqual(found.overall, "partial")
        self.assertEqual(found.last_done, "report")
        self.assertIsNone(found.resume_from)

    def test_an_incomplete_transcription_is_run_again(self) -> None:
        found = self.summary(transcribe="partial", report="partial")

        self.assertEqual(found.overall, "partial")
        self.assertEqual(found.resume_from, "transcribe")

    def test_ranking_failed_then_waiting_then_open(self) -> None:
        self.assertEqual(
            self.summary(speakers="waiting", txt="failed").overall, "failed"
        )
        self.assertEqual(
            self.summary(review="waiting", export="stale").overall,
            "waiting_for_review",
        )
        self.assertEqual(self.summary(export="stale").overall, "open")
        self.assertEqual(self.summary(report="pending").overall, "open")

    def test_resume_is_the_first_unfinished_step(self) -> None:
        found = self.summary(review="waiting", export="stale")

        self.assertEqual(found.last_done, "transcribe")
        self.assertEqual(found.resume_from, "review")
        self.assertEqual(found.command, f"transcript process {KEY}")

    def test_a_stale_reused_file_needs_redo(self) -> None:
        found = self.summary(extract="stale", redo_extract="1")

        self.assertEqual(found.resume_from, "extract")
        self.assertEqual(found.command, f"transcript process {KEY} --redo extract")


if __name__ == "__main__":
    unittest.main()
