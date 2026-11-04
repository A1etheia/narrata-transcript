"""The interface every local ASR backend implements, and the types it exchanges.

Generic pipeline code talks to a backend only through these types, so it never
imports a model library. Adapters import their runtime inside `load()`.

A missing capability is not an error: the matching result fields stay empty or
`None`. Only a step that cannot work without a capability calls
`Capabilities.require`.

Error messages name the backend and the audio path, never transcript text or
keywords: both may contain names of real people.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

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
