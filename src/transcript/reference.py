"""The internal reference transcript format: one versioned JSON file per segment.

A reference transcript holds what an ASR backend recognised in one segment WAV of
the manifest, normalized so that later steps never need to know the backend. The
backend's own answer is stored unchanged in a separate raw file next to it.

Times are whole milliseconds local to the segment WAV; `session_time` turns them
into session time. Speaker labels are generic
(`SPEAKER_00`), never names. Everything optional may be `None` or empty.

Error messages name the file, the field and the passage number, never text,
keywords or labels: they may contain names of real people.
"""

import collections
import datetime
import functools
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import transcript
from transcript import jsonfile, narrata
from transcript.asr import (
    Backend,
    BackendError,
    BackendInfo,
    BackendResult,
    ResultSegment,
)
from transcript.jsonfile import DataFileError
from transcript.manifest import Manifest, Segment
from transcript.session import SessionKey, SessionPaths, reference_raw_name
from transcript.timecode import seconds_to_ms

REFERENCE_FORMAT_VERSION = 2
READABLE_FORMAT_VERSIONS = (1, REFERENCE_FORMAT_VERSION)  # 1 has no snapshot id
STATUSES = ("transcribed", "failed")


class ReferenceError(DataFileError):
    """A reference transcript is missing, invalid or belongs to another segment."""


@dataclass(frozen=True)
class Word:
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
    confidence: float | None = None  # 0..1, on the backend's own scale
    speaker: str | None = None  # None is a valid value: no turn covers the word

    def __post_init__(self) -> None:
        check_span(self.start_ms, self.end_ms, "word time")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("word confidence outside 0..1")


@dataclass(frozen=True)
class Passage:
    """A stretch of speech as the backend delimited it, e.g. a Whisper segment."""

    index: int  # 1-based within the segment
    text: str  # as recognised, never corrected
    start_ms: int | None = None
    end_ms: int | None = None
    words: tuple[Word, ...] = ()
    speaker: str | None = None  # majority of the word labels, see majority_speaker
    signals: Mapping[str, float] = field(default_factory=dict)  # e.g. avg_logprob

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("passage index must be positive")
        check_span(self.start_ms, self.end_ms, "passage time")


@dataclass(frozen=True)
class SegmentRef:
    """The manifest segment the transcript belongs to."""

    index: int
    file: str  # WAV name in the audio dir
    source_sha256: str  # of the original recording, to notice a changed input


@dataclass(frozen=True)
class AsrInfo:
    """Backend, model and settings of the run, for provenance and resume."""

    backend_id: str
    model: str
    model_version: str | None = None
    runtime_version: str | None = None
    capabilities: Mapping[str, Any] = field(default_factory=dict)
    settings: Mapping[str, Any] = field(default_factory=dict)
    language: str | None = None
    language_probability: float | None = None
    keywords_used: tuple[str, ...] = ()
    knowledge_snapshot_id: str | None = None  # the knowledge the run was given

    @property
    def info(self) -> BackendInfo:
        """Backend and model as `BackendIdentity.matches` compares them."""
        return BackendInfo(
            self.backend_id, self.model, self.model_version, self.runtime_version
        )


@dataclass(frozen=True)
class Processing:
    pipeline_version: str
    processed_at: str  # ISO 8601 with offset
    elapsed_ms: int | None = None


@dataclass(frozen=True)
class Overlap:
    """A range where the diarization heard more than one person at once."""

    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        check_span(self.start_ms, self.end_ms, "overlap time")


@dataclass(frozen=True)
class Diarization:
    """Who-spoke-when metadata, kept apart from the ASR metadata (TOOL-76)."""

    backend_id: str
    model: str
    labels: tuple[str, ...]
    model_version: str | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)
    num_speakers: int | None = None  # the hint given, not the number found
    overlaps: tuple[Overlap, ...] = ()

    def __post_init__(self) -> None:
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("diarization labels repeat")
        if self.num_speakers is not None and self.num_speakers < 1:
            raise ValueError("num_speakers must be positive")


@dataclass(frozen=True)
class Failure:
    """Why a segment failed: the error class only, never its message."""

    category: str  # e.g. "ResourceError"
    retryable: bool


