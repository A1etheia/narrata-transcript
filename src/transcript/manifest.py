"""The session manifest: identity, consent note and the segment timeline.

`build_manifest` combines `audio.json`, the segment WAV headers and the session
block of the Narrata transcription context (IOA-1215) into `manifest.json`. Later
steps read it with `load_manifest` and need no audio analysis for that.

The session timeline is the recordings played back to back; pauses between them
are unknown. Times are whole milliseconds rounded from cumulative frame counts,
so a segment ends exactly where the next one starts.
"""

import datetime
import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcript import audio, jsonfile, narrata
from transcript.jsonfile import DataFileError
from transcript.session import SessionKey, SessionPaths
from transcript.timecode import frames_to_ms

MANIFEST_FORMAT_VERSION = 1


class ManifestError(DataFileError):
    """The manifest or one of its inputs is missing or inconsistent."""


@dataclass(frozen=True)
class SourceRecording:
    file: str
    size_bytes: int
    sha256: str
    container: str
    audio_index: int
    stream_index: int


@dataclass(frozen=True)
class Segment:
    index: int  # 1-based, in session order
    file: str  # WAV name in the session's audio dir
    source: SourceRecording
    frames: int
    start_ms: int
    end_ms: int
    overlap_before_ms: int  # shared with the previous segment; 0 without splitting

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_absolute_ms(self, local_ms: int) -> int:
        """Convert a time inside this segment to session time in milliseconds."""
        if not 0 <= local_ms <= self.duration_ms:
            raise ValueError(
                f"{local_ms} ms lies outside segment {self.index} "
                f"({self.duration_ms} ms)"
            )
        return self.start_ms + local_ms


@dataclass(frozen=True)
class Consent:
    oral: bool
    noted_at: str  # ISO 8601 with offset


@dataclass(frozen=True)
class Manifest:
    key: SessionKey
    play_session_id: int | str
    session_date: datetime.date
    consent: Consent | None
    sample_rate: int
    channels: int
    segments: tuple[Segment, ...]

    @property
    def duration_ms(self) -> int:
        return self.segments[-1].end_ms


def build_manifest(
    paths: SessionPaths,
    consent: bool,
    now: datetime.datetime | None = None,
) -> Manifest:
    """Build and write `manifest.json` from the extracted audio and Narrata context.

    Without `consent`, a consent note of an earlier manifest for the same play
    session is kept. An earlier manifest of a different play session is an error:
    Narrata reassigned the ordinal, and this work directory belongs to another one.
    """
    session = narrata.read_session(paths)
    if not paths.audio_metadata.is_file():
        raise ManifestError(
            f"{paths.audio_metadata}: audio metadata not found; "
            "run transcript extract first"
        )
    metadata = _read_json(paths.audio_metadata, "audio metadata")
    if metadata.get("format_version") != audio.METADATA_FORMAT_VERSION:
        raise ManifestError(
            f"{paths.audio_metadata}: unsupported format_version; "
            "run transcript extract again"
        )
    output_format = _field(metadata, "output_format", dict, paths.audio_metadata)
    sample_rate = _field(output_format, "sample_rate", int, paths.audio_metadata)
    channels = _field(output_format, "channels", int, paths.audio_metadata)
    entries = _field(metadata, "segments", list, paths.audio_metadata)
    if not entries:
        raise ManifestError(f"{paths.audio_metadata}: no segments")

    frames = [_checked_frames(paths, entry, sample_rate) for entry in entries]
    segments = tuple(
        Segment(
            index=index,
            file=_field(entry, "file", str, paths.audio_metadata),
            source=_source(entry, paths.audio_metadata),
            frames=count,
            start_ms=start_ms,
            end_ms=end_ms,
            overlap_before_ms=0,
        )
        for index, (entry, count, (start_ms, end_ms)) in enumerate(
            zip(entries, frames, timeline(frames, sample_rate), strict=True), start=1
        )
    )

    manifest = Manifest(
        key=paths.key,
        play_session_id=session.play_session_id,
        session_date=session.session_date,
        consent=_consent(paths, session.play_session_id, consent, now),
        sample_rate=sample_rate,
        channels=channels,
        segments=segments,
    )
    jsonfile.write_atomic(paths.manifest, _to_json(manifest))
    return manifest


