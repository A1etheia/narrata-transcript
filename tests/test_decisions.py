import dataclasses
import datetime
import json
from typing import Any

from test_candidates import ONLY_FIRST, _SessionCase
from test_uncertainty import passage, transcript, words

from transcript.candidates import SessionCandidates, collect, session_candidates
from transcript.decisions import (
    DECISIONS_FORMAT_VERSION,
    STATUSES,
    DecisionsError,
    ReviewStatus,
    SessionDecisions,
    decide,
    load_decisions,
    review_items,
    write_decisions,
)
from transcript.reference import Processing

MOMENT = datetime.datetime(2026, 11, 8, 10, tzinfo=datetime.timezone.utc)
NONE = SessionDecisions()


class _DecisionCase(_SessionCase):
    def setUp(self) -> None:
        super().setUp()
        self.reference = transcript(
            passage(words(0.3, 0.3, 0.9), index=1),  # uncertain
            passage(words(0.3, 0.9, 0.9), index=2),  # needs_review
        )
        self.rated(self.reference)
        self.found = session_candidates(self.paths, ONLY_FIRST)

    def decide(
        self,
        candidate: str,
        status: ReviewStatus,
        on: SessionDecisions = NONE,
        **optional: str,
    ) -> SessionDecisions:
        return decide(on, self.found, candidate, status, now=MOMENT, **optional)

    def edit(self, key: str, value: Any) -> None:
        self._change(lambda data: data.__setitem__(key, value))

    def edit_entry(self, key: str, value: Any) -> None:
        self._change(lambda data: data["decisions"][0].__setitem__(key, value))

    def _change(self, change) -> None:
        path = self.paths.review_decisions
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")


class DecisionTest(_DecisionCase):
    def test_a_candidate_without_a_decision_is_open(self) -> None:
        state = review_items(self.found, load_decisions(self.paths))

        self.assertEqual([i.status for i in state.items], ["open", "open"])
        self.assertIsNone(state.items[0].decision)

    def test_a_decision_leaves_the_candidate_untouched(self) -> None:
        before = self.paths.review_candidates.read_bytes()
        decisions = self.decide("s01-p0001", "corrected", target_text="Wort null")

        write_decisions(self.paths, decisions, MOMENT)

        self.assertEqual(self.paths.review_candidates.read_bytes(), before)
        item, _ = review_items(self.found, decisions).items
        self.assertEqual(item.status, "corrected")
        self.assertEqual(item.candidate.text, "wort0 wort1 wort2")
        assert item.decision is not None
        self.assertEqual(item.decision.target_text, "Wort null")

    def test_a_later_decision_replaces_the_earlier_one(self) -> None:
        first = self.decide("s01-p0002", "deferred", note="listen again")

        (decision,) = self.decide("s01-p0002", "confirmed", on=first).decisions

        self.assertEqual(decision.status, "confirmed")
        self.assertIsNone(decision.note)

    def test_target_text_belongs_to_corrected_only(self) -> None:
        with self.assertRaisesRegex(ValueError, "'target_text' required"):
            self.decide("s01-p0001", "corrected")
        with self.assertRaisesRegex(ValueError, "'target_text' required"):
            self.decide("s01-p0001", "corrected", target_text="  ")
        with self.assertRaisesRegex(ValueError, "'target_text' only allowed"):
            self.decide("s01-p0001", "confirmed", target_text="anders")

    def test_an_unknown_candidate_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate s01-p0009 not found"):
            self.decide("s01-p0009", "confirmed")

    def test_a_new_transcript_version_makes_a_decision_stale(self) -> None:
        decisions = self.decide("s01-p0001", "confirmed")
        newer = dataclasses.replace(
            self.reference,
            processing=Processing("0.0.1", "2026-11-09T20:00:00+01:00"),
        )
        self.rated(newer)

        state = review_items(collect(self.paths, ONLY_FIRST), decisions)

        self.assertEqual(state.items[0].status, "open")
        self.assertEqual(state.stale, decisions.decisions)
        self.assertEqual(state.orphaned, ())

    def test_a_decision_without_its_candidate_is_orphaned(self) -> None:
        decisions = self.decide("s01-p0002", "kept", note="Mundart")
        fewer = SessionCandidates(
            self.found.rated, self.found.not_rated, self.found.candidates[:1]
        )

        state = review_items(fewer, decisions)

        self.assertEqual(state.orphaned, decisions.decisions)
        self.assertEqual(len(state.items), 1)


class DecisionFileTest(_DecisionCase):
    def test_every_status_survives_a_round_trip(self) -> None:
        for status in STATUSES:
            with self.subTest(status=status):
                target = {"target_text": "neu"} if status == "corrected" else {}
                decisions = self.decide("s01-p0001", status, note="Notiz", **target)

                write_decisions(self.paths, decisions, MOMENT)

                self.assertEqual(load_decisions(self.paths), decisions)

    def test_the_file_has_a_version_and_names_each_candidate(self) -> None:
        decisions = self.decide(
            "s01-p0001", "open", on=self.decide("s01-p0002", "unintelligible")
        )

        write_decisions(self.paths, decisions, MOMENT)

        data = json.loads(self.paths.review_decisions.read_text(encoding="utf-8"))
        self.assertEqual(data["format_version"], DECISIONS_FORMAT_VERSION)
        self.assertEqual(
            [d["candidate"] for d in data["decisions"]], ["s01-p0001", "s01-p0002"]
        )
        self.assertEqual(
            data["decisions"][0]["reference_processed_at"],
            self.reference.processing.processed_at,
        )

    def test_another_format_version_or_session_is_rejected(self) -> None:
        for key, value, message in (
            ("format_version", 99, "format_version"),
            ("session", "andere/001", "another session"),
        ):
            with self.subTest(key=key):
                write_decisions(self.paths, NONE, MOMENT)
                self.edit(key, value)

                with self.assertRaisesRegex(DecisionsError, message):
                    load_decisions(self.paths)

    def test_an_invalid_entry_names_its_number_not_its_text(self) -> None:
        for key, value, message in (
            ("status", "maybe", "decision 1: field 'status' invalid"),
            ("target_text", "geheimer Text", "decision 1: field 'target_text'"),
            ("candidate", "s01-p0002", "decision 1: field 'candidate'"),
        ):
            with self.subTest(key=key):
                decisions = self.decide("s01-p0001", "confirmed")
                write_decisions(self.paths, decisions, MOMENT)
                self.edit_entry(key, value)

                with self.assertRaisesRegex(DecisionsError, message) as caught:
                    load_decisions(self.paths)
                self.assertNotIn("geheimer", str(caught.exception))

    def test_two_decisions_for_one_candidate_are_rejected(self) -> None:
        write_decisions(self.paths, self.decide("s01-p0001", "confirmed"), MOMENT)
        self._change(lambda data: data["decisions"].append(data["decisions"][0]))

        with self.assertRaisesRegex(DecisionsError, "two decisions"):
            load_decisions(self.paths)