@dataclass(frozen=True)
class ReferenceTranscript:
    key: SessionKey
    play_session_id: int | str
    segment: SegmentRef
    status: str  # one of STATUSES
    asr: AsrInfo
    processing: Processing
    passages: tuple[Passage, ...] = ()
    diarization: Diarization | None = None
    error: Failure | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError("unknown status")
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("error must be set exactly when the status is failed")
        if self.status == "failed" and self.passages:
            raise ValueError("a failed segment has no passages")
        for number, passage in enumerate(self.passages, start=1):
            if passage.index != number:
                raise ValueError(f"passage {number} is out of order")
        if self.diarization is not None:
            known = set(self.diarization.labels)
            for passage in self.passages:
                labels = {passage.speaker, *(word.speaker for word in passage.words)}
                if not labels - {None} <= known:
                    raise ValueError(
                        f"passage {passage.index} has a label outside the diarization"
                    )

    @property
    def raw_file(self) -> str:
        """Name of the raw file next to this transcript."""
        return reference_raw_name(self.segment.index)

    @property
    def words(self) -> tuple[Word, ...]:
        """The words of all passages in order."""
        return tuple(word for passage in self.passages for word in passage.words)

    @property
    def text(self) -> str:
        """The recognised text of all passages, separated by single spaces."""
        return " ".join(filter(None, (p.text.strip() for p in self.passages)))


def majority_speaker(words: Iterable[Word]) -> str | None:
    """The label most words carry; `None` without labels or on a tie."""
    counts = collections.Counter(w.speaker for w in words if w.speaker is not None)
    ranked = counts.most_common(2)
    if not ranked or (len(ranked) == 2 and ranked[0][1] == ranked[1][1]):
        return None
    return ranked[0][0]


def from_backend_result(
    result: BackendResult,
    backend: Backend,
    manifest: Manifest,
    segment: Segment,
    elapsed_ms: int | None = None,
    now: datetime.datetime | None = None,
    knowledge_snapshot_id: str | None = None,
) -> ReferenceTranscript:
    """Normalize a backend's answer for `segment`; `raw` stays out, see write_reference.

    Seconds become whole milliseconds, nothing else changes: text is kept as
    recognised. `diarization` stays empty until TOOL-76 adds it.
    """
    return ReferenceTranscript(
        key=manifest.key,
        play_session_id=manifest.play_session_id,
        segment=segment_ref(segment),
        status="transcribed",
        asr=_asr_info(
            result.info,
            backend,
            settings=dict(result.settings),
            language=result.language,
            language_probability=result.language_probability,
            keywords_used=tuple(result.keywords_used),
            knowledge_snapshot_id=knowledge_snapshot_id,
        ),
        processing=_processing(elapsed_ms, now),
        passages=tuple(
            _passage_from(passage, index)
            for index, passage in enumerate(result.segments, start=1)
        ),
    )


def failed_reference(
    error: BackendError,
    backend: Backend,
    manifest: Manifest,
    segment: Segment,
    elapsed_ms: int | None = None,
    now: datetime.datetime | None = None,
    knowledge_snapshot_id: str | None = None,
) -> ReferenceTranscript:
    """Record that `segment` failed; only the error class is kept, not its message."""
    return ReferenceTranscript(
        key=manifest.key,
        play_session_id=manifest.play_session_id,
        segment=segment_ref(segment),
        status="failed",
        error=Failure(category=type(error).__name__, retryable=error.retryable),
        asr=_asr_info(
            backend.info, backend, knowledge_snapshot_id=knowledge_snapshot_id
        ),
        processing=_processing(elapsed_ms, now),
    )


def write_reference(
    paths: SessionPaths, reference: ReferenceTranscript, raw: Any
) -> None:
    """Write the raw answer, then the transcript; only the latter marks it done.

    `raw` is the backend's answer, JSON-ready and stored unchanged; `None` for a
    failed segment.
    """
    _check_key(paths, reference)
    jsonfile.write_atomic(
        paths.reference_raw(reference.segment.index),
        {"backend_id": reference.asr.backend_id, "raw": raw},
    )
    update_reference(paths, reference)


def update_reference(paths: SessionPaths, reference: ReferenceTranscript) -> None:
    """Rewrite only the normalized transcript, e.g. with speaker labels added.

    The raw file stays as the backend wrote it.
    """
    _check_key(paths, reference)
    jsonfile.write_atomic(paths.reference(reference.segment.index), to_json(reference))


def _check_key(paths: SessionPaths, reference: ReferenceTranscript) -> None:
    if reference.key != paths.key:
        raise ValueError(f"transcript of {reference.key} given for {paths.key}")


def _asr_info(info: BackendInfo, backend: Backend, **result: Any) -> AsrInfo:
    """Provenance of a run; `result` adds what only a successful answer knows."""
    return AsrInfo(
        backend_id=info.backend_id,
        model=info.model,
        model_version=info.model_version,
        runtime_version=info.runtime_version,
        capabilities=backend.capabilities.to_dict(),
        **result,
    )