def load_manifest(paths: SessionPaths) -> Manifest:
    """Read `manifest.json` and check it against the session key and Narrata context."""
    data = _read_json(paths.manifest, "manifest")
    if data.get("format_version") != MANIFEST_FORMAT_VERSION:
        raise ManifestError(
            f"{paths.manifest}: unsupported format_version; "
            "run transcript manifest again"
        )
    manifest = _from_json(data, paths.manifest)
    if manifest.key != paths.key:
        raise ManifestError(
            f"{paths.manifest}: belongs to session {manifest.key}, not {paths.key}"
        )
    _check_timeline(manifest.segments, paths.manifest)
    context_exists = paths.narrata_context.is_file()
    if context_exists and (
        narrata.read_session(paths).play_session_id != manifest.play_session_id
    ):
        raise ManifestError(_reassigned(paths))
    return manifest


def audio_sources(paths: SessionPaths) -> tuple[SourceRecording, ...]:
    """The recordings `audio.json` was extracted from, in segment order."""
    metadata = _read_json(paths.audio_metadata, "audio metadata")
    if metadata.get("format_version") != audio.METADATA_FORMAT_VERSION:
        raise ManifestError(
            f"{paths.audio_metadata}: unsupported format_version; "
            "run transcript extract again"
        )
    entries = _field(metadata, "segments", list, paths.audio_metadata)
    return tuple(_source(entry, paths.audio_metadata) for entry in entries)


def timeline(frames: list[int], sample_rate: int) -> list[tuple[int, int]]:
    """Start and end in ms of segments played back to back, from their frame counts."""
    bounds = []
    total = 0
    for count in frames:
        start = frames_to_ms(total, sample_rate)
        total += count
        bounds.append((start, frames_to_ms(total, sample_rate)))
    return bounds


def _checked_frames(paths: SessionPaths, entry: Any, sample_rate: int) -> int:
    """Frame count from `audio.json`, confirmed against the WAV that was written."""
    source = paths.audio_metadata
    name = _field(entry, "file", str, source)
    expected = _field(entry, "frames", int, source)
    wav_path = paths.audio_dir / name
    try:
        actual = audio.wav_frames(wav_path)
    except audio.AudioError as error:
        raise ManifestError(
            f"{wav_path}: {error}; run transcript extract again"
        ) from error
    if actual != (expected, sample_rate):
        raise ManifestError(
            f"{wav_path}: does not match {source.name}; run transcript extract again"
        )
    return expected


def _source(entry: dict[str, Any], path: Path) -> SourceRecording:
    """Source and stream of a segment; `audio.json` and the manifest share the layout."""
    source = _field(entry, "source", dict, path)
    stream = _field(entry, "selected_stream", dict, path)
    return SourceRecording(
        file=_field(source, "file", str, path),
        size_bytes=_field(source, "size_bytes", int, path),
        sha256=_field(source, "sha256", str, path),
        container=_field(source, "container", str, path),
        audio_index=_field(stream, "audio_index", int, path),
        stream_index=_field(stream, "stream_index", int, path),
    )


def _consent(
    paths: SessionPaths,
    play_session_id: int | str,
    noted_now: bool,
    now: datetime.datetime | None,
) -> Consent | None:
    previous = (
        _read_json(paths.manifest, "manifest") if paths.manifest.is_file() else {}
    )
    if previous and previous.get("play_session_id") != play_session_id:
        raise ManifestError(_reassigned(paths))
    if noted_now:
        moment = now or datetime.datetime.now().astimezone()
        return Consent(oral=True, noted_at=moment.isoformat(timespec="seconds"))
    kept = previous.get("consent")
    if isinstance(kept, dict) and kept.get("oral") is True:
        return Consent(oral=True, noted_at=str(kept.get("noted_at", "")))
    return None


