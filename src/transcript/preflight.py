"""Preflight: check before a long local run that everything it needs is in place.

Every check runs, also after a failed one, so one run names every problem.
Errors stop a run, warnings do not. The preflight only reads: it writes no
file and creates no directory. Messages name paths, counts and models, never
participants, glossary entries or transcript text (TOOL-66).
"""

import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from transcript import audio, audio_tools, knowledge, manifest, narrata, speaker_player
from transcript.asr.backend import Backend, BackendError, BackendIdentity, BackendInfo
from transcript.asr.backend import identity as backend_identity
from transcript.asr.whisper import WhisperBackend
from transcript.config import Config, ConfigError, load_config
from transcript.diarization.pyannote import PyannoteDiarizer
from transcript.domain import DomainContext
from transcript.jsonfile import DataFileError
from transcript.narrata_client import NarrataClientError, read_token
from transcript.reference import load_reference
from transcript.session import SessionKey, SessionPaths
from transcript.timecode import format_ms
from transcript.transcription import TranscriptionError, check_audio, reusable

Level = Literal["ok", "warning", "error"]

_PCM_BYTES = 2  # the working WAVs are 16-bit PCM
_GB = 1e9


@dataclass(frozen=True)
class Finding:
    level: Level
    check: str  # e.g. "asr"; stable, for scripts and TOOL-55
    message: str


class _Diarizer(Protocol):
    def identity(self) -> BackendInfo: ...


@dataclass(frozen=True)
class Probes:
    """What the checks call outside this module; tests replace it."""

    search_path: str | None = None  # replaces PATH for ffmpeg and ffprobe
    asr: Callable[[Config], Backend] = WhisperBackend.from_config
    diarizer: Callable[[Config], _Diarizer] = PyannoteDiarizer.from_config
    # where the Narrata token is looked up
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    dotenv: Path = Path(".env")
    disk_free: Callable[[Path], int] = lambda path: shutil.disk_usage(path).free
    player: Callable[[], Path | None] = speaker_player.find_player


@dataclass(frozen=True)
class _Asr:
    """What `transcribe` compares a stored result with, known before `load`."""

    identity: BackendIdentity
    keyword_biasing: bool


_PROBES = Probes()


def run(
    config_path: Path,
    key: SessionKey | None = None,
    *,
    diarize: bool = True,
    strict_resume: bool = False,
    player: bool = False,
    probes: Probes = _PROBES,
) -> list[Finding]:
    """Check the environment and, with `key`, that session.

    `diarize=False` leaves the diarization out. `strict_resume` makes stored
    transcripts that `transcribe` would make again an error rather than a
    warning, for `process`, which must not transcribe again unasked. `player`
    adds the optional ffplay, for `doctor`; `process` plays nothing.
    """
    findings: list[Finding] = []
    tools = _check_audio_tools(findings, probes)
    if player:
        _check_player(findings, probes)
    config = _check_config(findings, config_path)
    if config is None:
        return findings
    asr = _check_asr(findings, config, probes)
    if diarize:
        _check_diarization(findings, config, probes)
    if key is not None:
        paths = config.session_paths(key)
        recordings, infos = _check_input(findings, paths, tools)
        _check_paths(findings, paths)
        _check_disk(findings, paths, config, infos, probes)
        _check_context(findings, paths, config, probes)
        snapshot = _check_snapshot(findings, paths, config)
        _check_resume(findings, paths, config, recordings, asr, snapshot, strict_resume)
    return findings


def blocked(findings: Sequence[Finding]) -> bool:
    """Whether a run must not start: any error does, warnings do not."""
    return errors(findings) > 0


def errors(findings: Sequence[Finding]) -> int:
    return sum(finding.level == "error" for finding in findings)


def warnings(findings: Sequence[Finding]) -> int:
    return sum(finding.level == "warning" for finding in findings)


def _check_audio_tools(
    findings: list[Finding], probes: Probes
) -> audio_tools.AudioTools | None:
    try:
        tools = audio_tools.check_audio_tools(probes.search_path)
    except audio_tools.AudioToolError as error:
        findings.append(Finding("error", "audio-tools", str(error)))
        return None
    found = ", ".join(
        f"{info.name} {info.version} ({info.path})"
        for info in (tools.ffmpeg, tools.ffprobe)
    )
    findings.append(Finding("ok", "audio-tools", found))
    return tools


def _check_player(findings: list[Finding], probes: Probes) -> None:
    """ffplay is optional: only `speakers --assign` plays samples with it."""
    player = probes.player()
    if player is None:
        findings.append(
            Finding(
                "warning",
                "player",
                f"{speaker_player.PLAYER} not found on PATH; speakers --assign "
                "cannot play samples (it comes with the ffmpeg package)",
            )
        )
    else:
        findings.append(Finding("ok", "player", str(player)))


