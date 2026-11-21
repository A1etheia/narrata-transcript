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
    IT_OT_SINCE,
    RECORDINGS_SINCE,
    SCHEMA_FILE,
    SCHEMA_SHA256,
    SINGLE_RECORDING_VERSION,
    load_schema,
    schema_bytes,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contract"
# Narrata's reference fixtures (IOA-1214, IOA-1287, IOA-1224, IOA-1300): an
# invented play session as one recording (1.0), two recordings (1.1), with the
# IT/OT layer (1.2) and as a timed and an untimed upload (1.3)
FIXTURE = FIXTURES / "session-v1.json"
MULTI_FIXTURE = FIXTURES / "session-v1-multi.json"
CLASSIFIED_FIXTURE = FIXTURES / "session-v1-classified.json"
UPLOAD_FIXTURES = (
    FIXTURES / "session-v1-upload-timed.json",
    FIXTURES / "session-v1-upload-untimed.json",
)
NARRATA_FIXTURES = (FIXTURE, MULTI_FIXTURE, CLASSIFIED_FIXTURE, *UPLOAD_FIXTURES)
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
def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load(path: Path) -> dict[str, Any]:
    """A fresh copy of one of Narrata's fixtures, to change in a test."""
    return copy.deepcopy(_load(path))


def _fixture() -> dict[str, Any]:
    return _load(FIXTURE)


def fixture() -> dict[str, Any]:
    """A fresh copy of Narrata's fixture, to change in a test."""
    return load(FIXTURE)


def _multi_fixture() -> dict[str, Any]:
    return _load(MULTI_FIXTURE)


def multi_fixture() -> dict[str, Any]:
    """A fresh copy of Narrata's two-recording fixture, to change in a test."""
    return load(MULTI_FIXTURE)


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
        self.assertEqual(_multi_fixture()["contract_version"], RECORDINGS_SINCE)
        self.assertEqual(load(CLASSIFIED_FIXTURE)["contract_version"], IT_OT_SINCE)
        for path in UPLOAD_FIXTURES:
            self.assertEqual(load(path)["contract_version"], CONTRACT_VERSION)

    def test_every_narrata_fixture_is_valid(self) -> None:
        for path in NARRATA_FIXTURES:
            with self.subTest(fixture=path.name):
                self.assertEqual(validate(load(path)), ())


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


class LaterMinorsTest(unittest.TestCase):
    """What 1.2 and 1.3 allow, kept out of a pipeline file."""

    def test_a_null_time_outside_an_upload_is_one_violation(self) -> None:
        document = fixture()
        for passage in document["passages"]:
            passage["start"] = passage["end"] = None
        first = document["passages"][0]["id"]
        expected = (
            f"/passages/0 ({first}): only an upload may leave "
            "passages[].start, passages[].end null"
        )

        self.assertEqual(validate(document), (expected,))

    def test_each_nullable_field_is_named_outside_an_upload(self) -> None:
        document = fixture()
        document["source"]["audio_sha256"] = None
        document["pipeline"] = None
        passage = document["passages"][2]
        passage["confidence_tier"] = None
        passage["markers"] = [{"type": "unintelligible", "at": None}]
        expected = (
            f"/passages/2 ({passage['id']}): only an upload may leave "
            "source.audio_sha256, pipeline, passages[].confidence_tier, "
            "passages[].markers[].at null"
        )

        self.assertEqual(validate(document), (expected,))

    def test_a_null_violation_quotes_no_value(self) -> None:
        document = fixture()
        document["passages"][0]["id"] = SECRET
        document["passages"][0]["start"] = None

        for violation in validate(document):
            self.assertNotIn("Geheim", violation)

    def test_a_position_id_outside_an_upload_is_named(self) -> None:
        document = fixture()
        passage = document["passages"][1]
        passage["id"] = "u-000002-mira"

        self.assertEqual(
            validate(document),
            ("/passages/1/id (u-000002-mira): position id outside an untimed upload",),
        )

    def test_kind_and_format_need_version_1_3(self) -> None:
        document = fixture()
        document["source"]["kind"] = "pipeline"

        self.assertEqual(
            validate(document),
            ("/source: kind and format need contract version 1.3 or later",),
        )

    def test_an_explicit_pipeline_kind_is_accepted_from_1_3(self) -> None:
        document = fixture()
        document["contract_version"] = "1.3"
        document["source"]["kind"] = "pipeline"

        self.assertEqual(validate(document), ())

    def test_a_format_belongs_to_an_upload(self) -> None:
        document = fixture()
        document["contract_version"] = "1.3"
        document["source"]["format"] = "vtt"
        document["passages"][0]["start"] = None

        self.assertEqual(validate(document), ("/source: format without kind upload",))

        document["source"]["kind"] = "pipeline"
        found = validate(document)

        self.assertEqual(found[0], "/source/format: only an upload carries a format")
        self.assertEqual(len(found), 2)  # and the null

    def test_the_it_ot_layer_needs_version_1_2(self) -> None:
        document = load(CLASSIFIED_FIXTURE)
        document["contract_version"] = "1.1"

        self.assertEqual(
            validate(document),
            ("/passages/0/layers/it_ot: needs contract version 1.2 or later",),
        )

    def test_it_ot_stats_alone_need_version_1_2(self) -> None:
        document = fixture()
        document["stats"]["it_ot"] = load(CLASSIFIED_FIXTURE)["stats"]["it_ot"]

        self.assertIn(
            "/stats/it_ot: needs contract version 1.2 or later", validate(document)
        )


if __name__ == "__main__":
    unittest.main()
