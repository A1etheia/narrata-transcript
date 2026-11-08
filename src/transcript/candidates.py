"""Review candidates: the passages worth checking by ear (TOOL-36).

A passage becomes a candidate when its rating from TOOL-35 is `needs_review` or
`uncertain`; a `confident` passage never does. This module adds no rule of its
own: knowledge triggers a candidate through the hint rules of the rating and
strengthens it by the hints attached to it, which also put it first among its
level. The text is the recognised one, unchanged.

`write_candidates` stores one file per session, `review/candidates.json`. It
holds recognised text and archive names, so it stays under `work/`; this module
logs nothing, and its error messages name file, field and numbers only.
"""

import datetime
import functools
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypeVar, get_args

from transcript import jsonfile
from transcript.config import LEVELS, Level
from transcript.hints import Hint, hint_from, stored_hints
from transcript.jsonfile import DataFileError, write_atomic
from transcript.manifest import Manifest, Segment
from transcript.reference import ReferenceTranscript, load_reference
from transcript.session import SessionPaths
from transcript.session_time import (
    Granularity,
    SessionSpan,
    passage_span,
    segment_of,
)
from transcript.uncertainty import (
    PassageRating,
    SegmentAssessment,
    UncertaintyError,
    level_counts,
    load_assessment,
    rating_from,
    rating_json,
)

CANDIDATES_FORMAT_VERSION = 1
_HOUR_MS = 3_600_000
_T = TypeVar("_T")


class CandidatesError(DataFileError):
    """The candidates cannot be built, or their file is missing or invalid."""


def candidate_id(segment: int, passage: int) -> str:
    """The stable review ID of a passage, e.g. `s01-p0042`."""
    return f"s{segment:02d}-p{passage:04d}"


@dataclass(frozen=True)
class ReviewCandidate:
    segment: int
    rating: PassageRating  # as stored in the rating file; never `confident`
    text: str  # as recognised, never corrected
    speaker: str | None  # diarization label of the segment, not a person
    time: SessionSpan | None  # None: the backend gave the passage no times
    hints: tuple[Hint, ...]  # those the rating used

    @property
    def passage(self) -> int:
        return self.rating.passage

    @property
    def level(self) -> Level:
        return self.rating.level

    @property
    def id(self) -> str:
        return candidate_id(self.segment, self.passage)

    @property
    def strong_hint(self) -> bool:
        """A known misrecognition or an ambiguous hint points into the passage."""
        return any(h.signal == "known_variant" or h.ambiguous for h in self.hints)


@dataclass(frozen=True)
class RatedSegment:
    """A segment whose ratings were read, and what they were made from."""

    segment: int
    duration_ms: int
    reference_processed_at: str
    knowledge_snapshot_id: str | None  # of the hints the rating used


@dataclass(frozen=True)
class SessionCandidates:
    rated: tuple[RatedSegment, ...]
    not_rated: tuple[int, ...]  # segments without a transcribed reference
    candidates: tuple[ReviewCandidate, ...]  # in review order

    @property
    def processed_at(self) -> dict[int, str]:
        """The transcript version each rated segment's candidates point at."""
        return {rated.segment: rated.reference_processed_at for rated in self.rated}

    @property
    def audio_ms(self) -> int:
        """Audio of the rated segments; the rate per hour counts only these."""
        return sum(segment.duration_ms for segment in self.rated)

    @property
    def per_hour(self) -> float | None:
        audio_ms = self.audio_ms
        if audio_ms == 0:
            return None
        return round(len(self.candidates) * _HOUR_MS / audio_ms, 1)

    def counts(self) -> Counter[Level]:
        """Candidates per level; `confident` is present with 0."""
        counts = level_counts()
        counts.update(candidate.level for candidate in self.candidates)
        return counts