def _check_config(findings: list[Finding], path: Path) -> Config | None:
    try:
        config = load_config(path)
    except ConfigError as error:
        findings.append(
            Finding(
                "error",
                "config",
                f"{error}; the checks that need the configuration were skipped",
            )
        )
        return None
    findings.append(Finding("ok", "config", f"{path} is valid"))
    return config


def _check_asr(findings: list[Finding], config: Config, probes: Probes) -> _Asr | None:
    """The model from the local cache and the device, without loading the model."""
    try:
        backend = probes.asr(config)
        found = backend_identity(backend)
    except BackendError as error:
        findings.append(Finding("error", "asr", str(error)))
        return None
    info = found.info
    device = found.settings.get("device")
    findings.append(
        Finding("ok", "asr", f"{info.backend_id} {info.model_label} on {device}")
    )
    if config.asr_device == "auto" and device == "cpu":
        findings.append(
            Finding(
                "warning",
                "asr",
                "no CUDA device found, the ASR runs on the CPU and takes "
                "much longer; asr.device: cpu silences this warning",
            )
        )
    return _Asr(found, backend.capabilities.keyword_biasing)


def _check_diarization(findings: list[Finding], config: Config, probes: Probes) -> None:
    """Runtime and model from the local cache; torch is not loaded."""
    try:
        info = probes.diarizer(config).identity()
    except BackendError as error:
        findings.append(Finding("error", "diarization", str(error)))
        return
    findings.append(Finding("ok", "diarization", info.model_label))


def _check_input(
    findings: list[Finding],
    paths: SessionPaths,
    tools: audio_tools.AudioTools | None,
) -> tuple[tuple[Path, ...] | None, list[audio.AudioInfo] | None]:
    """The recordings in `input/` and, when ffprobe runs, their metadata."""
    try:
        recordings = audio.find_recordings(paths)
    except audio.AudioError as error:
        findings.append(Finding("error", "session-input", str(error)))
        return None, None
    if tools is None:
        findings.append(
            Finding(
                "ok",
                "session-input",
                f"{len(recordings)} recording(s), not probed without ffprobe",
            )
        )
        return recordings, None
    infos = []
    for recording in recordings:
        try:
            infos.append(audio.probe(recording, tools))
        except audio.AudioError as error:
            findings.append(Finding("error", "session-input", str(error)))
    if len(infos) < len(recordings):
        return recordings, None
    total_ms = round(sum(info.duration for info in infos) * 1000)
    findings.append(
        Finding(
            "ok",
            "session-input",
            f"{len(recordings)} recording(s), {format_ms(total_ms)} in total",
        )
    )
    if len(recordings) > 1:
        findings.append(
            Finding(
                "warning",
                "session-input",
                f"{len(recordings)} recordings: they are transcribed as segments, "
                "but the JSON export of several recordings needs contract 1.1 "
                "(IOA-1287)",
            )
        )
    return recordings, infos


def _check_paths(findings: list[Finding], paths: SessionPaths) -> None:
    """`work/` and `output/` of the session, or where they would be created."""
    before = len(findings)
    for directory in (paths.work_dir, paths.output_dir):
        existing = _existing_ancestor(directory)
        if not existing.is_dir():
            problem = f"{directory}: {existing} is not a directory"
        elif not os.access(existing, os.W_OK | os.X_OK):
            problem = f"{directory}: {existing} is not writable"
        else:
            continue
        findings.append(Finding("error", "paths", problem))
    if len(findings) == before:
        findings.append(
            Finding("ok", "paths", f"{paths.work_dir} and {paths.output_dir} writable")
        )


def _check_disk(
    findings: list[Finding],
    paths: SessionPaths,
    config: Config,
    infos: Sequence[audio.AudioInfo] | None,
    probes: Probes,
) -> None:
    """Room for the working WAVs `transcript extract` writes, if they are missing."""
    if infos is None:
        return  # without durations there is nothing to estimate
    if audio.extracted(paths, len(infos)):
        findings.append(Finding("ok", "disk", "audio already extracted"))
        return
    seconds = sum(info.duration for info in infos)
    needed = round(
        seconds * config.audio_sample_rate * config.audio_channels * _PCM_BYTES
    )
    where = _existing_ancestor(paths.work_dir)
    try:
        free = probes.disk_free(where)
    except OSError as error:
        findings.append(
            Finding("error", "disk", f"{where}: free space unknown ({error.strerror})")
        )
        return
    room = f"{free / _GB:.1f} GB free at {where}, the WAVs need {needed / _GB:.1f} GB"
    findings.append(Finding("error" if free < needed else "ok", "disk", room))


def _check_context(
    findings: list[Finding], paths: SessionPaths, config: Config, probes: Probes
) -> None:
    """The stored Narrata context, or what it takes to fetch it."""
    if paths.narrata_context.is_file():
        try:
            narrata.read_session(paths)
        except DataFileError as error:
            findings.append(Finding("error", "knowledge", str(error)))
            return
        findings.append(Finding("ok", "knowledge", "Narrata context stored"))
        return
    missing = _narrata_access(paths.key, config, probes)
    if not missing:
        findings.append(
            Finding(
                "ok",
                "knowledge",
                "no stored Narrata context yet, transcript context fetches it",
            )
        )
        return
    findings.append(
        Finding(
            "error",
            "knowledge",
            "no stored Narrata context and no access to fetch it: "
            + "; ".join(missing)
            + "; or give a saved response with transcript context --from-file",
        )
    )


