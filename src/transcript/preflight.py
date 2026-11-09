"""Preflight: check before a long local run that everything it needs is in place.

Every check runs, also after a failed one, so one run names every problem.
Errors stop a run, warnings do not. The preflight only reads: it writes no
file and creates no directory. Messages name paths, counts and models, never
participants, glossary entries or transcript text (TOOL-66).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from transcript import audio_tools
from transcript.asr.backend import Backend, BackendError, BackendIdentity, BackendInfo
from transcript.asr.backend import identity as backend_identity
from transcript.asr.whisper import WhisperBackend
from transcript.config import Config, ConfigError, load_config
from transcript.diarization.pyannote import PyannoteDiarizer

Level = Literal["ok", "warning", "error"]


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


_PROBES = Probes()


def run(
    config_path: Path, *, diarize: bool = True, probes: Probes = _PROBES
) -> list[Finding]:
    """Check the environment; `diarize=False` leaves the diarization out."""
    findings: list[Finding] = []
    _check_audio_tools(findings, probes)
    config = _check_config(findings, config_path)
    if config is not None:
        _check_asr(findings, config, probes)
        if diarize:
            _check_diarization(findings, config, probes)
    return findings


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
    findings.append(
        Finding(
            "ok",
            "audio-tools",
            f"ffmpeg {tools.ffmpeg.version}, ffprobe {tools.ffprobe.version}",
        )
    )
    return tools


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


def _check_asr(
    findings: list[Finding], config: Config, probes: Probes
) -> BackendIdentity | None:
    """The model from the local cache and the device, without loading the model."""
    try:
        found = backend_identity(probes.asr(config))
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
    return found


def _check_diarization(findings: list[Finding], config: Config, probes: Probes) -> None:
    """Runtime and model from the local cache; torch is not loaded."""
    try:
        info = probes.diarizer(config).identity()
    except BackendError as error:
        findings.append(Finding("error", "diarization", str(error)))
        return
    findings.append(Finding("ok", "diarization", info.model_label))
