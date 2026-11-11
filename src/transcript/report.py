"""The closing report of a session (TOOL-53).

It derives figures from what the pipeline left under `work/` and adds no rule
of its own: a candidate is a passage whose rating is not `confident`, an open
passage is a block of the working version with `origin: open`, and markers come
from `markers.block_markers`. It describes the stored working version, the one
the export reads, and refuses one that the current files no longer give.

The report counts and measures; it claims no accuracy, since none is measured.
Speaking time is told per speaker label only, never per person (TOOL-66): the
knowledge snapshot holds no opt-in, so persons appear as a number. The report
holds no transcript text, no names and no user ids.

What leaves the transcript incomplete is a `gap`; data that is missing without
making the transcript less complete is a `note`.

`write_report` stores `report.json` and `report.md` under `output/`, next to the
exports they describe. Neither holds a time stamp, so equal inputs give equal
files.
"""

import dataclasses
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from transcript import __version__, jsonfile, markers, working
from transcript.candidates import SessionCandidates, collect
from transcript.config import LEVELS, Level
from transcript.decisions import SETTLED, STATUSES, ReviewStatus
from transcript.knowledge import load_snapshot
from transcript.manifest import Manifest
from transcript.markers import MARKER_KINDS, MARKER_LABELS
from transcript.reference import (
    Diarization,
    Failure,
    ReferenceTranscript,
    load_reference,
)
from transcript.session import SessionPaths
from transcript.speakers import ASSIGNED, Assigned, SpeakerAssignment, load_assignment
from transcript.timecode import format_clock
from transcript.uncertainty import SegmentAssessment, load_assessment
from transcript.working import FindingKind, Origin, WorkingTranscript

REPORT_FORMAT_VERSION = 1

SegmentState = Literal["transcribed", "failed", "missing"]
GapCode = Literal[
    "failed_segment",  # the backend failed on the segment
    "missing_segment",  # the segment has no transcript yet
    "open_passages",  # review candidates nobody has settled
    "working_findings",  # decisions or speaker entries not applied
    "open_speakers",  # speaker labels nobody has assigned yet
]
NoteCode = Literal[
    "no_diarization",  # transcribed without speaker labels
    "no_assignment",  # no speaker assignment file
    "effort_not_recorded",  # the assignment names no effort
    "untimed_passages",  # passages without times, missing from the durations
    "segment_without_hints",  # rated without knowledge hints
    "snapshot_differs",  # transcribed with other knowledge than the working version
]
_CANDIDATE_LEVELS: tuple[Level, ...] = tuple(x for x in LEVELS if x != "confident")
_SETTLED: tuple[ReviewStatus, ...] = tuple(s for s in STATUSES if s in SETTLED)
_UNSETTLED: tuple[ReviewStatus, ...] = tuple(s for s in STATUSES if s not in SETTLED)
# working findings that leave the transcript incomplete; a missing segment is
# reported with the recording already
_GAP_FINDINGS: frozenset[FindingKind] = frozenset(
    {"stale_decision", "orphaned_decision", "speaker_entry"}
)


@dataclass(frozen=True)
class SegmentReport:
    segment: int
    duration_ms: int
    state: SegmentState
    failure: Failure | None = None  # only with `failed`: error class, retryable


@dataclass(frozen=True)
class Recording:
    duration_ms: int
    segments: tuple[SegmentReport, ...]


@dataclass(frozen=True)
class Passages:
    total: int
    by_origin: dict[str, int]  # every origin, also with 0
    automatic_ms: int  # duration of the timed blocks taken over as recognised
    untimed: int  # blocks without start or end


@dataclass(frozen=True)
class Review:
    candidates: int
    by_level: dict[str, int]  # needs_review, uncertain
    rated_audio_ms: int
    per_hour: float | None  # candidates per hour of rated audio
    decided: dict[str, int]  # per settling status
    unresolved: dict[str, int]  # open, deferred


@dataclass(frozen=True)
class LabelReport:
    """One speaker label of one segment; labels hold per segment only."""

    segment: int
    label: str
    assigned: Assigned
    speaking_ms: int  # summed durations of its timed blocks


@dataclass(frozen=True)
class Speakers:
    diarized_segments: tuple[int, ...]
    labels: tuple[LabelReport, ...]  # by segment, then label
    by_assigned: dict[str, int]  # labels per assignment, every value present
    persons: int  # distinct persons assigned; never who
    effort_minutes: int | None  # None: not recorded


@dataclass(frozen=True)
class Used:
    """A configuration and the segments that ran with it."""

    values: dict[str, Any]
    segments: tuple[int, ...]


