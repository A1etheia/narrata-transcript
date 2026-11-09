import dataclasses
import unittest

from test_session_time import MANIFEST, SECOND

from transcript.contract import load_schema
from transcript.markers import (
    CONTRACT_MARKER_LABELS,
    MARKER_KINDS,
    Marker,
    block_markers,
    contract_marker_label,
    marker_label,
    rendered_text,
)
from transcript.session_time import END_TOLERANCE_MS
from transcript.speakers import Assigned, SpeakerRef
from transcript.timecode import parse_timecode
from transcript.working import Block

AT = parse_timecode("00:02:13.750")  # local to SECOND
SESSION_AT = "01:21:56"  # SECOND starts at 01:19:43.000; seconds rounded down


def block(
    origin: str = "automatic",
    status: str | None = None,
    text: str | None = "wort0 wort1",
    assigned: Assigned = "open",
    start_ms: int | None = AT,
    segment: int = SECOND.index,
) -> Block:
    return Block(
        segment=segment,
        passage=1,
        start_ms=start_ms,
        end_ms=None if start_ms is None else start_ms + 1500,
        level="confident" if origin == "automatic" else "needs_review",
        origin=origin,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        asr_text="wort0 wort1",
        text=text,
        speaker=SpeakerRef(
            segment, "SPEAKER_00", assigned, 11 if assigned == "person" else None
        ),
    )


UNINTELLIGIBLE = block("decided", "unintelligible", text=None)


class MarkerRuleTest(unittest.TestCase):
    def test_an_unintelligible_block_shows_no_text(self) -> None:
        self.assertEqual(
            rendered_text(UNINTELLIGIBLE, MANIFEST), f"[unverständlich {SESSION_AT}]"
        )

    def test_an_open_block_keeps_its_text_and_is_told_apart(self) -> None:
        for status in ("open", "deferred", None):
            with self.subTest(status=status):
                found = block("open", status)

                self.assertEqual(
                    rendered_text(found, MANIFEST), f"wort0 wort1 [unklar {SESSION_AT}]"
                )
                self.assertNotEqual(
                    block_markers(found, MANIFEST),
                    block_markers(UNINTELLIGIBLE, MANIFEST),
                )

    def test_settled_text_is_not_marked(self) -> None:
        for found in (
            block(),
            block("decided", "confirmed"),
            block("decided", "kept"),
            block("decided", "corrected", text="Grauwasser"),
        ):
            with self.subTest(status=found.status):
                self.assertEqual(block_markers(found, MANIFEST), ())
                self.assertEqual(rendered_text(found, MANIFEST), found.text)

    def test_only_a_speaker_nobody_can_tell_is_marked(self) -> None:
        expected: dict[Assigned, tuple[str, ...]] = {
            "open": (),
            "person": (),
            "unknown": ("speaker_unclear",),
            "multiple": ("crosstalk",),
        }
        for assigned, kinds in expected.items():
            with self.subTest(assigned=assigned):
                found = block(assigned=assigned)

                self.assertEqual(
                    tuple(m.kind for m in block_markers(found, MANIFEST)), kinds
                )

    def test_a_block_without_label_has_no_speaker_marker(self) -> None:
        found = dataclasses.replace(
            block(), speaker=SpeakerRef(SECOND.index, None, "open", None)
        )

        self.assertEqual(block_markers(found, MANIFEST), ())

    def test_the_text_marker_comes_before_the_speaker_marker(self) -> None:
        found = dataclasses.replace(
            UNINTELLIGIBLE, speaker=block(assigned="multiple").speaker
        )

        self.assertEqual(
            rendered_text(found, MANIFEST),
            f"[unverständlich {SESSION_AT}] [durcheinander {SESSION_AT}]",
        )

    def test_speaker_unclear_reads_as_such(self) -> None:
        found = block(assigned="unknown")

        self.assertEqual(
            rendered_text(found, MANIFEST),
            f"wort0 wort1 [Sprecher unklar {SESSION_AT}]",
        )


class MarkerTimeTest(unittest.TestCase):
    def test_the_time_is_session_time_of_the_start(self) -> None:
        (marker,) = block_markers(UNINTELLIGIBLE, MANIFEST)

        self.assertEqual(marker, Marker("unintelligible", SECOND.start_ms + AT))

    def test_without_start_there_is_no_time(self) -> None:
        found = dataclasses.replace(UNINTELLIGIBLE, start_ms=None, end_ms=AT)

        self.assertEqual(
            block_markers(found, MANIFEST), (Marker("unintelligible", None),)
        )
        self.assertEqual(rendered_text(found, MANIFEST), "[unverständlich]")

    def test_a_start_just_past_the_wav_end_is_the_segment_end(self) -> None:
        past = SECOND.duration_ms + END_TOLERANCE_MS
        found = dataclasses.replace(UNINTELLIGIBLE, start_ms=past, end_ms=past)

        (marker,) = block_markers(found, MANIFEST)

        self.assertEqual(marker.at_ms, SECOND.end_ms)

    def test_a_segment_missing_from_the_manifest_is_rejected(self) -> None:
        found = dataclasses.replace(UNINTELLIGIBLE, segment=9)

        with self.assertRaisesRegex(ValueError, "^segment 9 is not in the manifest$"):
            block_markers(found, MANIFEST)

    def test_label_without_time(self) -> None:
        self.assertEqual(marker_label(Marker("crosstalk", None)), "[durcheinander]")


class ContractTest(unittest.TestCase):
    def test_kinds_are_contract_markers_except_unresolved(self) -> None:
        # the schema test below ties CONTRACT_MARKER_LABELS to the contract's types
        self.assertEqual(
            set(MARKER_KINDS) - set(CONTRACT_MARKER_LABELS), {"unresolved"}
        )

    def test_every_marker_type_of_the_schema_has_a_label(self) -> None:
        marker = load_schema()["$defs"]["marker"]["properties"]["type"]["enum"]
        self.assertEqual(set(CONTRACT_MARKER_LABELS), set(marker))

    def test_a_contract_marker_reads_like_the_working_marker(self) -> None:
        for kind in sorted(set(MARKER_KINDS) & set(CONTRACT_MARKER_LABELS)):
            with self.subTest(kind=kind):
                self.assertEqual(
                    contract_marker_label(kind, AT), marker_label(Marker(kind, AT))
                )

    def test_a_gap_reads_as_such(self) -> None:
        self.assertEqual(contract_marker_label("gap", AT), "[Lücke 00:02:13]")
        self.assertEqual(contract_marker_label("gap", None), "[Lücke]")

    def test_an_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            contract_marker_label("unresolved", AT)
