"""The status of a session's steps, read from its files alone (TOOL-57).

No status file decides anything: each step's state comes from the files it
writes, checked with the loaders the steps use themselves, so a missing,
outdated or inconsistent file is never reported as done. A step whose file
can be built again from its inputs is built in memory and compared with the
stored bytes. Reading only: no file is written, no network called, no model
loaded; whether the configured model still matches a stored result is the
preflight's check.

Details name counts, segment numbers, gap codes, snapshot ids and paths,
never participants, labels, glossary entries or transcript text (TOOL-66).
"""

import functools
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple

from transcript import (
    audio,
    candidates,
    decisions,
    docx_render,
    export,
    knowledge,
    manifest,
    narrata,
    rendering,
    report,
    review_import,
    review_sheet,
    speakers,
    working,
)
from transcript.config import Config
from transcript.jsonfile import DataFileError
from transcript.pipeline import StepName
from transcript.reference import load_reference
from transcript.session import SessionPaths
from transcript.uncertainty import load_assessment

# pending: not started; stale: there, but outdated or inconsistent, so it is
# run again and never counts as done; waiting: for a person to fill in a file
StepState = Literal["pending", "done", "partial", "failed", "waiting", "stale"]
SessionState = Literal[
    "not_started", "failed", "waiting_for_review", "open", "partial", "complete"
]

_BUILD_ERRORS = (ValueError, DataFileError)  # what the steps' builders raise


@dataclass(frozen=True)
class StepStatus:
    step: StepName
    state: StepState
    detail: str = ""  # counts, segment numbers and paths only
    redo: bool = False  # `process` reuses the file as it is unless `--redo` is set


@dataclass(frozen=True)
class SessionStatus:
    steps: tuple[StepStatus, ...]
    overall: SessionState
    last_done: StepName | None  # the last of the steps done from the start on
    resume_from: StepName | None  # None: nothing left for `process` to do
    command: str | None  # what continues the session, if anything does


class _Found(NamedTuple):
    """What a check found; a `StepStatus` without its step."""

    state: StepState
    detail: str = ""
    redo: bool = False


class _Files:
    """The session's files, each read or built once for all checks.

    A build that fails raises again on every access, so each check reports it.
    """

    def __init__(self, paths: SessionPaths, config: Config) -> None:
        self.paths = paths
        self.config = config

    @functools.cached_property
    def manifest(self) -> manifest.Manifest:
        return manifest.load_manifest(self.paths)

    @functools.cached_property
    def report(self) -> report.SessionReport:
        """The report the current files give; refuses an outdated working version."""
        return report.compose(self.paths, self.manifest)

    @functools.cached_property
    def export_bytes(self) -> bytes:
        """The export the current files give, as `transcript export` writes it."""
        return export.encode(
            export.compose(
                self.paths, self.manifest, self.config.narrata_groups, self.report
            )
        )

    @functools.cached_property
    def export(self) -> dict[str, Any]:
        """`export_bytes` as `rendering.load_export` reads them back."""
        return json.loads(self.export_bytes)

    @functools.cached_property
    def paragraphs(self) -> tuple[rendering.Paragraph, ...]:
        return rendering.paragraphs(self.export)


def inspect(paths: SessionPaths, config: Config) -> SessionStatus:
    """The status of every step that writes a file, in run order, and overall."""
    files = _Files(paths, config)
    steps = tuple(StepStatus(step, *check(files)) for step, check in _CHECKS)
    return summarize(paths, steps)


def _extract(files: _Files) -> _Found:
    paths = files.paths
    try:
        recordings = audio.find_recordings(paths)
    except audio.AudioError as error:
        return _Found("failed", str(error))
    if not paths.audio_metadata.is_file():
        return _Found("pending", "")
    if not audio.extracted(paths, len(recordings)):
        return _Found(
            "stale", f"audio of {len(recordings)} recording(s) incomplete", True
        )
    problem = manifest.audio_metadata_problem(paths, recordings)
    if problem is not None:
        return _Found("stale", problem, True)
    return _Found("done", f"{len(recordings)} recording(s)")


def _context(files: _Files) -> _Found:
    if not files.paths.narrata_context.is_file():
        return _Found("pending", "")
    try:
        narrata.read_session(files.paths)
    except DataFileError as error:
        return _Found("stale", str(error), True)
    return _Found("done", "Narrata context stored")


def _snapshot(files: _Files) -> _Found:
    paths = files.paths
    if not paths.knowledge_snapshot.is_file():
        return _Found("pending", "")
    try:
        snapshot = knowledge.load_snapshot(paths)
        changed = knowledge.drift(snapshot, paths, files.config.keyword_budget)
    except DataFileError as error:
        return _Found("stale", str(error), True)
    # still valid: transcribe uses it until `snapshot --refresh` replaces it
    notes = [f"snapshot {snapshot.snapshot_id[: knowledge.SHORT_ID]}"]
    if changed.context_changed:
        notes.append(knowledge.BEHIND_CONTEXT)
    if changed.budget_changed:
        notes.append(knowledge.BUDGET_CHANGED)
    return _Found("done", "; ".join(notes))