@dataclass(frozen=True)
class Pipeline:
    tool_version: str
    asr: tuple[Used, ...]
    diarization: tuple[Used, ...]
    thresholds: tuple[Used, ...]  # of the uncertainty rating
    knowledge_snapshot_id: str
    context_contract_version: str  # of the Narrata transcription context


@dataclass(frozen=True)
class Gap:
    code: GapCode
    segments: tuple[int, ...]


@dataclass(frozen=True)
class Note:
    code: NoteCode
    segments: tuple[int, ...] = ()  # empty where it concerns the session


@dataclass(frozen=True)
class SessionReport:
    recording: Recording
    passages: Passages
    review: Review
    markers: dict[str, int]  # every marker kind, also with 0
    speakers: Speakers
    findings: dict[str, int]  # findings of the working version per kind
    pipeline: Pipeline
    gaps: tuple[Gap, ...]
    notes: tuple[Note, ...]


def build(
    stored: WorkingTranscript,
    manifest: Manifest,
    references: Mapping[int, ReferenceTranscript],
    found: SessionCandidates,
    assessments: Mapping[int, SegmentAssessment],
    assignment: SpeakerAssignment | None,
    context_contract_version: str,
) -> SessionReport:
    """The report of `stored`, the working version made from these inputs.

    `references` holds every segment that has a reference file, failed or not;
    `assessments` the rating of every rated segment.
    """
    blocks = stored.blocks
    recording = _recording(manifest, references)
    speakers = _speakers(stored, references, assignment)
    return SessionReport(
        recording=recording,
        passages=Passages(
            total=len(blocks),
            by_origin=dict(stored.counts()),
            automatic_ms=sum(
                b.duration_ms or 0 for b in blocks if b.origin == "automatic"
            ),
            untimed=sum(b.duration_ms is None for b in blocks),
        ),
        review=_review(stored, found),
        markers=_counts(
            MARKER_KINDS,
            (m.kind for b in blocks for m in markers.block_markers(b, manifest)),
        ),
        speakers=speakers,
        findings=dict(sorted(Counter(f.kind for f in stored.findings).items())),
        pipeline=Pipeline(
            tool_version=__version__,
            asr=_used((i, _asr_values(r)) for i, r in references.items()),
            diarization=_used(
                (i, _diarization_values(r.diarization))
                for i, r in references.items()
                if r.diarization is not None
            ),
            thresholds=_used(
                (i, dataclasses.asdict(a.thresholds)) for i, a in assessments.items()
            ),
            knowledge_snapshot_id=stored.inputs.knowledge_snapshot_id,
            context_contract_version=context_contract_version,
        ),
        gaps=_gaps(stored, recording, speakers),
        notes=_notes(
            stored, references, assessments, speakers.diarized_segments, assignment
        ),
    )


def _recording(
    manifest: Manifest, references: Mapping[int, ReferenceTranscript]
) -> Recording:
    segments = []
    for segment in manifest.segments:
        reference = references.get(segment.index)
        state: SegmentState
        if reference is None:
            state, failure = "missing", None
        else:
            state = "failed" if reference.status == "failed" else "transcribed"
            failure = reference.error
        segments.append(
            SegmentReport(segment.index, segment.duration_ms, state, failure)
        )
    return Recording(manifest.duration_ms, tuple(segments))


def _review(stored: WorkingTranscript, found: SessionCandidates) -> Review:
    candidates = [b for b in stored.blocks if b.is_candidate]
    return Review(
        candidates=len(candidates),
        by_level=_counts(_CANDIDATE_LEVELS, (b.level for b in candidates)),
        rated_audio_ms=found.audio_ms,
        per_hour=found.per_hour,
        decided=_counts(
            _SETTLED, (b.status for b in candidates if b.origin == "decided")
        ),
        unresolved=_counts(
            _UNSETTLED, (b.status for b in candidates if b.origin == "open")
        ),
    )


def _speakers(
    stored: WorkingTranscript,
    references: Mapping[int, ReferenceTranscript],
    assignment: SpeakerAssignment | None,
) -> Speakers:
    assigned: dict[tuple[int, str], Assigned] = {}
    speaking: Counter[tuple[int, str]] = Counter()
    persons = set()
    for block in stored.blocks:
        label = block.speaker.label
        if label is None:
            continue
        key = (block.segment, label)
        assigned[key] = block.speaker.assigned
        speaking[key] += block.duration_ms or 0
        if block.speaker.user_id is not None:
            persons.add(block.speaker.user_id)
    labels = tuple(
        LabelReport(segment, label, assigned[segment, label], speaking[segment, label])
        for segment, label in sorted(assigned)
    )
    return Speakers(
        diarized_segments=tuple(
            sorted(i for i, r in references.items() if r.diarization is not None)
        ),
        labels=labels,
        by_assigned=_counts(ASSIGNED, (label.assigned for label in labels)),
        persons=len(persons),
        effort_minutes=None if assignment is None else assignment.effort_minutes,
    )


