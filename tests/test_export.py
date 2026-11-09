import dataclasses
import unittest
from typing import Any

from test_candidates import ONLY_FIRST
from test_decisions import NONE
from test_report import BLOCK_MS, _ReportCase
from test_session_time import MANIFEST, SECOND, SOURCE
from test_speakers import NAME, PARTICIPANTS, entry
from test_uncertainty import diarized, transcript
from test_working import SURE, UNSURE, spoken

from transcript.contract import validate
from transcript.decisions import SETTLED, SessionDecisions
from transcript.export import _REVIEW_STATUS, UNLABELLED, ExportError, build
from transcript.manifest import Manifest
from transcript.reference import Passage, ReferenceTranscript
from transcript.report import report_json
from transcript.speakers import SpeakerAssignment

GROUP_ID = 7  # made up, like every id here


def at(passage: Passage, start_ms: int | None) -> Passage:
    """`passage`, moved to start at `start_ms`; None leaves it without times."""
    end_ms = None if start_ms is None else start_ms + BLOCK_MS
    return dataclasses.replace(passage, start_ms=start_ms, end_ms=end_ms)


def one_per_second(*passages: Passage) -> ReferenceTranscript:
    """A diarized transcript whose n-th passage starts at n - 1 seconds."""
    return transcript(
        *(at(p, n * 1000) for n, p in enumerate(passages)), diarization=diarized()
    )


class _ExportCase(_ReportCase):
    """A confident passage and five candidates, one second apart."""

    def setUp(self) -> None:
        super().setUp()
        self.reference = one_per_second(
            spoken(1, *SURE), *(spoken(n, *UNSURE) for n in range(2, 7))
        )
        self.rated(self.reference)

    def exported(
        self,
        decisions: SessionDecisions = NONE,
        assignment: SpeakerAssignment | None = None,
        manifest: Manifest = ONLY_FIRST,
        reference: ReferenceTranscript | None = None,
    ) -> dict[str, Any]:
        stored, report = self.reported(decisions, assignment, manifest, reference)
        return build(stored, manifest, report, PARTICIPANTS, GROUP_ID)

    def passages(self, document: dict[str, Any], name: str) -> list[Any]:
        return [passage[name] for passage in document["passages"]]


class DocumentTest(_ExportCase):
    def test_the_export_is_valid_contract_v1(self) -> None:
        self.assertEqual(validate(self.exported()), ())

    def test_the_head_names_session_source_and_pipeline(self) -> None:
        document = self.exported()

        self.assertEqual(document["contract_version"], "1.0")
        self.assertEqual(
            document["session"],
            {
                "group": GROUP_ID,
                "ordinal": 42,
                "play_session_id": 4711,
                "session_date": "2026-11-04",
            },
        )
        self.assertEqual(
            document["source"],
            {
                "file_name": SOURCE.file,
                "duration_seconds": ONLY_FIRST.duration_ms / 1000,
                "audio_sha256": SOURCE.sha256,
            },
        )
        pipeline = document["pipeline"]
        self.assertEqual((pipeline["backend"], pipeline["model"]), ("fake", "fake"))
        self.assertEqual(pipeline["knowledge_snapshot_id"], "snapshot")
        self.assertRegex(pipeline["config_hash"], r"^[0-9a-f]{16}$")
        self.assertEqual(pipeline["thresholds"]["uncertainty"][0]["segments"], (1,))

    def test_stats_is_the_report_unchanged(self) -> None:
        stored, report = self.reported()

        document = build(stored, ONLY_FIRST, report, PARTICIPANTS, GROUP_ID)

        self.assertEqual(document["stats"], report_json(report))

    def test_a_passage_carries_time_label_text_tier_and_status(self) -> None:
        first = self.exported()["passages"][0]

        self.assertEqual(
            first,
            {
                "id": "p-00000000-s01-speaker-00",
                "start": 0.0,
                "end": 0.85,
                "speaker_label": "s01-SPEAKER_00",
                "participant_id": None,
                "text": "wort0 wort1 wort2",
                "asr_text": None,
                "confidence_tier": "confident",
                "review_status": "unreviewed",
                "review_note": None,
                "markers": [],
                "segment_ref": None,
                "knowledge_hints": [],
                "layers": {},
            },
        )

    def test_a_split_recording_names_the_segment(self) -> None:
        document = self.exported(manifest=MANIFEST)

        self.assertEqual(set(self.passages(document, "segment_ref")), {"segment-01"})
        self.assertEqual(validate(document), ())


