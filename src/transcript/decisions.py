"""Review decisions: what a person decided about a review candidate (TOOL-46).

The candidates (TOOL-36) are made by the pipeline and replaced on every rating;
the decisions are made by hand and live in a file of their own,
`review/decisions.json`, so that neither can overwrite the other. A decision
never changes the candidate's text or rating: a correction is stored beside it
as `target_text`, and applying it is a later step.

A decision names the version of the transcript it was made on. When the segment
is transcribed again, the decision is *stale*; when its candidate is gone, it is
*orphaned*. Both stay in the file and are reported, never applied or dropped.

The file holds corrected text and notes, so it stays under `work/`; this module
logs nothing, and its error messages name file, entry and field only.
"""

import dataclasses
import datetime
import functools
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from transcript import jsonfile
from transcript.candidates import ReviewCandidate, SessionCandidates, candidate_id
from transcript.jsonfile import DataFileError, write_atomic
from transcript.session import SessionPaths

DECISIONS_FORMAT_VERSION = 1

ReviewStatus = Literal[
    "open",  # not decided yet; also a candidate without a decision
    "confirmed",  # the recognised wording is right
    "corrected",  # the wording is wrong; `target_text` holds the right one
    "unintelligible",  # nobody can tell what was said
    "kept",  # left as recognised on purpose, though it may be wrong
    "deferred",  # to be checked later
]
STATUSES: tuple[ReviewStatus, ...] = get_args(ReviewStatus)


class DecisionsError(DataFileError):
    """The decisions file is invalid, or a decision does not fit its candidates."""


@dataclass(frozen=True)
class ReviewDecision:
    segment: int
    passage: int
    reference_processed_at: str  # the transcript version decided on
    status: ReviewStatus
    decided_at: str
    target_text: str | None = None  # only with `corrected`
    note: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError("field 'status' invalid")
        if self.status == "corrected":
            if self.target_text is None or not self.target_text.strip():
                raise ValueError("field 'target_text' required for corrected")
        elif self.target_text is not None:
            raise ValueError("field 'target_text' only allowed for corrected")
        if self.note is not None and not self.note.strip():
            raise ValueError("field 'note' empty")

    @property
    def id(self) -> str:
        """The ID of the candidate it decides on."""
        return candidate_id(self.segment, self.passage)


@dataclass(frozen=True)
class SessionDecisions:
    decisions: tuple[ReviewDecision, ...] = ()  # one per candidate ID, in order

    def __post_init__(self) -> None:
        ids = [decision.id for decision in self.decisions]
        if len(set(ids)) != len(ids):
            raise ValueError("two decisions for one candidate")


def _ordered(decisions: Iterable[ReviewDecision]) -> SessionDecisions:
    return SessionDecisions(
        tuple(sorted(decisions, key=lambda d: (d.segment, d.passage)))
    )


def decide(
    decisions: SessionDecisions,
    found: SessionCandidates,
    candidate: str,
    status: ReviewStatus,
    target_text: str | None = None,
    note: str | None = None,
    now: datetime.datetime | None = None,
) -> SessionDecisions:
    """`decisions` with the decision on `candidate` set; an earlier one is replaced.

    `ValueError` if `candidate` is not among `found` or the decision is invalid.
    """
    match = next((c for c in found.candidates if c.id == candidate), None)
    if match is None:
        raise ValueError(f"candidate {candidate} not found")
    decision = ReviewDecision(
        segment=match.segment,
        passage=match.passage,
        reference_processed_at=found.processed_at[match.segment],
        status=status,
        decided_at=_timestamp(now),
        target_text=target_text,
        note=note,
    )
    others = (d for d in decisions.decisions if d.id != candidate)
    return _ordered([*others, decision])


def _timestamp(now: datetime.datetime | None) -> str:
    moment = now or datetime.datetime.now().astimezone()
    return moment.isoformat(timespec="seconds")