def _reassigned(paths: SessionPaths) -> str:
    return (
        f"{paths.manifest}: play_session_id differs from {paths.narrata_context.name}; "
        f"the ordinal of {paths.key} was reassigned in Narrata, "
        "move this work directory aside before rebuilding"
    )


def _check_timeline(segments: tuple[Segment, ...], path: Path) -> None:
    if not segments:
        raise ManifestError(f"{path}: no segments")
    previous_end = 0
    for number, segment in enumerate(segments, start=1):
        if (
            segment.index != number
            or segment.overlap_before_ms < 0
            or segment.start_ms != previous_end - segment.overlap_before_ms
            or segment.end_ms < segment.start_ms
        ):
            raise ManifestError(
                f"{path}: segment {number} is out of order or leaves a gap"
            )
        previous_end = segment.end_ms


def _to_json(manifest: Manifest) -> dict[str, Any]:
    return {
        "format_version": MANIFEST_FORMAT_VERSION,
        "session": {"group": manifest.key.group, "ordinal": manifest.key.ordinal},
        "play_session_id": manifest.play_session_id,
        "session_date": manifest.session_date.isoformat(),
        "consent": (
            None
            if manifest.consent is None
            else {"oral": manifest.consent.oral, "noted_at": manifest.consent.noted_at}
        ),
        "audio": {"sample_rate": manifest.sample_rate, "channels": manifest.channels},
        "duration_ms": manifest.duration_ms,
        "segments": [
            {
                "index": segment.index,
                "file": segment.file,
                "frames": segment.frames,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "duration_ms": segment.duration_ms,
                "overlap_before_ms": segment.overlap_before_ms,
                "source": {
                    "file": segment.source.file,
                    "size_bytes": segment.source.size_bytes,
                    "sha256": segment.source.sha256,
                    "container": segment.source.container,
                },
                "selected_stream": {
                    "audio_index": segment.source.audio_index,
                    "stream_index": segment.source.stream_index,
                },
            }
            for segment in manifest.segments
        ],
    }


def _from_json(data: dict[str, Any], path: Path) -> Manifest:
    session = _field(data, "session", dict, path)
    try:
        key = SessionKey(
            _field(session, "group", str, path), _field(session, "ordinal", int, path)
        )
        session_date = datetime.date.fromisoformat(
            _field(data, "session_date", str, path)
        )
    except ValueError as error:
        raise ManifestError(f"{path}: {error}") from error
    play_session_id = data.get("play_session_id")
    if not narrata.is_narrata_id(play_session_id):
        raise ManifestError(f"{path}: play_session_id missing or invalid")
    consent = data.get("consent")
    audio = _field(data, "audio", dict, path)
    return Manifest(
        key=key,
        play_session_id=play_session_id,
        session_date=session_date,
        consent=(
            None
            if consent is None
            else Consent(
                oral=_field(consent, "oral", bool, path),
                noted_at=_field(consent, "noted_at", str, path),
            )
        ),
        sample_rate=_field(audio, "sample_rate", int, path),
        channels=_field(audio, "channels", int, path),
        segments=tuple(
            Segment(
                index=_field(entry, "index", int, path),
                file=_field(entry, "file", str, path),
                source=_source(entry, path),
                frames=_field(entry, "frames", int, path),
                start_ms=_field(entry, "start_ms", int, path),
                end_ms=_field(entry, "end_ms", int, path),
                overlap_before_ms=_field(entry, "overlap_before_ms", int, path),
            )
            for entry in _field(data, "segments", list, path)
        ),
    )


_field = functools.partial(jsonfile.field, error=ManifestError)
_read_json = functools.partial(jsonfile.read_object, error=ManifestError)
