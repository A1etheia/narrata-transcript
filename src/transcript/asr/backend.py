"""The interface every local ASR backend implements, and the types it exchanges.

Generic pipeline code talks to a backend only through these types, so it never
imports a model library. Adapters import their runtime inside `load()`.

A missing capability is not an error: the matching result fields stay empty or
`None`. Only a step that cannot work without a capability calls
`Capabilities.require`.

Error messages name the backend and the audio path, never transcript text or
keywords: both may contain names of real people.
"""

import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar

from transcript.timecode import seconds_to_ms

_T = TypeVar("_T")

DEVICES = ("cpu", "cuda")
FEATURES = (
    "word_timestamps",
    "segment_timestamps",
    "speaker_labels",
    "keyword_biasing",
    "word_confidence",
    "segment_signals",
)


class BackendError(Exception):
    """A backend failed; `retryable` says whether the same call may succeed later."""

    retryable = False


class AudioInputError(BackendError):
    """The audio is missing, unreadable or in a format the backend rejects."""


class BackendUnavailableError(BackendError):
    """The model, its runtime or a required device is not installed or found."""


class ResourceError(BackendError):
    """Memory or the device ran out; the call may succeed once resources free up."""

    retryable = True


class BackendRuntimeError(BackendError):
    """The backend failed unexpectedly; the message never carries the original one."""

    retryable = True


class UnsupportedCapabilityError(BackendError):
    """A step needs a capability the backend does not declare."""


@dataclass(frozen=True)
class Capabilities:
    """What a backend can deliver; downstream code checks these, not the backend."""

    word_timestamps: bool = False
    segment_timestamps: bool = False
    speaker_labels: bool = False
    keyword_biasing: bool = False
    word_confidence: bool = False
    segment_signals: bool = False
    devices: frozenset[str] = frozenset({"cpu"})
    max_audio_seconds: float | None = None  # None: whole recordings in one call

    def __post_init__(self) -> None:
        if not self.devices or not set(self.devices) <= set(DEVICES):
            raise ValueError(f"devices must be a non-empty subset of {DEVICES}")
        if self.max_audio_seconds is not None and not self.max_audio_seconds > 0:
            raise ValueError("max_audio_seconds must be positive or None")

    def to_dict(self) -> dict[str, Any]:
        """The capabilities as JSON-ready values, devices sorted."""
        data = asdict(self)
        data["devices"] = sorted(self.devices)
        return data

    def require(self, feature: str) -> None:
        """Fail when a step cannot work without `feature`, one of `FEATURES`.

        Callers that know the backend add its id to the message.
        """
        if feature not in FEATURES:
            raise ValueError(f"unknown capability: {feature}")
        if not getattr(self, feature):
            raise UnsupportedCapabilityError(f"capability missing: {feature}")


@dataclass(frozen=True)
class BackendInfo:
    """Which backend and model produced a result, for provenance and resume."""

    backend_id: str  # e.g. "faster-whisper"
    model: str  # e.g. "large-v3-turbo"
    model_version: str | None = None  # revision or checksum, when known
    runtime_version: str | None = None  # version of the backend library


def hub_revision(model_path: Path) -> str | None:
    """The revision of a Hugging Face cache snapshot (`…/snapshots/<sha>`), else None."""
    return model_path.name if model_path.parent.name == "snapshots" else None


def resolve_device(requested: str, cuda_available: bool, backend_id: str) -> str:
    """`auto` picks cuda when available, else cpu; `cuda` without a GPU is an error."""
    if requested == "auto":
        return "cuda" if cuda_available else "cpu"
    if requested == "cuda" and not cuda_available:
        raise BackendUnavailableError(f"{backend_id}: no CUDA device found")
    return requested


def cached_model_dir(
    name: str,
    lookup: Callable[[str], str],
    required: Sequence[str],
    backend_id: str,
) -> Path:
    """A local model directory, or `name` resolved by `lookup` from the local cache.

    `lookup` must never download; a miss names the model and the README step.
    """
    if os.path.isdir(name):
        path = Path(name)
    else:
        try:
            path = Path(lookup(name))
        except Exception as error:
            raise BackendUnavailableError(
                f"{backend_id}: model {name} not in the local cache, "
                f"download it once, see README ({type(error).__name__})"
            ) from error
    if not all((path / file).is_file() for file in required):
        raise BackendUnavailableError(
            f"{backend_id}: {path} lacks {' or '.join(required)}"
        )
    return path


