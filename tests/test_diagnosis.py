import unittest

from test_glossary import entry, glossary

from transcript.diagnosis import Finding, diagnose
from transcript.narrata import Ambiguity, Character, GlossaryEntry, Participant

# Every name below is made up.
MARKER = "Zzyzxbeispiel"  # a name that must never reach a finding


def player(*person_ids: int, former: bool = False) -> Participant:
    return Participant(
        user_id=3,
        display_name="Erika Beispiel",
        role="player",
        is_former=former,
        characters=tuple(Character(i, f"Figur {i}", ()) for i in person_ids),
    )


def pc(entry_id: int, name: str = "Brakk") -> GlossaryEntry:
    return entry(name, entry_id=entry_id, entry_type="person", relevance="pc")


def codes(findings: tuple[Finding, ...]) -> list[str]:
    return [f.code for f in findings]


class ValidKnowledgeTest(unittest.TestCase):
    def test_consistent_knowledge_has_no_findings(self) -> None:
        knowledge = glossary(
            pc(18),
            entry("Grauwasser", "Grauwassr", variants=("Grau Wasser",), entry_id=5),
            entry("Nebelsee", entry_id=9, entry_type="lore", relevance="archive"),
        )

        self.assertEqual(diagnose([player(18)], knowledge), ())

    def test_repeated_term_within_one_entry_is_no_finding(self) -> None:
        knowledge = glossary(entry("Grauwasser", "grauwasser", entry_id=5))

        self.assertEqual(diagnose([], knowledge), ())


class TermTest(unittest.TestCase):
    def test_empty_alias_and_variant_are_reported_by_position(self) -> None:
        knowledge = glossary(entry("Grauwasser", " ", variants=("",), entry_id=5))

        findings = diagnose([], knowledge)

        self.assertEqual(codes(findings), ["empty_term", "empty_term"])
        self.assertEqual(
            [f.where for f in findings],
            [("glossary[0].aliases[0]",), ("glossary[0].asr_variants[0]",)],
        )
        self.assertEqual({f.severity for f in findings}, {"warning"})

    def test_alias_shared_with_another_name_names_both_entries(self) -> None:
        knowledge = glossary(
            entry("Grauwasser", entry_id=5),
            entry("Hafen", "GRAUWASSER", entry_id=7, entry_type="organisation"),
        )

        (finding,) = diagnose([], knowledge)

        self.assertEqual(finding.severity, "warning")
        self.assertEqual(finding.code, "shared_term")
        self.assertEqual(finding.where, ("glossary[0].name", "glossary[1].aliases[0]"))
        self.assertEqual(finding.entries, (("place", 5), ("organisation", 7)))


class VariantTest(unittest.TestCase):
    def test_variant_reported_by_narrata_is_only_ambiguous(self) -> None:
        knowledge = glossary(
            entry("Grauwasser", variants=("Grau Wasser",), entry_id=5),
            entry("Grauwaser", variants=("grau wasser",), entry_id=9),
            ambiguities=(Ambiguity("grau wasser", (("place", 5), ("place", 9))),),
        )

        self.assertEqual(codes(diagnose([], knowledge)), ["ambiguous_asr_variant"])

    def test_variant_narrata_did_not_report_is_flagged(self) -> None:
        knowledge = glossary(
            entry("Grauwasser", variants=("Grau Wasser",), entry_id=5),
            entry("Grauwaser", variants=("grau wasser",), entry_id=9),
        )

        (finding,) = diagnose([], knowledge)

        self.assertEqual(finding.code, "unreported_asr_variant")
        self.assertEqual(finding.entries, (("place", 5), ("place", 9)))

    def test_ambiguity_naming_an_entry_without_the_variant_is_stale(self) -> None:
        knowledge = glossary(
            entry("Grauwasser", variants=("Grau Wasser",), entry_id=5),
            entry("Grauwaser", entry_id=9),
            ambiguities=(Ambiguity("Grau Wasser", (("place", 5), ("place", 9))),),
        )

        (finding,) = diagnose([], knowledge)

        self.assertEqual(finding.code, "stale_ambiguity")
        self.assertEqual(finding.where, ("asr_ambiguities[0]",))
        self.assertEqual(finding.entries, (("place", 9),))

    def test_variant_that_is_another_entrys_name_shadows_it(self) -> None:
        knowledge = glossary(
            entry("Grauwasser", variants=("Nebelsee",), entry_id=5),
            entry("Nebelsee", entry_id=9, entry_type="lore"),
        )

        (finding,) = diagnose([], knowledge)

        self.assertEqual(finding.code, "variant_shadows_term")
        self.assertEqual(
            finding.where, ("glossary[0].asr_variants[0]", "glossary[1].name")
        )
        self.assertEqual(finding.entries, (("place", 5), ("lore", 9)))


class CharacterTest(unittest.TestCase):
    def test_character_without_glossary_entry_is_unknown(self) -> None:
        (finding,) = diagnose([player(18)], glossary())

        self.assertEqual(finding.code, "unknown_character")
        self.assertEqual(finding.where, ("participants[0].characters[0]",))
        self.assertEqual(finding.entries, (("person", 18),))

    def test_active_players_character_outside_the_pc_tier(self) -> None:
        knowledge = glossary(entry("Brakk", entry_id=18, entry_type="person"))

        (finding,) = diagnose([player(18)], knowledge)

        self.assertEqual(finding.code, "character_not_pc")
        self.assertEqual(
            finding.where, ("participants[0].characters[0]", "glossary[0]")
        )

    def test_former_participants_characters_are_not_checked(self) -> None:
        knowledge = glossary(
            entry("Brakk", entry_id=18, entry_type="person", relevance="archive")
        )

        self.assertEqual(diagnose([player(18, 19, former=True)], knowledge), ())

    def test_pc_entry_without_an_active_player_is_orphaned(self) -> None:
        knowledge = glossary(
            pc(18), entry("Ort", entry_id=19, relevance="pc"), pc(20, "Gorm")
        )

        findings = diagnose([player(20), player(18, former=True)], knowledge)

        self.assertEqual(codes(findings), ["orphan_pc", "orphan_pc"])
        self.assertEqual(
            [f.entries for f in findings], [(("person", 18),), (("place", 19),)]
        )


class PrivacyTest(unittest.TestCase):
    def test_findings_never_contain_a_name(self) -> None:
        knowledge = glossary(
            entry(MARKER, "", variants=(MARKER.lower(),), entry_id=5),
            entry(f"{MARKER}s", MARKER, variants=(MARKER,), entry_id=9),
            pc(18, MARKER),
        )

        findings = diagnose([player(18, 30)], knowledge)

        self.assertGreater(len(findings), 3)
        self.assertNotIn(MARKER.casefold(), repr(findings).casefold())


if __name__ == "__main__":
    unittest.main()
