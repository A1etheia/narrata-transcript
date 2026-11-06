import datetime
import json
import tempfile
import time
import unittest
from pathlib import Path

from test_glossary import entry, glossary
from test_reference import minimal

from transcript.domain import DomainContext, Origin
from transcript.hints import (
    Hint,
    HintsError,
    cologne_phonetic,
    find_hints,
    load_hints,
    segment_hints,
    write_hints,
)
from transcript.narrata import Ambiguity, GlossaryEntry
from transcript.reference import AsrInfo, Passage, ReferenceTranscript, Word
from transcript.session import SessionPaths

# Every name below is made up.
ORIGIN = Origin("ab" * 32, "ctx.json", "1.1", 4711)
GRAUWASSER = entry("Grauwasser", "Graues Wasser", variants=("Grauwassa",), entry_id=1)
NEBELAU = entry("Nebelau", variants=("Nebel Au",), entry_id=2, relevance="recent")
ALTFURT = entry("Altfurt", variants=("Nebel Au",), entry_id=3, relevance="archive")
BRAKK = entry(
    "Brakk Þornfeld", "Brakk", entry_id=7, relevance="pc", entry_type="person"
)


def domain(
    *entries: GlossaryEntry, ambiguities: tuple[Ambiguity, ...] = ()
) -> DomainContext:
    known = glossary(*entries, ambiguities=ambiguities)
    return DomainContext((), known, {e.ref for e in entries}, ORIGIN)


def spoken(*texts: str, keywords: tuple[str, ...] = ()) -> ReferenceTranscript:
    """One passage per text, each word 100 ms long."""
    passages = []
    clock = 0
    for number, text in enumerate(texts, start=1):
        words = []
        for word in text.split():
            words.append(Word(word, clock, clock + 100, 0.9))
            clock += 100
        passages.append(Passage(number, text, words[0].start_ms, clock, tuple(words)))
    return minimal(
        passages=tuple(passages),
        asr=AsrInfo(backend_id="fake", model="fake", keywords_used=keywords),
    )


def only(hints: tuple[Hint, ...]) -> Hint:
    if len(hints) != 1:
        raise AssertionError(f"expected one hint, got {hints}")
    return hints[0]


class KnownVariantTest(unittest.TestCase):
    def test_a_known_misrecognition_is_a_strong_unambiguous_hint(self) -> None:
        hint = only(
            find_hints(spoken("Wir reiten nach Grauwassa."), domain(GRAUWASSER))
        )

        self.assertEqual(hint.signal, "known_variant")
        self.assertIsNone(hint.method)
        self.assertFalse(hint.ambiguous)
        self.assertEqual(hint.heard, "Grauwassa.")
        self.assertEqual((hint.passage, hint.first_word, hint.last_word), (1, 3, 3))
        self.assertEqual((hint.start_ms, hint.end_ms), (300, 400))
        (candidate,) = hint.candidates
        self.assertEqual(candidate.ref, ("place", 1))
        self.assertEqual(
            (candidate.term, candidate.kind, candidate.field),
            ("Grauwassa", "asr_variant", "asr_variants[0]"),
        )

    def test_a_variant_two_entries_share_is_ambiguous(self) -> None:
        shared = (Ambiguity("Nebel Au", (NEBELAU.ref, ALTFURT.ref)),)
        hint = only(
            find_hints(
                spoken("Hinter Nebel Au liegt nichts."),
                domain(NEBELAU, ALTFURT, ambiguities=shared),
            )
        )

        self.assertEqual(hint.signal, "known_variant")
        self.assertTrue(hint.ambiguous)
        self.assertEqual(hint.heard, "Nebel Au")
        self.assertEqual([c.ref for c in hint.candidates], [NEBELAU.ref, ALTFURT.ref])

    def test_narrata_reported_ambiguity_alone_makes_a_hint_ambiguous(self) -> None:
        shared = (Ambiguity("Nebel Au", (NEBELAU.ref, ALTFURT.ref)),)
        hint = only(find_hints(spoken("Nebel Au"), domain(NEBELAU, ambiguities=shared)))

        self.assertTrue(hint.ambiguous)
        self.assertEqual(len(hint.candidates), 1)


class SimilarTest(unittest.TestCase):
    def test_a_split_name_is_a_weak_spelling_hint(self) -> None:
        hint = only(
            find_hints(spoken("Bis Grau Wasser sind es Tage."), domain(GRAUWASSER))
        )

        self.assertEqual(
            (hint.signal, hint.method, hint.score), ("similar", "spelling", 1.0)
        )
        self.assertEqual(hint.heard, "Grau Wasser")
        self.assertEqual((hint.first_word, hint.last_word), (1, 2))
        self.assertEqual(hint.candidates[0].kind, "name")

    def test_a_close_spelling_is_a_weak_hint(self) -> None:
        hint = only(find_hints(spoken("Grauwasserr"), domain(GRAUWASSER)))

        self.assertEqual(hint.signal, "similar")
        self.assertEqual(hint.method, "spelling")
        self.assertGreaterEqual(hint.score or 0, 0.85)

    def test_the_same_sound_is_a_weak_hint(self) -> None:
        place = entry("Kaltenfels", entry_id=4)
        self.assertEqual(cologne_phonetic("Kaltenfels"), cologne_phonetic("Caltenvelz"))

        hint = only(find_hints(spoken("Caltenvelz"), domain(place)))

        self.assertEqual(
            (hint.signal, hint.method, hint.score), ("similar", "sound", None)
        )

    def test_close_to_two_entries_is_ambiguous(self) -> None:
        first = entry("Morwenstein", entry_id=5)
        second = entry("Marwenstein", entry_id=6)

        hint = only(find_hints(spoken("Merwenstein"), domain(first, second)))

        self.assertTrue(hint.ambiguous)
        self.assertEqual([c.ref for c in hint.candidates], [first.ref, second.ref])

    def test_short_or_lowercase_words_give_no_hint(self) -> None:
        place = entry("Graufels", "Ruhe", entry_id=4)

        self.assertEqual(
            find_hints(spoken("Ruhig graufelz Ruhe Rune"), domain(place)), ()
        )


