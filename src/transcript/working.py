"""The working version of a session's transcript (TOOL-49).

It is derived, never edited: from the reference transcripts, the review
candidates and decisions (TOOL-36, TOOL-46) and the speaker assignment
(TOOL-68). Each passage of the reference becomes one block, in recording order:

- a passage that is no candidate is taken over as recognised (`automatic`);
- a candidate with a current decision gets that decision's text (`decided`);
- any other candidate stays `open`, with its recognised text.

The recognised text stays beside the result, so no uncertainty disappears, and
no step makes text up: an `unintelligible` passage has no text at all. The
speaker label stays; a validly assigned person is added to it.

A decision or speaker entry that does not fit the transcript any more, and a
segment without a transcript, is a finding: reported, never applied. Equal
inputs give an equal result, so nothing in it depends on when it was made.

`write_working` stores `working/transcript.json`. It holds text and user ids,
so it stays under `work/`; this module logs nothing, and its error messages
name file, block and field only.
"""

import dataclasses
import functools
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar, get_args

from transcript import jsonfile
from transcript.audio import sha256_file
from transcript.candidates import SessionCandidates, collect
from transcript.config import LEVELS, Level
from transcript.decisions import (
    SETTLED,
    STATUSES,
    ReviewItem,
    ReviewStatus,
    SessionDecisions,
    load_decisions,
    review_items,
)
from transcript.jsonfile import DataFileError, write_atomic
from transcript.knowledge import load_snapshot
from transcript.manifest import Manifest
from transcript.reference import Passage, ReferenceTranscript, load_transcribed
from transcript.session import SessionPaths
from transcript.speakers import (
    ASSIGNED,
    SpeakerAssignment,
    SpeakerMap,
    SpeakerRef,
    check,
    labels_version,
    load_assignment,
)
from transcript.speakers import FindingKind as SpeakerFindingKind

WORKING_FORMAT_VERSION = 1
_T = TypeVar("_T")


class WorkingError(DataFileError):
    """The working version file is missing or invalid."""


Origin = Literal[
    "automatic",  # no candidate: taken over as recognised
    "decided",  # a current decision says what the text is
    "open",  # a candidate nobody has decided on yet, or deferred
]
ORIGINS: tuple[Origin, ...] = get_args(Origin)

FindingKind = Literal[
    "missing_segment",  # the segment has no transcript, so no blocks
    "stale_decision",  # made on another transcript version; its block is open
    "orphaned_decision",  # its passage is no candidate any more
    "speaker_entry",  # an entry of the speaker assignment not applied
]


@dataclass(frozen=True)
class Block:
    """One passage of the reference, as the working version reads it."""

    segment: int
    passage: int
    start_ms: int | None  # local to the segment, as in the reference
    end_ms: int | None
    level: Level
    origin: Origin
    status: ReviewStatus | None  # None for `automatic`
    asr_text: str  # as recognised, unchanged
    text: str | None  # the result; None for `unintelligible`
    speaker: SpeakerRef

    @property
    def is_candidate(self) -> bool:
        """Whether the passage was a review candidate, settled or not."""
        return self.level != "confident"

    @property
    def duration_ms(self) -> int | None:
        """End minus start; None without both times."""
        if self.start_ms is None or self.end_ms is None:
            return None
        return self.end_ms - self.start_ms


@dataclass(frozen=True)
class WorkingFinding:
    kind: FindingKind
    segment: int
    passage: int | None = None  # for a decision
    entry: int | None = None  # for a speaker entry, its position in the file
    speaker_kind: SpeakerFindingKind | None = None  # why it was not applied


@dataclass(frozen=True)
class SegmentInput:
    """The version of one segment the working version was made from."""

    segment: int
    reference_processed_at: str
    labels_version: str | None  # None without diarization


@dataclass(frozen=True)
class Inputs:
    """What the working version was made from; equal inputs, equal result."""

    knowledge_snapshot_id: str
    decisions_sha256: str | None  # of the file; None without one
    assignment_sha256: str | None
    segments: tuple[SegmentInput, ...]


@dataclass(frozen=True)
class WorkingTranscript:
    inputs: Inputs
    blocks: tuple[Block, ...]  # in recording order
    findings: tuple[WorkingFinding, ...]

    def counts(self) -> Counter[Origin]:
        """Blocks per origin; every origin is present, with 0 if unused."""
        counts: Counter[Origin] = Counter(dict.fromkeys(ORIGINS, 0))
        counts.update(block.origin for block in self.blocks)
        return counts


