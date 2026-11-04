"""Recording inspection: container, audio streams and duration via ffprobe.

The file extension is never trusted; ffprobe decides what a recording is.
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcript.audio_tools import AudioTools, ToolInfo

# ffprobe `format_name` values accepted as input. MP4 and M4A share one demuxer.
MP4_CONTAINER = "mov,mp4,m4a,3gp,3g2,mj2"
SUPPORTED_CONTAINERS = frozenset({MP4_CONTAINER, "mp3", "wav"})

_PROBE_TIMEOUT_SECONDS = 60

_logger = logging.getLogger(__name__)


class AudioError(Exception):
    """A recording is unusable or a step failed; the message is meant for the user."""


@dataclass(frozen=True)
class AudioStream:
    index: int  # absolute stream index in the container, as in `-map 0:<index>`
    codec: str
    channels: int | None
    sample_rate: int | None
    duration: float | None


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    container: str
    duration: float
    audio_streams: tuple[AudioStream, ...]
    has_video: bool


def probe(path: Path, tools: AudioTools) -> AudioInfo:
    """Read a recording's metadata, or raise `AudioError` if it is not usable."""
    if not path.is_file():
        raise AudioError(f"{path}: file not found")
    if not os.access(path, os.R_OK):
        raise AudioError(f"{path}: file is not readable")

    data = _read_probe(path, tools)
    format_ = data.get("format", {})
    container = str(format_.get("format_name", ""))
    if container not in SUPPORTED_CONTAINERS:
        raise AudioError(
            f"{path.name}: unsupported container {container or 'unknown'}; "
            "supported are MP4, M4A, MP3 and WAV"
        )

    streams = data.get("streams", [])
    audio_streams = tuple(
        _audio_stream(stream)
        for stream in streams
        if stream.get("codec_type") == "audio"
    )
    if not audio_streams:
        raise AudioError(f"{path.name}: no audio stream")

    duration = _float(format_.get("duration"))
    if duration is None or duration <= 0:
        raise AudioError(f"{path.name}: duration unknown or zero")

    _logger.info(
        "probed recording: container %s, %d audio stream(s), first codec %s, %.1f s",
        container,
        len(audio_streams),
        audio_streams[0].codec,
        duration,
    )
    return AudioInfo(
        path=path,
        container=container,
        duration=duration,
        audio_streams=audio_streams,
        has_video=any(stream.get("codec_type") == "video" for stream in streams),
    )


def _read_probe(path: Path, tools: AudioTools) -> dict[str, Any]:
    args = ["-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    try:
        result = _run(tools.ffprobe, args, path, _PROBE_TIMEOUT_SECONDS)
    except AudioError as error:
        raise AudioError(
            f"{path.name}: damaged or not a media file ({error})"
        ) from error
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AudioError(f"{path.name}: ffprobe returned unreadable output") from error


def _run(
    tool: ToolInfo, args: list[str], path: Path, timeout: float | None
) -> subprocess.CompletedProcess[str]:
    """Run an audio tool on `path`; failures become `AudioError` with ffmpeg's reason."""
    try:
        result = subprocess.run(
            [str(tool.path), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AudioError(f"{tool.name} did not finish within {timeout} s") from error
    except OSError as error:
        raise AudioError(f"{tool.name} cannot run ({error.strerror})") from error
    if result.returncode != 0:
        raise AudioError(_last_line(result.stderr, path))
    return result


def _audio_stream(stream: dict[str, Any]) -> AudioStream:
    return AudioStream(
        index=int(stream["index"]),
        codec=str(stream.get("codec_name", "unknown")),
        channels=_int(stream.get("channels")),
        sample_rate=_int(stream.get("sample_rate")),
        duration=_float(stream.get("duration")),
    )


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _last_line(stderr: str, path: Path) -> str:
    """Last ffmpeg/ffprobe error line, with the full path shortened to the file name."""
    lines = [line for line in stderr.strip().splitlines() if line.strip()]
    return lines[-1].replace(str(path), path.name) if lines else "no details"
