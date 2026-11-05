import datetime
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from transcript.narrata import (
    Character,
    NarrataContextError,
    Participant,
    check_contract,
    read_participants,
    read_session,
    store_context,
)
from transcript.session import SessionKey, SessionPaths

PLAY_SESSION_ID = 4711  # made up; real ids never enter the repo
NAME = "Erika Beispiel"  # made up; stands in for a participant's real name
CHARACTER = "Brakk der Beispielhafte"  # made up, like every name below


def participant(**values: object) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "user_id": 3,
        "display_name": NAME,
        "role": "player",
        "is_former": False,
        "characters": [],
    }
    entry.update(values)
    return entry


def context(
    version: Any = "1.1",
    participants: list[Any] | None = None,
    **session: object,
) -> dict[str, Any]:
    values: dict[str, object] = {
        "play_session_id": PLAY_SESSION_ID,
        "ordinal": 42,
        "session_date": "2026-10-30",
        "title": None,
        "adventures": [],
    }
    values.update(session)
    data: dict[str, Any] = {
        "session": values,
        "participants": [participant()] if participants is None else participants,
        "glossary": [],
        "glossary_meta": {"archive_total": 0, "archive_returned": 0},
        "asr_ambiguities": [],
    }
    if version is not None:
        data["contract_version"] = version
    return data


def encoded(data: dict[str, Any]) -> bytes:
    # Not the layout `write_atomic` produces, so an unchanged copy is visible.
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()


class ContractTest(unittest.TestCase):
    def test_every_minor_of_major_1_is_accepted(self) -> None:
        for version in ("1.0", "1.1", "1.12"):
            with self.subTest(version=version):
                check_contract(context(version), Path("ctx.json"))

    def test_other_versions_are_rejected_with_the_supported_one(self) -> None:
        for version, expected in (
            (None, "contract_version missing or invalid"),
            (1.1, "contract_version missing or invalid"),
            ("1", "contract_version missing or invalid"),
            ("1.01", "contract_version missing or invalid"),
            ("v1.1", "contract_version missing or invalid"),
            ("0.9", "contract_version missing or invalid"),
            ("2.0", "contract_version 2.0 is not supported"),
        ):
            with self.subTest(version=version):
                with self.assertRaises(NarrataContextError) as caught:
                    check_contract(context(version), Path("ctx.json"))
                message = str(caught.exception)
                self.assertIn(expected, message)
                self.assertIn("supported is 1.x", message)


class StoreContextTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(
            SessionKey("beispielgruppe", 42), Path(directory.name)
        )

    def test_response_is_stored_byte_for_byte(self) -> None:
        raw = encoded(context())

        session = store_context(self.paths, raw)

        self.assertEqual(self.paths.narrata_context.read_bytes(), raw)
        self.assertEqual(session.play_session_id, PLAY_SESSION_ID)
        self.assertEqual(session.session_date, datetime.date(2026, 10, 30))
        self.assertEqual(read_session(self.paths), session)

    def test_invalid_response_keeps_the_stored_file(self) -> None:
        good = encoded(context())
        store_context(self.paths, good)
        for raw, expected in (
            (b"\xff", "Narrata context is unreadable"),
            (b"{", "Narrata context is unreadable"),
            (b"[]", "not a JSON object"),
            (encoded(context("2.0")), "contract_version 2.0 is not supported"),
            (encoded(context(ordinal=43)), "session.ordinal is 43"),
            (encoded(context(session_date="30.10.2026")), "session.session_date"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaises(NarrataContextError) as caught:
                    store_context(self.paths, raw)

                self.assertIn(expected, str(caught.exception))
                self.assertNotIn(NAME, str(caught.exception))
                self.assertEqual(self.paths.narrata_context.read_bytes(), good)

    def test_failed_write_keeps_the_stored_file(self) -> None:
        good = encoded(context())
        store_context(self.paths, good)

        with (
            mock.patch("transcript.jsonfile.os.replace", side_effect=OSError("full")),
            self.assertRaises(OSError),
        ):
            store_context(self.paths, encoded(context(title="neu")))

        self.assertEqual(self.paths.narrata_context.read_bytes(), good)
        self.assertEqual(
            list(self.paths.narrata_context.parent.iterdir()),
            [self.paths.narrata_context],
        )

    def test_stored_file_with_unsupported_version_is_rejected_on_read(self) -> None:
        self.paths.narrata_context.parent.mkdir(parents=True)
        self.paths.narrata_context.write_bytes(encoded(context("2.0")))

        with self.assertRaises(NarrataContextError) as caught:
            read_session(self.paths)

        self.assertIn("contract_version 2.0 is not supported", str(caught.exception))

    def test_missing_file_points_to_the_context_command(self) -> None:
        with self.assertRaises(NarrataContextError) as caught:
            read_session(self.paths)

        self.assertIn("run transcript context first", str(caught.exception))


class ParticipantsTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(
            SessionKey("beispielgruppe", 42), Path(directory.name)
        )

    def load(self, participants: list[Any]) -> tuple[Participant, ...]:
        store_context(self.paths, encoded(context(participants=participants)))
        return read_participants(self.paths).participants

    def test_several_participants_keep_narrata_order_and_ids(self) -> None:
        loaded = self.load(
            [
                participant(user_id=7, display_name="Anna Muster", role="gm"),
                participant(
                    characters=[
                        {"person_id": 18, "name": CHARACTER, "aliases": ["Brakk"]},
                        {"person_id": 19, "name": "Ilse Erdacht", "aliases": []},
                    ]
                ),
                participant(user_id="u-9", display_name="Max Muster", is_former=True),
            ]
        )

        self.assertEqual([p.user_id for p in loaded], [7, 3, "u-9"])
        self.assertEqual([p.role for p in loaded], ["gm", "player", "player"])
        self.assertEqual([p.is_former for p in loaded], [False, False, True])
        self.assertEqual(loaded[0].characters, ())
        self.assertEqual(
            loaded[1].characters,
            (
                Character(18, CHARACTER, ("Brakk",)),
                Character(19, "Ilse Erdacht", ()),
            ),
        )
        self.assertTrue(all(p.present is None for p in loaded))

    def test_origin_is_kept(self) -> None:
        store_context(self.paths, encoded(context()))

        loaded = read_participants(self.paths)

        self.assertEqual(loaded.source, self.paths.narrata_context)
        self.assertEqual(loaded.contract_version, "1.1")
        self.assertEqual(loaded.play_session_id, PLAY_SESSION_ID)

    def test_missing_optional_parts_are_tolerated(self) -> None:
        without_characters = participant(role="gm")
        del without_characters["characters"]
        loaded = self.load(
            [
                without_characters,
                participant(user_id=4, characters=None),
                participant(
                    user_id=5,
                    characters=[{"person_id": 18, "name": CHARACTER}],
                ),
                participant(
                    user_id=6,
                    characters=[{"person_id": 19, "name": CHARACTER, "aliases": None}],
                ),
                participant(user_id=8, avatar="later minor"),
            ]
        )

        self.assertEqual([len(p.characters) for p in loaded], [0, 0, 1, 1, 0])
        self.assertEqual(loaded[2].characters[0].aliases, ())
        self.assertEqual(loaded[3].characters[0].aliases, ())

    def test_empty_list_is_valid(self) -> None:
        self.assertEqual(self.load([]), ())

    def test_contract_violations_name_position_never_values(self) -> None:
        character = {"person_id": 18, "name": CHARACTER, "aliases": []}
        for participants, expected in (
            ("none", "field 'participants' missing or invalid"),
            ([NAME], "participants[0] is not an object"),
            ([participant(user_id=True)], "participants[0].user_id"),
            ([participant(user_id="")], "participants[0].user_id"),
            ([participant(display_name=" ")], "participants[0].display_name"),
            ([participant(role=NAME)], "participants[0].role"),
            ([participant(is_former=None)], "participants[0].is_former"),
            ([participant(characters={})], "participants[0].characters"),
            ([participant(characters=[CHARACTER])], "characters[0] is not an object"),
            (
                [participant(characters=[{**character, "person_id": None}])],
                "participants[0].characters[0].person_id",
            ),
            (
                [participant(characters=[{**character, "name": ""}])],
                "participants[0].characters[0].name",
            ),
            (
                [participant(characters=[{**character, "aliases": [NAME, 1]}])],
                "participants[0].characters[0].aliases",
            ),
            (
                [participant(), participant()],
                "participants[1].user_id repeats an earlier id",
            ),
            (
                [
                    participant(characters=[character]),
                    participant(user_id=4, characters=[character]),
                ],
                "participants[1].characters[0].person_id repeats an earlier id",
            ),
        ):
            with self.subTest(expected=expected):
                data = context(participants=[])
                data["participants"] = participants
                with self.assertRaises(NarrataContextError) as caught:
                    store_context(self.paths, encoded(data))

                message = str(caught.exception)
                self.assertIn(expected, message)
                self.assertNotIn(NAME, message)
                self.assertNotIn(CHARACTER, message)
                self.assertFalse(self.paths.narrata_context.exists())

    def test_hand_placed_file_is_checked_on_read(self) -> None:
        self.paths.narrata_context.parent.mkdir(parents=True)
        self.paths.narrata_context.write_bytes(
            encoded(context(participants=[participant(role="sl")]))
        )

        self.assertEqual(read_session(self.paths).play_session_id, PLAY_SESSION_ID)
        with self.assertRaises(NarrataContextError) as caught:
            read_participants(self.paths)

        self.assertIn("participants[0].role missing or invalid", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
