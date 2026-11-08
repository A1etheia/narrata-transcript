import dataclasses
import datetime
import json
import tempfile
import unittest
from pathlib import Path

from test_reference import minimal
from test_session_time import FIRST, MANIFEST, SECOND
from test_uncertainty import LIMITS, hint, hints, passage, transcript, words

from transcript.candidates import (
    CANDIDATES_FORMAT_VERSION,
    CandidatesError,
    collect,
    load_candidates,
    session_candidates,
    write_candidates,
)
from transcript.hints import write_hints
from transcript.reference import (
    Processing,
    ReferenceTranscript,
    SegmentRef,
    update_reference,
)
from transcript.session import SessionPaths
from transcript.uncertainty import assess_session

ONLY_FIRST = dataclasses.replace(MANIFEST, segments=(FIRST,))


class _SessionCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(minimal().key, Path(directory.name))

    def rated(self, reference: ReferenceTranscript, *found) -> None:
        update_reference(self.paths, reference)
        if found:
            write_hints(self.paths, hints(*found))
        assess_session(self.paths, [reference.segment.index], LIMITS)


class CandidateTest(_SessionCase):
    def test_only_flagged_passages_appear_uncertain_first(self) -> None:
        self.rated(
            transcript(
                passage(words(0.9, 0.9, 0.9), index=1),  # confident
                passage(words(0.3, 0.9, 0.9), index=2),  # needs_review
                passage(words(0.3, 0.3, 0.9), index=3),  # uncertain
            )
        )

        found = collect(self.paths, ONLY_FIRST).candidates

        self.assertEqual([c.id for c in found], ["s01-p0003", "s01-p0002"])
        self.assertEqual([c.level for c in found], ["uncertain", "needs_review"])
        self.assertEqual(found[0].text, "wort0 wort1 wort2")
        self.assertEqual(found[0].speaker, "SPEAKER_00")

    def test_a_candidate_keeps_every_reason(self) -> None:
        self.rated(
            transcript(passage(words(0.1, 0.3, 0.9), index=1)),
        )

        (candidate,) = collect(self.paths, ONLY_FIRST).candidates

        self.assertEqual(
            [r.rule for r in candidate.rating.reasons],
            ["low_confidence", "very_low_confidence"],
        )

    def test_knowledge_triggers_a_candidate_and_puts_it_first(self) -> None:
        variant = dataclasses.replace(hint(), passage=2)
        self.rated(
            transcript(
                passage(words(0.3, 0.9, 0.9), index=1),  # needs_review, no hint
                passage(words(0.9, 0.9, 0.9), index=2),  # confident but for the hint
            ),
            variant,
        )

        found = collect(self.paths, ONLY_FIRST).candidates

        self.assertEqual([c.passage for c in found], [2, 1])
        self.assertEqual(found[0].hints, (variant,))
        self.assertEqual(found[0].text, "wort0 wort1 wort2")  # never corrected
        self.assertEqual(found[1].hints, ())

    def test_a_sound_only_hint_does_not_make_a_candidate(self) -> None:
        sound = dataclasses.replace(hint("similar"), method="sound", score=None)
        self.rated(transcript(passage(words(0.9, 0.9, 0.9))), sound)

        self.assertEqual(collect(self.paths, ONLY_FIRST).candidates, ())

    def test_times_are_session_times_or_none(self) -> None:
        second = transcript(
            passage(words(0.3, 0.9, 0.9), index=1),
            passage(words(0.3, 0.9, 0.9), index=2, start_ms=None, end_ms=None),
        )
        second = dataclasses.replace(
            second, segment=SegmentRef(2, "segment-02.wav", "ab" * 32)
        )
        self.rated(second)

        found = collect(self.paths, MANIFEST)

        timed, untimed = found.candidates
        assert timed.time is not None
        self.assertEqual(timed.time.start_ms, SECOND.start_ms)
        self.assertEqual(timed.time.local_end_ms, 850)
        self.assertIsNone(untimed.time)
        self.assertEqual(found.not_rated, (1,))
        self.assertEqual(found.audio_ms, SECOND.duration_ms)  # 10 min
        self.assertEqual(found.per_hour, 12.0)

    def test_a_session_without_ratings_has_no_rate(self) -> None:
        found = collect(self.paths, ONLY_FIRST)

        self.assertEqual(found.not_rated, (1,))
        self.assertIsNone(found.per_hour)

    def test_a_missing_rating_asks_for_assess(self) -> None:
        update_reference(self.paths, transcript(passage(words(0.3))))

        with self.assertRaisesRegex(CandidatesError, "run transcript assess"):
            collect(self.paths, ONLY_FIRST)

    def test_a_rating_of_another_version_is_an_error(self) -> None:
        reference = transcript(passage(words(0.3)))
        self.rated(reference)
        newer = dataclasses.replace(
            reference,
            processing=Processing("0.0.1", "2026-11-05T20:00:00+01:00"),
        )
        update_reference(self.paths, newer)

        with self.assertRaisesRegex(CandidatesError, "another version of segment 1"):
            collect(self.paths, ONLY_FIRST)

    def test_hints_of_another_snapshot_are_not_attached(self) -> None:
        self.rated(transcript(passage(words(0.3, 0.9, 0.9))), hint())
        write_hints(
            self.paths,
            dataclasses.replace(hints(hint()), knowledge_snapshot_id="cd" * 32),
        )

        (candidate,) = collect(self.paths, ONLY_FIRST).candidates

        self.assertEqual(candidate.hints, ())


class CandidateFileTest(_SessionCase):
    def test_a_round_trip_keeps_every_field(self) -> None:
        self.rated(
            transcript(
                passage(words(0.3, 0.3, 0.9), index=1),
                passage(words(0.9, 0.9, 0.9), index=2, start_ms=None, end_ms=None),
            ),
            hint(ambiguous=True),
        )
        found = collect(self.paths, ONLY_FIRST)

        write_candidates(self.paths, found, datetime.datetime(2026, 11, 8, 9))

        self.assertEqual(load_candidates(self.paths), found)
        data = json.loads(self.paths.review_candidates.read_text(encoding="utf-8"))
        self.assertEqual(data["format_version"], CANDIDATES_FORMAT_VERSION)
        self.assertEqual(data["candidates"][0]["id"], "s01-p0001")
        self.assertEqual(
            data["counts"], {"confident": 0, "needs_review": 1, "uncertain": 1}
        )

    def test_the_session_step_writes_what_it_found(self) -> None:
        self.rated(transcript(passage(words(0.3, 0.3, 0.9))))

        found = session_candidates(self.paths, ONLY_FIRST)

        self.assertEqual(load_candidates(self.paths), found)

    def test_another_format_version_is_rejected(self) -> None:
        self.rated(transcript(passage(words(0.3))))
        session_candidates(self.paths, ONLY_FIRST)
        path = self.paths.review_candidates
        data = json.loads(path.read_text(encoding="utf-8"))
        data["format_version"] = 99
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(CandidatesError, "format_version"):
            load_candidates(self.paths)

    def test_an_invalid_candidate_names_its_number_not_its_text(self) -> None:
        self.rated(transcript(passage(words(0.3))))
        session_candidates(self.paths, ONLY_FIRST)
        path = self.paths.review_candidates
        data = json.loads(path.read_text(encoding="utf-8"))
        data["candidates"][0]["level"] = "confident"
        path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(CandidatesError, "candidate 1: field 'level'"):
            load_candidates(self.paths)