@dataclass(frozen=True)
class ReviewItem:
    """A candidate with the decision that still applies to it, if any."""

    candidate: ReviewCandidate  # unchanged
    decision: ReviewDecision | None
    earlier: ReviewDecision | None = None  # stale, made on another transcript

    @property
    def status(self) -> ReviewStatus:
        return "open" if self.decision is None else self.decision.status


@dataclass(frozen=True)
class ReviewState:
    items: tuple[ReviewItem, ...]  # in the review order of the candidates
    stale: tuple[ReviewDecision, ...]  # made on another transcript version
    orphaned: tuple[ReviewDecision, ...]  # their candidate is gone


def review_items(found: SessionCandidates, decisions: SessionDecisions) -> ReviewState:
    """Pair each candidate with its decision; set aside those that no longer fit."""
    processed_at = found.processed_at
    ids = {candidate.id for candidate in found.candidates}
    current: dict[str, ReviewDecision] = {}
    stale: dict[str, ReviewDecision] = {}
    orphaned: list[ReviewDecision] = []
    for decision in decisions.decisions:
        if decision.id not in ids:
            orphaned.append(decision)
        elif processed_at[decision.segment] != decision.reference_processed_at:
            stale[decision.id] = decision
        else:
            current[decision.id] = decision
    return ReviewState(
        items=tuple(
            ReviewItem(c, current.get(c.id), stale.get(c.id)) for c in found.candidates
        ),
        stale=tuple(stale.values()),
        orphaned=tuple(orphaned),
    )


def write_decisions(
    paths: SessionPaths,
    decisions: SessionDecisions,
    now: datetime.datetime | None = None,
) -> None:
    """Replace the session's decisions file atomically."""
    write_atomic(
        paths.review_decisions,
        {
            "format_version": DECISIONS_FORMAT_VERSION,
            "session": str(paths.key),
            "updated_at": _timestamp(now),
            "decisions": [
                {"candidate": decision.id, **dataclasses.asdict(decision)}
                for decision in decisions.decisions
            ],
        },
    )


def load_decisions(paths: SessionPaths) -> SessionDecisions:
    """The stored decisions of the session; none if the file does not exist."""
    path = paths.review_decisions
    if not path.is_file():
        return SessionDecisions()
    data = _read_json(path, "review decisions")
    if data.get("format_version") != DECISIONS_FORMAT_VERSION:
        # no "run …" hint: decisions are made by hand, nothing can rebuild them
        raise DecisionsError(f"{path}: unsupported format_version")
    if data.get("session") != str(paths.key):
        raise DecisionsError(f"{path}: belongs to another session")
    entries = jsonfile.list_of(data, "decisions", dict, path, DecisionsError)
    found = [_decision_from(item, n, path) for n, item in enumerate(entries, start=1)]
    try:
        return _ordered(found)
    except ValueError as error:
        raise DecisionsError(f"{path}: {error}") from None


def _decision_from(data: dict[str, Any], number: int, path: Path) -> ReviewDecision:
    """One decision; an error from it names the entry number."""
    try:
        decision = ReviewDecision(
            segment=_field(data, "segment", int, path),
            passage=_field(data, "passage", int, path),
            reference_processed_at=_field(data, "reference_processed_at", str, path),
            status=_one_of(data, "status", STATUSES, path),
            decided_at=_field(data, "decided_at", str, path),
            target_text=_optional(data, "target_text", str, path),
            note=_optional(data, "note", str, path),
        )
        if _field(data, "candidate", str, path) != decision.id:
            raise ValueError("field 'candidate' does not match segment and passage")
        return decision
    except (DataFileError, ValueError) as error:
        detail = str(error).removeprefix(f"{path}: ")
        raise DecisionsError(f"{path}: decision {number}: {detail}") from None


_field = functools.partial(jsonfile.field, error=DecisionsError)
_one_of = functools.partial(jsonfile.one_of, error=DecisionsError)
_optional = functools.partial(jsonfile.optional_field, error=DecisionsError)
_read_json = functools.partial(jsonfile.read_object, error=DecisionsError)