def segment_ref(segment: Segment) -> SegmentRef:
    """How a transcript names its manifest segment."""
    return SegmentRef(
        index=segment.index, file=segment.file, source_sha256=segment.source.sha256
    )


def _processing(elapsed_ms: int | None, now: datetime.datetime | None) -> Processing:
    moment = now or datetime.datetime.now().astimezone()
    return Processing(
        pipeline_version=transcript.__version__,
        processed_at=moment.isoformat(timespec="seconds"),
        elapsed_ms=elapsed_ms,
    )


def _passage_from(segment: ResultSegment, index: int) -> Passage:
    """One backend segment as a passage; word labels decide its speaker."""
    words = tuple(
        Word(
            text=word.text,
            start_ms=_ms(word.start),
            end_ms=_ms(word.end),
            confidence=word.confidence,
        )
        for word in segment.words
    )
    return Passage(
        index=index,
        text=segment.text,
        start_ms=_ms(segment.start),
        end_ms=_ms(segment.end),
        words=words,
        speaker=majority_speaker(words) or segment.speaker,
        signals=dict(segment.signals),
    )


def _ms(seconds: float | None) -> int | None:
    return None if seconds is None else seconds_to_ms(seconds)


def load_reference(paths: SessionPaths, index: int) -> ReferenceTranscript:
    """Read the reference transcript of segment `index` and check where it belongs."""
    path = paths.reference(index)
    data = _read_json(path, "reference transcript")
    if data.get("format_version") not in READABLE_FORMAT_VERSIONS:
        raise ReferenceError(
            f"{path}: unsupported format_version; transcribe the segment again"
        )
    reference = from_json(data, path)
    if reference.key != paths.key:
        raise ReferenceError(
            f"{path}: belongs to session {reference.key}, not {paths.key}"
        )
    if reference.segment.index != index:
        raise ReferenceError(
            f"{path}: belongs to segment {reference.segment.index}, not {index}"
        )
    return reference


def to_json(reference: ReferenceTranscript) -> dict[str, Any]:
    asr = reference.asr
    diarization = reference.diarization
    return {
        "format_version": REFERENCE_FORMAT_VERSION,
        "session": {"group": reference.key.group, "ordinal": reference.key.ordinal},
        "play_session_id": reference.play_session_id,
        "segment": {
            "index": reference.segment.index,
            "file": reference.segment.file,
            "source_sha256": reference.segment.source_sha256,
        },
        "status": reference.status,
        "error": (
            None
            if reference.error is None
            else {
                "category": reference.error.category,
                "retryable": reference.error.retryable,
            }
        ),
        "asr": {
            "backend_id": asr.backend_id,
            "model": asr.model,
            "model_version": asr.model_version,
            "runtime_version": asr.runtime_version,
            "capabilities": dict(asr.capabilities),
            "settings": dict(asr.settings),
            "language": asr.language,
            "language_probability": asr.language_probability,
            "keywords_used": list(asr.keywords_used),
            "knowledge_snapshot_id": asr.knowledge_snapshot_id,
        },
        "processing": {
            "pipeline_version": reference.processing.pipeline_version,
            "processed_at": reference.processing.processed_at,
            "elapsed_ms": reference.processing.elapsed_ms,
        },
        "diarization": (
            None
            if diarization is None
            else {
                "backend_id": diarization.backend_id,
                "model": diarization.model,
                "model_version": diarization.model_version,
                "settings": dict(diarization.settings),
                "num_speakers": diarization.num_speakers,
                "labels": list(diarization.labels),
                "overlaps": [
                    {"start_ms": overlap.start_ms, "end_ms": overlap.end_ms}
                    for overlap in diarization.overlaps
                ],
            }
        ),
        "raw_file": reference.raw_file,
        "passages": [
            {
                "index": passage.index,
                "text": passage.text,
                "start_ms": passage.start_ms,
                "end_ms": passage.end_ms,
                "speaker": passage.speaker,
                "signals": dict(passage.signals),
                "words": [
                    {
                        "text": word.text,
                        "start_ms": word.start_ms,
                        "end_ms": word.end_ms,
                        "confidence": word.confidence,
                        "speaker": word.speaker,
                    }
                    for word in passage.words
                ],
            }
            for passage in reference.passages
        ],
    }


