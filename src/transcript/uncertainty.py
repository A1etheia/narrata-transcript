"""Rating passages as confident, needs_review or uncertain (TOOL-35).

Each passage of a reference transcript gets a level and the reasons behind it.
The rules are small and fixed; their thresholds come from `review.uncertainty`
in the configuration. A rule whose data is missing does not fire: the missing
signal family is listed instead, and no value is guessed. A passage without any
signal on the quality of the recognition is `needs_review`, never `confident`.

The rating reads the transcript and its hints and changes neither. It holds no
text, so this module has nothing to hide from a log. `write_assessment` stores
the ratings of one segment as `review/segment-NN.uncertainty.json`, together with
the thresholds and the transcript they came from.
"""

import bisect
import dataclasses
import datetime
import functools
import itertools
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from transcript import jsonfile
from transcript.config import LEVELS, Level, UncertaintyThresholds
from transcript.hints import Hint, SegmentHints, stored_hints
from transcript.jsonfile import DataFileError, write_atomic
from transcript.reference import (
    Overlap,
    Passage,
    ReferenceTranscript,
    load_reference,
)
from transcript.session import SessionPaths

UNCERTAINTY_FORMAT_VERSION = 1


class UncertaintyError(DataFileError):
    """A rating file is missing, invalid or belongs to another segment."""


Rule = Literal[
    "no_signals",
    "low_confidence",
    "very_low_confidence",
    "no_speech",
    "low_logprob",
    "repetition",
    "gap",
    "sparse",
    "missing_times",
    "speaker_unclear",
    "crosstalk",
    "known_variant",
    "ambiguous",
    "similar",
]
# Signal families a rule needs; a passage lists those it lacks.
Family = Literal["word_confidence", "segment_signals", "word_times", "speaker", "hints"]
# Families that say how sure the recognition itself was. Times, speakers and
# hints can raise a level but never make a passage confident on their own.
_QUALITY: tuple[Family, ...] = ("word_confidence", "segment_signals")
_SEGMENT_SIGNALS = ("no_speech_prob", "avg_logprob", "compression_ratio")
_MIN_SPARSE_SPAN_MS = 1000  # shorter passages are too short to judge density

Span = tuple[int | None, int | None]


@dataclass(frozen=True)
class Reason:
    """A rule that fired, with the value it saw and the threshold it used."""

    rule: Rule
    level: Level
    value: float | None = None
    threshold: float | None = None
    words: tuple[int, ...] = ()  # positions in `Passage.words`


@dataclass(frozen=True)
class PassageRating:
    passage: int
    level: Level
    reasons: tuple[Reason, ...]
    missing: tuple[Family, ...]  # in the order of `Family`


def assess(
    reference: ReferenceTranscript,
    hints: SegmentHints | None,
    thresholds: UncertaintyThresholds,
) -> tuple[PassageRating, ...]:
    """One rating per passage, in order; equal input gives equal output.

    Hints made from another version of the transcript are not used.
    """
    by_passage: dict[int, list[Hint]] | None = None
    if hints is not None and hints.matches(reference):
        by_passage = {}
        for hint in hints.hints:
            by_passage.setdefault(hint.passage, []).append(hint)
    rater = _Rater(
        thresholds,
        timed=reference.asr.delivers_times,
        overlaps=None
        if reference.diarization is None
        else _Overlaps(reference.diarization.overlaps),
        hints=by_passage,
    )
    return tuple(rater.rate(passage) for passage in reference.passages)


class _Overlaps:
    """Crosstalk ranges, merged and sorted, for a lookup per passage."""

    def __init__(self, overlaps: Sequence[Overlap]) -> None:
        merged: list[list[int]] = []
        for overlap in sorted(overlaps, key=lambda o: (o.start_ms, o.end_ms)):
            if merged and overlap.start_ms <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], overlap.end_ms)
            else:
                merged.append([overlap.start_ms, overlap.end_ms])
        self._starts = [start for start, _ in merged]
        self._ends = [end for _, end in merged]

    def shared_ms(self, start: int, end: int) -> int:
        """Milliseconds of `start`..`end` that lie in a crosstalk range."""
        first = bisect.bisect_right(self._ends, start)  # ends grow with starts
        last = bisect.bisect_left(self._starts, end)
        return sum(
            min(end, self._ends[n]) - max(start, self._starts[n])
            for n in range(first, last)
        )