def _narrata_access(key: SessionKey, config: Config, probes: Probes) -> list[str]:
    """What is missing to fetch the context; the token itself is never shown."""
    missing = []
    if config.narrata_url is None:
        missing.append("narrata.url is not set")
    if key.group not in config.narrata_groups:
        missing.append(f"narrata.groups has no group id for {key.group}")
    try:
        read_token(probes.environ, probes.dotenv)
    except NarrataClientError as error:
        missing.append(str(error))
    return missing


def _check_snapshot(
    findings: list[Finding], paths: SessionPaths, config: Config
) -> knowledge.Snapshot | None:
    """The stored snapshot, if it is valid, and whether it is behind."""
    if not paths.knowledge_snapshot.is_file():
        findings.append(
            Finding(
                "warning",
                "knowledge",
                "no knowledge snapshot: transcribe would run without keywords; "
                "transcript snapshot builds it",
            )
        )
        return None
    try:
        snapshot = knowledge.load_snapshot(paths)
        changed = knowledge.drift(snapshot, paths, config.keyword_budget)
    except DataFileError as error:
        findings.append(Finding("error", "knowledge", str(error)))
        return None
    short_id = snapshot.snapshot_id[: knowledge.SHORT_ID]
    findings.append(Finding("ok", "knowledge", f"snapshot {short_id}"))
    if changed.context_changed:
        findings.append(Finding("warning", "knowledge", knowledge.BEHIND_CONTEXT))
    if changed.budget_changed:
        findings.append(Finding("warning", "knowledge", knowledge.BUDGET_CHANGED))
    return snapshot


def _check_resume(
    findings: list[Finding],
    paths: SessionPaths,
    config: Config,
    recordings: Sequence[Path] | None,
    asr: _Asr | None,
    snapshot: knowledge.Snapshot | None,
    strict: bool = False,
) -> None:
    """Whether the artifacts of an earlier run fit the input and each other."""
    if not paths.audio_metadata.is_file() and not paths.manifest.is_file():
        findings.append(Finding("ok", "resume", "no earlier artifacts"))
        return
    if paths.audio_metadata.is_file() and recordings is not None:
        problem = manifest.audio_metadata_problem(paths, recordings)
        if problem is not None:
            findings.append(Finding("error", "resume", problem))
    if not paths.manifest.is_file():
        findings.append(Finding("ok", "resume", "audio extracted, no manifest yet"))
        return
    try:
        session_manifest = manifest.load_manifest(paths)
    except DataFileError as error:
        findings.append(Finding("error", "resume", str(error)))
        return
    if session_manifest.consent is None:
        findings.append(
            Finding(
                "warning",
                "resume",
                "the manifest has no consent note; transcript manifest --consent "
                "notes it once everyone audible agreed",
            )
        )
    snapshot_id, hints = _passed_knowledge(asr, snapshot)
    transcribed = 0
    again = []
    for segment in session_manifest.segments:
        try:
            check_audio(paths, segment.index)
        except TranscriptionError as error:
            findings.append(Finding("error", "resume", str(error)))
        if not paths.reference(segment.index).is_file():
            continue
        try:
            reference = load_reference(paths, segment.index)
        except DataFileError as error:
            findings.append(Finding("error", "resume", str(error)))
            continue
        if reference.status != "transcribed":
            continue
        transcribed += 1
        if asr is not None and not reusable(
            reference, asr.identity, config.language, snapshot_id, hints
        ):
            again.append(segment.index)
    findings.append(
        Finding(
            "ok",
            "resume",
            f"manifest with {len(session_manifest.segments)} segment(s), "
            f"{transcribed} transcribed",
        )
    )
    if again:
        message = (
            "segment(s) "
            + ", ".join(str(index) for index in again)
            + " are transcribed again: model, settings, snapshot, keywords "
            "or language differ from the stored result"
        )
        if strict:
            message += "; --redo transcribe runs them again on purpose"
        findings.append(Finding("error" if strict else "warning", "resume", message))


def _passed_knowledge(
    asr: _Asr | None, snapshot: knowledge.Snapshot | None
) -> tuple[str | None, tuple[str, ...] | None]:
    """Snapshot id and keywords as `transcribe` would pass them to `reusable`."""
    biasing = asr is not None and asr.keyword_biasing
    if snapshot is None:
        return None, (() if biasing else None)
    keywords = DomainContext.from_snapshot(snapshot).transcription_keywords()
    return snapshot.snapshot_id, (tuple(keywords) if biasing else None)


def _existing_ancestor(path: Path) -> Path:
    """`path` itself or the nearest parent that exists; the root always does."""
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return path