class ReviewTest(_ExportCase):
    def test_each_outcome_has_its_status_and_markers(self) -> None:
        document = self.exported(
            self.decided(
                (2, "confirmed", None),
                (3, "corrected", "Grauwasser"),
                (4, "unintelligible", None),
                (5, "kept", None),
                (6, "deferred", None),
            )
        )

        self.assertEqual(
            self.passages(document, "review_status"),
            ["unreviewed", "confirmed", "corrected", "corrected", "confirmed", "open"],
        )
        self.assertEqual(
            self.passages(document, "confidence_tier"),
            ["confident", *["needs_review"] * 5],
        )
        corrected, unintelligible = document["passages"][2:4]
        self.assertEqual(
            (corrected["text"], corrected["asr_text"]),
            ("Grauwasser", "wort0 wort1 wort2"),
        )
        self.assertEqual(
            (unintelligible["text"], unintelligible["asr_text"]),
            ("", "wort0 wort1 wort2"),
        )
        self.assertEqual(
            self.passages(document, "markers"),
            [[], [], [], [{"type": "unintelligible", "at": 3.0}], [], []],
        )
        self.assertEqual(validate(document), ())

    def test_ids_stay_when_the_review_changes(self) -> None:
        before = self.exported()
        after = self.exported(
            self.decided((3, "corrected", "Grauwasser"), (4, "unintelligible", None))
        )

        self.assertEqual(self.passages(before, "id"), self.passages(after, "id"))
        self.assertNotEqual(before["passages"][2], after["passages"][2])

    def test_passages_with_the_same_start_and_label_get_a_suffix(self) -> None:
        reference = transcript(
            at(spoken(1, *SURE), 0), at(spoken(2, *SURE), 0), diarization=diarized()
        )
        self.rated(reference)

        document = self.exported(reference=reference)

        self.assertEqual(
            self.passages(document, "id"),
            ["p-00000000-s01-speaker-00", "p-00000000-s01-speaker-00-2"],
        )
        self.assertEqual(validate(document), ())


class SpeakerTest(_ExportCase):
    def setUp(self) -> None:
        super().setUp()
        self.reference = one_per_second(
            spoken(1, *SURE, label="SPEAKER_00"),
            spoken(2, *SURE, label="SPEAKER_01"),
            spoken(3, *SURE, label="SPEAKER_00"),
        )
        self.rated(self.reference)

    def test_only_a_person_is_named_and_crosstalk_is_marked(self) -> None:
        assignment = SpeakerAssignment(
            (
                entry(self.reference, "SPEAKER_00", 11),
                entry(self.reference, "SPEAKER_01", assigned="multiple"),
            )
        )

        document = self.exported(assignment=assignment)

        self.assertEqual(
            document["speakers"],
            {
                "s01-SPEAKER_00": {"participant_id": 11, "display_name": f"{NAME} 11"},
                "s01-SPEAKER_01": None,
            },
        )
        self.assertEqual(self.passages(document, "participant_id"), [11, None, 11])
        self.assertEqual(
            self.passages(document, "markers"),
            [[], [{"type": "crosstalk", "at": 1.0}], []],
        )
        self.assertEqual(validate(document), ())

    def test_an_open_label_stays_a_label(self) -> None:
        document = self.exported()

        self.assertEqual(
            document["speakers"], {"s01-SPEAKER_00": None, "s01-SPEAKER_01": None}
        )
        self.assertEqual(self.passages(document, "markers"), [[], [], []])

    def test_a_passage_without_label_is_unlabelled(self) -> None:
        reference = transcript(at(spoken(1, *SURE, label=None), 0))
        self.rated(reference)

        document = self.exported(reference=reference)

        self.assertEqual(document["speakers"], {UNLABELLED: None})
        self.assertEqual(self.passages(document, "id"), ["p-00000000-unlabelled"])
        self.assertEqual(validate(document), ())


class RefusalTest(_ExportCase):
    def test_a_passage_without_times_is_refused(self) -> None:
        reference = transcript(
            at(spoken(1, *SURE), 0), at(spoken(2, *SURE), None), diarization=diarized()
        )
        self.rated(reference)

        with self.assertRaises(ExportError) as raised:
            self.exported(reference=reference)

        message = str(raised.exception)
        self.assertIn("segment 1, passage 2: no start or end time", message)
        self.assertNotIn("wort", message)

    def test_several_recordings_are_refused(self) -> None:
        other = dataclasses.replace(SOURCE, file="zweite.m4a", sha256="cd" * 32)
        manifest = dataclasses.replace(
            MANIFEST,
            segments=(
                ONLY_FIRST.segments[0],
                dataclasses.replace(SECOND, source=other),
            ),
        )

        with self.assertRaisesRegex(ExportError, "2 recordings.*IOA-1287"):
            self.exported(manifest=manifest)

    def test_a_play_session_id_that_is_no_integer_is_refused(self) -> None:
        manifest = dataclasses.replace(ONLY_FIRST, play_session_id="ps-4711")

        with self.assertRaises(ExportError) as raised:
            self.exported(manifest=manifest)

        self.assertIn("'play_session_id' is no integer", str(raised.exception))
        self.assertNotIn("ps-4711", str(raised.exception))

    def test_an_empty_working_version_is_refused(self) -> None:
        stored, report = self.reported()

        with self.assertRaisesRegex(ExportError, "nothing to export"):
            build(
                dataclasses.replace(stored, blocks=()),
                ONLY_FIRST,
                report,
                PARTICIPANTS,
                GROUP_ID,
            )


class MappingTest(unittest.TestCase):
    def test_every_settling_status_has_a_contract_status(self) -> None:
        self.assertEqual(set(_REVIEW_STATUS), set(SETTLED))


if __name__ == "__main__":
    unittest.main()