@dataclass(frozen=True)
class _Rater:
    limits: UncertaintyThresholds
    timed: bool  # the backend can deliver times
    overlaps: _Overlaps | None  # None: no diarization
    hints: dict[int, list[Hint]] | None  # by passage; None: no usable hints

    def rate(self, passage: Passage) -> PassageRating:
        span = _span(passage)
        missing: list[Family] = []
        reasons: list[Reason] = []
        checks: tuple[tuple[Family, Callable[[], list[Reason] | None]], ...] = (
            ("word_confidence", lambda: self._confidence(passage)),
            ("segment_signals", lambda: self._signals(passage)),
            ("word_times", lambda: self._timing(passage, span)),
            ("speaker", lambda: self._speaker(passage, span)),
            ("hints", lambda: self._hints(passage)),
        )
        for family, check in checks:
            found = check()
            if found is None:
                missing.append(family)
            else:
                reasons += found
        reasons += self._missing_times(passage)
        if all(family in missing for family in _QUALITY):
            reasons.insert(0, Reason("no_signals", "needs_review"))
        level = max((r.level for r in reasons), key=LEVELS.index, default="confident")
        return PassageRating(passage.index, level, tuple(reasons), tuple(missing))

    def _confidence(self, passage: Passage) -> list[Reason] | None:
        rated = [
            (n, w.confidence)
            for n, w in enumerate(passage.words)
            if w.confidence is not None
        ]
        if not rated:
            return None
        limits = self.limits
        reasons = []
        low = tuple(n for n, value in rated if value < limits.word_low)
        share = len(low) / len(rated)
        if share >= limits.low_share_uncertain:
            level: Level | None = "uncertain"
            threshold = limits.low_share_uncertain
        elif share >= limits.low_share_review:
            level, threshold = "needs_review", limits.low_share_review
        else:
            level = None
        if low and level is not None:
            reasons.append(Reason("low_confidence", level, share, threshold, low))
        very_low = tuple(n for n, value in rated if value < limits.word_very_low)
        if very_low:
            lowest = min(value for _, value in rated)
            reasons.append(
                Reason(
                    "very_low_confidence",
                    "needs_review",
                    lowest,
                    limits.word_very_low,
                    very_low,
                )
            )
        return reasons

    def _signals(self, passage: Passage) -> list[Reason] | None:
        signals = passage.signals
        if not any(name in signals for name in _SEGMENT_SIGNALS):
            return None
        limits = self.limits
        reasons = []
        no_speech = signals.get("no_speech_prob")
        if no_speech is not None and no_speech >= limits.no_speech_prob:
            reasons.append(
                Reason("no_speech", "needs_review", no_speech, limits.no_speech_prob)
            )
        logprob = signals.get("avg_logprob")
        if logprob is not None and logprob <= limits.avg_logprob:
            reasons.append(
                Reason("low_logprob", "needs_review", logprob, limits.avg_logprob)
            )
        ratio = signals.get("compression_ratio")
        if ratio is not None and ratio >= limits.compression_ratio:
            # Whisper's sign of a loop: the text may not have been spoken at all.
            reasons.append(
                Reason("repetition", "uncertain", ratio, limits.compression_ratio)
            )
        return reasons

    def _timing(self, passage: Passage, span: Span) -> list[Reason] | None:
        """Pauses and sparse speech, where words may have been left out."""
        timed = [
            (n, w.start_ms, w.end_ms)
            for n, w in enumerate(passage.words)
            if w.start_ms is not None and w.end_ms is not None
        ]
        start, end = span
        if not timed or start is None or end is None:
            return None
        limits = self.limits
        reasons = []
        # (pause, position of the word after it); ties go to the later word
        widest = max(
            (
                (later - earlier, n)
                for (_, _, earlier), (n, later, _) in itertools.pairwise(timed)
            ),
            default=None,
        )
        if widest is not None and widest[0] >= limits.gap_ms:
            reasons.append(
                Reason("gap", "needs_review", widest[0], limits.gap_ms, (widest[1],))
            )
        if end - start >= _MIN_SPARSE_SPAN_MS:
            rate = len(passage.words) / ((end - start) / 1000)
            if rate < limits.min_words_per_second:
                reasons.append(
                    Reason("sparse", "needs_review", rate, limits.min_words_per_second)
                )
        return reasons

    def _speaker(self, passage: Passage, span: Span) -> list[Reason] | None:
        if self.overlaps is None:
            return None
        reasons = []
        if passage.speaker is None and passage.words:
            unlabelled = tuple(
                n for n, w in enumerate(passage.words) if w.speaker is None
            )
            reasons.append(
                Reason(
                    "speaker_unclear", "needs_review", len(unlabelled), None, unlabelled
                )
            )
        start, end = span
        if start is not None and end is not None:
            shared = self.overlaps.shared_ms(start, end)
            if shared > 0:
                reasons.append(Reason("crosstalk", "needs_review", shared))
        return reasons

    def _hints(self, passage: Passage) -> list[Reason] | None:
        if self.hints is None:
            return None
        similar_level = self.limits.similar_level
        reasons = []
        for hint in self.hints.get(passage.index, ()):
            words = _hint_words(hint)
            if hint.ambiguous:
                reasons.append(
                    Reason("ambiguous", "uncertain", hint.score, None, words)
                )
            elif hint.signal == "known_variant":
                reasons.append(
                    Reason("known_variant", "needs_review", None, None, words)
                )
            elif similar_level != "confident":
                reasons.append(
                    Reason("similar", similar_level, hint.score, None, words)
                )
        return reasons

    def _missing_times(self, passage: Passage) -> list[Reason]:
        """Times the backend can deliver but did not, for the passage or its words."""
        if not self.timed:
            return []
        untimed = tuple(
            n
            for n, w in enumerate(passage.words)
            if w.start_ms is None or w.end_ms is None
        )
        if passage.start_ms is None or passage.end_ms is None or untimed:
            return [
                Reason("missing_times", "needs_review", len(untimed), None, untimed)
            ]
        return []