class NoHintTest(unittest.TestCase):
    def test_a_correctly_recognised_name_or_alias_gives_no_hint(self) -> None:
        reference = spoken("Grauwasser und Graues Wasser.", "Brakk Þornfeld kommt.")

        self.assertEqual(find_hints(reference, domain(GRAUWASSER, BRAKK)), ())

    def test_without_knowledge_or_words_there_is_no_hint(self) -> None:
        self.assertEqual(find_hints(spoken("Grauwassa"), domain()), ())
        self.assertEqual(find_hints(minimal(), domain(GRAUWASSER)), ())

    def test_text_without_words_still_gives_hints_without_positions(self) -> None:
        reference = minimal(passages=(Passage(1, "Nach Grauwassa!"),))

        hint = only(find_hints(reference, domain(GRAUWASSER)))

        self.assertEqual((hint.first_word, hint.start_ms), (None, None))
        self.assertEqual(hint.heard, "Grauwassa!")


class InfluenceTest(unittest.TestCase):
    def test_a_candidate_says_whether_it_was_an_asr_hint(self) -> None:
        reference = spoken("Grau Wasser", keywords=("grauwasser",))

        (candidate,) = only(find_hints(reference, domain(GRAUWASSER))).candidates

        self.assertTrue(candidate.biased)
        (candidate,) = only(
            find_hints(spoken("Grau Wasser"), domain(GRAUWASSER))
        ).candidates
        self.assertFalse(candidate.biased)

    def test_the_transcript_is_unchanged(self) -> None:
        reference = spoken("Nach Grauwassa und Grau Wasser.")
        before = repr(reference)

        self.assertEqual(len(find_hints(reference, domain(GRAUWASSER))), 2)

        self.assertEqual(repr(reference), before)


class HintFileTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(minimal().key, Path(directory.name))
        reference = spoken("Nach Grauwassa.", "Hinter Nebel Au und Grau Wasser")
        shared = (Ambiguity("Nebel Au", (NEBELAU.ref, ALTFURT.ref)),)
        self.hints = segment_hints(
            reference, domain(GRAUWASSER, NEBELAU, ALTFURT, ambiguities=shared)
        )
        self.path = self.paths.review_hints(1)

    def stored(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def rewrite(self, data: dict) -> None:
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_a_round_trip_keeps_every_field(self) -> None:
        write_hints(self.paths, self.hints, datetime.datetime(2026, 11, 6, 9, 0))

        self.assertEqual(load_hints(self.paths, 1), self.hints)
        data = self.stored()
        self.assertEqual(data["format_version"], 1)
        self.assertEqual(data["reference"]["file"], "segment-01.json")
        self.assertEqual(
            data["counts"], {"ambiguous": 1, "known_variant": 2, "similar": 1}
        )

    def test_another_version_or_segment_is_rejected(self) -> None:
        write_hints(self.paths, self.hints)
        data = self.stored()
        self.rewrite({**data, "format_version": 2})
        with self.assertRaisesRegex(HintsError, "unsupported format_version"):
            load_hints(self.paths, 1)
        self.rewrite({**data, "segment": 2})
        with self.assertRaisesRegex(HintsError, "another session or segment"):
            load_hints(self.paths, 1)

    def test_an_invalid_hint_names_position_and_field_but_no_value(self) -> None:
        write_hints(self.paths, self.hints)
        data = self.stored()
        data["hints"][1]["candidates"][0]["kind"] = "Grauwasser"
        self.rewrite(data)

        with self.assertRaises(HintsError) as raised:
            load_hints(self.paths, 1)

        message = str(raised.exception)
        self.assertIn("hint 2: field 'kind' invalid", message)
        self.assertNotIn("Grauwasser", message)
        self.assertNotIn("Nebel", message)


class PhoneticTest(unittest.TestCase):
    def test_reference_codes(self) -> None:
        for term, code in (
            ("Müller-Lüdenscheidt", "65752682"),
            ("Wikipedia", "3412"),
            ("Breschnew", "17863"),
            ("Xaver", "4837"),
            ("Ærwyn", "736"),
        ):
            self.assertEqual(cologne_phonetic(term), code, term)


class SpeedTest(unittest.TestCase):
    def test_a_long_segment_against_a_full_archive(self) -> None:
        letters = "bdfgklmnprst"
        terms = [
            entry(
                f"{letters[n % 12].upper()}{letters[n // 12 % 12]}a"
                f"{letters[n // 144 % 12]}or{n}",
                entry_id=n,
                relevance="archive",
            )
            for n in range(1500)
        ]
        words = " ".join(
            f"{letters[n % 12].upper()}a{letters[n // 7 % 12]}ur{n % 1700} und"
            if n % 3
            else f"Halde{n % 50}"
            for n in range(18_000)
        )
        reference = spoken(words)
        self.assertEqual(len(reference.words), 30_000)
        context = domain(*terms)

        start = time.monotonic()
        find_hints(reference, context)

        self.assertLess(time.monotonic() - start, 10)


if __name__ == "__main__":
    unittest.main()
