import dataclasses
import json
from typing import Any

from test_candidates import ONLY_FIRST, _SessionCase
from test_decisions import MOMENT, NONE
from test_narrata import context, encoded, participant
from test_session_time import MANIFEST
from test_speakers import PARTICIPANTS, entry
from test_uncertainty import PROCESSED_AT, diarized, passage, transcript, words

from transcript.candidates import candidate_id, collect
from transcript.config import DEFAULT_KEYWORD_BUDGET
from transcript.decisions import (
    ReviewDecision,
    ReviewStatus,
    SessionDecisions,
    decide,
    write_decisions,
)
from transcript.jsonfile import DataFileError
from transcript.knowledge import build_snapshot
from transcript.manifest import Manifest
from transcript.narrata import store_context
from transcript.reference import Passage, Processing, ReferenceTranscript
from transcript.speakers import (
    SpeakerAssignment,
    SpeakerMap,
    SpeakerRef,
    check,
    write_assignment,
)
from transcript.working import (
    WorkingError,
    WorkingFinding,
    WorkingTranscript,
    build,
    compose,
    load_working,
    write_working,
)

UNSURE = (0.3, 0.9, 0.9)  # needs_review
SURE = (0.9, 0.9, 0.9)  # confident


def spoken(
    index: int, *confidences: float, label: str | None = "SPEAKER_00"
) -> Passage:
    """A passage whose words, and so the passage itself, carry `label`."""
    found = tuple(dataclasses.replace(w, speaker=label) for w in words(*confidences))
    return passage(found, index=index, speaker=label)


def transcribed_again(reference: ReferenceTranscript) -> ReferenceTranscript:
    return dataclasses.replace(
        reference, processing=Processing("0.0.1", "2026-11-09T20:00:00+01:00")
    )


class _WorkingCase(_SessionCase):
    """A segment of a confident passage followed by five review candidates."""

    def setUp(self) -> None:
        super().setUp()
        self.reference = transcript(
            spoken(1, *SURE),
            *(spoken(n, *UNSURE) for n in range(2, 7)),
            diarization=diarized(),
        )
        self.rated(self.reference)

    def decided(
        self, *decisions: tuple[int, ReviewStatus, str | None]
    ) -> SessionDecisions:
        found = collect(self.paths, ONLY_FIRST)
        result = NONE
        for passage_index, status, target_text in decisions:
            result = decide(
                result,
                found,
                candidate_id(1, passage_index),
                status,
                target_text=target_text,
                now=MOMENT,
            )
        return result

    def working(
        self,
        decisions: SessionDecisions = NONE,
        speakers: SpeakerMap | None = None,
        manifest: Manifest = ONLY_FIRST,
        reference: ReferenceTranscript | None = None,
    ) -> WorkingTranscript:
        reference = reference or self.reference
        speakers = speakers or check(SpeakerAssignment(), [reference], PARTICIPANTS)
        found = collect(self.paths, manifest)
        return build(
            [reference],
            found,
            decisions,
            speakers,
            knowledge_snapshot_id="snapshot",
            decisions_sha256=None,
            assignment_sha256=None,
        )


