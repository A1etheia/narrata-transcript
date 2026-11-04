"""Transcribe one manifest segment with a backend and store the reference transcript.

The caller picks the backend (V0.1: `WhisperBackend.from_config`); this module only
knows the `transcript.asr` interface. Every check that needs no model runs before
the model is loaded, because loading takes minutes.

A successful result is never replaced by a failed one: a failure is recorded as
`status: failed` only where no transcribed result exists.

Error messages and summaries name the segment, files and error classes, never
transcript text or keywords.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass

from transcript.asr import (
    Backend,
    BackendError,
    TranscriptionRequest,
    opened,
    transcribe,
)
from transcript.manifest import Manifest, Segment
from transcript.reference import (
    ReferenceError,
    failed_reference,
    from_backend_result,
    load_reference,
    write_reference,
)
from transcript.session import SessionPaths


class TranscriptionError(Exception):
    """A segment cannot be transcribed for a reason found before the backend runs."""


@dataclass(frozen=True)
class SegmentResult:
    """What one transcription produced: counts and provenance only, never text."""

    index: int
    backend_id: str
    model: str
    model_version: str | None
    language: str | None
    passages: int
    words: int
    words_with_confidence: int
    elapsed_ms: int


def transcribe_segment(
    paths: SessionPaths,
    manifest: Manifest,
    index: int,
    backend: Backend,
    language: str | None,
    keywords: Sequence[str] = (),
    force: bool = False,
) -> SegmentResult:
    """Transcribe segment `index` of `manifest` and write its reference transcript.

    An existing transcribed result stops the call unless `force`. A `BackendError`
    from loading writes nothing; one from transcribing is recorded as a failed
    reference, unless a transcribed one exists, and is raised again either way.
    `keywords` are hints in priority order; the backend decides whether it uses them.
    """
    segment = _segment(manifest, index)
    audio = paths.segment_wav(index)
    if not audio.is_file():
        raise TranscriptionError(
            f"{audio}: segment {index} audio not found; run transcript extract"
        )
    try:
        keep_existing = _is_transcribed(paths, index)
    except ReferenceError:
        if not force:
            raise
        keep_existing = False  # an unreadable file holds no result worth keeping
    if keep_existing and not force:
        raise TranscriptionError(
            f"{paths.reference(index)}: segment {index} is already transcribed; "
            "use --force to transcribe it again"
        )

    request = TranscriptionRequest(
        audio=audio, language=language, keywords=tuple(keywords)
    )
    with opened(backend):
        started = time.perf_counter()
        try:
            result = transcribe(backend, request)
        except BackendError as error:
            if not keep_existing:
                failure = failed_reference(
                    error, backend, manifest, segment, _elapsed_ms(started)
                )
                write_reference(paths, failure, None)
            raise
        elapsed_ms = _elapsed_ms(started)

    reference = from_backend_result(result, backend, manifest, segment, elapsed_ms)
    write_reference(paths, reference, result.raw)
    words = [word for passage in reference.passages for word in passage.words]
    return SegmentResult(
        index=index,
        backend_id=reference.asr.backend_id,
        model=reference.asr.model,
        model_version=reference.asr.model_version,
        language=reference.asr.language,
        passages=len(reference.passages),
        words=len(words),
        words_with_confidence=sum(word.confidence is not None for word in words),
        elapsed_ms=elapsed_ms,
    )


def _segment(manifest: Manifest, index: int) -> Segment:
    for segment in manifest.segments:
        if segment.index == index:
            return segment
    raise TranscriptionError(
        f"segment {index} not in the manifest of {manifest.key}; "
        f"it has segments 1 to {len(manifest.segments)}"
    )


def _is_transcribed(paths: SessionPaths, index: int) -> bool:
    """Whether segment `index` has a stored, successful transcript."""
    return (
        paths.reference(index).is_file()
        and load_reference(paths, index).status == "transcribed"
    )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