def collect(paths: SessionPaths, manifest: Manifest) -> SessionCandidates:
    """The candidates of every rated segment of `manifest`, in review order.

    A rating made from another version of a transcript is an error: the
    candidates would point at text that is no longer there.
    """
    rated: list[RatedSegment] = []
    not_rated: list[int] = []
    found: list[ReviewCandidate] = []
    for entry in manifest.segments:
        reference = _transcribed(paths, entry.index)
        if reference is None:
            not_rated.append(entry.index)
            continue
        assessment = _current_assessment(paths, reference)
        segment = _checked(segment_of, manifest, reference)
        rated.append(
            RatedSegment(
                segment.index,
                segment.duration_ms,
                assessment.reference_processed_at,
                assessment.knowledge_snapshot_id,
            )
        )
        found += _segment_candidates(paths, segment, reference, assessment)
    found.sort(key=_review_order)
    return SessionCandidates(tuple(rated), tuple(not_rated), tuple(found))


def _transcribed(paths: SessionPaths, index: int) -> ReferenceTranscript | None:
    if not paths.reference(index).is_file():
        return None
    reference = load_reference(paths, index)
    return reference if reference.status == "transcribed" else None


def _current_assessment(
    paths: SessionPaths, reference: ReferenceTranscript
) -> SegmentAssessment:
    index = reference.segment.index
    try:
        assessment = load_assessment(paths, index)
    except UncertaintyError as error:
        raise CandidatesError(f"{error}; run transcript assess") from None
    if not assessment.matches(reference):
        raise CandidatesError(
            f"{paths.review_uncertainty(index)}: rates another version of "
            f"segment {index}; run transcript assess"
        )
    return assessment


def _segment_candidates(
    paths: SessionPaths,
    segment: Segment,
    reference: ReferenceTranscript,
    assessment: SegmentAssessment,
) -> list[ReviewCandidate]:
    used = assessment.used_hints(stored_hints(paths, segment.index))
    hints = {} if used is None else used.by_passage()
    passages = {passage.index: passage for passage in reference.passages}
    found = []
    for rating in assessment.ratings:
        if rating.level == "confident":
            continue
        passage = passages.get(rating.passage)
        if passage is None:
            raise CandidatesError(
                f"{paths.review_uncertainty(segment.index)}: passage "
                f"{rating.passage} is not in segment {segment.index}; "
                "run transcript assess"
            )
        found.append(
            ReviewCandidate(
                segment=segment.index,
                rating=rating,
                text=passage.text,
                speaker=passage.speaker,
                time=_checked(passage_span, segment, passage),
                hints=hints.get(passage.index, ()),
            )
        )
    return found


def _checked(step: Callable[..., _T], *args: Any) -> _T:
    """`step(*args)`, its `ValueError` (numbers only) as a `CandidatesError`."""
    try:
        return step(*args)
    except ValueError as error:
        raise CandidatesError(str(error)) from None


def _review_order(candidate: ReviewCandidate) -> tuple[int, bool, int, int]:
    """Uncertain first, strong hints first within a level, then recording order."""
    return (
        -LEVELS.index(candidate.level),
        not candidate.strong_hint,
        candidate.segment,
        candidate.passage,
    )


def session_candidates(paths: SessionPaths, manifest: Manifest) -> SessionCandidates:
    """Collect and write the session's candidates; what was written."""
    found = collect(paths, manifest)
    write_candidates(paths, found)
    return found


def write_candidates(
    paths: SessionPaths,
    found: SessionCandidates,
    now: datetime.datetime | None = None,
) -> None:
    """Replace the session's candidate file atomically."""
    moment = now or datetime.datetime.now().astimezone()
    write_atomic(
        paths.review_candidates,
        {
            "format_version": CANDIDATES_FORMAT_VERSION,
            "session": str(paths.key),
            "created_at": moment.isoformat(timespec="seconds"),
            "segments": [
                {
                    "segment": rated.segment,
                    "duration_ms": rated.duration_ms,
                    "reference": {
                        "file": paths.reference(rated.segment).name,
                        "processed_at": rated.reference_processed_at,
                    },
                    "knowledge_snapshot_id": rated.knowledge_snapshot_id,
                }
                for rated in found.rated
            ],
            "not_rated": list(found.not_rated),
            # an overview for people reading the file; `load_candidates` ignores it
            "audio_ms": found.audio_ms,
            "per_hour": found.per_hour,
            "counts": dict(found.counts()),
            "candidates": [
                {
                    "id": candidate.id,
                    "segment": candidate.segment,
                    **rating_json(candidate.rating),
                    "time": None if candidate.time is None else asdict(candidate.time),
                    "speaker": candidate.speaker,
                    "text": candidate.text,
                    "hints": [asdict(hint) for hint in candidate.hints],
                }
                for candidate in found.candidates
            ],
        },
    )


