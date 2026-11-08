import dataclasses
import json

from test_candidates import ONLY_FIRST, _SessionCase
from test_decisions import MOMENT
from test_glossary import entry, glossary
from test_uncertainty import passage, transcript, words

from transcript.candidates import SessionCandidates, session_candidates
from transcript.decisions import SessionDecisions, decide
from transcript.domain import DomainContext, Origin
from transcript.narrata import GlossaryEntry
from transcript.reference import Processing
from transcript.variant_suggestions import (
    SUGGESTIONS_FORMAT_VERSION,
    DecisionRef,
    OtherName,
    SuggestedEntry,
    review_session,
    suggest,
    write_suggestions,
)

# Every name below is made up.
DECIDED = MOMENT.isoformat(timespec="seconds")
ORIGIN = Origin("snap-1", "snapshot.json", "1.1", 4711)
QUENDOLIN = entry("Quendolin", "Quen", entry_id=5, entry_type="person")
NEBELAU = entry("Nebelau", variants=("Nebel Au",), entry_id=6)


def domain(*entries: GlossaryEntry) -> DomainContext:
    return DomainContext((), glossary(*entries), set(), ORIGIN)


class _Case(_SessionCase):
    def setUp(self) -> None:
        super().setUp()
        self.passages(
            "Dann kam Kwendolin, endlich.",
            "Wir reiten nach Nebel Au.",
            "Das war wirklich gut.",
        )

    def passages(self, *texts: str) -> None:
        self.reference = transcript(
            *(
                passage(words(0.3, 0.3, 0.9), index=n, text=text)  # uncertain
                for n, text in enumerate(texts, start=1)
            )
        )
        self.rated(self.reference)
        self.found = session_candidates(self.paths, ONLY_FIRST)

    def corrected(self, *targets: tuple[int, str]) -> SessionDecisions:
        decisions = SessionDecisions()
        for passage_index, target in targets:
            decisions = decide(
                decisions,
                self.found,
                f"s01-p{passage_index:04d}",
                "corrected",
                target_text=target,
                now=MOMENT,
            )
        return decisions


