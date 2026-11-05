import datetime
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from transcript.narrata import (
    NarrataContextError,
    check_contract,
    read_session,
    store_context,
)
from transcript.session import SessionKey, SessionPaths

PLAY_SESSION_ID = 4711  # made up; real ids never enter the repo
NAME = "Erika Beispiel"  # made up; stands in for a participant's real name


def context(version: Any = "1.1", **session: object) -> dict[str, Any]:
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
        "participants": [{"user_id": 3, "display_name": NAME, "characters": []}],
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


if __name__ == "__main__":
    unittest.main()
