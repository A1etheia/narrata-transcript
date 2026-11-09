"""Recording inspection via ffprobe and extraction of the working audio track.

The file extension is never trusted; ffprobe decides what a recording is. A
session may consist of several recordings (the recorder stops after five hours);
each becomes one segment WAV. Recordings are only read: everything this module
writes goes to `work/`.
"""

import hashlib
import json
import logging
import os
import subprocess
import tempfile
import wave
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from transcript.audio_tools import AudioTools, ToolInfo
from transcript.config import Config
from transcript.session import SessionPaths
from transcript.timecode import frames_to_ms

# ffprobe `format_name` values accepted as input. MP4 and M4A share one demuxer.
MP4_CONTAINER = "mov,mp4,m4a,3gp,3g2,mj2"
SUPPORTED_CONTAINERS = frozenset({MP4_CONTAINER, "mp3", "wav"})

_PROBE_TIMEOUT_SECONDS = 60
# A larger gap between ffprobe's duration and the extracted samples means lost audio.
_DURATION_TOLERANCE_SECONDS = 0.5
_WAV_CODEC = "pcm_s16le"
METADATA_FORMAT_VERSION = 2
_HASH_CHUNK_BYTES = 1 << 20
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
class ExtractedSegment:
    """One extracted recording; the WAV is at `SessionPaths.segment_wav(index)`."""

    index: int  # 1-based, in session order
    source: AudioInfo
    audio_index: int  # counts audio streams only, as `extract(stream=…)`
    frames: int
    sample_rate: int
    sha256: str  # of the original recording

    @property
    def stream(self) -> AudioStream:
        return self.source.audio_streams[self.audio_index]

    @property
    def duration_ms(self) -> int:
        return frames_to_ms(self.frames, self.sample_rate)


def find_recordings(paths: SessionPaths) -> tuple[Path, ...]:
    """Return the session's recordings in `input/`, sorted by file name.

    The sort order is the session order, so `… 1.m4a` comes before `… 2.m4a`.
    Hidden files and the `:Zone.Identifier` files Windows leaves behind when
    recordings are copied into WSL are ignored.
    """
    directory = paths.input_dir
    if not directory.is_dir():
        raise AudioError(f"{directory}: no input directory for session {paths.key}")
    files = tuple(
        sorted(
            entry
            for entry in directory.iterdir()
            if entry.is_file()
            and not entry.name.startswith(".")
            and not entry.name.endswith(_ZONE_IDENTIFIER)
        )
    )
    if not files:
        raise AudioError(f"{directory}: no recording found")
    return files


def extracted(paths: SessionPaths, recordings: int) -> bool:
    """Whether `audio.json` and a WAV for each of `recordings` are in place.

    Presence only: whether they fit the recordings is the preflight's check.
    """
    return paths.audio_metadata.is_file() and all(
        paths.segment_wav(index).is_file() for index in range(1, recordings + 1)
    )


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
    infos: Sequence[AudioInfo],
    paths: SessionPaths,
    config: Config,
    tools: AudioTools,
    stream: int = 0,
) -> tuple[ExtractedSegment, ...]:
    """Write one WAV per recording plus `audio.json` to the session's audio dir.

    `infos` is in session order. `stream` counts audio streams only, so 0 is the
    first one, and applies to every recording. The new files replace the old ones
    only after every recording was extracted; `audio.json` is replaced last.
    """
    if not infos:
        raise AudioError(f"{paths.key}: no recording to extract")
    for info in infos:
        count = len(info.audio_streams)
        if not 0 <= stream < count:
            raise AudioError(
                f"{info.path.name}: no audio stream {stream}; "
                f"the recording has {count} (0 to {count - 1})"
            )

    paths.audio_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=paths.audio_dir, prefix=".extract-") as tmp:
        segments = tuple(
            _extract_one(index, info, stream, paths, Path(tmp), config, tools)
            for index, info in enumerate(infos, start=1)
        )
        tmp_metadata = Path(tmp) / paths.audio_metadata.name
        metadata = _metadata(segments, paths, config, tools)
        tmp_metadata.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        for segment in segments:
            target = paths.segment_wav(segment.index)
            os.replace(Path(tmp) / target.name, target)
        os.replace(tmp_metadata, paths.audio_metadata)

    current = {paths.segment_wav(segment.index) for segment in segments}
    for stale in paths.segment_wavs():
        if stale not in current:
            stale.unlink()

    _logger.info(
        "%s: extracted %d segment(s), %d ms at %d Hz, %d channel(s)",
        paths.key,
        len(segments),
        sum(segment.duration_ms for segment in segments),
        config.audio_sample_rate,
        config.audio_channels,
    )
    return segments


def _extract_one(
    index: int,
    info: AudioInfo,
    stream: int,
    paths: SessionPaths,
    tmp: Path,
    config: Config,
    tools: AudioTools,
) -> ExtractedSegment:
    chosen = info.audio_streams[stream]
    expected = chosen.duration if chosen.duration is not None else info.duration
    tmp_wav = tmp / paths.segment_wav(index).name
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
        raise AudioError(f"{info.path.name}: extraction failed ({error})") from error

    # Hashed right after ffmpeg read the file, while it is likely still cached.
    sha256 = sha256_file(info.path)
    frames, sample_rate = wav_frames(tmp_wav)
    duration = frames / sample_rate
    if abs(duration - expected) > _DURATION_TOLERANCE_SECONDS:
        raise AudioError(
            f"{info.path.name}: extracted {duration:.2f} s of audio, "
            f"but the recording reports {expected:.2f} s; the file may be damaged"
        )
    return ExtractedSegment(
        index=index,
        source=info,
        audio_index=stream,
        frames=frames,
        sample_rate=sample_rate,
        sha256=sha256,
    )


def _metadata(
    segments: Sequence[ExtractedSegment],
    paths: SessionPaths,
    config: Config,
    tools: AudioTools,
) -> dict[str, Any]:
    return {
        "format_version": METADATA_FORMAT_VERSION,
        "output_format": {
            "codec": _WAV_CODEC,
            "sample_rate": config.audio_sample_rate,
            "channels": config.audio_channels,
        },
        "tools": {"ffmpeg": tools.ffmpeg.version, "ffprobe": tools.ffprobe.version},
        "segments": [
            {
                "index": segment.index,
                "file": paths.segment_wav(segment.index).name,
                "frames": segment.frames,
                "source": {
                    "file": segment.source.path.name,
                    "size_bytes": segment.source.path.stat().st_size,
                    "sha256": segment.sha256,
                    "container": segment.source.container,
                    "duration_seconds": segment.source.duration,
                    "has_video": segment.source.has_video,
                    "audio_streams": [
                        asdict(item) for item in segment.source.audio_streams
                    ],
                },
                "selected_stream": {
                    "audio_index": segment.audio_index,
                    "stream_index": segment.stream.index,
                },
            }
            for segment in segments
        ],
    }


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks so large recordings fit in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def wav_frames(path: Path) -> tuple[int, int]:
    """Frame count and sample rate from the WAV header; frames are the exact length."""
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes(), wav.getframerate()
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