class SuggestionTest(_Case):
    def test_a_misheard_name_is_suggested_for_its_entry(self) -> None:
        decisions = self.corrected((1, "Dann kam Quendolin, endlich."))

        found = suggest(self.found, decisions, domain(QUENDOLIN, NEBELAU))

        (suggestion,) = found.suggestions
        self.assertEqual(suggestion.variant, "Kwendolin")
        self.assertEqual(
            suggestion.entries, (SuggestedEntry("person", 5, "Quendolin", "name"),)
        )
        self.assertFalse(suggestion.ambiguous)
        self.assertEqual(suggestion.also_names, ())
        self.assertEqual(suggestion.decisions, (DecisionRef("s01-p0001", DECIDED),))
        self.assertEqual(
            found.counts(), {"corrected": 1, "suggested": 1, "known": 0, "no_term": 0}
        )

    def test_an_alias_as_correction_is_a_term_too(self) -> None:
        decisions = self.corrected((1, "Dann kam Quen, endlich."))

        (suggestion,) = suggest(self.found, decisions, domain(QUENDOLIN)).suggestions

        self.assertEqual(
            suggestion.entries, (SuggestedEntry("person", 5, "Quen", "aliases[0]"),)
        )

    def test_a_variant_narrata_keeps_is_not_suggested(self) -> None:
        decisions = self.corrected((2, "Wir reiten nach Nebelau."))

        found = suggest(self.found, decisions, domain(NEBELAU))

        self.assertEqual(found.suggestions, ())
        self.assertEqual(found.known, 1)

    def test_a_correction_without_a_glossary_term_suggests_nothing(self) -> None:
        decisions = self.corrected((3, "Das war wirklich schlecht."))

        found = suggest(self.found, decisions, domain(QUENDOLIN))

        self.assertEqual(found.suggestions, ())
        self.assertEqual(found.no_term, 1)

    def test_an_event_keeps_no_misrecognitions(self) -> None:
        battle = entry("Quendolin", entry_id=9, entry_type="event")
        decisions = self.corrected((1, "Dann kam Quendolin, endlich."))

        found = suggest(self.found, decisions, domain(battle))

        self.assertEqual(found.suggestions, ())
        self.assertEqual(found.no_term, 1)

    def test_a_shared_term_names_every_entry_and_picks_none(self) -> None:
        namesake = entry("Quendolin", entry_id=7)
        decisions = self.corrected((1, "Dann kam Quendolin, endlich."))

        (suggestion,) = suggest(
            self.found, decisions, domain(QUENDOLIN, namesake)
        ).suggestions

        self.assertTrue(suggestion.ambiguous)
        self.assertEqual(
            [(e.type, e.id) for e in suggestion.entries], [("person", 5), ("place", 7)]
        )

    def test_a_variant_naming_another_entry_says_so(self) -> None:
        other = entry("Kwendolin", entry_id=8)
        decisions = self.corrected((1, "Dann kam Quendolin, endlich."))

        (suggestion,) = suggest(
            self.found, decisions, domain(QUENDOLIN, other)
        ).suggestions

        self.assertEqual(suggestion.also_names, (OtherName("place", 8, "name"),))

    def test_the_same_variant_in_two_decisions_is_one_suggestion(self) -> None:
        self.passages("Kwendolin lacht.", "Und kwendolin schweigt.")
        decisions = self.corrected(
            (1, "Quendolin lacht."), (2, "Und Quendolin schweigt.")
        )

        (suggestion,) = suggest(self.found, decisions, domain(QUENDOLIN)).suggestions

        self.assertEqual(suggestion.variant, "Kwendolin")
        self.assertEqual(
            [d.candidate for d in suggestion.decisions], ["s01-p0001", "s01-p0002"]
        )

    def test_only_corrected_decisions_in_force_count(self) -> None:
        decisions = decide(
            self.corrected((1, "Dann kam Quendolin, endlich.")),
            self.found,
            "s01-p0003",
            "confirmed",
            now=MOMENT,
        )
        stale = dataclasses.replace(
            self.reference,
            processing=Processing("0.0.1", "2026-11-09T20:00:00+01:00"),
        )
        self.rated(stale)
        newer = session_candidates(self.paths, ONLY_FIRST)

        found = suggest(newer, decisions, domain(QUENDOLIN))

        self.assertEqual(found.suggestions, ())
        self.assertEqual(found.corrected, 0)

    def test_an_orphaned_correction_is_ignored(self) -> None:
        decisions = self.corrected((1, "Dann kam Quendolin, endlich."))
        fewer = SessionCandidates(
            self.found.rated, self.found.not_rated, self.found.candidates[1:]
        )

        found = suggest(fewer, decisions, domain(QUENDOLIN))

        self.assertEqual((found.corrected, found.suggestions), (0, ()))

    def test_without_corrections_the_list_is_empty(self) -> None:
        found = suggest(self.found, SessionDecisions(), domain(QUENDOLIN))

        self.assertEqual(found.suggestions, ())
        self.assertEqual(
            found.counts(), {"corrected": 0, "suggested": 0, "known": 0, "no_term": 0}
        )

    def test_insertions_and_deletions_are_no_misrecognition(self) -> None:
        decisions = self.corrected((3, "Das war Quendolin wirklich gut."))

        found = suggest(self.found, decisions, domain(QUENDOLIN))

        self.assertEqual(found.suggestions, ())
        self.assertEqual(found.counts()["no_term"], 0)


class SuggestionFileTest(_Case):
    def test_the_file_is_written_and_stable(self) -> None:
        decisions = self.corrected((1, "Dann kam Quendolin, endlich."))
        found = suggest(self.found, decisions, domain(QUENDOLIN))

        write_suggestions(self.paths, found)
        first = self.paths.review_variant_suggestions.read_bytes()
        write_suggestions(self.paths, suggest(self.found, decisions, domain(QUENDOLIN)))

        self.assertEqual(self.paths.review_variant_suggestions.read_bytes(), first)
        data = json.loads(first)
        self.assertEqual(data["format_version"], SUGGESTIONS_FORMAT_VERSION)
        self.assertEqual(data["session"], str(self.paths.key))
        self.assertEqual(data["knowledge_snapshot_id"], "snap-1")
        self.assertEqual(data["target_field"], "asr_variants")
        self.assertEqual(data["counts"]["suggested"], 1)
        self.assertEqual(
            data["suggestions"][0]["entries"],
            [{"type": "person", "id": 5, "term": "Quendolin", "field": "name"}],
        )
        self.assertEqual(
            data["suggestions"][0]["decisions"],
            [{"candidate": "s01-p0001", "decided_at": DECIDED}],
        )

    def test_an_empty_list_is_still_written(self) -> None:
        written = review_session(
            self.paths, self.found, SessionDecisions(), domain(QUENDOLIN)
        )

        assert written is not None
        self.assertEqual(written.suggestions, ())
        data = json.loads(self.paths.review_variant_suggestions.read_text("utf-8"))
        self.assertEqual(data["suggestions"], [])

    def test_without_knowledge_an_older_file_is_removed(self) -> None:
        review_session(self.paths, self.found, SessionDecisions(), domain(QUENDOLIN))

        self.assertIsNone(
            review_session(self.paths, self.found, SessionDecisions(), None)
        )
        self.assertFalse(self.paths.review_variant_suggestions.exists())
        self.assertIsNone(
            review_session(self.paths, self.found, SessionDecisions(), None)
        )
