"""Passages to listen to per speaker label, for assigning labels by hand (TOOL-68).

For each (segment, label) the sheet lists the label's speech time and the
passages in which it speaks longest, with session time and time in the
segment's WAV, so a few seconds of each can be found in the recording. A label
with only a small share of its segment's speech time is likely a fragment of
another speaker and is marked as a candidate for merging.

The sheet holds recognised text and participant names, so it stays under
`work/`; it is rebuilt on every run and never read back. This module logs nothing.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from transcript.jsonfile import write_bytes_atomic
from transcript.manifest import Manifest
from transcript.narrata import Participant
from transcript.reference import Passage, ReferenceTranscript
from transcript.session import SessionKey, SessionPaths
from transcript.session_time import SessionSpan, passage_span, segment_of
from transcript.speakers import SpeakerMap, segment_labels
from transcript.timecode import format_ms

SAMPLES_PER_LABEL = 5
MERGE_SHARE = 0.03  # below this share of its segment's speech time, a label is suspect
_INTRO = (
    "Assign each label in `assignment.json` next to this file: `assigned` is "
    "`person` with a `user_id` from the list below, `unknown`, `multiple` or "
    "`open`. Labels hold per segment only. Note the minutes spent in "
    "`effort_minutes`."
)


@dataclass(frozen=True)
class Sample:
    passage: int
    speech_ms: int  # of the label within the passage
    local_start_ms: int | None  # in the segment's WAV
    span: SessionSpan | None
    text: str


@dataclass(frozen=True)
class LabelSamples:
    segment: int
    file: str  # the segment's WAV
    label: str
    speech_ms: int
    share: float | None  # of the segment's labelled speech; None without any
    samples: tuple[Sample, ...]  # longest first

    @property
    def merge_candidate(self) -> bool:
        return self.share is not None and self.share < MERGE_SHARE


def speech_ms(passage: Passage) -> Counter[str]:
    """How long each label speaks in `passage`, from its timed words.

    Without timed words, the passage counts whole for its majority label.
    """
    spoken: Counter[str] = Counter()
    timed = False
    for word in passage.words:
        if word.start_ms is not None and word.end_ms is not None:
            timed = True
            if word.speaker is not None:
                spoken[word.speaker] += word.end_ms - word.start_ms
    start, end = passage.start_ms, passage.end_ms
    if (
        not timed
        and passage.speaker is not None
        and start is not None
        and end is not None
    ):
        spoken[passage.speaker] += end - start
    return spoken


def label_samples(
    manifest: Manifest, references: Iterable[ReferenceTranscript]
) -> tuple[LabelSamples, ...]:
    """Speech time and the longest passages of every label, in the given order."""
    found: list[LabelSamples] = []
    for reference in references:
        segment = segment_of(manifest, reference)
        totals: Counter[str] = Counter()
        rows: dict[str, list[tuple[int, Passage]]] = {}
        for passage in reference.passages:
            spoken = speech_ms(passage)
            totals.update(spoken)
            if passage.speaker is not None and spoken[passage.speaker]:
                rows.setdefault(passage.speaker, []).append(
                    (spoken[passage.speaker], passage)
                )
        segment_total = sum(totals.values())
        for label in segment_labels(reference):
            spoken_in = sorted(rows.get(label, ()), key=lambda r: (-r[0], r[1].index))
            found.append(
                LabelSamples(
                    segment=segment.index,
                    file=segment.file,
                    label=label,
                    speech_ms=totals[label],
                    share=totals[label] / segment_total if segment_total else None,
                    samples=tuple(
                        Sample(
                            passage=p.index,
                            speech_ms=ms,
                            local_start_ms=p.start_ms,
                            span=passage_span(segment, p),
                            text=" ".join(p.text.split()),
                        )
                        for ms, p in spoken_in[:SAMPLES_PER_LABEL]
                    ),
                )
            )
    return tuple(found)


def render(
    key: SessionKey,
    labels: Sequence[LabelSamples],
    participants: Sequence[Participant],
    assignment: SpeakerMap,
) -> str:
    """The sheet as Markdown."""
    lines = [
        f"# Speakers of {key}",
        "",
        _INTRO,
        "",
        "## Participants",
        "",
        "| user_id | name | role | membership |",
        "| --- | --- | --- | --- |",
    ]
    for participant in sorted(participants, key=lambda p: p.is_former):
        membership = "former" if participant.is_former else "active"
        lines.append(
            f"| {participant.user_id} | {_cell(participant.display_name)} "
            f"| {participant.role} | {membership} |"
        )
    segment = None
    for found in labels:
        if found.segment != segment:
            segment = found.segment
            lines += ["", f"## Segment {segment} (`{found.file}`)"]
        lines += ["", f"### {found.label}", "", _summary(found, assignment)]
        if found.merge_candidate:
            lines.append(
                f"- candidate for merging: under {MERGE_SHARE:.0%} of the "
                "segment's speech time"
            )
        if found.samples:
            lines.append("")
        lines += [_sample(sample) for sample in found.samples]
    return "\n".join(lines) + "\n"


def _summary(found: LabelSamples, assignment: SpeakerMap) -> str:
    share = "" if found.share is None else f", {found.share:.0%} of the segment"
    ref = assignment.resolve(found.segment, found.label)
    who = ref.assigned if ref.user_id is None else f"person {ref.user_id}"
    return f"- speech time {format_ms(found.speech_ms)}{share}; assigned: {who}"


def _sample(sample: Sample) -> str:
    session = "?" if sample.span is None else sample.span.timecode()
    local = "?" if sample.local_start_ms is None else format_ms(sample.local_start_ms)
    return (
        f"- {session} (WAV {local}, passage {sample.passage}, "
        f"{format_ms(sample.speech_ms)}): {sample.text}"
    )


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def write_samples(paths: SessionPaths, sheet: str) -> None:
    write_bytes_atomic(paths.speaker_samples, sheet.encode("utf-8"))
