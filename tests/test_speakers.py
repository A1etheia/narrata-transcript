import dataclasses
import json
import unittest
from typing import Any

from test_candidates import _SessionCase
from test_reference import minimal

from transcript.narrata import Participant
from transcript.reference import (
    Diarization,
    Passage,
    Processing,
    ReferenceTranscript,
    SegmentRef,
    Word,
    update_reference,
)
from transcript.speakers import (
    ASSIGNMENT_FORMAT_VERSION,
    Assigned,
    AssignmentEntry,
    AssignmentError,
    SpeakerAssignment,
    check,
    labels_version,
    load_assignment,
    set_effort,
    set_entry,
    template,
    with_entry,
    write_assignment,
    write_template,
)

# Every name and id below is made up.
SECRET_LABEL = "SPEAKER_ZZYZX"  # stands in for a label that must not reach a message
NAME = "Erika Beispiel"


def participant(user_id: int, is_former: bool = False) -> Participant:
    return Participant(
        user_id=user_id,
        display_name=f"{NAME} {user_id}",
        role="player",
        is_former=is_former,
        characters=(),
    )


PARTICIPANTS = (participant(11), participant(12), participant(13, is_former=True))


def segment(index: int, *labels: str, **changes: Any) -> ReferenceTranscript:
    """A transcript whose n-th passage is spoken by the n-th label."""
    passages = tuple(
        Passage(
            index=n,
            text=" wort",
            start_ms=n * 1000,
            end_ms=n * 1000 + 800,
            words=(Word(" wort", n * 1000, n * 1000 + 800, 0.9, label),),
            speaker=label,
        )
        for n, label in enumerate(labels, start=1)
    )
    values: dict[str, Any] = {
        "segment": SegmentRef(index, f"segment-{index:02d}.wav", "ab" * 32),
        "passages": passages,
        "diarization": Diarization(
            backend_id="fake-diar", model="fake-diar", labels=tuple(sorted(labels))
        ),
    }
    values.update(changes)
    return minimal(**values)


FIRST = segment(1, "SPEAKER_00", "SPEAKER_01")
SECOND = segment(2, "SPEAKER_00")


def entry(
    reference: ReferenceTranscript,
    label: str,
    user_id: int | None = None,
    assigned: Assigned | None = None,
    version: str | None = None,
) -> AssignmentEntry:
    return AssignmentEntry(
        reference.segment.index,
        label,
        version or labels_version(reference),
        assigned or ("person" if user_id is not None else "open"),
        user_id,
    )