def load_candidates(paths: SessionPaths) -> SessionCandidates:
    """The stored candidates of the session; `CandidatesError` if absent or invalid."""
    path = paths.review_candidates
    data = _read_json(path, "review candidates")
    if data.get("format_version") != CANDIDATES_FORMAT_VERSION:
        raise CandidatesError(
            f"{path}: unsupported format_version; run transcript assess again"
        )
    if data.get("session") != str(paths.key):
        raise CandidatesError(f"{path}: belongs to another session")
    return SessionCandidates(
        rated=tuple(
            _rated_from(item, path)
            for item in jsonfile.list_of(data, "segments", dict, path, CandidatesError)
        ),
        not_rated=tuple(
            jsonfile.list_of(data, "not_rated", int, path, CandidatesError)
        ),
        candidates=tuple(
            _candidate_from(item, number, path)
            for number, item in enumerate(
                jsonfile.list_of(data, "candidates", dict, path, CandidatesError),
                start=1,
            )
        ),
    )


def _rated_from(data: dict[str, Any], path: Path) -> RatedSegment:
    reference = _field(data, "reference", dict, path)
    return RatedSegment(
        segment=_field(data, "segment", int, path),
        duration_ms=_field(data, "duration_ms", int, path),
        reference_processed_at=_field(reference, "processed_at", str, path),
        knowledge_snapshot_id=_optional(data, "knowledge_snapshot_id", str, path),
    )


def _candidate_from(data: dict[str, Any], number: int, path: Path) -> ReviewCandidate:
    """One candidate; an error from it names the entry number."""
    try:
        rating = rating_from(data, number, path)
        if rating.level == "confident":
            raise CandidatesError(f"{path}: field 'level' invalid")
        time = _optional(data, "time", dict, path)
        return ReviewCandidate(
            segment=_field(data, "segment", int, path),
            rating=rating,
            text=_field(data, "text", str, path),
            speaker=_optional(data, "speaker", str, path),
            time=None if time is None else _span_from(time, path),
            hints=tuple(
                hint_from(item, n, path)
                for n, item in enumerate(
                    jsonfile.list_of(data, "hints", dict, path, CandidatesError),
                    start=1,
                )
            ),
        )
    except DataFileError as error:
        detail = str(error).removeprefix(f"{path}: ")
        raise CandidatesError(f"{path}: candidate {number}: {detail}") from None


def _span_from(data: dict[str, Any], path: Path) -> SessionSpan:
    return SessionSpan(
        granularity=_one_of(data, "granularity", _GRANULARITIES, path),
        local_start_ms=_optional(data, "local_start_ms", int, path),
        local_end_ms=_optional(data, "local_end_ms", int, path),
        start_ms=_optional(data, "start_ms", int, path),
        end_ms=_optional(data, "end_ms", int, path),
        clamped=_field(data, "clamped", bool, path),
    )


_GRANULARITIES: Sequence[Granularity] = get_args(Granularity)
_field = functools.partial(jsonfile.field, error=CandidatesError)
_one_of = functools.partial(jsonfile.one_of, error=CandidatesError)
_optional = functools.partial(jsonfile.optional_field, error=CandidatesError)
_read_json = functools.partial(jsonfile.read_object, error=CandidatesError)