def _manifest(files: _Files) -> _Found:
    if not files.paths.manifest.is_file():
        return _Found("pending", "")
    try:
        found = files.manifest
    except DataFileError as error:
        return _Found("stale", str(error), True)
    consent = "" if found.consent is not None else ", no consent note"
    return _Found("done", f"{len(found.segments)} segment(s){consent}")


# what can be wrong with a segment and the step state it gives; the first
# state in _SEVERITY that a found kind gives is the step's state
_SEGMENT_KINDS: tuple[tuple[str, StepState], ...] = (
    ("failed", "failed"),
    ("unreadable", "stale"),
    ("other snapshot", "stale"),
    ("rating outdated", "stale"),
    ("missing", "partial"),
    ("no speaker labels", "partial"),
)
_SEVERITY: tuple[StepState, ...] = ("failed", "stale", "partial")
# `transcribe` reuses a transcript of another snapshot only after `--redo`
_REDO_KINDS = frozenset({"other snapshot"})


def _transcribe(files: _Files) -> _Found:
    """Transcript, rating and speaker labels of every segment.

    `process` always diarizes and rates, so a segment without either is
    not done. A transcript made with another snapshot than the stored one,
    or a rating of another transcript version, is stale.
    """
    paths = files.paths
    if not paths.manifest.is_file():
        return _Found("pending", "needs the manifest")
    try:
        segments = [segment.index for segment in files.manifest.segments]
        snapshot_id = (
            knowledge.load_snapshot(paths).snapshot_id
            if paths.knowledge_snapshot.is_file()
            else None
        )
    except DataFileError as error:
        return _Found("stale", str(error))
    found: dict[str, list[int]] = {kind: [] for kind, _ in _SEGMENT_KINDS}
    transcribed = 0
    for index in segments:
        if not paths.reference(index).is_file():
            found["missing"].append(index)
            continue
        try:
            reference = load_reference(paths, index)
        except DataFileError:
            found["unreadable"].append(index)
            continue
        if reference.status == "failed":
            found["failed"].append(index)
            continue
        transcribed += 1
        if reference.asr.knowledge_snapshot_id != snapshot_id:
            found["other snapshot"].append(index)
        try:
            rated = load_assessment(paths, index).matches(reference)
        except DataFileError:
            rated = False
        if not rated:
            found["rating outdated"].append(index)
        if reference.diarization is None:
            found["no speaker labels"].append(index)
    detail = "; ".join(
        [f"{transcribed} of {len(segments)} segment(s) transcribed"]
        + [
            f"{kind}: {', '.join(map(str, indices))}"
            for kind, indices in found.items()
            if indices
        ]
    )
    if transcribed == 0 and len(found["missing"]) == len(segments):
        return _Found("pending", detail)
    given = {state for kind, state in _SEGMENT_KINDS if found[kind]}
    state = next((state for state in _SEVERITY if state in given), "done")
    redo = state == "stale" and any(found[kind] for kind in _REDO_KINDS)
    return _Found(state, detail, redo)


def _review(files: _Files) -> _Found:
    """Decisions on the candidates; a sheet not yet read in waits for a person."""
    paths = files.paths
    if not paths.review_candidates.is_file():
        return _Found("pending", "needs the review candidates")
    try:
        found = candidates.load_candidates(paths)
        made = decisions.load_decisions(paths)
        still_open = len(review_sheet.review_sheet(found, made).rows)
        rows = (
            review_import.read_review_sheet(paths.review_sheet)
            if paths.review_sheet.is_file()
            else None
        )
    except DataFileError as error:
        return _Found("failed", str(error))
    counts = f"{len(found.candidates)} candidate(s), {still_open} open"
    if rows is None:
        return _Found("pending" if still_open else "done", counts)
    result = review_import.import_rows(found, made, rows)
    if result.problems:
        return _Found("failed", f"{counts}; {len(result.problems)} row(s) left out")
    if result.changed:
        return _Found("waiting", f"{counts}; {paths.review_sheet} not imported yet")
    if not paths.review_decisions.is_file():
        return _Found("waiting", f"{counts}; fill in {paths.review_sheet}")
    return _Found("partial" if still_open else "done", counts)


def _speakers(files: _Files) -> _Found:
    """The assignment of the speaker labels; an untouched template waits."""
    paths = files.paths
    if not paths.speaker_assignment.is_file():
        return _Found("pending", "")
    try:
        references = speakers.diarized_references(paths, files.manifest)
        assignment = speakers.load_assignment(paths) or speakers.SpeakerAssignment()
        participants = knowledge.load_snapshot(paths).participants
    except DataFileError as error:
        return _Found("failed", str(error))
    applied = speakers.check(assignment, references, participants)
    counts = applied.counts()
    detail = f"{len(applied.labels)} label(s)" + "".join(
        f", {count} {assigned}" for assigned, count in sorted(counts.items())
    )
    if applied.findings:
        return _Found(
            "failed", f"{detail}; {len(applied.findings)} entry(ies) not applied"
        )
    if applied.labels and counts["open"] == len(applied.labels):
        return _Found("waiting", f"{detail}; fill in {paths.speaker_assignment}")
    return _Found("partial" if counts["open"] else "done", detail)