class CheckTest(unittest.TestCase):
    def test_each_label_can_be_a_person_unknown_or_multiple(self) -> None:
        third = segment(3, "SPEAKER_00", "SPEAKER_01", "SPEAKER_02")
        assignment = SpeakerAssignment(
            (
                entry(third, "SPEAKER_00", 11),
                entry(third, "SPEAKER_01", assigned="unknown"),
                entry(third, "SPEAKER_02", assigned="multiple"),
            )
        )

        found = check(assignment, [third], PARTICIPANTS)

        self.assertEqual(found.resolve(3, "SPEAKER_00").user_id, 11)
        self.assertEqual(found.resolve(3, "SPEAKER_01").assigned, "unknown")
        self.assertIsNone(found.resolve(3, "SPEAKER_01").user_id)
        self.assertEqual(found.resolve(3, "SPEAKER_02").assigned, "multiple")
        self.assertEqual(found.findings, ())
        self.assertEqual(found.counts()["open"], 0)

    def test_a_label_without_entry_stays_open_and_a_missing_label_is_no_person(
        self,
    ) -> None:
        found = check(SpeakerAssignment(), [FIRST], PARTICIPANTS)

        self.assertEqual(found.resolve(1, "SPEAKER_00").assigned, "open")
        self.assertIsNone(found.resolve(1, "SPEAKER_00").user_id)
        self.assertIsNone(found.resolve(1, None).user_id)
        self.assertEqual(found.counts()["open"], 2)

    def test_two_labels_of_one_person_are_merged_with_a_warning(self) -> None:
        assignment = SpeakerAssignment(
            (
                entry(FIRST, "SPEAKER_00", 11),
                entry(FIRST, "SPEAKER_01", 11),
                entry(SECOND, "SPEAKER_00", 11),
            )
        )

        found = check(assignment, [FIRST, SECOND], PARTICIPANTS)

        self.assertEqual(
            found.persons(),
            {11: ((1, "SPEAKER_00"), (1, "SPEAKER_01"), (2, "SPEAKER_00"))},
        )
        # the same person in another segment is normal and no warning
        self.assertEqual([(s.segment, s.labels) for s in found.splits], [(1, 2)])

    def test_a_former_participant_can_be_chosen(self) -> None:
        found = check(
            SpeakerAssignment((entry(SECOND, "SPEAKER_00", 13),)),
            [SECOND],
            PARTICIPANTS,
        )

        self.assertEqual(found.resolve(2, "SPEAKER_00").user_id, 13)

    def test_entries_that_do_not_fit_are_reported_and_not_applied(self) -> None:
        assignment = SpeakerAssignment(
            (
                entry(FIRST, "SPEAKER_00", 99),  # not in the snapshot
                entry(FIRST, SECRET_LABEL, 11),  # not in the segment
                entry(SECOND, "SPEAKER_00", 12),  # segment not transcribed
                entry(FIRST, "SPEAKER_01", 12, version="0" * 16),
            )
        )

        found = check(assignment, [FIRST], PARTICIPANTS)

        self.assertEqual(
            [(f.entry, f.segment, f.kind) for f in found.findings],
            [
                (1, 1, "unknown_person"),
                (2, 1, "unknown_label"),
                (3, 2, "unknown_segment"),
                (4, 1, "stale"),
            ],
        )
        self.assertIsNone(found.resolve(1, "SPEAKER_00").user_id)
        self.assertIsNone(found.resolve(1, "SPEAKER_01").user_id)
        self.assertEqual(found.persons(), {})

    def test_new_labels_make_an_entry_stale_but_the_same_labels_keep_it(self) -> None:
        assignment = SpeakerAssignment((entry(FIRST, "SPEAKER_00", 11),))
        swapped = segment(1, "SPEAKER_01", "SPEAKER_00")
        retranscribed = dataclasses.replace(
            FIRST,
            processing=Processing("0.0.1", "2026-11-05T20:00:00+01:00"),
        )

        self.assertEqual(check(assignment, [FIRST], PARTICIPANTS).findings, ())
        for changed in (swapped, retranscribed):
            with self.subTest(changed=changed.processing.processed_at):
                kinds = [
                    f.kind for f in check(assignment, [changed], PARTICIPANTS).findings
                ]
                self.assertEqual(kinds, ["stale"])

    def test_with_entry_replaces_in_place_or_appends(self) -> None:
        first, second = entry(FIRST, "SPEAKER_00"), entry(FIRST, "SPEAKER_01")
        assignment = SpeakerAssignment((first, second), 3)
        chosen = entry(FIRST, "SPEAKER_00", 11)
        added = entry(SECOND, "SPEAKER_00", 12)

        self.assertEqual(
            with_entry(assignment, chosen), SpeakerAssignment((chosen, second), 3)
        )
        self.assertEqual(with_entry(assignment, added).entries, (first, second, added))

    def test_a_person_needs_a_user_id_and_only_a_person_has_one(self) -> None:
        with self.assertRaisesRegex(ValueError, "user_id"):
            AssignmentEntry(1, "SPEAKER_00", "v", "person")
        with self.assertRaisesRegex(ValueError, "user_id"):
            AssignmentEntry(1, "SPEAKER_00", "v", "unknown", 11)
        with self.assertRaisesRegex(ValueError, "two entries"):
            SpeakerAssignment((entry(FIRST, "SPEAKER_00"), entry(FIRST, "SPEAKER_00")))


