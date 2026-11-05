"""Transcribe manifest segments with a backend and store the reference transcripts.

The caller picks the backend (V0.1: `WhisperBackend.from_config`); this module only
knows the `transcript.asr` interface. Every check that needs no model runs before
the model is loaded, because loading takes minutes.

`transcribe_session` loads the backend once for all segments that need it and
reuses a stored result made with the same model, revision and settings.

A successful result is never replaced by a failed one: a failure is recorded as
`status: failed` only where no transcribed result exists.

Error messages and summaries name the segment, files and error classes, never
transcript text or keywords.
"""

import time
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from transcript.asr import (
    Backend,
    BackendError,
    BackendIdentity,
    TranscriptionRequest,
    identity,
    opened,
    transcribe,
)
from transcript.manifest import Manifest, Segment
from transcript.reference import (
    ReferenceError,
    ReferenceTranscript,
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


@dataclass(frozen=True)
class SegmentOutcome:
    """What a session run did with one segment: counts and error class, never text.

    `status` is `transcribed` or `reused` (a stored result counts), `failed` (the
    backend raised `error`) or `open` (not reached, the backend did not load).
    """

    index: int
    status: str
    passages: int = 0
    words: int = 0
    words_with_confidence: int = 0
    language: str | None = None
    elapsed_ms: int | None = None  # of the backend call, when it transcribed
    error: str | None = None  # error class of a failure
    retryable: bool | None = None


@dataclass(frozen=True)
class SessionRun:
    """The outcome per selected segment in manifest order, and what decided them."""

    identity: BackendIdentity
    outcomes: tuple[SegmentOutcome, ...]
    load_error: BackendError | None = None  # why `open` segments were not reached

    @property
    def complete(self) -> bool:
        """Whether every selected segment now has a transcribed result."""
        return all(o.status in ("transcribed", "reused") for o in self.outcomes)


def transcribe_session(
    paths: SessionPaths,
    manifest: Manifest,
    backend: Backend,
    language: str | None,
    keywords: Sequence[str] = (),
    force: bool = False,
    indices: Collection[int] | None = None,
    progress: Callable[[SegmentOutcome], None] | None = None,
) -> SessionRun:
    """Transcribe the selected segments of `manifest`, all of them by default.

    A stored transcribed result is reused, unless `force`, when backend, model,
    revision and settings match the backend's identity and, with `language` set,
    the detected language matches it. Everything else is transcribed in manifest
    order with the backend loaded once. A `BackendError` from one segment is
    recorded as `failed` and the run goes on; one from loading leaves the
    remaining segments `open`. `progress` gets each outcome as it is known.

    Raises before loading: a `BackendError` when the backend cannot run, a
    `TranscriptionError` for an unknown segment or missing audio, and a
    `ReferenceError` for an unreadable stored result unless `force`.
    """
    report = progress or _ignore
    found = identity(backend)
    segments = _selected(manifest, indices)
    for segment in segments:
        _check_audio(paths, segment.index)

    outcomes: dict[int, SegmentOutcome] = {}
    pending: list[tuple[Segment, bool]] = []
    for segment in segments:
        stored = _stored(paths, segment.index, force)
        transcribed = stored is not None and stored.status == "transcribed"
        if transcribed and not force and _reusable(stored, found, language):
            outcomes[segment.index] = _outcome(stored, "reused")
            report(outcomes[segment.index])
        else:
            pending.append((segment, transcribed))

    load_error = None
    if pending:
        try:
            with opened(backend):
                for segment, keep_existing in pending:
                    outcome = _run_or_fail(
                        paths,
                        manifest,
                        segment,
                        backend,
                        language,
                        keywords,
                        keep_existing,
                    )
                    outcomes[segment.index] = outcome
                    report(outcome)
        except BackendError as error:  # from load or close; segments catch their own
            load_error = error
    return SessionRun(
        identity=found,
        outcomes=tuple(
            outcomes.get(segment.index, SegmentOutcome(segment.index, "open"))
            for segment in segments
        ),
        load_error=load_error if len(outcomes) < len(segments) else None,
    )


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
    _check_audio(paths, index)
    stored = _stored(paths, index, force)
    keep_existing = stored is not None and stored.status == "transcribed"
    if keep_existing and not force:
        raise TranscriptionError(
            f"{paths.reference(index)}: segment {index} is already transcribed; "
            "use --force to transcribe it again"
        )

    with opened(backend):
        reference = _run(
            paths, manifest, segment, backend, language, keywords, keep_existing
        )
    outcome = _outcome(reference, "transcribed")
    return SegmentResult(
        index=index,
        backend_id=reference.asr.backend_id,
        model=reference.asr.model,
        model_version=reference.asr.model_version,
        language=outcome.language,
        passages=outcome.passages,
        words=outcome.words,
        words_with_confidence=outcome.words_with_confidence,
        elapsed_ms=reference.processing.elapsed_ms or 0,
    )


def _run(
    paths: SessionPaths,
    manifest: Manifest,
    segment: Segment,
    backend: Backend,
    language: str | None,
    keywords: Sequence[str],
    keep_existing: bool,
) -> ReferenceTranscript:
    """Transcribe `segment` with the loaded `backend` and write the result.

    A `BackendError` is recorded as a failed reference, unless `keep_existing`
    (a transcribed one exists), and raised again.
    """
    request = TranscriptionRequest(
        audio=paths.segment_wav(segment.index),
        language=language,
        keywords=tuple(keywords),
    )
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
    reference = from_backend_result(
        result, backend, manifest, segment, _elapsed_ms(started)
    )
    write_reference(paths, reference, result.raw)
    return reference


def _run_or_fail(
    paths: SessionPaths,
    manifest: Manifest,
    segment: Segment,
    backend: Backend,
    language: str | None,
    keywords: Sequence[str],
    keep_existing: bool,
) -> SegmentOutcome:
    try:
        reference = _run(
            paths, manifest, segment, backend, language, keywords, keep_existing
        )
    except BackendError as error:
        return SegmentOutcome(
            segment.index,
            "failed",
            error=type(error).__name__,
            retryable=error.retryable,
        )
    return _outcome(reference, "transcribed")


def _selected(manifest: Manifest, indices: Collection[int] | None) -> list[Segment]:
    if indices is None:
        return list(manifest.segments)
    for index in sorted(indices):
        _segment(manifest, index)  # raises for an unknown index
    return [segment for segment in manifest.segments if segment.index in indices]


def _check_audio(paths: SessionPaths, index: int) -> None:
    audio = paths.segment_wav(index)
    if not audio.is_file():
        raise TranscriptionError(
            f"{audio}: segment {index} audio not found; run transcript extract"
        )


def _stored(paths: SessionPaths, index: int, force: bool) -> ReferenceTranscript | None:
    """The stored result of segment `index`; an unreadable one only with `force`."""
    if not paths.reference(index).is_file():
        return None
    try:
        return load_reference(paths, index)
    except ReferenceError:
        if not force:
            raise
        return None  # an unreadable file holds no result worth keeping


def _reusable(
    reference: ReferenceTranscript, found: BackendIdentity, language: str | None
) -> bool:
    asr = reference.asr
    return found.matches(asr.info, asr.settings) and (
        language is None or asr.language == language
    )


def _outcome(reference: ReferenceTranscript, status: str) -> SegmentOutcome:
    words = reference.words
    return SegmentOutcome(
        index=reference.segment.index,
        status=status,
        passages=len(reference.passages),
        words=len(words),
        words_with_confidence=sum(word.confidence is not None for word in words),
        language=reference.asr.language,
        elapsed_ms=reference.processing.elapsed_ms if status == "transcribed" else None,
    )


def _ignore(outcome: SegmentOutcome) -> None:
    pass


def _segment(manifest: Manifest, index: int) -> Segment:
    for segment in manifest.segments:
        if segment.index == index:
            return segment
    raise TranscriptionError(
        f"segment {index} not in the manifest of {manifest.key}; "
        f"it has segments 1 to {len(manifest.segments)}"
    )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
