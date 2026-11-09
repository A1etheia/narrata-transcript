"""Markers for what the working version leaves unresolved (TOOL-50).

One place decides how an unclear passage shows, so that every renderer and the
export mark it alike. A block of the working version gets:

- `unintelligible` when a decision says nobody can tell what was said; it shows
  no text at all, so nothing stands in for the lost words;
- `unresolved` when its review is still open; the recognised text stays, with
  the marker after it, so it reads as not checked;
- `speaker_unclear` when nobody can tell who speaks (`unknown`);
- `crosstalk` when several people speak at once (`multiple`).

A speaker not assigned yet (`open`), or a passage without a speaker label, is no
marker: it would mark every block of a session without an assignment.

Each marker carries the session time of the block's start, if the transcript has
one, so it leads back to the recording. `unintelligible`, `speaker_unclear` and
`crosstalk` are named as the markers of the Narrata contract (IOA-1214); an
`unresolved` block is a review status there, not a marker.

Nothing here logs or writes; the rendered text holds recognised words and goes
only where its caller writes it.
"""

from dataclasses import dataclass
from typing import Literal, get_args

from transcript.manifest import Manifest
from transcript.session_time import passage_span
from transcript.speakers import Assigned
from transcript.timecode import format_clock
from transcript.working import Block

MarkerKind = Literal["unintelligible", "unresolved", "speaker_unclear", "crosstalk"]
MARKER_KINDS: tuple[MarkerKind, ...] = get_args(MarkerKind)

MARKER_LABELS: dict[MarkerKind, str] = {
    "unintelligible": "unverständlich",
    "unresolved": "unklar",
    "speaker_unclear": "Sprecher unklar",
    "crosstalk": "durcheinander",
}
_SPEAKER_KINDS: dict[Assigned, MarkerKind] = {
    "unknown": "speaker_unclear",
    "multiple": "crosstalk",
}


@dataclass(frozen=True)
class Marker:
    kind: MarkerKind
    at_ms: int | None  # session time of the block's start; None without one


def block_markers(block: Block, manifest: Manifest) -> tuple[Marker, ...]:
    """The block's markers: first what is unclear about the text, then the speaker.

    `ValueError` if the block's segment is not in `manifest`.
    """
    kinds: list[MarkerKind] = []
    if block.origin == "open":
        kinds.append("unresolved")
    elif block.status == "unintelligible":
        kinds.append("unintelligible")
    speaker = _SPEAKER_KINDS.get(block.speaker.assigned)
    if speaker is not None:
        kinds.append(speaker)
    if not kinds:
        return ()
    segment = next((s for s in manifest.segments if s.index == block.segment), None)
    if segment is None:
        raise ValueError(f"segment {block.segment} is not in the manifest")
    span = passage_span(segment, block)
    at_ms = None if span is None else span.start_ms
    return tuple(Marker(kind, at_ms) for kind in kinds)


def marker_label(marker: Marker) -> str:
    """The marker as it reads in a transcript, e.g. `[unverständlich 01:42:17]`."""
    label = MARKER_LABELS[marker.kind]
    if marker.at_ms is None:
        return f"[{label}]"
    return f"[{label} {format_clock(marker.at_ms)}]"


def rendered_text(block: Block, manifest: Manifest) -> str:
    """The block's text with its markers, as text and document renderers show it.

    An unintelligible block is its markers only; no text is ever made up.
    """
    parts = [block.text] if block.text else []
    parts += (marker_label(m) for m in block_markers(block, manifest))
    return " ".join(parts)
