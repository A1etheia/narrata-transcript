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
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, get_args

from transcript.candidates import SessionCandidates
from transcript.config import Level
from transcript.decisions import (
    SETTLED,
    ReviewItem,
    ReviewStatus,
    SessionDecisions,
    review_items,
)
from transcript.reference import Passage, ReferenceTranscript
from transcript.speakers import FindingKind as SpeakerFindingKind
from transcript.speakers import SpeakerMap, SpeakerRef, labels_version

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
