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
    load_schema,
    schema_bytes,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
# Narrata's reference fixture (IOA-1214): an invented play session
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "contract" / "session-v1.json"
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


class SchemaTest(unittest.TestCase):
    def test_the_schema_is_a_valid_draft_2020_12_schema(self) -> None:
        Draft202012Validator.check_schema(load_schema())

    def test_the_copy_is_the_recorded_one(self) -> None:
        self.assertEqual(hashlib.sha256(schema_bytes()).hexdigest(), SCHEMA_SHA256)

    def test_the_copy_equals_narratas_schema(self) -> None:
        if not NARRATA_SCHEMA.is_file():
            self.skipTest("Narrata repository not next to this one")
        self.assertEqual(schema_bytes(), NARRATA_SCHEMA.read_bytes())

    def test_the_contract_version_is_the_one_of_the_fixture(self) -> None:
        self.assertEqual(_fixture()["contract_version"], CONTRACT_VERSION)


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


if __name__ == "__main__":
    unittest.main()
