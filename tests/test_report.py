import dataclasses
import json

from test_candidates import ONLY_FIRST
from test_decisions import NONE
from test_narrata import NAME, context, encoded, participant
from test_session_time import MANIFEST
from test_speakers import PARTICIPANTS, entry
from test_uncertainty import PROCESSED_AT, diarized, transcript
from test_working import SURE, UNSURE, _WorkingCase, spoken

from transcript.candidates import collect
from transcript.config import DEFAULT_KEYWORD_BUDGET
from transcript.decisions import ReviewDecision, SessionDecisions, write_decisions
from transcript.knowledge import build_snapshot
from transcript.manifest import Manifest
from transcript.narrata import store_context
from transcript.reference import AsrInfo, Failure, ReferenceTranscript, SegmentRef
from transcript.report import (
    Gap,
    LabelReport,
    Note,
    SegmentReport,
    SessionReport,
    Used,
    build,
    compose,
    report_json,
)
from transcript.speakers import SpeakerAssignment, check, write_assignment
from transcript.uncertainty import load_assessment
from transcript.working import WorkingError, write_working
from transcript.working import compose as compose_working

BLOCK_MS = 850  # three made-up words, 300 ms apart and 250 ms long


class _ReportCase(_WorkingCase):
    def report(
        self,
        decisions: SessionDecisions = NONE,
        assignment: SpeakerAssignment | None = None,
        manifest: Manifest = ONLY_FIRST,
        reference: ReferenceTranscript | None = None,
        others: tuple[ReferenceTranscript, ...] = (),
    ) -> SessionReport:
        reference = reference or self.reference
        speakers = check(assignment or SpeakerAssignment(), [reference], PARTICIPANTS)
        stored = self.working(decisions, speakers, manifest, reference)
        found = collect(self.paths, manifest)
        return build(
            stored,
            manifest,
            {r.segment.index: r for r in (reference, *others)},
            found,
            {r.segment: load_assessment(self.paths, r.segment) for r in found.rated},
            assignment,
            "1.1",
        )


def failed_segment(index: int, model: str = "fake") -> ReferenceTranscript:
    return dataclasses.replace(
        transcript(),
        segment=SegmentRef(index, f"segment-{index:02d}.wav", "ab" * 32),
        status="failed",
        error=Failure("ResourceError", retryable=True),
        asr=AsrInfo(backend_id="fake", model=model),
    )


class CountTest(_ReportCase):
    def test_passages_review_and_markers_follow_the_working_version(self) -> None:
        report = self.report(
            self.decided(
                (2, "corrected", "Grauwasser"),
                (3, "confirmed", None),
                (4, "unintelligible", None),
                (5, "deferred", None),
            )
        )

        self.assertEqual(report.passages.total, 6)
        self.assertEqual(
            report.passages.by_origin, {"automatic": 1, "decided": 3, "open": 2}
        )
        self.assertEqual(report.passages.automatic_ms, BLOCK_MS)
        self.assertEqual(report.passages.untimed, 0)
        self.assertEqual(report.review.candidates, 5)
        self.assertEqual(report.review.by_level, {"needs_review": 5, "uncertain": 0})
        self.assertEqual(
            report.review.decided,
            {"confirmed": 1, "corrected": 1, "unintelligible": 1, "kept": 0},
        )
        self.assertEqual(report.review.unresolved, {"open": 1, "deferred": 1})
        self.assertEqual(
            report.markers,
            {
                "unintelligible": 1,
                "unresolved": 2,
                "speaker_unclear": 0,
                "crosstalk": 0,
            },
        )
        self.assertEqual(report.gaps, (Gap("open_passages", (1,)),))

    def test_the_rate_counts_rated_audio_only(self) -> None:
        report = self.report(manifest=MANIFEST)

        found = collect(self.paths, MANIFEST)
        self.assertEqual(report.review.rated_audio_ms, ONLY_FIRST.duration_ms)
        self.assertEqual(report.review.per_hour, found.per_hour)

    def test_a_settled_session_has_no_gap(self) -> None:
        report = self.report(
            self.decided(*((n, "confirmed", None) for n in range(2, 7)))
        )

        self.assertEqual(report.gaps, ())
        self.assertEqual(report.markers["unresolved"], 0)


class SegmentTest(_ReportCase):
    def test_failed_and_missing_segments_are_gaps(self) -> None:
        third = dataclasses.replace(
            MANIFEST.segments[1],
            index=3,
            start_ms=MANIFEST.duration_ms,
            end_ms=MANIFEST.duration_ms + 1000,
        )
        manifest = dataclasses.replace(MANIFEST, segments=(*MANIFEST.segments, third))

        report = self.report(manifest=manifest, others=(failed_segment(2),))

        self.assertEqual(
            report.recording.segments,
            (
                SegmentReport(1, ONLY_FIRST.duration_ms, "transcribed"),
                SegmentReport(
                    2,
                    MANIFEST.segments[1].duration_ms,
                    "failed",
                    Failure("ResourceError", retryable=True),
                ),
                SegmentReport(3, 1000, "missing"),
            ),
        )
        self.assertEqual(report.recording.duration_ms, manifest.duration_ms)
        self.assertIn(Gap("failed_segment", (2,)), report.gaps)
        self.assertIn(Gap("missing_segment", (3,)), report.gaps)
        self.assertNotIn("working_findings", [g.code for g in report.gaps])

    def test_differing_configurations_are_listed_with_their_segments(self) -> None:
        report = self.report(
            manifest=MANIFEST, others=(failed_segment(2, model="other"),)
        )

        self.assertEqual(
            [(u.values["model"], u.segments) for u in report.pipeline.asr],
            [("fake", (1,)), ("other", (2,))],
        )
        self.assertEqual(len(report.pipeline.thresholds), 1)
        self.assertEqual(report.pipeline.thresholds[0].segments, (1,))
        self.assertEqual(
            report.pipeline.diarization,
            (
                Used(
                    {
                        "backend_id": "fake",
                        "model": "fake",
                        "model_version": None,
                        "settings": {},
                        "num_speakers": None,
                    },
                    (1,),
                ),
            ),
        )
        self.assertEqual(report.pipeline.knowledge_snapshot_id, "snapshot")
        self.assertEqual(report.pipeline.context_contract_version, "1.1")

    def test_a_decision_not_applied_is_a_gap(self) -> None:
        orphan = ReviewDecision(1, 1, PROCESSED_AT, "corrected", "x", "Grauwasser")

        report = self.report(SessionDecisions((orphan,)))

        self.assertIn(Gap("working_findings", (1,)), report.gaps)
        self.assertEqual(report.findings, {"orphaned_decision": 1})


