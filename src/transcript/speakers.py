"""Manual assignment of speaker labels to session participants (TOOL-68).

Diarization (TOOL-76) gives each segment generic labels such as `SPEAKER_00`;
they hold per segment only, so the key of an assignment is (segment, label).
A person fills `speakers/assignment.json` by hand. The tool writes it once as a
template with every label `open` and never touches it again.

An entry names the `labels_version` of the segment it was made on. When the
segment is transcribed or diarized again with another outcome, the entry is
*stale*: it stays in the file and is reported, never applied. An entry that
points at an unknown segment, label or participant is reported the same way.
Whatever is not validly assigned to a person stays a bare label; no step ever
guesses a person.

The file holds user ids and lies under `work/`; this module logs nothing, and
its messages name file, entry number, segment and field only, never a label,
name or id.
"""

import dataclasses
import functools
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from transcript import jsonfile
from transcript.jsonfile import DataFileError, write_atomic
from transcript.manifest import Manifest
from transcript.narrata import Participant, is_narrata_id
from transcript.reference import ReferenceTranscript, load_transcribed
from transcript.session import SessionPaths

ASSIGNMENT_FORMAT_VERSION = 1

Assigned = Literal[
    "open",  # not decided yet; also a label without an entry
    "person",  # a participant of the snapshot, named by `user_id`
    "unknown",  # nobody can tell who it is
    "multiple",  # several people, e.g. crosstalk
]
ASSIGNED: tuple[Assigned, ...] = get_args(Assigned)
LabelKey = tuple[int, str]  # (segment, label)
UserId = int | str

FindingKind = Literal["unknown_segment", "unknown_label", "unknown_person", "stale"]


class AssignmentError(DataFileError):
    """The speaker assignment file is invalid."""


@dataclass(frozen=True)
class AssignmentEntry:
    segment: int
    label: str
    labels_version: str  # of the segment the entry was made on
    assigned: Assigned = "open"
    user_id: UserId | None = None  # only with `person`

    def __post_init__(self) -> None:
        if self.segment < 1:
            raise ValueError("field 'segment' invalid")
        if not self.label:
            raise ValueError("field 'label' empty")
        if self.assigned not in ASSIGNED:
            raise ValueError("field 'assigned' invalid")
        if self.assigned == "person":
            if not is_narrata_id(self.user_id):
                raise ValueError("field 'user_id' required for person")
        elif self.user_id is not None:
            raise ValueError("field 'user_id' only allowed for person")

    @property
    def key(self) -> LabelKey:
        return (self.segment, self.label)


@dataclass(frozen=True)
class SpeakerAssignment:
    entries: tuple[AssignmentEntry, ...] = ()  # in file order
    effort_minutes: int | None = None  # time spent assigning, filled by hand

    def __post_init__(self) -> None:
        keys = [entry.key for entry in self.entries]
        if len(set(keys)) != len(keys):
            raise ValueError("two entries for one segment and label")
        if self.effort_minutes is not None and self.effort_minutes < 0:
            raise ValueError("field 'effort_minutes' invalid")


@dataclass(frozen=True)
class Finding:
    """An entry that is not applied; its label stays a bare label."""

    entry: int  # 1-based position in the file
    segment: int
    kind: FindingKind


@dataclass(frozen=True)
class Split:
    """Several labels of one segment assigned to the same person; they are merged."""

    segment: int
    labels: int  # how many


@dataclass(frozen=True)
class SpeakerRef:
    """Who speaks: the label as diarized, and the person if validly assigned."""

    segment: int
    label: str | None  # None: no turn covered the words
    assigned: Assigned
    user_id: UserId | None  # set exactly when `assigned` is `person`


@dataclass(frozen=True)
class SpeakerMap:
    """The applicable entries of an assignment, checked against the session."""

    labels: tuple[LabelKey, ...]  # every label of the checked segments, sorted
    applied: Mapping[LabelKey, AssignmentEntry]
    findings: tuple[Finding, ...] = ()
    splits: tuple[Split, ...] = ()

    def resolve(self, segment: int, label: str | None) -> SpeakerRef:
        """The person behind `label` in `segment`; never a guess."""
        entry = None if label is None else self.applied.get((segment, label))
        if entry is None:
            return SpeakerRef(segment, label, "open", None)
        return SpeakerRef(segment, label, entry.assigned, entry.user_id)

    def persons(self) -> dict[UserId, tuple[LabelKey, ...]]:
        """The labels of each assigned person, merged across labels and segments."""
        found: dict[UserId, list[LabelKey]] = {}
        for key in self.labels:
            ref = self.resolve(*key)
            if ref.user_id is not None:
                found.setdefault(ref.user_id, []).append(key)
        return {user: tuple(keys) for user, keys in found.items()}

    def counts(self) -> Counter[Assigned]:
        """Labels per assignment state; every state is present, with 0 if unused."""
        counts: Counter[Assigned] = Counter(dict.fromkeys(ASSIGNED, 0))
        counts.update(self.resolve(*key).assigned for key in self.labels)
        return counts


def segment_labels(reference: ReferenceTranscript) -> tuple[str, ...]:
    """The segment's diarization labels; none without diarization.

    The reference format guarantees that no word or passage carries another.
    """
    return reference.diarization.labels if reference.diarization else ()


