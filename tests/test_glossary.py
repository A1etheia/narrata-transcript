import unicodedata
import unittest
from pathlib import Path

from transcript.glossary import GlossaryIndex, Match, keyword_terms, normalize
from transcript.narrata import Ambiguity, GlossaryEntry, NarrataGlossary, Relevance

# Every name below is made up.


def entry(
    name: str,
    *aliases: str,
    variants: tuple[str, ...] = (),
    entry_id: int = 1,
    relevance: Relevance = "session",
    entry_type: str = "place",
) -> GlossaryEntry:
    return GlossaryEntry(
        type=entry_type,  # type: ignore[arg-type]
        id=entry_id,
        name=name,
        aliases=aliases,
        asr_variants=variants,
        summary=None,
        relevance=relevance,
    )


def glossary(
    *entries: GlossaryEntry, ambiguities: tuple[Ambiguity, ...] = ()
) -> NarrataGlossary:
    return NarrataGlossary(
        source=Path("ctx.json"),
        contract_version="1.1",
        play_session_id=4711,
        entries=entries,
        archive_total=0,
        archive_returned=0,
        ambiguities=ambiguities,
    )


class NormalizeTest(unittest.TestCase):
    def test_spellings_of_the_same_term_share_a_key(self) -> None:
        composed = "Mühlbräu"
        decomposed = unicodedata.normalize("NFD", composed)
        self.assertNotEqual(composed, decomposed)
        for left, right in (
            (composed, decomposed),
            ("Straße der Ahnen", "STRASSE DER AHNEN"),
            ("  Ærwyn   Þornfeld ", "ærwyn þornfeld"),
            ("Ærwyn Þornfeld", "ærwyn þornfeld"),
            ("Grau­was\u200bser﻿", "grauwasser"),
            ("ΟΔΟΣ", "οδος"),
        ):
            with self.subTest(left=left):
                self.assertEqual(normalize(left), normalize(right))

    def test_key_is_nfc_even_where_casefold_breaks_it(self) -> None:
        for term in ("İstanbul", "ΐ", "Ǆ", unicodedata.normalize("NFD", "ÅNGSTRÖM")):
            with self.subTest(term=term):
                key = normalize(term)
                self.assertEqual(key, unicodedata.normalize("NFC", key))
                self.assertEqual(normalize(key), key)

    def test_distinct_terms_stay_distinct(self) -> None:
        self.assertNotEqual(normalize("Mühl"), normalize("Muhl"))
        self.assertNotEqual(normalize("Ka'ran"), normalize("Karan"))
        self.assertNotEqual(normalize("Nebel-Au"), normalize("Nebel Au"))


class GlossaryIndexTest(unittest.TestCase):
    def test_finds_by_name_alias_and_variant_with_the_kind(self) -> None:
        place = entry("Grauwasser", "Grauwassr", variants=("Grau Wasser",))
        index = GlossaryIndex(glossary(place))

        self.assertEqual(
            index.lookup("grauwasser"), (Match(place, "name", "name", "Grauwasser"),)
        )
        self.assertEqual(
            index.lookup("GRAUWASSR"),
            (Match(place, "alias", "aliases[0]", "Grauwassr"),),
        )
        self.assertEqual(
            index.lookup(" grau  wasser "),
            (Match(place, "asr_variant", "asr_variants[0]", "Grau Wasser"),),
        )

    def test_unicode_and_fantasy_names_are_found(self) -> None:
        composed = entry("Mühlbräu", entry_id=1)
        fantasy = entry("Ærwyn Þornfeld", "Ka'ran-Dûl", entry_id=2)
        kanji = entry("雪の門", entry_id=3)
        index = GlossaryIndex(glossary(composed, fantasy, kanji))

        self.assertEqual(
            index.lookup(unicodedata.normalize("NFD", "MÜHLBRÄU")),
            (Match(composed, "name", "name", "Mühlbräu"),),
        )
        self.assertEqual(
            index.lookup(unicodedata.normalize("NFD", "KA'RAN-DÛL")),
            (Match(fantasy, "alias", "aliases[0]", "Ka'ran-Dûl"),),
        )
        self.assertEqual(
            index.lookup("雪の門"), (Match(kanji, "name", "name", "雪の門"),)
        )

    def test_shared_term_returns_every_entry_in_glossary_order(self) -> None:
        first = entry("Brakk", entry_id=1, relevance="pc")
        second = entry("Brakkenfels", "brakk", entry_id=2)
        third = entry("Ödland", variants=("Brakk",), entry_id=3)
        index = GlossaryIndex(glossary(first, second, third))

        self.assertEqual(
            index.lookup("Brakk"),
            (
                Match(first, "name", "name", "Brakk"),
                Match(second, "alias", "aliases[0]", "brakk"),
                Match(third, "asr_variant", "asr_variants[0]", "Brakk"),
            ),
        )

    def test_one_entry_matches_once_with_its_strongest_kind(self) -> None:
        place = entry("Grauwasser", "GRAUWASSER", variants=("grauwasser",))

        self.assertEqual(
            GlossaryIndex(glossary(place)).lookup("Grauwasser"),
            (Match(place, "name", "name", "Grauwasser"),),
        )

    def test_unknown_and_blank_terms_find_nothing(self) -> None:
        index = GlossaryIndex(glossary(entry("Grauwasser", " ")))

        self.assertEqual(index.lookup("Nebelsee"), ())
        self.assertEqual(index.lookup(" "), ())
        self.assertEqual(GlossaryIndex(glossary()).lookup("Grauwasser"), ())


class KeywordTermsTest(unittest.TestCase):
    def test_names_and_aliases_in_glossary_order_without_variants(self) -> None:
        terms = keyword_terms(
            (
                entry("Ærwyn", entry_id=3),
                entry("Brakk", "Brakki", entry_id=1),
                entry("Grauwasser", variants=("Grau Wasser",), entry_id=2),
            )
        )

        self.assertEqual(terms, ("Ærwyn", "Brakk", "Brakki", "Grauwasser"))

    def test_repeats_keep_the_first_spelling(self) -> None:
        decomposed = unicodedata.normalize("NFD", "MÜHLBRÄU")
        terms = keyword_terms(
            (
                entry("Mühlbräu", "mühlbräu", entry_id=1),
                entry(decomposed, " ", entry_id=2),
            )
        )

        self.assertEqual(terms, ("Mühlbräu",))

    def test_terms_are_tidied_but_keep_letters_and_case(self) -> None:
        decomposed = unicodedata.normalize("NFD", "Mühl Bräu")
        terms = keyword_terms([entry(f"  {decomposed}\t", "Grau­Wasser", entry_id=1)])

        self.assertEqual(terms, ("Mühl Bräu", "GrauWasser"))
        self.assertEqual(terms[0], unicodedata.normalize("NFC", terms[0]))

    def test_empty_glossary_gives_no_terms(self) -> None:
        self.assertEqual(keyword_terms(()), ())


if __name__ == "__main__":
    unittest.main()