def _asr_values(reference: ReferenceTranscript) -> dict[str, Any]:
    """What identifies the ASR run; no keywords, they are names of the campaign."""
    asr = reference.asr
    return {
        "backend_id": asr.backend_id,
        "model": asr.model,
        "model_version": asr.model_version,
        "runtime_version": asr.runtime_version,
        "language": asr.language,
        "settings": dict(asr.settings),
    }


def _diarization_values(diarization: Diarization) -> dict[str, Any]:
    """What identifies the diarization run; the labels are counted elsewhere."""
    return {
        "backend_id": diarization.backend_id,
        "model": diarization.model,
        "model_version": diarization.model_version,
        "settings": dict(diarization.settings),
        "num_speakers": diarization.num_speakers,
    }


def _used(runs: Iterable[tuple[int, dict[str, Any]]]) -> tuple[Used, ...]:
    """Equal configurations of (segment, values) merged, by first segment."""
    grouped: dict[str, tuple[dict[str, Any], list[int]]] = {}
    for segment, found in runs:
        key = json.dumps(found, sort_keys=True)
        grouped.setdefault(key, (found, []))[1].append(segment)
    used = (Used(found, tuple(sorted(s))) for found, s in grouped.values())
    return tuple(sorted(used, key=lambda u: u.segments))


def _gaps(
    stored: WorkingTranscript, recording: Recording, speakers: Speakers
) -> tuple[Gap, ...]:
    segments = recording.segments
    found: tuple[tuple[GapCode, tuple[int, ...]], ...] = (
        ("failed_segment", tuple(s.segment for s in segments if s.state == "failed")),
        ("missing_segment", tuple(s.segment for s in segments if s.state == "missing")),
        (
            "open_passages",
            _segments(b.segment for b in stored.blocks if b.origin == "open"),
        ),
        (
            "working_findings",
            _segments(f.segment for f in stored.findings if f.kind in _GAP_FINDINGS),
        ),
        (
            "open_speakers",
            _segments(x.segment for x in speakers.labels if x.assigned == "open"),
        ),
    )
    return tuple(Gap(code, segments) for code, segments in found if segments)


def _notes(
    stored: WorkingTranscript,
    references: Mapping[int, ReferenceTranscript],
    assessments: Mapping[int, SegmentAssessment],
    diarized_segments: tuple[int, ...],
    assignment: SpeakerAssignment | None,
) -> tuple[Note, ...]:
    transcribed = [r for r in references.values() if r.status == "transcribed"]
    snapshot_id = stored.inputs.knowledge_snapshot_id
    found = (
        _per_segment(
            "no_diarization",
            (r.segment.index for r in transcribed if r.diarization is None),
        ),
        Note("no_assignment") if diarized_segments and assignment is None else None,
        Note("effort_not_recorded")
        if assignment is not None and assignment.effort_minutes is None
        else None,
        _per_segment(
            "untimed_passages",
            (b.segment for b in stored.blocks if b.duration_ms is None),
        ),
        _per_segment(
            "segment_without_hints",
            (i for i, a in assessments.items() if a.knowledge_snapshot_id is None),
        ),
        _per_segment(
            "snapshot_differs",
            (
                r.segment.index
                for r in transcribed
                if r.asr.knowledge_snapshot_id != snapshot_id
            ),
        ),
    )
    return tuple(note for note in found if note is not None)


def _per_segment(code: NoteCode, indices: Iterable[int]) -> Note | None:
    """The note for these segments; None if there are none."""
    segments = _segments(indices)
    return Note(code, segments) if segments else None


def _segments(indices: Iterable[int]) -> tuple[int, ...]:
    return tuple(sorted(set(indices)))


def _counts(keys: Iterable[str], values: Iterable[Any]) -> dict[str, int]:
    """How often each of `keys` occurs in `values`; every key present."""
    counted = Counter(values)
    return {key: counted[key] for key in keys}