def build(
    references: Iterable[ReferenceTranscript],
    found: SessionCandidates,
    decisions: SessionDecisions,
    speakers: SpeakerMap,
    *,
    knowledge_snapshot_id: str,
    decisions_sha256: str | None,
    assignment_sha256: str | None,
) -> WorkingTranscript:
    """The working version of the rated segments in `references`.

    `ValueError` if a reference is not the version the candidates were made from.
    """
    ordered = sorted(references, key=lambda r: r.segment.index)
    processed_at = found.processed_at
    for reference in ordered:
        index = reference.segment.index
        if processed_at.get(index) != reference.processing.processed_at:
            raise ValueError(f"segment {index}: candidates rate another version")
    state = review_items(found, decisions)
    items = {(i.candidate.segment, i.candidate.passage): i for i in state.items}
    blocks = tuple(
        _block(reference.segment.index, passage, items, speakers)
        for reference in ordered
        for passage in reference.passages
    )
    findings = [
        *(WorkingFinding("missing_segment", index) for index in found.not_rated),
        *(
            WorkingFinding(kind, d.segment, passage=d.passage)
            for kind, set_aside in (
                ("stale_decision", state.stale),
                ("orphaned_decision", state.orphaned),
            )
            for d in set_aside
        ),
        *(
            WorkingFinding(
                "speaker_entry", f.segment, entry=f.entry, speaker_kind=f.kind
            )
            for f in speakers.findings
        ),
    ]
    inputs = Inputs(
        knowledge_snapshot_id,
        decisions_sha256,
        assignment_sha256,
        _segment_inputs(ordered),
    )
    return WorkingTranscript(inputs, blocks, tuple(sorted(findings, key=_order)))


def _segment_inputs(
    ordered: Sequence[ReferenceTranscript],
) -> tuple[SegmentInput, ...]:
    return tuple(
        SegmentInput(
            r.segment.index,
            r.processing.processed_at,
            None if r.diarization is None else labels_version(r),
        )
        for r in ordered
    )


def _block(
    segment: int,
    passage: Passage,
    items: dict[tuple[int, int], ReviewItem],
    speakers: SpeakerMap,
) -> Block:
    item = items.get((segment, passage.index))
    level: Level = "confident" if item is None else item.candidate.level
    origin, status, text = _outcome(passage, item)
    return Block(
        segment=segment,
        passage=passage.index,
        start_ms=passage.start_ms,
        end_ms=passage.end_ms,
        level=level,
        origin=origin,
        status=status,
        asr_text=passage.text,
        text=text,
        speaker=speakers.resolve(segment, passage.speaker),
    )


def _outcome(
    passage: Passage, item: ReviewItem | None
) -> tuple[Origin, ReviewStatus | None, str | None]:
    """Origin, status and resulting text of a passage."""
    if item is None:
        return "automatic", None, passage.text
    decision = item.decision
    if decision is None or decision.status not in SETTLED:
        return "open", item.status, passage.text
    text = {"corrected": decision.target_text, "unintelligible": None}.get(
        decision.status,
        passage.text,  # confirmed or kept
    )
    return "decided", decision.status, text


def _order(finding: WorkingFinding) -> tuple[int, str, int, int]:
    return (finding.segment, finding.kind, finding.passage or 0, finding.entry or 0)


def compose(paths: SessionPaths, manifest: Manifest) -> WorkingTranscript:
    """The working version of the session, from the files under `work/`.

    A rating of another transcript version, a missing snapshot or an invalid
    decisions or assignment file is a `DataFileError`.
    """
    found = collect(paths, manifest)
    loaded = (load_transcribed(paths, segment.index) for segment in manifest.segments)
    references = [reference for reference in loaded if reference is not None]
    snapshot = load_snapshot(paths)
    speakers = check(
        load_assignment(paths) or SpeakerAssignment(),
        [reference for reference in references if reference.diarization is not None],
        snapshot.participants,
    )
    return build(
        references,
        found,
        load_decisions(paths),
        speakers,
        knowledge_snapshot_id=snapshot.snapshot_id,
        decisions_sha256=_sha256(paths.review_decisions),
        assignment_sha256=_sha256(paths.speaker_assignment),
    )