def _working(files: _Files) -> _Found:
    paths = files.paths
    if not paths.working_transcript.is_file():
        return _Found("pending", "")
    try:
        current = working.load_current(paths, files.manifest)
    except _BUILD_ERRORS as error:
        return _Found("stale", str(error))
    detail = f"{len(current.blocks)} block(s)"
    if current.findings:
        return _Found("partial", f"{detail}, {len(current.findings)} finding(s)")
    return _Found("done", detail)


def _export(files: _Files) -> _Found:
    path = files.paths.transcript_export
    if not path.is_file():
        return _Found("pending", "")
    try:
        current = files.export_bytes
    except _BUILD_ERRORS as error:
        return _Found("stale", str(error))
    if path.read_bytes() != current:
        return _Found("stale", f"{path}: outdated")
    document = files.export
    return _with_gaps(
        f"{len(document['passages'])} passage(s)",
        ((gap["code"], gap["segments"]) for gap in document["stats"]["gaps"]),
    )


def _txt(files: _Files) -> _Found:
    return _rendered(
        files,
        files.paths.transcript_text,
        lambda found: rendering.render_txt(
            found, files.config.render_timestamps
        ).encode("utf-8"),
    )


def _docx(files: _Files) -> _Found:
    return _rendered(
        files,
        files.paths.transcript_document,
        lambda found: docx_render.render_docx(
            files.paths.key, files.export, found, files.config.render_timestamps
        ),
    )


def _rendered(
    files: _Files,
    path: Path,
    render: Callable[[tuple[rendering.Paragraph, ...]], bytes],
) -> _Found:
    """A rendering of the export the current files give, compared with `path`."""
    if not path.is_file():
        return _Found("pending", "")
    try:
        found = files.paragraphs
        current = render(found)
    except _BUILD_ERRORS as error:
        return _Found("stale", str(error))
    if path.read_bytes() != current:
        return _Found("stale", f"{path}: outdated")
    return _Found("done", f"{len(found)} paragraph(s)")


def _report(files: _Files) -> _Found:
    paths = files.paths
    if not paths.report_json.is_file():
        return _Found("pending", "")
    try:
        current = files.report
    except _BUILD_ERRORS as error:
        return _Found("stale", str(error))
    for path, data in report.outputs(paths, current):
        if not path.is_file() or path.read_bytes() != data:
            return _Found("stale", f"{path}: outdated")
    return _with_gaps(
        f"{current.passages.total} passage(s)",
        ((gap.code, gap.segments) for gap in current.gaps),
    )


def _with_gaps(detail: str, gaps: Iterable[tuple[str, Sequence[int]]]) -> _Found:
    """`done`, or `partial` with the gap codes and their segments."""
    named = []
    for code, segments in gaps:
        named.append(f"{code} ({', '.join(map(str, segments))})" if segments else code)
    if named:
        return _Found("partial", f"{detail}; gaps: {', '.join(named)}")
    return _Found("done", detail)


_CHECKS: tuple[tuple[StepName, Callable[[_Files], _Found]], ...] = (
    ("extract", _extract),
    ("context", _context),
    ("snapshot", _snapshot),
    ("manifest", _manifest),
    ("transcribe", _transcribe),
    ("review", _review),
    ("speakers", _speakers),
    ("working", _working),
    ("export", _export),
    ("txt", _txt),
    ("docx", _docx),
    ("report", _report),
)
STEPS: tuple[StepName, ...] = tuple(step for step, _ in _CHECKS)  # in run order

_SUCCEEDED: frozenset[StepState] = frozenset({"done", "partial"})
# `process` stops at an incomplete transcription and runs it again; a partial
# review or assignment is a gap for people and lets the run go on
_RESUMES_WHEN_PARTIAL: frozenset[StepName] = frozenset({"transcribe"})


def summarize(paths: SessionPaths, steps: tuple[StepStatus, ...]) -> SessionStatus:
    """The session's state from its steps' states, and where `process` goes on."""
    states = {step.state for step in steps}
    overall: SessionState
    if states == {"pending"}:
        overall = "not_started"
    elif "failed" in states:
        overall = "failed"
    elif "waiting" in states:
        overall = "waiting_for_review"
    elif states & {"pending", "stale"}:
        overall = "open"
    elif "partial" in states:
        overall = "partial"
    else:
        overall = "complete"
    first_open = next(
        (n for n, step in enumerate(steps) if step.state not in _SUCCEEDED), len(steps)
    )
    last_done = steps[first_open - 1].step if first_open else None
    resume = next(
        (
            step
            for step in steps
            if step.state not in _SUCCEEDED
            or (step.state == "partial" and step.step in _RESUMES_WHEN_PARTIAL)
        ),
        None,
    )
    command = None
    if resume is not None:
        redo = f" --redo {resume.step}" if resume.redo else ""
        command = f"transcript process {paths.key}{redo}"
    return SessionStatus(
        steps=steps,
        overall=overall,
        last_done=last_done,
        resume_from=None if resume is None else resume.step,
        command=command,
    )