def runtime_error(error: Exception, cause: str) -> BackendError:
    """Out of memory as a `ResourceError`, anything else as a `BackendRuntimeError`.

    `cause` names backend, action and exception type; the runtime's own message
    is only searched, never repeated.
    """
    message = str(error).lower() if isinstance(error, RuntimeError) else ""
    if isinstance(error, MemoryError) or "out of memory" in message:
        return ResourceError(f"{cause}, out of memory")
    return BackendRuntimeError(cause)


@dataclass(frozen=True)
class TranscriptionRequest:
    """One audio segment to transcribe; device and model belong to the adapter."""

    audio: Path  # segment WAV from the manifest, segment-local times
    language: str | None = None  # two-letter code; None lets the backend detect
    keywords: tuple[str, ...] = ()  # hints from the knowledge snapshot


@dataclass(frozen=True)
class ResultWord:
    text: str
    start: float | None = None  # seconds, local to the segment WAV
    end: float | None = None
    confidence: float | None = None  # 0..1, None when the backend has none


@dataclass(frozen=True)
class ResultSegment:
    text: str
    start: float | None = None  # seconds, local to the segment WAV
    end: float | None = None
    words: tuple[ResultWord, ...] = ()
    speaker: str | None = None  # generic backend label, never a name
    signals: Mapping[str, float] = field(default_factory=dict)  # e.g. avg_logprob


@dataclass(frozen=True)
class BackendResult:
    """A backend's answer for one segment; transient, not a stored format."""

    info: BackendInfo
    segments: tuple[ResultSegment, ...]
    language: str | None = None
    language_probability: float | None = None
    keywords_used: tuple[str, ...] = ()  # the hints that took effect, after cuts
    settings: Mapping[str, Any] = field(default_factory=dict)  # inference params
    raw: Any = None  # the backend's own answer, JSON-ready and unchanged


class Backend(Protocol):
    """A local ASR backend: load once, transcribe many segments, close."""

    @property
    def info(self) -> BackendInfo: ...

    @property
    def capabilities(self) -> Capabilities: ...

    def load(self) -> None:
        """Load model and runtime; may take minutes and occupy the GPU."""

    def transcribe(self, request: TranscriptionRequest) -> BackendResult:
        """Transcribe one segment; raise only `BackendError` subclasses."""

    def close(self) -> None:
        """Release the model; safe to call when `load` failed or never ran."""


@contextmanager
def opened(backend: Backend) -> Iterator[Backend]:
    """Load the backend for a block of `transcribe` calls and always close it."""
    try:
        _guarded(backend, backend.load)
        yield backend
    finally:
        _guarded(backend, backend.close)


def transcribe(backend: Backend, request: TranscriptionRequest) -> BackendResult:
    """Transcribe one segment; every failure arrives as a `BackendError`."""
    if not request.audio.is_file():
        raise AudioInputError(f"{request.audio}: audio not found")
    result = _guarded(backend, lambda: backend.transcribe(request))
    problem = _result_problem(result, request, backend.capabilities.keyword_biasing)
    if problem:
        raise BackendRuntimeError(
            f"{backend.info.backend_id}: invalid result, {problem}"
        )
    return result


def _guarded(backend: Backend, call: Callable[[], _T]) -> _T:
    """Run a backend call; foreign exceptions lose their message, it may hold text."""
    try:
        return call()
    except BackendError:
        raise
    except Exception as error:
        category = _category(error)
        raise category(f"{backend.info.backend_id}: {type(error).__name__}") from error


def _category(error: Exception) -> type[BackendError]:
    if isinstance(error, ImportError):
        return BackendUnavailableError
    if isinstance(error, MemoryError):
        return ResourceError
    return BackendRuntimeError


def _result_problem(
    result: BackendResult, request: TranscriptionRequest, biasing: bool
) -> str:
    """Describe the first inconsistency in `result`, or return an empty string."""
    if result.keywords_used and not biasing:
        return "keywords_used without keyword_biasing"
    if not set(request.keywords).issuperset(result.keywords_used):
        return "keywords_used holds terms that were not requested"
    for number, segment in enumerate(result.segments, start=1):
        if not _valid_span(segment.start, segment.end):
            return f"segment time out of range in segment {number}"
        for word in segment.words:
            if not _valid_span(word.start, word.end):
                return f"word time out of range in segment {number}"
            if word.confidence is not None and not 0 <= word.confidence <= 1:
                return f"word confidence outside 0..1 in segment {number}"
    return ""


def _valid_span(start: float | None, end: float | None) -> bool:
    """Both times absent or valid for `seconds_to_ms`, and in order."""
    try:
        for value in (start, end):
            if value is not None:
                seconds_to_ms(value)
    except ValueError:
        return False
    return start is None or end is None or start <= end