def from_json(data: dict[str, Any], path: Path) -> ReferenceTranscript:
    """Build a transcript from its JSON form; every violation is a `ReferenceError`."""
    session = _field(data, "session", dict, path)
    segment = _field(data, "segment", dict, path)
    asr = _field(data, "asr", dict, path)
    processing = _field(data, "processing", dict, path)
    play_session_id = data.get("play_session_id")
    if not narrata.is_narrata_id(play_session_id):
        raise ReferenceError(f"{path}: field 'play_session_id' missing or invalid")
    error = _optional(data, "error", dict, path)
    diarization = _optional(data, "diarization", dict, path)
    passages = _field(data, "passages", list, path)
    try:
        return ReferenceTranscript(
            key=SessionKey(
                _field(session, "group", str, path),
                _field(session, "ordinal", int, path),
            ),
            play_session_id=play_session_id,
            segment=SegmentRef(
                index=_field(segment, "index", int, path),
                file=_field(segment, "file", str, path),
                source_sha256=_field(segment, "source_sha256", str, path),
            ),
            status=_field(data, "status", str, path),
            error=(
                None
                if error is None
                else Failure(
                    category=_field(error, "category", str, path),
                    retryable=_field(error, "retryable", bool, path),
                )
            ),
            asr=AsrInfo(
                backend_id=_field(asr, "backend_id", str, path),
                model=_field(asr, "model", str, path),
                model_version=_optional(asr, "model_version", str, path),
                runtime_version=_optional(asr, "runtime_version", str, path),
                capabilities=_field(asr, "capabilities", dict, path),
                settings=_field(asr, "settings", dict, path),
                language=_optional(asr, "language", str, path),
                language_probability=_number(asr, "language_probability", path),
                keywords_used=_strings(asr, "keywords_used", path),
                knowledge_snapshot_id=_optional(
                    asr, "knowledge_snapshot_id", str, path
                ),
            ),
            processing=Processing(
                pipeline_version=_field(processing, "pipeline_version", str, path),
                processed_at=_field(processing, "processed_at", str, path),
                elapsed_ms=_optional(processing, "elapsed_ms", int, path),
            ),
            diarization=(
                None if diarization is None else _diarization(diarization, path)
            ),
            passages=tuple(
                _passage(entry, number, path)
                for number, entry in enumerate(passages, start=1)
            ),
        )
    except ValueError as error:
        raise ReferenceError(f"{path}: {error}") from None


def _diarization(data: dict[str, Any], path: Path) -> Diarization:
    return Diarization(
        backend_id=_field(data, "backend_id", str, path),
        model=_field(data, "model", str, path),
        model_version=_optional(data, "model_version", str, path),
        settings=_field(data, "settings", dict, path),
        num_speakers=_optional(data, "num_speakers", int, path),
        labels=_strings(data, "labels", path),
        overlaps=tuple(
            Overlap(
                start_ms=_field(entry, "start_ms", int, path),
                end_ms=_field(entry, "end_ms", int, path),
            )
            for entry in _field(data, "overlaps", list, path)
        ),
    )


def _passage(data: Any, number: int, path: Path) -> Passage:
    """One passage; a ValueError from it names the passage number."""
    try:
        signals = _field(data, "signals", dict, path)
        if not all(_is_number(value) for value in signals.values()):
            raise ReferenceError(f"{path}: passage {number}: field 'signals' invalid")
        return Passage(
            index=_field(data, "index", int, path),
            text=_field(data, "text", str, path),
            start_ms=_optional(data, "start_ms", int, path),
            end_ms=_optional(data, "end_ms", int, path),
            speaker=_optional(data, "speaker", str, path),
            signals=signals,
            words=tuple(
                Word(
                    text=_field(entry, "text", str, path),
                    start_ms=_optional(entry, "start_ms", int, path),
                    end_ms=_optional(entry, "end_ms", int, path),
                    confidence=_number(entry, "confidence", path),
                    speaker=_optional(entry, "speaker", str, path),
                )
                for entry in _field(data, "words", list, path)
            ),
        )
    except ValueError as error:
        raise ValueError(f"passage {number}: {error}") from None


def check_span(start: int | None, end: int | None, what: str) -> None:
    """Both times absent or non-negative, and in order when both are given."""
    if any(value is not None and value < 0 for value in (start, end)):
        raise ValueError(f"{what} is negative")
    if start is not None and end is not None and start > end:
        raise ValueError(f"{what} ends before it starts")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _strings(data: Any, name: str, path: Path) -> tuple[str, ...]:
    return tuple(jsonfile.list_of(data, name, str, path, ReferenceError))


_field = functools.partial(jsonfile.field, error=ReferenceError)
_optional = functools.partial(jsonfile.optional_field, error=ReferenceError)
_number = functools.partial(jsonfile.optional_number, error=ReferenceError)
_read_json = functools.partial(jsonfile.read_object, error=ReferenceError)