class DecisionRuleTest(_WorkingCase):
    def test_each_decision_gives_its_text(self) -> None:
        result = self.working(
            self.decided(
                (2, "confirmed", None),
                (3, "corrected", "Grauwasser"),
                (4, "unintelligible", None),
                (5, "kept", None),
            )
        )

        outcome = [(b.origin, b.status, b.text) for b in result.blocks[1:5]]
        self.assertEqual(
            outcome,
            [
                ("decided", "confirmed", "wort0 wort1 wort2"),
                ("decided", "corrected", "Grauwasser"),
                ("decided", "unintelligible", None),
                ("decided", "kept", "wort0 wort1 wort2"),
            ],
        )
        self.assertTrue(all(b.asr_text == "wort0 wort1 wort2" for b in result.blocks))

    def test_a_passage_without_candidate_is_taken_over(self) -> None:
        block = self.working().blocks[0]

        self.assertEqual(
            (block.level, block.origin, block.status), ("confident", "automatic", None)
        )
        self.assertEqual(block.text, block.asr_text)

    def test_undecided_and_deferred_candidates_stay_open(self) -> None:
        result = self.working(self.decided((2, "deferred", None), (3, "open", None)))

        self.assertEqual(
            [(b.origin, b.status) for b in result.blocks[1:4]],
            [("open", "deferred"), ("open", "open"), ("open", "open")],
        )
        self.assertEqual(result.blocks[1].level, "needs_review")
        self.assertEqual(result.findings, ())

    def test_blocks_keep_the_recording_order_and_times(self) -> None:
        result = self.working()

        self.assertEqual([b.passage for b in result.blocks], [1, 2, 3, 4, 5, 6])
        self.assertEqual((result.blocks[0].start_ms, result.blocks[0].end_ms), (0, 850))
        self.assertEqual(
            dict(result.counts()), {"automatic": 1, "decided": 0, "open": 5}
        )


class FindingTest(_WorkingCase):
    def test_a_stale_decision_is_reported_and_its_block_open(self) -> None:
        decisions = self.decided((2, "corrected", "Grauwasser"))
        newer = transcribed_again(self.reference)
        self.rated(newer)

        result = self.working(decisions, reference=newer)

        block = result.blocks[1]
        self.assertEqual((block.origin, block.text), ("open", "wort0 wort1 wort2"))
        self.assertEqual(
            result.findings, (WorkingFinding("stale_decision", 1, passage=2),)
        )

    def test_an_orphaned_decision_is_reported_never_applied(self) -> None:
        orphan = ReviewDecision(1, 1, PROCESSED_AT, "corrected", "x", "Grauwasser")

        result = self.working(SessionDecisions((orphan,)))

        self.assertEqual(result.blocks[0].origin, "automatic")
        self.assertEqual(result.blocks[0].text, "wort0 wort1 wort2")
        self.assertEqual(
            result.findings, (WorkingFinding("orphaned_decision", 1, passage=1),)
        )

    def test_a_segment_without_transcript_is_reported(self) -> None:
        result = self.working(manifest=MANIFEST)

        self.assertEqual(result.findings, (WorkingFinding("missing_segment", 2),))

    def test_a_reference_of_another_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "segment 1: candidates rate another"):
            self.working(reference=transcribed_again(self.reference))


class SpeakerTest(_WorkingCase):
    def test_the_label_stays_and_the_person_is_added(self) -> None:
        reference = transcript(
            spoken(1, *SURE, label="SPEAKER_00"),
            spoken(2, *SURE, label="SPEAKER_01"),
            diarization=diarized(),
        )
        self.rated(reference)
        speakers = check(
            SpeakerAssignment((entry(reference, "SPEAKER_00", 11),)),
            [reference],
            PARTICIPANTS,
        )

        result = self.working(speakers=speakers, reference=reference)

        self.assertEqual(
            [block.speaker for block in result.blocks],
            [
                SpeakerRef(1, "SPEAKER_00", "person", 11),
                SpeakerRef(1, "SPEAKER_01", "open", None),
            ],
        )

    def test_an_entry_not_applied_is_reported(self) -> None:
        speakers = check(
            SpeakerAssignment((entry(self.reference, "SPEAKER_00", 99),)),
            [self.reference],
            PARTICIPANTS,
        )

        result = self.working(speakers=speakers)

        self.assertEqual(result.blocks[0].speaker.assigned, "open")
        self.assertEqual(
            result.findings,
            (
                WorkingFinding(
                    "speaker_entry", 1, entry=1, speaker_kind="unknown_person"
                ),
            ),
        )

    def test_a_segment_without_diarization_has_no_label(self) -> None:
        reference = transcript(spoken(1, *SURE, label=None))
        self.rated(reference)

        result = self.working(reference=reference)

        self.assertEqual(
            [block.speaker for block in result.blocks],
            [SpeakerRef(1, None, "open", None)],
        )
        self.assertIsNone(result.inputs.segments[0].labels_version)