def _span(passage: Passage) -> Span:
    """The passage's times, else those of its first and last timed word."""
    start, end = passage.start_ms, passage.end_ms
    if start is None:
        start = min(
            (w.start_ms for w in passage.words if w.start_ms is not None), default=None
        )
    if end is None:
        end = max(
            (w.end_ms for w in passage.words if w.end_ms is not None), default=None
        )
    return start, end


def _hint_words(hint: Hint) -> tuple[int, ...]:
    if hint.first_word is None or hint.last_word is None:
        return ()
    return tuple(range(hint.first_word, hint.last_word + 1))


def level_counts() -> Counter[Level]:
    """A counter of passages per level with every level present, also at 0."""
    return Counter(dict.fromkeys(LEVELS, 0))


@dataclass(frozen=True)
class SegmentAssessment:
    """The ratings of one segment and what they were made from."""

    segment: int
    reference_processed_at: str  # of the reference transcript that was rated
    knowledge_snapshot_id: str | None  # of the hints used; None: no hints used
    thresholds: UncertaintyThresholds
    ratings: tuple[PassageRating, ...]

    def counts(self) -> Counter[Level]:
        """Passages per level; every level is present, also with 0."""
        counts = level_counts()
        counts.update(rating.level for rating in self.ratings)
        return counts


def segment_assessment(
    reference: ReferenceTranscript,
    hints: SegmentHints | None,
    thresholds: UncertaintyThresholds,
) -> SegmentAssessment:
    used = hints if hints is not None and hints.matches(reference) else None
    return SegmentAssessment(
        segment=reference.segment.index,
        reference_processed_at=reference.processing.processed_at,
        knowledge_snapshot_id=None if used is None else used.knowledge_snapshot_id,
        thresholds=thresholds,
        ratings=assess(reference, used, thresholds),
    )


def assess_session(
    paths: SessionPaths, indices: Iterable[int], thresholds: UncertaintyThresholds
) -> Counter[Level]:
    """Rate the transcribed segments among `indices`; passages per level.

    A failed segment loses its rating; a segment without a transcript keeps
    whatever it has. Hints are used where a hint file exists.
    """
    total = level_counts()
    for index in indices:
        if not paths.reference(index).is_file():
            continue
        reference = load_reference(paths, index)
        if reference.status != "transcribed":
            paths.review_uncertainty(index).unlink(missing_ok=True)
            continue
        assessment = segment_assessment(
            reference, stored_hints(paths, index), thresholds
        )
        write_assessment(paths, assessment)
        total.update(assessment.counts())
    return total


