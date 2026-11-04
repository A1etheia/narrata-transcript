"""Local ASR backends behind one interface; see docs/asr-backends.md."""

from transcript.asr.backend import (
    DEVICES,
    FEATURES,
    AudioInputError,
    Backend,
    BackendError,
    BackendInfo,
    BackendResult,
    BackendRuntimeError,
    BackendUnavailableError,
    Capabilities,
    ResourceError,
    ResultSegment,
    ResultWord,
    TranscriptionRequest,
    UnsupportedCapabilityError,
)

__all__ = [
    "DEVICES",
    "FEATURES",
    "AudioInputError",
    "Backend",
    "BackendError",
    "BackendInfo",
    "BackendResult",
    "BackendRuntimeError",
    "BackendUnavailableError",
    "Capabilities",
    "ResourceError",
    "ResultSegment",
    "ResultWord",
    "TranscriptionRequest",
    "UnsupportedCapabilityError",
]
