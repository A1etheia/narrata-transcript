"""The session's transcript for people to read, rendered from the JSON export (TOOL-51).

This is the reading core shared by TXT (`render_txt`) and DOCX
(`transcript.docx_render`, TOOL-52).
The JSON export (`output/<s>/transcript.json`, contract v1) is the only source:
nothing here reads the working version, so TXT, DOCX and Narrata show the same
state. `load_export` reads the file and refuses one that `contract.validate`
finds fault with.

`paragraphs` groups the passages into one paragraph per change of speaker. A
speaker is the assigned person, so two labels of one person in a row stay one
paragraph, or else the label. A person shows by display name, a label as
`<label> (nicht zugeordnet)`, a person without a known name as
`<label> (zugeordnet, ohne Namen)`, so the two are always told apart.

A passage's text stays as the export has it, only line breaks and runs of
white space become one space. Its markers, kept apart from the text in `Line`,
follow it, labelled as in
`transcript.markers`: an open passage gets `[unklar …]` at its start, then come
the contract's markers in file order, each at its own time. A passage without
text shows its markers only; no text is ever made up.

`layout` lays the paragraphs out by `render.timestamps`, the same for every
renderer: `turn` gives each paragraph the head `[HH:MM:SS] <speaker>` and its
text below; `passage` gives the head `<speaker>` and each passage on a row of its
own, `[HH:MM:SS] <text>`. Each row is a run of typed segments (time, name, label,
text, marker) read with one space between; `render_txt` joins them as plain
text. Times are session time rounded down to the second. Nothing of the export's head,
pipeline or stats goes into the text.

The text holds transcript words and names; `write_txt` stores it as
`output/<s>/transcript.txt` and nothing here logs. Error messages name the path
and contract rules, never a value.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import groupby
from typing import Any, Literal

from transcript.config import TimestampRule
from transcript.contract import summarize, validate
from transcript.jsonfile import DataFileError, read_object, write_bytes_atomic
from transcript.markers import Marker, contract_marker_label, marker_label
from transcript.session import SessionPaths
from transcript.timecode import format_clock, seconds_to_ms


class ExportUnreadable(DataFileError):
    """The JSON export is missing, unreadable or no valid contract v1."""


@dataclass(frozen=True)
class Line:
    """A passage as it reads: its start, its text on one line, its marker labels.

    Text and markers stay apart, so a document renderer can set them apart.
    """

    start_ms: int
    text: str  # empty for a passage without text
    markers: tuple[str, ...] = ()

    @property
    def segments(self) -> tuple["Segment", ...]:
        """The text, if any, then each marker label."""
        text = (Segment(self.text, "text"),) if self.text else ()
        return (*text, *(Segment(marker, "marker") for marker in self.markers))

    @property
    def shown(self) -> str:
        """Text and markers as plain text; empty without either."""
        return joined(self.segments)


SegmentKind = Literal["time", "name", "label", "text", "marker"]


@dataclass(frozen=True)
class Segment:
    """A piece of a rendered row and what it is, so a document can style it."""

    text: str
    kind: SegmentKind


@dataclass(frozen=True)
class Block:
    """A speaker's head row and the rows below it, each a run of segments.

    The segments of a row read with one space between them.
    """

    head: tuple[Segment, ...]
    rows: tuple[tuple[Segment, ...], ...]


@dataclass(frozen=True)
class Paragraph:
    """The passages of one speaker in a row.

    `named` tells a person's name from a label, so a document can set them apart.
    """

    speaker: str
    lines: tuple[Line, ...]
    named: bool


def load_export(paths: SessionPaths) -> dict[str, Any]:
    """The session's JSON export, checked against contract v1."""
    path = paths.transcript_export
    if not path.exists():
        raise ExportUnreadable(f"{path}: JSON export not found; run transcript export")
    document = read_object(path, "JSON export", ExportUnreadable)
    violations = validate(document)
    if violations:
        raise ExportUnreadable(f"{path}: not rendered, {summarize(violations)}")
    return document


def paragraphs(document: Mapping[str, Any]) -> tuple[Paragraph, ...]:
    """The passages of a valid export, one paragraph per change of speaker."""
    speakers: Mapping[str, Any] = document["speakers"]

    def who(passage: Mapping[str, Any]) -> tuple[str, Any]:
        label = passage["speaker_label"]
        person = speakers[label]
        return (
            ("label", label) if person is None else ("person", person["participant_id"])
        )

    found = []
    for _, run in groupby(document["passages"], key=who):
        passages = list(run)
        label = passages[0]["speaker_label"]
        person = speakers[label]
        found.append(
            Paragraph(
                speaker_name(label, person),
                tuple(map(_line, passages)),
                named=person is not None and person.get("display_name") is not None,
            )
        )
    return tuple(found)


def speaker_name(label: str, person: Mapping[str, Any] | None) -> str:
    """How a speaker shows: the person's name, or the label marked as such."""
    if person is None:
        return f"{label} (nicht zugeordnet)"
    name = person.get("display_name")
    return f"{label} (zugeordnet, ohne Namen)" if name is None else name


def layout(found: Sequence[Paragraph], rule: TimestampRule) -> tuple[Block, ...]:
    """The paragraphs laid out by `render.timestamps`, for every renderer.

    `turn`: head time and speaker, then one row of all text, left out if empty.
    `passage`: head speaker, then a row per passage with its time.
    """
    blocks = []
    for paragraph in found:
        speaker = Segment(paragraph.speaker, "name" if paragraph.named else "label")
        if rule == "turn":
            text = tuple(s for line in paragraph.lines for s in line.segments)
            head = (_time(paragraph.lines[0].start_ms), speaker)
            rows = (text,) if text else ()
        else:
            head = (speaker,)
            rows = tuple(
                (_time(line.start_ms), *line.segments) for line in paragraph.lines
            )
        blocks.append(Block(head, rows))
    return tuple(blocks)


def joined(segments: Sequence[Segment]) -> str:
    """A row as plain text, one space between its segments."""
    return " ".join(segment.text for segment in segments)


def render_txt(found: Sequence[Paragraph], rule: TimestampRule) -> str:
    """The paragraphs as plain text, separated by an empty line."""
    blocks = [
        "\n".join(map(joined, (block.head, *block.rows)))
        for block in layout(found, rule)
    ]
    return "\n\n".join(blocks) + "\n" if blocks else ""


def write_txt(paths: SessionPaths, text: str) -> None:
    """Replace the session's TXT transcript, UTF-8 without BOM."""
    write_bytes_atomic(paths.transcript_text, text.encode("utf-8"))


def _time(start_ms: int) -> Segment:
    return Segment(f"[{format_clock(start_ms)}]", "time")


def _line(passage: Mapping[str, Any]) -> Line:
    """The passage's text on one line, an open passage's marker, then the contract's."""
    start_ms = seconds_to_ms(passage["start"])
    unresolved = (
        [marker_label(Marker("unresolved", start_ms))]
        if passage["review_status"] == "open"
        else []
    )
    return Line(
        start_ms,
        " ".join(passage["text"].split()),
        (
            *unresolved,
            *(
                contract_marker_label(marker["type"], seconds_to_ms(marker["at"]))
                for marker in passage["markers"]
            ),
        ),
    )
