"""Session time of passages and words, computed from the manifest on read.

Reference transcripts store times local to their segment WAV; nothing here is
written back. A span keeps the local values next to the session values, says
whether it is word or passage time, and shows when an end past the WAV end was
set to the segment end. Missing backend times stay `None` and are never derived
from neighbouring units.

Error messages name segment numbers and milliseconds only, never text.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from transcript.manifest import Manifest, Segment
from transcript.reference import ReferenceTranscript, Word, segment_ref
from transcript.timecode import format_ms

# Backends round and pad the last word; a time further past the WAV end means the
# transcript does not belong to this WAV.
END_TOLERANCE_MS = 1000

Granularity = Literal["word", "passage"]


class Timed(Protocol):
    """A word, passage or working block, with times local to its segment."""

    @property
    def start_ms(self) -> int | None: ...

    @property
    def end_ms(self) -> int | None: ...


@dataclass(frozen=True)
class SessionSpan:
    granularity: Granularity
    local_start_ms: int | None
    local_end_ms: int | None
    start_ms: int | None  # session time
    end_ms: int | None
    clamped: bool = False  # a local time lay just past the WAV end

    def timecode(self) -> str:
        """`HH:MM:SS.mmm–HH:MM:SS.mmm` in session time, `?` for a missing bound."""
        return f"{_format(self.start_ms)}–{_format(self.end_ms)}"


def segment_of(manifest: Manifest, reference: ReferenceTranscript) -> Segment:
    """The manifest segment `reference` was transcribed from."""
    index = reference.segment.index
    segment = next((s for s in manifest.segments if s.index == index), None)
    if segment is None:
        raise ValueError(f"segment {index} is not in the manifest")
    if segment_ref(segment) != reference.segment:
        raise ValueError(f"segment {index} of the manifest has another source")
    return segment


def passage_span(segment: Segment, passage: Timed) -> SessionSpan | None:
    """Session time of a passage or a block made from one; `None` without times."""
    return _span(segment, "passage", passage)


def word_span(segment: Segment, word: Word) -> SessionSpan | None:
    """Session time of a word; `None` when the backend gave it no times."""
    return _span(segment, "word", word)


def time_granularity(
    reference: ReferenceTranscript,
) -> Granularity | Literal["none"]:
    """The finest level the transcript actually has times for.

    The stored data decides, not the capabilities: a backend able to time words
    may still return none for a segment.
    """
    if any(_timed(word) for passage in reference.passages for word in passage.words):
        return "word"
    if any(_timed(passage) for passage in reference.passages):
        return "passage"
    return "none"


def _span(
    segment: Segment, granularity: Granularity, unit: Timed
) -> SessionSpan | None:
    if not _timed(unit):
        return None
    start_ms, start_clamped = _absolute(segment, unit.start_ms)
    end_ms, end_clamped = _absolute(segment, unit.end_ms)
    return SessionSpan(
        granularity=granularity,
        local_start_ms=unit.start_ms,
        local_end_ms=unit.end_ms,
        start_ms=start_ms,
        end_ms=end_ms,
        clamped=start_clamped or end_clamped,
    )


def _absolute(segment: Segment, local_ms: int | None) -> tuple[int | None, bool]:
    """Session time of `local_ms`, and whether it was set to the segment end."""
    if local_ms is None:
        return None, False
    if segment.duration_ms < local_ms <= segment.duration_ms + END_TOLERANCE_MS:
        return segment.end_ms, True
    return segment.to_absolute_ms(local_ms), False


def _timed(unit: Timed) -> bool:
    return unit.start_ms is not None or unit.end_ms is not None


def _format(ms: int | None) -> str:
    return "?" if ms is None else format_ms(ms)
