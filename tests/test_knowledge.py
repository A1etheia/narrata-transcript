import datetime
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from test_narrata import CHARACTER, NAME, context, encoded, glossary_entry
from test_narrata import participant as participant_json

from transcript.jsonfile import DataFileError
from transcript.knowledge import (
    SnapshotError,
    _snapshot_id,
    build_snapshot,
    drift,
    load_snapshot,
    select_keywords,
)
from transcript.narrata import GlossaryEntry, Relevance, store_context
from transcript.session import SessionKey, SessionPaths

# Every name below is made up.
MARKER = "Zzyzxbeispiel"  # a name that must never reach a message
BUDGET = {
    "person": 2,
    "place": 1,
    "organisation": 0,
    "artifact": 0,
    "event": 0,
    "lore": 0,
}
NOW = datetime.datetime(2026, 11, 5, 20, 0, tzinfo=datetime.timezone.utc)


def entry(
    entry_id: int, relevance: Relevance, entry_type: str = "person"
) -> GlossaryEntry:
    return GlossaryEntry(
        type=entry_type,  # type: ignore[arg-type]
        id=entry_id,
        name=f"Name {entry_id}",
        aliases=(),
        asr_variants=(),
        summary=None,
        relevance=relevance,
    )


class SelectKeywordsTest(unittest.TestCase):
    def test_player_characters_are_always_chosen_and_never_counted(self) -> None:
        entries = [entry(i, "pc") for i in range(1, 5)] + [entry(9, "session")]

        chosen = select_keywords(entries, {"person": 1})

        self.assertEqual([e.id for e in chosen], [1, 2, 3, 4, 9])

    def test_nearer_tier_fills_the_budget_first(self) -> None:
        entries = [
            entry(1, "session"),
            entry(2, "session"),
            entry(3, "recent"),
            entry(4, "recent", "place"),
            entry(5, "recent", "place"),
        ]

        chosen = select_keywords(entries, BUDGET)

        self.assertEqual([e.id for e in chosen], [1, 2, 4])

    def test_archive_and_types_without_budget_are_never_chosen(self) -> None:
        entries = [
            entry(1, "archive"),
            entry(2, "session", "lore"),
            entry(3, "session", "event"),
        ]

        self.assertEqual(select_keywords(entries, {"person": 9, "lore": 0}), ())


class SnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(
            SessionKey("beispielgruppe", 42), Path(directory.name)
        )

    def store(self, **overrides: Any) -> dict[str, Any]:
        data = context(
            participants=[
                participant_json(
                    characters=[{"person_id": 7, "name": CHARACTER, "aliases": []}]
                )
            ]
        )
        data["glossary"] = [
            glossary_entry(type="person", id=7, name=CHARACTER, relevance="pc"),
            glossary_entry(id=5, relevance="session"),
            glossary_entry(id=6, name="Nebelau", relevance="recent"),
            glossary_entry(id=8, name="Altfurt", relevance="archive"),
        ]
        data["glossary_meta"] = {"archive_total": 40, "archive_returned": 1}
        data["asr_ambiguities"] = [
            {
                "variant": "Nebel",
                "entries": [{"type": "place", "id": 6}, {"type": "place", "id": 8}],
            }
        ]
        data.update(overrides)
        store_context(self.paths, encoded(data))
        return data

    def build(self, budget: dict[str, int] = BUDGET) -> Any:
        return build_snapshot(self.paths, budget, now=NOW)

    def test_snapshot_keeps_origin_reason_and_ids_of_every_entry(self) -> None:
        self.store()

        snapshot = self.build()

        self.assertEqual(snapshot.path, self.paths.knowledge_snapshot)
        self.assertEqual(snapshot.created_at, "2026-11-05T20:00:00+00:00")
        self.assertEqual(snapshot.source.file, "transcription-context.json")
        self.assertEqual(snapshot.source.contract_version, "1.1")
        self.assertEqual(snapshot.source.play_session_id, 4711)
        self.assertEqual(
            [(e.type, e.id, e.relevance) for e in snapshot.glossary.entries],
            [
                ("person", 7, "pc"),
                ("place", 5, "session"),
                ("place", 6, "recent"),
                ("place", 8, "archive"),
            ],
        )
        self.assertEqual(
            [participant.display_name for participant in snapshot.participants],
            [NAME],
        )
        self.assertEqual(snapshot.participants[0].characters[0].person_id, 7)

    def test_keywords_follow_tier_and_budget(self) -> None:
        self.store()

        snapshot = self.build()

        # place budget 1: the session entry wins over the recent one
        self.assertEqual([e.id for e in snapshot.keyword_entries], [7, 5])
        self.assertEqual(dict(snapshot.keyword_budget), BUDGET)

    def test_ambiguities_and_archive_cap_survive(self) -> None:
        self.store()

        glossary = self.build().glossary

        self.assertEqual(
            [(a.variant, a.entries) for a in glossary.ambiguities],
            [("Nebel", (("place", 6), ("place", 8)))],
        )
        self.assertEqual((glossary.archive_total, glossary.archive_returned), (40, 1))

    def test_snapshot_reads_without_the_context_file(self) -> None:
        self.store()
        built = self.build()
        self.paths.narrata_context.unlink()

        self.assertEqual(load_snapshot(self.paths), built)

    def test_same_knowledge_gives_the_same_id(self) -> None:
        self.store()
        first = self.build()

        later = build_snapshot(self.paths, BUDGET, now=NOW + datetime.timedelta(days=3))

        self.assertEqual(later.snapshot_id, first.snapshot_id)
        self.assertNotEqual(later.created_at, first.created_at)

    def test_changed_knowledge_or_budget_gives_a_new_id(self) -> None:
        self.store()
        first = self.build().snapshot_id

        self.assertNotEqual(self.build({**BUDGET, "place": 2}).snapshot_id, first)
        self.store(glossary_meta={"archive_total": 41, "archive_returned": 1})
        self.assertNotEqual(self.build().snapshot_id, first)

    def test_drift_names_a_changed_context_or_budget(self) -> None:
        self.store()
        snapshot = self.build()

        self.assertFalse(drift(snapshot, self.paths, BUDGET).any)
        changed_budget = drift(snapshot, self.paths, {**BUDGET, "lore": 1})
        self.assertEqual(
            (changed_budget.context_changed, changed_budget.budget_changed),
            (False, True),
        )
        self.store(glossary_meta={"archive_total": 41, "archive_returned": 1})
        self.assertTrue(drift(snapshot, self.paths, BUDGET).context_changed)
        self.paths.narrata_context.unlink()
        self.assertFalse(drift(snapshot, self.paths, BUDGET).any)

    def test_invalid_context_writes_no_snapshot(self) -> None:
        self.store()
        self.build()
        before = self.paths.knowledge_snapshot.read_bytes()
        data = json.loads(self.paths.narrata_context.read_bytes())
        data["glossary"][1]["relevance"] = "elsewhere"
        self.paths.narrata_context.write_bytes(encoded(data))

        with self.assertRaises(DataFileError):
            self.build()
        self.assertEqual(self.paths.knowledge_snapshot.read_bytes(), before)

    def test_missing_snapshot_points_to_the_command(self) -> None:
        with self.assertRaises(SnapshotError) as caught:
            load_snapshot(self.paths)

        self.assertIn("run transcript snapshot", str(caught.exception))

    def test_damaged_snapshot_is_rejected_without_naming_values(self) -> None:
        self.store(
            glossary=[glossary_entry(id=5, name=MARKER, relevance="session")],
            asr_ambiguities=[],
        )
        self.build()
        original = json.loads(self.paths.knowledge_snapshot.read_bytes())

        def damaged(change: Any) -> dict[str, Any]:
            data = json.loads(json.dumps(original))
            change(data)
            return data

        for name, data, expected in (
            (
                "version",
                damaged(lambda d: d.update(format_version=2)),
                "unsupported format_version; run transcript snapshot --refresh",
            ),
            (
                "session",
                damaged(lambda d: d["session"].update(ordinal=43)),
                "belongs to another session than beispielgruppe/042",
            ),
            (
                "edited name",
                damaged(lambda d: d["glossary"][0].update(name=MARKER + "x")),
                "snapshot_id does not match the content",
            ),
            (
                "keyword flag",
                damaged(lambda d: d["glossary"][0].update(keyword="yes")),
                "snapshot_id does not match the content",
            ),
        ):
            with self.subTest(name=name):
                self.paths.knowledge_snapshot.write_text(json.dumps(data))

                with self.assertRaises(DataFileError) as caught:
                    load_snapshot(self.paths)

                self.assertIn(expected, str(caught.exception))
                self.assertNotIn(MARKER, str(caught.exception))

    def test_consistent_but_invalid_snapshot_names_the_field(self) -> None:
        self.store(glossary=[glossary_entry(id=5, name=MARKER)], asr_ambiguities=[])
        self.build()
        data = json.loads(self.paths.knowledge_snapshot.read_bytes())
        data["glossary"][0]["keyword"] = "yes"
        resigned = _resigned(data)
        self.paths.knowledge_snapshot.write_text(json.dumps(resigned))

        with self.assertRaises(SnapshotError) as caught:
            load_snapshot(self.paths)

        self.assertIn("glossary[0].keyword missing or invalid", str(caught.exception))
        self.assertNotIn(MARKER, str(caught.exception))

    def test_participants_survive_with_characters_and_aliases(self) -> None:
        self.store(
            participants=[
                participant_json(
                    role="gm",
                    characters=[
                        {"person_id": 7, "name": CHARACTER, "aliases": ["Brakk"]}
                    ],
                ),
                participant_json(user_id=4, is_former=True),
            ]
        )
        self.build()

        [gm, former] = load_snapshot(self.paths).participants

        self.assertEqual((gm.role, gm.is_former, gm.present), ("gm", False, None))
        self.assertEqual(
            [(c.person_id, c.name, c.aliases) for c in gm.characters],
            [(7, CHARACTER, ("Brakk",))],
        )
        self.assertEqual((former.user_id, former.is_former), (4, True))

    def test_resigned_snapshot_with_invalid_content_names_the_field(self) -> None:
        self.store(glossary=[glossary_entry(id=5, name=MARKER)], asr_ambiguities=[])
        self.build()
        original = json.loads(self.paths.knowledge_snapshot.read_bytes())
        for change, expected in (
            (
                lambda d: d["source"].update(contract_version="2.0"),
                "contract_version 2.0 is not supported",
            ),
            (
                lambda d: d["glossary"][0].update(relevance="elsewhere"),
                "glossary[0].relevance missing or not a known value",
            ),
            (
                lambda d: d["participants"][0].update(role="bard"),
                "participants[0].role missing or invalid",
            ),
            (
                lambda d: d.update(format_version=True),
                "unsupported format_version",
            ),
        ):
            with self.subTest(expected=expected):
                data = json.loads(json.dumps(original))
                change(data)
                self.paths.knowledge_snapshot.write_text(json.dumps(_resigned(data)))

                with self.assertRaises(SnapshotError) as caught:
                    load_snapshot(self.paths)

                self.assertIn(expected, str(caught.exception))
                self.assertNotIn(MARKER, str(caught.exception))

    def test_building_leaves_the_context_unchanged(self) -> None:
        self.store()
        before = self.paths.narrata_context.read_bytes()

        self.build()

        self.assertEqual(self.paths.narrata_context.read_bytes(), before)


def _resigned(data: dict[str, Any]) -> dict[str, Any]:
    """`data` with a `snapshot_id` that fits its content again."""
    return {**data, "snapshot_id": _snapshot_id(data)}


if __name__ == "__main__":
    unittest.main()