class AssignmentFileTest(_SessionCase):
    def stored(self, **changes: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "format_version": ASSIGNMENT_FORMAT_VERSION,
            "session": str(self.paths.key),
            "effort_minutes": 7,
            "entries": [
                {
                    "segment": 1,
                    "label": SECRET_LABEL,
                    "labels_version": "v",
                    "assigned": "person",
                    "user_id": 11,
                }
            ],
        }
        data.update(changes)
        self.paths.speakers_dir.mkdir(parents=True, exist_ok=True)
        self.paths.speaker_assignment.write_text(json.dumps(data), encoding="utf-8")
        return data

    def test_template_has_one_open_entry_per_label_and_round_trips(self) -> None:
        self.assertTrue(write_template(self.paths, [SECOND, FIRST]))

        loaded = load_assignment(self.paths)

        assert loaded is not None
        self.assertEqual(loaded, template([FIRST, SECOND]))
        self.assertEqual(
            [(e.segment, e.label, e.assigned) for e in loaded.entries],
            [
                (1, "SPEAKER_00", "open"),
                (1, "SPEAKER_01", "open"),
                (2, "SPEAKER_00", "open"),
            ],
        )
        self.assertIsNone(loaded.effort_minutes)

    def test_an_existing_assignment_is_never_replaced(self) -> None:
        self.stored()
        before = self.paths.speaker_assignment.read_bytes()

        self.assertFalse(write_template(self.paths, [FIRST]))
        self.assertEqual(self.paths.speaker_assignment.read_bytes(), before)

    def test_hand_made_entries_and_effort_are_read(self) -> None:
        self.stored()

        loaded = load_assignment(self.paths)

        assert loaded is not None
        self.assertEqual(loaded.effort_minutes, 7)
        self.assertEqual(loaded.entries[0].user_id, 11)

    def test_no_file_means_no_assignment(self) -> None:
        self.assertIsNone(load_assignment(self.paths))

    def test_the_reference_transcripts_stay_unchanged(self) -> None:
        update_reference(self.paths, FIRST)
        before = self.paths.reference(1).read_bytes()

        write_template(self.paths, [FIRST])
        loaded = load_assignment(self.paths)
        assert loaded is not None
        check(loaded, [FIRST], PARTICIPANTS)

        self.assertEqual(self.paths.reference(1).read_bytes(), before)

    def test_invalid_files_are_refused_without_naming_their_content(self) -> None:
        entry_ok = self.stored()["entries"][0]
        cases = {
            "version": ({"format_version": 2}, "format_version"),
            "session": ({"session": "anderegruppe/001"}, "another session"),
            "assigned": (
                {"entries": [{**entry_ok, "assigned": "vielleicht"}]},
                "entry 1: field 'assigned'",
            ),
            "user_id": (
                {"entries": [{**entry_ok, "user_id": True}]},
                "entry 1: field 'user_id'",
            ),
            "person without id": (
                {"entries": [{**entry_ok, "user_id": None}]},
                "entry 1: field 'user_id' required",
            ),
            "duplicate": ({"entries": [entry_ok, entry_ok]}, "two entries"),
            "effort": ({"effort_minutes": -1}, "effort_minutes"),
        }
        for name, (changes, message) in cases.items():
            with self.subTest(name):
                self.stored(**changes)
                with self.assertRaisesRegex(AssignmentError, message) as caught:
                    load_assignment(self.paths)
                self.assertNotIn(SECRET_LABEL, str(caught.exception))
                self.assertNotIn("11", str(caught.exception).split(": ", 1)[1])

    def test_set_entry_changes_only_its_label_and_keeps_the_rest_as_read(
        self,
    ) -> None:
        other = {
            "note": "von Hand",  # an extra field survives
            "labels_version": "w",
            "segment": 2,
            "label": "SPEAKER_00",
            "assigned": "unknown",
        }
        replaced = {**self.stored()["entries"][0], "note": "zur alten Wahl"}
        self.stored(entries=[replaced, other])
        chosen = AssignmentEntry(1, SECRET_LABEL, "v2", "multiple")

        set_entry(self.paths, chosen)

        written = json.loads(self.paths.speaker_assignment.read_text("utf-8"))
        self.assertEqual(written["entries"][1], other)
        self.assertEqual(list(written["entries"][1]), list(other))
        # the chosen entry is written fresh; a note on the old choice goes with it
        self.assertEqual(written["entries"][0], dataclasses.asdict(chosen))
        self.assertEqual(written["effort_minutes"], 7)

    def test_set_entry_appends_a_new_label_and_set_effort_keeps_entries(
        self,
    ) -> None:
        data = self.stored()
        added = entry(SECOND, "SPEAKER_00", 12)

        set_entry(self.paths, added)
        set_effort(self.paths, 9)

        loaded = load_assignment(self.paths)
        assert loaded is not None
        self.assertEqual(loaded.entries[1], added)
        self.assertEqual(loaded.effort_minutes, 9)
        written = json.loads(self.paths.speaker_assignment.read_text("utf-8"))
        self.assertEqual(written["entries"][0], data["entries"][0])

    def test_set_entry_refuses_an_invalid_file_and_writes_nothing(self) -> None:
        self.stored(format_version=2)
        before = self.paths.speaker_assignment.read_bytes()

        with self.assertRaisesRegex(AssignmentError, "format_version"):
            set_entry(self.paths, entry(FIRST, "SPEAKER_00", 11))
        self.assertEqual(self.paths.speaker_assignment.read_bytes(), before)

    def test_written_assignment_keeps_person_entries(self) -> None:
        assignment = SpeakerAssignment((entry(FIRST, "SPEAKER_00", 11),), 5)

        write_assignment(self.paths, assignment)

        self.assertEqual(load_assignment(self.paths), assignment)


if __name__ == "__main__":
    unittest.main()