class WorkingFileTest(_WorkingCase):
    def setUp(self) -> None:
        super().setUp()
        store_context(
            self.paths, encoded(context(participants=[participant(user_id=11)]))
        )
        build_snapshot(self.paths, DEFAULT_KEYWORD_BUDGET)

    def written(self) -> bytes:
        write_working(self.paths, compose(self.paths, ONLY_FIRST))
        return self.paths.working_transcript.read_bytes()

    def stored(self) -> dict[str, Any]:
        return json.loads(self.paths.working_transcript.read_text(encoding="utf-8"))

    def test_equal_inputs_give_an_equal_file(self) -> None:
        write_decisions(self.paths, self.decided((2, "corrected", "Grauwasser")))

        first = self.written()

        self.assertEqual(self.written(), first)

    def test_the_stored_version_loads_as_written(self) -> None:
        write_decisions(self.paths, self.decided((2, "unintelligible", None)))
        working = compose(self.paths, ONLY_FIRST)

        write_working(self.paths, working)

        self.assertEqual(load_working(self.paths), working)

    def test_a_new_decision_changes_its_block_and_the_inputs_only(self) -> None:
        before = self.stored_after(NONE)
        after = self.stored_after(self.decided((3, "kept", None)))

        pairs = zip(before["blocks"], after["blocks"], strict=True)
        changed = [b["passage"] for a, b in pairs if a != b]
        self.assertEqual(changed, [3])
        self.assertIsNone(before["inputs"]["decisions_sha256"])
        self.assertIsNotNone(after["inputs"]["decisions_sha256"])
        self.assertEqual(before["findings"], after["findings"])

    def stored_after(self, decisions: SessionDecisions) -> dict[str, Any]:
        self.paths.review_decisions.unlink(missing_ok=True)
        if decisions.decisions:
            write_decisions(self.paths, decisions)
        self.written()
        return self.stored()

    def test_the_reference_stays_unchanged(self) -> None:
        reference = self.paths.reference(1).read_bytes()
        write_decisions(self.paths, self.decided((2, "corrected", "Grauwasser")))

        self.written()

        self.assertEqual(self.paths.reference(1).read_bytes(), reference)

    def test_the_assignment_is_recorded_by_its_bytes(self) -> None:
        self.assertIsNone(compose(self.paths, ONLY_FIRST).inputs.assignment_sha256)
        write_assignment(
            self.paths, SpeakerAssignment((entry(self.reference, "SPEAKER_00", 11),))
        )

        working = compose(self.paths, ONLY_FIRST)

        self.assertIsNotNone(working.inputs.assignment_sha256)
        self.assertEqual(working.blocks[0].speaker.user_id, 11)

    def test_without_snapshot_nothing_is_composed(self) -> None:
        self.paths.knowledge_snapshot.unlink()

        with self.assertRaisesRegex(DataFileError, "run transcript snapshot"):
            compose(self.paths, ONLY_FIRST)

    def test_a_file_of_another_version_or_session_is_rejected(self) -> None:
        for key, value, message in (
            ("format_version", 99, "unsupported format_version"),
            ("session", "andere/001", "belongs to another session"),
        ):
            with self.subTest(key=key):
                data = self.fresh()
                data[key] = value
                self.save(data)

                with self.assertRaisesRegex(WorkingError, message):
                    load_working(self.paths)

    def test_an_invalid_block_is_named_by_number(self) -> None:
        for field, value, message in (
            ("origin", "guessed", "'origin' invalid"),
            ("speaker", {"assigned": "open", "user_id": 11}, "'user_id' only allowed"),
        ):
            with self.subTest(field=field):
                data = self.fresh()
                data["blocks"][1][field] = value
                self.save(data)

                with self.assertRaisesRegex(WorkingError, f"block 2: field {message}"):
                    load_working(self.paths)

    def fresh(self) -> dict[str, Any]:
        """The working version as just written, to change by hand."""
        self.written()
        return self.stored()

    def save(self, data: dict[str, Any]) -> None:
        self.paths.working_transcript.write_text(json.dumps(data))