def compose(paths: SessionPaths, manifest: Manifest) -> SessionReport:
    """The report of the session's stored working version.

    A missing or outdated working version is a `WorkingError`, an invalid input
    file a `DataFileError`.
    """
    stored = working.load_current(paths, manifest)
    references = {
        segment.index: load_reference(paths, segment.index)
        for segment in manifest.segments
        if paths.reference(segment.index).is_file()
    }
    found = collect(paths, manifest)
    return build(
        stored,
        manifest,
        references,
        found,
        {rated.segment: load_assessment(paths, rated.segment) for rated in found.rated},
        load_assignment(paths),
        load_snapshot(paths).source.contract_version,
    )


def report_json(report: SessionReport) -> dict[str, Any]:
    """The report as JSON data; the export carries it as `stats` (TOOL-69)."""
    return dataclasses.asdict(report)


def outputs(
    paths: SessionPaths, report: SessionReport
) -> tuple[tuple[Path, bytes], ...]:
    """The files `write_report` writes and their bytes, in the order written."""
    text = render_markdown(str(paths.key), report)
    data = {
        "format_version": REPORT_FORMAT_VERSION,
        "session": str(paths.key),
        **report_json(report),
    }
    return (
        (paths.report_markdown, text.encode("utf-8")),
        (paths.report_json, jsonfile.encode(data)),
    )


def write_report(paths: SessionPaths, report: SessionReport) -> None:
    """Replace `report.md`, then `report.json` of the session.

    Each file is replaced atomically, the pair is not: the JSON comes last, so a
    current `report.json` means its `report.md` was written before it.
    """
    for path, data in outputs(paths, report):
        jsonfile.write_bytes_atomic(path, data)


_STATES: dict[SegmentState, str] = {
    "transcribed": "transkribiert",
    "failed": "fehlgeschlagen",
    "missing": "fehlt",
}
_ORIGIN_NAMES: dict[Origin, str] = {
    "automatic": "automatisch übernommen",
    "decided": "entschieden",
    "open": "offen",
}
_STATUS_NAMES: dict[ReviewStatus, str] = {
    "confirmed": "bestätigt",
    "corrected": "korrigiert",
    "unintelligible": "unverständlich",
    "kept": "belassen",
    "open": "offen",
    "deferred": "zurückgestellt",
}
_LEVEL_NAMES: dict[Level, str] = {"needs_review": "prüfen", "uncertain": "unsicher"}
_ASSIGNED_NAMES: dict[Assigned, str] = {
    "person": "Person",
    "unknown": "unbekannt",
    "multiple": "mehrere",
    "open": "offen",
}
_GAP_TEXTS: dict[GapCode, str] = {
    "failed_segment": "Transkription fehlgeschlagen",
    "missing_segment": "noch nicht transkribiert",
    "open_passages": "Review-Kandidaten noch offen",
    "working_findings": "Entscheidungen oder Sprecher-Einträge nicht angewendet",
    "open_speakers": "Sprecher-Labels noch nicht zugeordnet",
}
_NOTE_TEXTS: dict[NoteCode, str] = {
    "no_diarization": "ohne Diarisierung, also ohne Sprecher-Labels",
    "no_assignment": "keine Sprecherzuordnung angelegt",
    "effort_not_recorded": "Aufwand der Sprecherzuordnung nicht erfasst",
    "untimed_passages": "Passagen ohne Zeit, in keiner Dauer enthalten",
    "segment_without_hints": "ohne Wissenshinweise bewertet",
    "snapshot_differs": "mit anderem Wissens-Snapshot transkribiert",
}


_NO_ACCURACY = (
    "Der Bericht zählt und misst. Eine Genauigkeit des Transkripts wurde "
    "nicht gemessen und wird nicht behauptet."
)
_SPEAKING_TIME = (
    "Redezeit ist die Summe der Passagendauern nach dem Mehrheitslabel "
    "der Passage, nicht die Sprechzeit aus der Diarisierung."
)


def render_markdown(session: str, report: SessionReport) -> str:
    """The report for people: German, short, with the codes spelled out."""
    lines = [
        f"# Abschlussbericht {session}",
        "",
        _NO_ACCURACY,
        "",
        *_recording_lines(report.recording),
        *_passage_lines(report.passages, report.markers),
        *_review_lines(report.review),
        *_speaker_lines(report.speakers),
        *_pipeline_lines(report.pipeline),
        "## Lücken",
        "",
        *_coded_lines([(_GAP_TEXTS[g.code], g.segments) for g in report.gaps]),
        "",
        "## Hinweise",
        "",
        *_coded_lines([(_NOTE_TEXTS[n.code], n.segments) for n in report.notes]),
    ]
    return "\n".join(lines) + "\n"


