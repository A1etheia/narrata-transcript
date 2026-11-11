"""The status of a session's steps, read from its files alone (TOOL-57).

No status file decides anything: each step's state comes from the files it
writes, checked with the loaders the steps use themselves, so a missing,
outdated or inconsistent file is never reported as done. Reading only: no
file is written, no network called, no model loaded; whether the configured
model still matches a stored result is the preflight's check.

Details name counts, segment numbers, snapshot ids and paths, never
participants, labels, glossary entries or transcript text (TOOL-66).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from transcript import audio, knowledge, manifest, narrata
from transcript.config import Config
from transcript.jsonfile import DataFileError
from transcript.pipeline import StepName
from transcript.reference import load_reference
from transcript.session import SessionPaths
from transcript.uncertainty import load_assessment

# pending: not started; stale: there, but outdated or inconsistent, so it is
# run again and never counts as done; waiting: for a person to fill in a file
StepState = Literal["pending", "done", "partial", "failed", "waiting", "stale"]


@dataclass(frozen=True)
class StepStatus:
    step: StepName
    state: StepState
    detail: str = ""  # counts, segment numbers and paths only


_Check = Callable[[SessionPaths, Config], tuple[StepState, str]]


def inspect(paths: SessionPaths, config: Config) -> tuple[StepStatus, ...]:
    """The status of every step that writes a file, in run order."""
    return tuple(StepStatus(step, *check(paths, config)) for step, check in _CHECKS)


def _extract(paths: SessionPaths, config: Config) -> tuple[StepState, str]:
    try:
        recordings = audio.find_recordings(paths)
    except audio.AudioError as error:
        return "failed", str(error)
    if not paths.audio_metadata.is_file():
        return "pending", ""
    if not audio.extracted(paths, len(recordings)):
        return "stale", f"audio of {len(recordings)} recording(s) incomplete"
    problem = manifest.audio_metadata_problem(paths, recordings)
    if problem is not None:
        return "stale", problem
    return "done", f"{len(recordings)} recording(s)"


def _context(paths: SessionPaths, config: Config) -> tuple[StepState, str]:
    if not paths.narrata_context.is_file():
        return "pending", ""
    try:
        narrata.read_session(paths)
    except DataFileError as error:
        return "stale", str(error)
    return "done", "Narrata context stored"


def _snapshot(paths: SessionPaths, config: Config) -> tuple[StepState, str]:
    if not paths.knowledge_snapshot.is_file():
        return "pending", ""
    try:
        snapshot = knowledge.load_snapshot(paths)
        changed = knowledge.drift(snapshot, paths, config.keyword_budget)
    except DataFileError as error:
        return "stale", str(error)
    # still valid: transcribe uses it until `snapshot --refresh` replaces it
    notes = [f"snapshot {snapshot.snapshot_id[: knowledge.SHORT_ID]}"]
    if changed.context_changed:
        notes.append(knowledge.BEHIND_CONTEXT)
    if changed.budget_changed:
        notes.append(knowledge.BUDGET_CHANGED)
    return "done", "; ".join(notes)


def _manifest(paths: SessionPaths, config: Config) -> tuple[StepState, str]:
    if not paths.manifest.is_file():
        return "pending", ""
    try:
        found = manifest.load_manifest(paths)
    except DataFileError as error:
        return "stale", str(error)
    consent = "" if found.consent is not None else ", no consent note"
    return "done", f"{len(found.segments)} segment(s){consent}"


# what can be wrong with a segment, and the step state it gives; the first
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


def _transcribe(paths: SessionPaths, config: Config) -> tuple[StepState, str]:
    """Transcript, rating and speaker labels of every segment.

    `process` always diarizes and rates, so a segment without either is
    not done. A transcript made with another snapshot than the stored one,
    or a rating of another transcript version, is stale.
    """
    if not paths.manifest.is_file():
        return "pending", "needs the manifest"
    try:
        segments = [segment.index for segment in manifest.load_manifest(paths).segments]
        snapshot_id = (
            knowledge.load_snapshot(paths).snapshot_id
            if paths.knowledge_snapshot.is_file()
            else None
        )
    except DataFileError as error:
        return "stale", str(error)
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
        return "pending", detail
    given = {state for kind, state in _SEGMENT_KINDS if found[kind]}
    return next((state for state in _SEVERITY if state in given), "done"), detail


_CHECKS: tuple[tuple[StepName, _Check], ...] = (
    ("extract", _extract),
    ("context", _context),
    ("snapshot", _snapshot),
    ("manifest", _manifest),
    ("transcribe", _transcribe),
)
