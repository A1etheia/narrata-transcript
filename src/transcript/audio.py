"""Recording inspection via ffprobe and extraction of the working audio track.

The file extension is never trusted; ffprobe decides what a recording is. The
recording itself is only read: everything this module writes goes to `work/`.
"""

import json
import logging
import os
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from transcript.audio_tools import AudioTools, ToolInfo
from transcript.config import Config
from transcript.session import SessionPaths

# ffprobe `format_name` values accepted as input. MP4 and M4A share one demuxer.
MP4_CONTAINER = "mov,mp4,m4a,3gp,3g2,mj2"
SUPPORTED_CONTAINERS = frozenset({MP4_CONTAINER, "mp3", "wav"})

_PROBE_TIMEOUT_SECONDS = 60
# A larger gap between ffprobe's duration and the extracted samples means lost audio.
_DURATION_TOLERANCE_SECONDS = 0.5
_WAV_CODEC = "pcm_s16le"
METADATA_FORMAT_VERSION = 1
_ZONE_IDENTIFIER = ":Zone.Identifier"

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


@dataclass(frozen=True)
class ExtractedAudio:
    """Result of `extract`; the files are at `SessionPaths.audio_wav`/`audio_metadata`."""

    stream: AudioStream
    duration: float


def find_recording(paths: SessionPaths) -> Path:
    """Return the session's single recording in `input/`.

    Hidden files and the `:Zone.Identifier` files Windows leaves behind when
    recordings are copied into WSL are ignored.
    """
    directory = paths.input_dir
    if not directory.is_dir():
        raise AudioError(f"{directory}: no input directory for session {paths.key}")
    files = sorted(
        entry
        for entry in directory.iterdir()
        if entry.is_file()
        and not entry.name.startswith(".")
        and not entry.name.endswith(_ZONE_IDENTIFIER)
    )
    if len(files) != 1:
        raise AudioError(f"{directory}: expected one recording, found {len(files)}")
    return files[0]


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


def extract(
    info: AudioInfo,
    paths: SessionPaths,
    config: Config,
    tools: AudioTools,
    stream: int = 0,
) -> ExtractedAudio:
    """Write the chosen audio stream as WAV plus `audio.json` to the session's audio dir.

    `stream` counts audio streams only, so 0 is the first one. Both files are
    replaced atomically; on any failure neither is touched.
    """
    count = len(info.audio_streams)
    if not 0 <= stream < count:
        raise AudioError(
            f"{info.path.name}: no audio stream {stream}; "
            f"the recording has {count} (0 to {count - 1})"
        )
    chosen = info.audio_streams[stream]
    expected = chosen.duration if chosen.duration is not None else info.duration

    paths.audio_dir.mkdir(parents=True, exist_ok=True)
    wav_path = paths.audio_wav
    metadata_path = paths.audio_metadata
    with tempfile.TemporaryDirectory(dir=paths.audio_dir, prefix=".extract-") as tmp:
        tmp_wav = Path(tmp) / wav_path.name
        args = [
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(info.path),
            "-map",
            f"0:{chosen.index}",
            "-vn",
            "-ac",
            str(config.audio_channels),
            "-ar",
            str(config.audio_sample_rate),
            "-c:a",
            _WAV_CODEC,
            "-f",
            "wav",
            str(tmp_wav),
        ]
        try:
            _run(tools.ffmpeg, args, info.path, timeout=None)
        except AudioError as error:
            raise AudioError(
                f"{info.path.name}: extraction failed ({error})"
            ) from error

        duration = _wav_duration(tmp_wav)
        if abs(duration - expected) > _DURATION_TOLERANCE_SECONDS:
            raise AudioError(
                f"{info.path.name}: extracted {duration:.2f} s of audio, "
                f"but the recording reports {expected:.2f} s; the file may be damaged"
            )

        tmp_metadata = Path(tmp) / metadata_path.name
        metadata = _metadata(info, stream, wav_path.name, config, tools, duration)
        tmp_metadata.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_wav, wav_path)
        os.replace(tmp_metadata, metadata_path)

    _logger.info(
        "%s: extracted audio stream %d, %.1f s at %d Hz, %d channel(s)",
        paths.key,
        stream,
        duration,
        config.audio_sample_rate,
        config.audio_channels,
    )
    return ExtractedAudio(stream=chosen, duration=duration)


def _metadata(
    info: AudioInfo,
    stream: int,
    wav_name: str,
    config: Config,
    tools: AudioTools,
    duration: float,
) -> dict[str, Any]:
    return {
        "format_version": METADATA_FORMAT_VERSION,
        "source": {
            "file": info.path.name,
            "size_bytes": info.path.stat().st_size,
            "container": info.container,
            "duration_seconds": info.duration,
            "has_video": info.has_video,
            "audio_streams": [asdict(item) for item in info.audio_streams],
        },
        "selected_stream": {
            "audio_index": stream,
            "stream_index": info.audio_streams[stream].index,
        },
        "output": {
            "file": wav_name,
            "codec": _WAV_CODEC,
            "sample_rate": config.audio_sample_rate,
            "channels": config.audio_channels,
            "duration_seconds": duration,
        },
        "tools": {"ffmpeg": tools.ffmpeg.version, "ffprobe": tools.ffprobe.version},
    }


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / wav.getframerate()
    except (OSError, wave.Error, EOFError) as error:
        raise AudioError(f"extracted WAV is unreadable ({error})") from error


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