class SpeakerTest(_ReportCase):
    def setUp(self) -> None:
        super().setUp()
        self.two = transcript(
            spoken(1, *SURE, label="SPEAKER_00"),
            spoken(2, *UNSURE, label="SPEAKER_01"),
            spoken(3, *SURE, label="SPEAKER_00"),
            diarization=diarized(),
        )
        self.rated(self.two)

    def test_labels_count_per_segment_and_persons_only_as_a_number(self) -> None:
        assignment = SpeakerAssignment(
            (entry(self.two, "SPEAKER_00", 11),), effort_minutes=12
        )

        report = self.report(assignment=assignment, reference=self.two)

        self.assertEqual(
            report.speakers.labels,
            (
                LabelReport(1, "SPEAKER_00", "person", 2 * BLOCK_MS),
                LabelReport(1, "SPEAKER_01", "open", BLOCK_MS),
            ),
        )
        self.assertEqual(
            report.speakers.by_assigned,
            {"open": 1, "person": 1, "unknown": 0, "multiple": 0},
        )
        self.assertEqual(report.speakers.persons, 1)
        self.assertEqual(report.speakers.effort_minutes, 12)
        self.assertEqual(report.speakers.diarized_segments, (1,))
        codes = [note.code for note in report.notes]
        self.assertNotIn("effort_not_recorded", codes)
        self.assertNotIn("no_assignment", codes)

    def test_missing_assignment_and_effort_are_notes(self) -> None:
        without = self.report(reference=self.two)
        unrecorded = self.report(
            assignment=SpeakerAssignment((entry(self.two, "SPEAKER_00", 11),)),
            reference=self.two,
        )

        self.assertIn(Note("no_assignment"), without.notes)
        self.assertIsNone(without.speakers.effort_minutes)
        self.assertIn(Note("effort_not_recorded"), unrecorded.notes)
        self.assertNotIn(Note("no_assignment"), unrecorded.notes)

    def test_the_report_names_no_person_and_holds_no_text(self) -> None:
        assignment = SpeakerAssignment((entry(self.two, "SPEAKER_00", 11),))

        written = json.dumps(
            report_json(
                self.report(
                    self.decided((2, "corrected", "Grauwasser")),
                    assignment=assignment,
                    reference=self.two,
                )
            )
        )

        for absent in ("user_id", "wort", "Grauwasser", NAME, "display_name"):
            self.assertNotIn(absent, written)


class NoteTest(_ReportCase):
    def test_missing_data_is_named_per_segment(self) -> None:
        reference = transcript(
            spoken(1, *SURE, label=None),
            dataclasses.replace(spoken(2, *UNSURE, label=None), start_ms=None),
        )
        self.rated(reference)

        report = self.report(reference=reference)

        self.assertEqual(
            report.notes,
            (
                Note("no_diarization", (1,)),
                Note("untimed_passages", (1,)),
                Note("segment_without_hints", (1,)),
                Note("snapshot_differs", (1,)),
            ),
        )
        self.assertEqual(report.passages.untimed, 1)
        self.assertEqual(report.speakers.labels, ())


class ComposeTest(_ReportCase):
    def setUp(self) -> None:
        super().setUp()
        store_context(
            self.paths, encoded(context(participants=[participant(user_id=11)]))
        )
        build_snapshot(self.paths, DEFAULT_KEYWORD_BUDGET)

    def test_the_stored_working_version_is_reported(self) -> None:
        write_assignment(
            self.paths,
            SpeakerAssignment(
                (entry(self.reference, "SPEAKER_00", 11),), effort_minutes=5
            ),
        )
        write_working(self.paths, compose_working(self.paths, ONLY_FIRST))

        report = compose(self.paths, ONLY_FIRST)

        self.assertEqual(report.passages.total, 6)
        self.assertEqual(report.speakers.effort_minutes, 5)
        self.assertEqual(report.pipeline.context_contract_version, "1.1")

    def test_without_working_version_there_is_no_report(self) -> None:
        with self.assertRaisesRegex(WorkingError, "not found; run transcript working"):
            compose(self.paths, ONLY_FIRST)

    def test_an_outdated_working_version_is_refused(self) -> None:
        write_working(self.paths, compose_working(self.paths, ONLY_FIRST))
        write_decisions(self.paths, self.decided((2, "confirmed", None)))

        with self.assertRaisesRegex(WorkingError, "outdated; run transcript working"):
            compose(self.paths, ONLY_FIRST)