def _coded_lines(items: list[tuple[str, tuple[int, ...]]]) -> list[str]:
    """One line per gap or note, its segments after it; `keine` without any."""
    return [
        f"- {text}: {_segment_list(segments)}" if segments else f"- {text}"
        for text, segments in items
    ] or ["- keine"]


def _recording_lines(recording: Recording) -> list[str]:
    rows = []
    for s in recording.segments:
        state = _STATES[s.state]
        if s.failure is not None:
            again = "wiederholbar" if s.failure.retryable else "nicht wiederholbar"
            state += f" ({s.failure.category}, {again})"
        rows.append(f"| {s.segment} | {format_clock(s.duration_ms)} | {state} |")
    count = len(recording.segments)
    return [
        "## Aufnahme",
        "",
        f"Dauer {format_clock(recording.duration_ms)}, {count} Segment(e).",
        "",
        "| Segment | Dauer | Zustand |",
        "| --- | --- | --- |",
        *rows,
        "",
    ]


def _passage_lines(passages: Passages, marked: Mapping[str, int]) -> list[str]:
    return [
        "## Passagen",
        "",
        f"- gesamt: {passages.total}",
        f"- {_named(passages.by_origin, _ORIGIN_NAMES)}",
        f"- Dauer automatisch übernommen: {format_clock(passages.automatic_ms)}",
        f"- ohne Zeit: {passages.untimed}",
        f"- Markierungen: {_named(marked, MARKER_LABELS)}",
        "",
    ]


def _review_lines(review: Review) -> list[str]:
    rate = (
        "keine bewertete Aufnahme"
        if review.per_hour is None
        else f"{review.per_hour:.1f}".replace(".", ",") + " pro Stunde"
    )
    return [
        "## Review",
        "",
        f"- Kandidaten: {review.candidates} ({_named(review.by_level, _LEVEL_NAMES)})",
        f"- Rate: {rate}, bewertet {format_clock(review.rated_audio_ms)}",
        f"- entschieden: {_named(review.decided, _STATUS_NAMES)}",
        f"- offen: {_named(review.unresolved, _STATUS_NAMES)}",
        "",
    ]


def _speaker_lines(speakers: Speakers) -> list[str]:
    effort = (
        "nicht erfasst"
        if speakers.effort_minutes is None
        else f"{speakers.effort_minutes} min"
    )
    assigned = _named(speakers.by_assigned, _ASSIGNED_NAMES)
    rows = [
        f"| {x.segment} | {x.label} | {_ASSIGNED_NAMES[x.assigned]} "
        f"| {format_clock(x.speaking_ms)} |"
        for x in speakers.labels
    ]
    table = [
        "",
        _SPEAKING_TIME,
        "",
        "| Segment | Label | Zuordnung | Redezeit |",
        "| --- | --- | --- | --- |",
        *rows,
    ]
    return [
        "## Sprecher",
        "",
        f"- diarisierte Segmente: {_segment_list(speakers.diarized_segments)}",
        f"- Labels: {len(speakers.labels)} ({assigned})",
        f"- verschiedene Personen: {speakers.persons}",
        f"- Aufwand der Zuordnung: {effort}",
        *(table if rows else []),
        "",
    ]


def _pipeline_lines(pipeline: Pipeline) -> list[str]:
    return [
        "## Pipeline",
        "",
        f"- Werkzeug: {pipeline.tool_version}",
        *_used_lines("ASR", pipeline.asr),
        *_used_lines("Diarisierung", pipeline.diarization),
        *_used_lines("Schwellenwerte", pipeline.thresholds),
        f"- Wissens-Snapshot: `{pipeline.knowledge_snapshot_id}`",
        f"- Contract des Transkriptionskontexts: {pipeline.context_contract_version}",
        "",
    ]


def _used_lines(what: str, used: tuple[Used, ...]) -> list[str]:
    if not used:
        return [f"- {what}: keine"]
    return [
        f"- {what} ({_segment_list(u.segments)}): "
        f"`{json.dumps(u.values, sort_keys=True, ensure_ascii=False)}`"
        for u in used
    ]


def _named(counts: Mapping[str, int], names: Mapping[Any, str]) -> str:
    return ", ".join(f"{names[key]} {n}" for key, n in counts.items())


def _segment_list(segments: tuple[int, ...]) -> str:
    if not segments:
        return "keine"
    word = "Segment" if len(segments) == 1 else "Segmente"
    return f"{word} {', '.join(map(str, segments))}"