def write_assessment(
    paths: SessionPaths,
    assessment: SegmentAssessment,
    now: datetime.datetime | None = None,
) -> None:
    """Replace the rating file of `assessment.segment` atomically."""
    moment = now or datetime.datetime.now().astimezone()
    write_atomic(
        paths.review_uncertainty(assessment.segment),
        {
            "format_version": UNCERTAINTY_FORMAT_VERSION,
            "session": str(paths.key),
            "segment": assessment.segment,
            "created_at": moment.isoformat(timespec="seconds"),
            "reference": {
                "file": paths.reference(assessment.segment).name,
                "processed_at": assessment.reference_processed_at,
            },
            "knowledge_snapshot_id": assessment.knowledge_snapshot_id,
            "thresholds": dataclasses.asdict(assessment.thresholds),
            # an overview for people reading the file; `load_assessment` ignores it
            "counts": dict(assessment.counts()),
            "passages": [
                {
                    "passage": rating.passage,
                    "level": rating.level,
                    "reasons": [dataclasses.asdict(r) for r in rating.reasons],
                    "missing": list(rating.missing),
                }
                for rating in assessment.ratings
            ],
        },
    )


def load_assessment(paths: SessionPaths, index: int) -> SegmentAssessment:
    """The stored rating of segment `index`; `UncertaintyError` if absent or invalid."""
    path = paths.review_uncertainty(index)
    data = _read_json(path, "uncertainty rating")
    if data.get("format_version") != UNCERTAINTY_FORMAT_VERSION:
        raise UncertaintyError(
            f"{path}: unsupported format_version; run transcript assess again"
        )
    if data.get("session") != str(paths.key) or data.get("segment") != index:
        raise UncertaintyError(f"{path}: belongs to another session or segment")
    reference = _field(data, "reference", dict, path)
    return SegmentAssessment(
        segment=index,
        reference_processed_at=_field(reference, "processed_at", str, path),
        knowledge_snapshot_id=_optional(data, "knowledge_snapshot_id", str, path),
        thresholds=_thresholds_from(_field(data, "thresholds", dict, path), path),
        ratings=tuple(
            _rating_from(item, number, path)
            for number, item in enumerate(
                jsonfile.list_of(data, "passages", dict, path, UncertaintyError),
                start=1,
            )
        ),
    )


def _thresholds_from(data: dict[str, Any], path: Path) -> UncertaintyThresholds:
    names = {f.name for f in dataclasses.fields(UncertaintyThresholds)}
    try:
        if set(data) != names:
            raise ValueError("thresholds do not match")
        return UncertaintyThresholds(**data)
    except (TypeError, ValueError):
        raise UncertaintyError(f"{path}: field 'thresholds' invalid") from None


def _rating_from(data: dict[str, Any], number: int, path: Path) -> PassageRating:
    """One passage rating; an error from it names the entry number."""
    try:
        return PassageRating(
            passage=_field(data, "passage", int, path),
            level=_one_of(data, "level", LEVELS, path),
            reasons=tuple(
                _reason_from(item, path)
                for item in jsonfile.list_of(
                    data, "reasons", dict, path, UncertaintyError
                )
            ),
            missing=tuple(
                _check(value, _FAMILIES, "missing", path)
                for value in jsonfile.list_of(
                    data, "missing", str, path, UncertaintyError
                )
            ),
        )
    except UncertaintyError as error:
        detail = str(error).removeprefix(f"{path}: ")
        raise UncertaintyError(f"{path}: passage entry {number}: {detail}") from None


def _reason_from(data: dict[str, Any], path: Path) -> Reason:
    return Reason(
        rule=_one_of(data, "rule", _RULES, path),
        level=_one_of(data, "level", LEVELS, path),
        value=_number(data, "value", path),
        threshold=_number(data, "threshold", path),
        words=tuple(jsonfile.list_of(data, "words", int, path, UncertaintyError)),
    )


_RULES: tuple[Rule, ...] = get_args(Rule)
_FAMILIES: tuple[Family, ...] = get_args(Family)
_field = functools.partial(jsonfile.field, error=UncertaintyError)
_one_of = functools.partial(jsonfile.one_of, error=UncertaintyError)
_check = functools.partial(jsonfile.check_one_of, error=UncertaintyError)
_optional = functools.partial(jsonfile.optional_field, error=UncertaintyError)
_number = functools.partial(jsonfile.optional_number, error=UncertaintyError)
_read_json = functools.partial(jsonfile.read_object, error=UncertaintyError)
