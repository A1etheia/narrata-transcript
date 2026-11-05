import tempfile
import unittest
from pathlib import Path

from test_glossary import entry, glossary
from test_narrata import (
    ALIAS,
    CHARACTER,
    NAME,
    PLACE,
    PLAY_SESSION_ID,
    VARIANT,
    context,
    encoded,
    glossary_entry,
    participant,
)

from transcript.domain import DomainContext, Origin
from transcript.knowledge import SnapshotError, build_snapshot
from transcript.narrata import GlossaryEntry, store_context
from transcript.session import SessionKey, SessionPaths

# Every name below is made up.
BUDGET = {"person": 2, "place": 1}


class DomainContextTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(
            SessionKey("beispielgruppe", 42), Path(directory.name)
        )
        data = context(
            participants=[
                participant(
                    characters=[
                        {"person_id": 7, "name": CHARACTER, "aliases": ["Brakk"]}
                    ]
                )
            ]
        )
        data["glossary"] = [
            glossary_entry(
                type="person",
                id=7,
                name=CHARACTER,
                aliases=["Brakk"],
                asr_variants=[],
                relevance="pc",
            ),
            glossary_entry(id=5, relevance="session"),
            glossary_entry(
                id=6,
                name="Nebelau",
                aliases=[],
                asr_variants=["Nebel"],
                relevance="recent",
            ),
            glossary_entry(
                id=8,
                name="Altfurt",
                aliases=[],
                asr_variants=["Nebel"],
                relevance="archive",
            ),
        ]
        data["asr_ambiguities"] = [
            {
                "variant": "Nebel",
                "entries": [{"type": "place", "id": 6}, {"type": "place", "id": 8}],
            }
        ]
        store_context(self.paths, encoded(data))
        self.snapshot = build_snapshot(self.paths, BUDGET)
        self.context = DomainContext.load(self.paths)

    def test_a_hit_names_its_entry_field_and_origin(self) -> None:
        (hit,) = self.context.lookup(ALIAS.upper())

        self.assertEqual(hit.entry.ref, ("place", 5))
        self.assertEqual(hit.entry.name, PLACE)
        self.assertEqual(
            (hit.kind, hit.field, hit.term), ("alias", "aliases[0]", ALIAS)
        )
        self.assertEqual(hit.entry.relevance, "session")
        self.assertTrue(hit.keyword)
        self.assertEqual(
            hit.origin,
            Origin(
                snapshot_id=self.snapshot.snapshot_id,
                source_file=self.paths.narrata_context.name,
                contract_version="1.1",
                play_session_id=PLAY_SESSION_ID,
            ),
        )

    def test_a_shared_misrecognition_returns_every_entry(self) -> None:
        hits = self.context.lookup("nebel")

        self.assertEqual([h.entry.ref for h in hits], [("place", 6), ("place", 8)])
        self.assertEqual({h.kind for h in hits}, {"asr_variant"})
        self.assertEqual([h.keyword for h in hits], [False, False])
        self.assertEqual(self.context.ambiguities[0].variant, "Nebel")
        self.assertEqual(self.context.lookup("Nebelsee"), ())

    def test_speakers_and_characters_by_archive_id(self) -> None:
        found = self.context.participant(3)
        assert found is not None
        self.assertEqual(found.display_name, NAME)
        self.assertIsNone(self.context.participant(99))

        played = self.context.character(7)
        assert played is not None
        self.assertEqual((played[0].user_id, played[1].name), (3, CHARACTER))
        self.assertIsNone(self.context.character(5))

    def test_entries_by_ref_tier_and_keyword_choice(self) -> None:
        def ids(entries: tuple[GlossaryEntry, ...]) -> list[int | str]:
            return [e.id for e in entries]

        self.assertEqual(ids(self.context.relevant_entries()), [7, 5, 6])
        self.assertEqual(ids(self.context.keyword_entries()), [7, 5])
        place = self.context.entry(("place", 8))
        assert place is not None
        self.assertEqual(place.name, "Altfurt")
        self.assertIsNone(self.context.entry(("place", 99)))

    def test_transcription_keywords_leave_out_misrecognitions(self) -> None:
        self.assertEqual(
            self.context.transcription_keywords(), (CHARACTER, "Brakk", PLACE, ALIAS)
        )

    def test_match_candidates_hold_every_term_with_misrecognitions(self) -> None:
        terms = [(h.entry.id, h.term) for h in self.context.match_candidates()]

        self.assertEqual(
            terms,
            [
                (7, CHARACTER),
                (7, "Brakk"),
                (5, PLACE),
                (5, ALIAS),
                (5, VARIANT),
                (6, "Nebelau"),
                (6, "Nebel"),
                (8, "Altfurt"),
                (8, "Nebel"),
            ],
        )

    def test_queries_change_no_knowledge(self) -> None:
        before = self.paths.knowledge_snapshot.read_bytes()

        self.context.lookup(PLACE)
        self.context.match_candidates()
        self.context.transcription_keywords()
        self.context.relevant_entries()

        self.assertEqual(self.paths.knowledge_snapshot.read_bytes(), before)
        self.assertEqual(DomainContext.load(self.paths).entries, self.context.entries)

    def test_missing_snapshot_points_to_the_command(self) -> None:
        self.paths.knowledge_snapshot.unlink()

        with self.assertRaisesRegex(SnapshotError, "run transcript snapshot"):
            DomainContext.load(self.paths)


class OtherSourceTest(unittest.TestCase):
    def test_context_builds_from_parts_without_a_snapshot(self) -> None:
        place = entry("Grauwasser", "Grauwassr", entry_id=5)
        origin = Origin(None, "elsewhere.json", "1.1", 4711)

        built = DomainContext((), glossary(place), {place.ref}, origin)

        self.assertEqual(built.transcription_keywords(), ("Grauwasser", "Grauwassr"))
        self.assertEqual(built.lookup("grauwassr")[0].origin, origin)