def _sha256(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


def write_working(paths: SessionPaths, working: WorkingTranscript) -> None:
    """Replace the session's working version atomically."""
    write_atomic(
        paths.working_transcript,
        {
            "format_version": WORKING_FORMAT_VERSION,
            "session": str(paths.key),
            "inputs": dataclasses.asdict(working.inputs),
            "findings": [dataclasses.asdict(found) for found in working.findings],
            "blocks": [_block_json(block) for block in working.blocks],
        },
    )


def _block_json(block: Block) -> dict[str, Any]:
    data = dataclasses.asdict(block)
    del data["speaker"]["segment"]  # the block's own
    return data


def load_working(paths: SessionPaths) -> WorkingTranscript:
    """The stored working version; `WorkingError` if absent or invalid."""
    path = paths.working_transcript
    data = jsonfile.read_object(path, "working version", WorkingError)
    if data.get("format_version") != WORKING_FORMAT_VERSION:
        raise WorkingError(
            f"{path}: unsupported format_version; run transcript working again"
        )
    if data.get("session") != str(paths.key):
        raise WorkingError(f"{path}: belongs to another session")
    return WorkingTranscript(
        inputs=_inputs_from(_field(data, "inputs", dict, path), path),
        blocks=tuple(
            _numbered(_block_from, "block", item, n, path)
            for n, item in enumerate(_list(data, "blocks", dict, path), start=1)
        ),
        findings=tuple(
            _numbered(_finding_from, "finding", item, n, path)
            for n, item in enumerate(_list(data, "findings", dict, path), start=1)
        ),
    )


def load_current(paths: SessionPaths, manifest: Manifest) -> WorkingTranscript:
    """The stored working version if the current files still give it.

    `WorkingError` if it is missing or outdated, so that what is reported or
    exported is what the files say now.
    """
    path = paths.working_transcript
    if not path.is_file():
        raise WorkingError(f"{path}: working version not found; run transcript working")
    stored = load_working(paths)
    if stored != compose(paths, manifest):
        raise WorkingError(f"{path}: working version outdated; run transcript working")
    return stored


def _inputs_from(data: dict[str, Any], path: Path) -> Inputs:
    return Inputs(
        knowledge_snapshot_id=_field(data, "knowledge_snapshot_id", str, path),
        decisions_sha256=_optional(data, "decisions_sha256", str, path),
        assignment_sha256=_optional(data, "assignment_sha256", str, path),
        segments=tuple(
            SegmentInput(
                segment=_field(item, "segment", int, path),
                reference_processed_at=_field(
                    item, "reference_processed_at", str, path
                ),
                labels_version=_optional(item, "labels_version", str, path),
            )
            for item in _list(data, "segments", dict, path)
        ),
    )


def _numbered(
    read: Callable[[dict[str, Any], Path], _T],
    what: str,
    data: dict[str, Any],
    number: int,
    path: Path,
) -> _T:
    """`read(data, path)`; an error from it names the entry number."""
    try:
        return read(data, path)
    except (DataFileError, ValueError) as error:
        detail = str(error).removeprefix(f"{path}: ")
        raise WorkingError(f"{path}: {what} {number}: {detail}") from None


def _block_from(data: dict[str, Any], path: Path) -> Block:
    segment = _field(data, "segment", int, path)
    speaker = _field(data, "speaker", dict, path)
    return Block(
        segment=segment,
        passage=_field(data, "passage", int, path),
        start_ms=_optional(data, "start_ms", int, path),
        end_ms=_optional(data, "end_ms", int, path),
        level=_one_of(data, "level", LEVELS, path),
        origin=_one_of(data, "origin", ORIGINS, path),
        status=_optional_one_of(data, "status", STATUSES, path),
        asr_text=_field(data, "asr_text", str, path),
        text=_optional(data, "text", str, path),
        speaker=SpeakerRef(  # checks `user_id` itself
            segment=segment,
            label=_optional(speaker, "label", str, path),
            assigned=_one_of(speaker, "assigned", ASSIGNED, path),
            user_id=speaker.get("user_id"),
        ),
    )


def _finding_from(data: dict[str, Any], path: Path) -> WorkingFinding:
    return WorkingFinding(
        kind=_one_of(data, "kind", get_args(FindingKind), path),
        segment=_field(data, "segment", int, path),
        passage=_optional(data, "passage", int, path),
        entry=_optional(data, "entry", int, path),
        speaker_kind=_optional_one_of(
            data, "speaker_kind", get_args(SpeakerFindingKind), path
        ),
    )


_field = functools.partial(jsonfile.field, error=WorkingError)
_optional = functools.partial(jsonfile.optional_field, error=WorkingError)
_one_of = functools.partial(jsonfile.one_of, error=WorkingError)
_optional_one_of = functools.partial(jsonfile.optional_one_of, error=WorkingError)
_list = functools.partial(jsonfile.list_of, error=WorkingError)