def labels_version(reference: ReferenceTranscript) -> str:
    """Fingerprint of the segment's labels; changes with a new transcript or labels.

    `processed_at` alone is not enough, since diarizing again keeps it.
    """
    content = {
        "processed_at": reference.processing.processed_at,
        "labels": segment_labels(reference),
        "passages": [
            [passage.speaker, [word.speaker for word in passage.words]]
            for passage in reference.passages
        ],
    }
    raw = json.dumps(content, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class _Labelled:
    """What an entry is checked against: one segment's labels and their version."""

    labels: tuple[str, ...]
    version: str


def _labelled(references: Iterable[ReferenceTranscript]) -> dict[int, _Labelled]:
    return {
        r.segment.index: _Labelled(segment_labels(r), labels_version(r))
        for r in sorted(references, key=lambda r: r.segment.index)
    }


def diarized_references(
    paths: SessionPaths, manifest: Manifest
) -> tuple[ReferenceTranscript, ...]:
    """The transcribed and diarized segments of `manifest`, in order."""
    found = (load_transcribed(paths, segment.index) for segment in manifest.segments)
    return tuple(r for r in found if r is not None and r.diarization is not None)


def check(
    assignment: SpeakerAssignment,
    references: Iterable[ReferenceTranscript],
    participants: Sequence[Participant],
) -> SpeakerMap:
    """Pair the entries with the session's labels; set aside those that do not fit."""
    segments = _labelled(references)
    users = {participant.user_id for participant in participants}
    applied: dict[LabelKey, AssignmentEntry] = {}
    findings: list[Finding] = []
    for number, entry in enumerate(assignment.entries, start=1):
        kind = _finding(entry, segments.get(entry.segment), users)
        if kind is None:
            applied[entry.key] = entry
        else:
            findings.append(Finding(number, entry.segment, kind))
    return SpeakerMap(
        labels=tuple(
            (index, label)
            for index, found in segments.items()
            for label in found.labels
        ),
        applied=applied,
        findings=tuple(findings),
        splits=_splits(applied.values()),
    )


def _finding(
    entry: AssignmentEntry, segment: _Labelled | None, users: set[UserId]
) -> FindingKind | None:
    if segment is None:
        return "unknown_segment"
    if entry.label not in segment.labels:
        return "unknown_label"
    if entry.labels_version != segment.version:
        return "stale"
    if entry.assigned == "person" and entry.user_id not in users:
        return "unknown_person"
    return None


def _splits(entries: Iterable[AssignmentEntry]) -> tuple[Split, ...]:
    per_person = Counter(
        (entry.segment, entry.user_id)
        for entry in entries
        if entry.assigned == "person"
    )
    return tuple(
        sorted(
            (Split(segment, n) for (segment, _), n in per_person.items() if n > 1),
            key=lambda split: split.segment,
        )
    )


def template(references: Iterable[ReferenceTranscript]) -> SpeakerAssignment:
    """An `open` entry for every label of the given segments."""
    entries = [
        AssignmentEntry(index, label, found.version)
        for index, found in _labelled(references).items()
        for label in found.labels
    ]
    return SpeakerAssignment(tuple(entries))


def write_template(
    paths: SessionPaths, references: Iterable[ReferenceTranscript]
) -> bool:
    """Write the template unless an assignment exists; whether it was written."""
    if paths.speaker_assignment.exists():
        return False
    write_assignment(paths, template(references))
    return True


def write_assignment(paths: SessionPaths, assignment: SpeakerAssignment) -> None:
    """Replace the assignment file atomically."""
    write_atomic(
        paths.speaker_assignment,
        {
            "format_version": ASSIGNMENT_FORMAT_VERSION,
            "session": str(paths.key),
            "effort_minutes": assignment.effort_minutes,
            "entries": [dataclasses.asdict(entry) for entry in assignment.entries],
        },
    )


def load_assignment(paths: SessionPaths) -> SpeakerAssignment | None:
    """The stored assignment of the session; `None` if the file does not exist."""
    path = paths.speaker_assignment
    if not path.is_file():
        return None
    data = _read_json(path, "speaker assignment")
    if data.get("format_version") != ASSIGNMENT_FORMAT_VERSION:
        # no "run …" hint: the assignment is made by hand, nothing can rebuild it
        raise AssignmentError(f"{path}: unsupported format_version")
    if data.get("session") != str(paths.key):
        raise AssignmentError(f"{path}: belongs to another session")
    effort = _optional(data, "effort_minutes", int, path)
    items = jsonfile.list_of(data, "entries", dict, path, AssignmentError)
    entries = tuple(_entry_from(item, n, path) for n, item in enumerate(items, 1))
    try:
        return SpeakerAssignment(entries, effort)
    except ValueError as error:
        raise AssignmentError(f"{path}: {error}") from None


def _entry_from(data: dict[str, Any], number: int, path: Path) -> AssignmentEntry:
    """One entry; an error from it names the entry number."""
    try:
        return AssignmentEntry(
            segment=_field(data, "segment", int, path),
            label=_field(data, "label", str, path),
            labels_version=_field(data, "labels_version", str, path),
            assigned=_one_of(data, "assigned", ASSIGNED, path),
            user_id=data.get("user_id"),  # checked by the entry itself
        )
    except (DataFileError, ValueError) as error:
        detail = str(error).removeprefix(f"{path}: ")
        raise AssignmentError(f"{path}: entry {number}: {detail}") from None


_field = functools.partial(jsonfile.field, error=AssignmentError)
_one_of = functools.partial(jsonfile.one_of, error=AssignmentError)
_optional = functools.partial(jsonfile.optional_field, error=AssignmentError)
_read_json = functools.partial(jsonfile.read_object, error=AssignmentError)
