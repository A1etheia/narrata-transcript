import copy
import functools
import hashlib
import json
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from transcript.contract import (
    CONTRACT_VERSION,
    SCHEMA_FILE,
    SCHEMA_SHA256,
    SINGLE_RECORDING_VERSION,
    load_schema,
    schema_bytes,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contract"
# Narrata's reference fixtures (IOA-1214, IOA-1287): an invented play session,
# once as one recording and once as two
FIXTURE = FIXTURES / "session-v1.json"
MULTI_FIXTURE = FIXTURES / "session-v1-multi.json"
NARRATA_SCHEMA = (
    REPO_ROOT.parent
    / "ios-archiv"
    / "ios-archiv-backend"
    / "resources"
    / "contracts"
    / SCHEMA_FILE
)
SECRET = "Geheimname Mira"


@functools.cache
def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fixture() -> dict[str, Any]:
    """A fresh copy of Narrata's fixture, to change in a test."""
    return copy.deepcopy(_fixture())


@functools.cache
def _multi_fixture() -> dict[str, Any]:
    return json.loads(MULTI_FIXTURE.read_text(encoding="utf-8"))


def multi_fixture() -> dict[str, Any]:
    """A fresh copy of Narrata's two-recording fixture, to change in a test."""
    return copy.deepcopy(_multi_fixture())


class SchemaTest(unittest.TestCase):
    def test_the_schema_is_a_valid_draft_2020_12_schema(self) -> None:
        Draft202012Validator.check_schema(load_schema())

    def test_the_copy_is_the_recorded_one(self) -> None:
        self.assertEqual(hashlib.sha256(schema_bytes()).hexdigest(), SCHEMA_SHA256)

    def test_the_copy_equals_narratas_schema(self) -> None:
        if not NARRATA_SCHEMA.is_file():
            self.skipTest("Narrata repository not next to this one")
        self.assertEqual(schema_bytes(), NARRATA_SCHEMA.read_bytes())

    def test_the_contract_versions_are_those_of_the_fixtures(self) -> None:
        self.assertEqual(_fixture()["contract_version"], SINGLE_RECORDING_VERSION)
        self.assertEqual(_multi_fixture()["contract_version"], CONTRACT_VERSION)


class ValidateTest(unittest.TestCase):
    def test_narratas_fixture_is_valid(self) -> None:
        self.assertEqual(validate(fixture()), ())

    def test_a_later_minor_is_accepted(self) -> None:
        document = fixture()
        document["contract_version"] = "1.7"

        self.assertEqual(validate(document), ())

    def test_an_unknown_major_is_the_only_violation(self) -> None:
        document = fixture()
        document["contract_version"] = "2.0"
        document["passages"] = []

        self.assertEqual(
            validate(document), ("/contract_version: unsupported major 2",)
        )

    def test_a_duplicate_id_names_both_positions(self) -> None:
        document = fixture()
        passages = document["passages"]
        passages[1]["id"] = passages[0]["id"]

        self.assertEqual(
            validate(document),
            (f"/passages/1 ({passages[0]['id']}): duplicate id, also at /passages/0",),
        )

    def test_a_passage_out_of_order_is_named(self) -> None:
        document = fixture()
        passage = document["passages"][3]
        passage["start"] = 0
        passage["end"] = max(passage["end"], 0)

        self.assertEqual(
            validate(document),
            (f"/passages/3 ({passage['id']}): start before the previous passage",),
        )

    def test_an_end_before_the_start_is_named(self) -> None:
        document = fixture()
        passage = document["passages"][0]
        passage["end"] = passage["start"] - 0.5

        self.assertEqual(
            validate(document), (f"/passages/0 ({passage['id']}): end before start",)
        )

    def test_an_unknown_speaker_label_is_named(self) -> None:
        document = fixture()
        passage = document["passages"][0]
        passage["speaker_label"] = "SPEAKER_99"

        self.assertEqual(
            validate(document),
            (f"/passages/0 ({passage['id']}): speaker_label not in speakers",),
        )

    def test_a_schema_violation_names_path_and_rule(self) -> None:
        document = fixture()
        passage = document["passages"][2]
        passage["confidence_tier"] = "sicher"
        del document["stats"]

        self.assertEqual(
            validate(document),
            (
                "/: required",
                f"/passages/2/confidence_tier ({passage['id']}): enum",
            ),
        )

    def test_an_invalid_id_is_not_quoted(self) -> None:
        document = fixture()
        document["passages"][0]["id"] = SECRET

        self.assertEqual(validate(document), ("/passages/0/id: pattern",))

    def test_no_violation_quotes_a_value(self) -> None:
        document = fixture()
        passage = document["passages"][0]
        passage["review_status"] = SECRET
        passage["text"] = {"wort": SECRET}
        passage[SECRET] = SECRET
        document["session"]["session_date"] = SECRET

        found = validate(document)

        self.assertTrue(found)
        for violation in found:
            self.assertNotIn("Geheim", violation)

    def test_a_speaker_label_in_a_path_is_not_quoted(self) -> None:
        document = fixture()
        document["speakers"][SECRET] = {"participant_id": 0, "display_name": None}

        self.assertEqual(validate(document), ("/speakers/*/participant_id: minimum",))

    def test_a_document_that_is_no_object_is_reported(self) -> None:
        self.assertEqual(validate([]), ("/: type",))


class RecordingsTest(unittest.TestCase):
    """`source.recordings` (contract 1.1), on the two-recording fixture."""

    def test_narratas_two_recording_fixture_is_valid(self) -> None:
        self.assertEqual(validate(multi_fixture()), ())

    def test_recordings_need_version_1_1(self) -> None:
        document = multi_fixture()
        document["contract_version"] = "1.0"

        self.assertEqual(
            validate(document),
            ("/source/recordings: needs contract version 1.1 or later",),
        )

    def test_the_first_recording_must_repeat_the_source(self) -> None:
        for field, value in (
            ("file_name", "andere.flac"),
            ("audio_sha256", "ab" * 32),
            ("duration_seconds", 1.5),
            ("starts_at", 0.5),
        ):
            with self.subTest(field=field):
                document = multi_fixture()
                document["source"]["recordings"][0][field] = value

                self.assertIn(
                    "/source/recordings/0: does not repeat source file_name, "
                    "duration_seconds and audio_sha256 or does not start at 0",
                    validate(document),
                )

    def test_a_falling_start_is_named_by_position(self) -> None:
        document = multi_fixture()
        recordings = document["source"]["recordings"]
        recordings.append(
            {**recordings[1], "starts_at": recordings[1]["starts_at"] - 1}
        )

        self.assertEqual(
            validate(document),
            ("/source/recordings/2/starts_at: before the previous recording",),
        )

    def test_overlapping_recordings_are_allowed(self) -> None:
        document = multi_fixture()
        first, second = document["source"]["recordings"]
        first["duration_seconds"] = second["starts_at"] + 60  # a second device
        document["source"]["duration_seconds"] = first["duration_seconds"]

        self.assertEqual(validate(document), ())

    def test_a_passage_between_the_recordings_is_named(self) -> None:
        document = multi_fixture()
        first, second = document["source"]["recordings"]
        passages = document["passages"]
        n = next(i for i, p in enumerate(passages) if p["start"] >= second["starts_at"])
        passage = passages[n]
        passage["start"] = (first["duration_seconds"] + second["starts_at"]) / 2
        passage["end"] = max(passage["end"], passage["start"])

        self.assertEqual(
            validate(document),
            (f"/passages/{n}/start ({passage['id']}): in no recording",),
        )

    def test_a_recording_the_schema_rejects_is_one_violation(self) -> None:
        document = multi_fixture()
        document["source"]["recordings"][1]["starts_at"] = SECRET

        found = validate(document)

        self.assertEqual(found, ("/source/recordings/1/starts_at: type",))


if __name__ == "__main__":
    unittest.main()
