"""Transcribe manifest segments with a backend and store the reference transcripts.

The caller picks the backend (V0.1: `WhisperBackend.from_config`); this module only
knows the `transcript.asr` interface. Every check that needs no model runs before
the model is loaded, because loading takes minutes.

`transcribe_session` loads the backend once for all segments that need it and
reuses a stored result made with the same model, revision and settings.

A successful result is never replaced by a failed one: a failure is recorded as
`status: failed` only where no transcribed result exists. A retryable failure is
tried again up to `retries` times first (`transcript.retry`).

Error messages, logs and summaries name the session, segment, backend, files
and error classes, never transcript text or keywords.
"""

import logging
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
from transcript.retry import FailureLog, SegmentFailure, attempt
from transcript.session import SessionPaths

_logger = logging.getLogger(__name__)

OUTCOME_STATUSES = ("transcribed", "reused", "failed", "open")


class TranscriptionError(Exception):
    """A segment cannot be transcribed for a reason found before the backend runs."""


@dataclass(frozen=True)
class SegmentOutcome:
    """What a session run did with one segment: counts and error class, never text.

    `status` is one of `OUTCOME_STATUSES`: `transcribed` or `reused` (a stored
    result counts), `failed` (see `failure`) or `open` (not reached, the
    backend did not load).
    """

    index: int
    status: str
    passages: int = 0
    words: int = 0
    words_with_confidence: int = 0
    language: str | None = None
    elapsed_ms: int | None = None  # of the successful backend call
    failure: SegmentFailure | None = None  # set exactly when `failed`
    attempts: int = 0  # backend calls made in this run


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
    retries: int = 0,
    sleep: Callable[[float], None] = time.sleep,
) -> SessionRun:
    """Transcribe the selected segments of `manifest`, all of them by default.

    A stored transcribed result is reused, unless `force`, when backend, model,
    revision and settings match the backend's identity and, with `language` set,
    the detected language matches it. Everything else is transcribed in manifest
    order with the backend loaded once. A retryable `BackendError` from one
    segment is tried again up to `retries` times, each failed attempt logged;
    the last error is recorded as `failed` and the run goes on. One from
    loading leaves the remaining segments `open`. `progress` gets each outcome
    as it is known.

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
                    outcome = _run(
                        paths,
                        manifest,
                        segment,
                        backend,
                        language,
                        keywords,
                        keep_existing,
                        retries,
                        sleep,
                    )
                    outcomes[segment.index] = outcome
                    report(outcome)
        except BackendError as error:  # from load or close; segments catch their own
            load_error = error
    unreached = [segment for segment in segments if segment.index not in outcomes]
    for segment in unreached:
        outcomes[segment.index] = SegmentOutcome(segment.index, "open")
        report(outcomes[segment.index])
    return SessionRun(
        identity=found,
        outcomes=tuple(outcomes[segment.index] for segment in segments),
        load_error=load_error if unreached else None,
    )


def _run(
    paths: SessionPaths,
    manifest: Manifest,
    segment: Segment,
    backend: Backend,
    language: str | None,
    keywords: Sequence[str],
    keep_existing: bool,
    retries: int,
    sleep: Callable[[float], None],
) -> SegmentOutcome:
    """Transcribe `segment` with the loaded `backend` and write the result.

    The last `BackendError` after the retries becomes a `failed` outcome and a
    failed reference, unless `keep_existing`: a transcribed result is never
    replaced by a failure.
    """
    request = TranscriptionRequest(
        audio=paths.segment_wav(segment.index),
        language=language,
        keywords=tuple(keywords),
    )
    log = FailureLog(
        _logger,
        f"{manifest.key} segment {segment.index}: {backend.info.backend_id}",
        retries,
    )
    done = attempt(lambda: transcribe(backend, request), retries, log, sleep)
    if done.error is not None:
        if not keep_existing:
            failure = failed_reference(
                done.error, backend, manifest, segment, done.elapsed_ms
            )
            write_reference(paths, failure, None)
        return SegmentOutcome(
            segment.index,
            "failed",
            failure=SegmentFailure.of(done),
            attempts=done.attempts,
        )
    assert done.result is not None
    reference = from_backend_result(
        done.result, backend, manifest, segment, done.elapsed_ms
    )
    write_reference(paths, reference, done.result.raw)
    return _outcome(reference, "transcribed", done.attempts)


def _selected(manifest: Manifest, indices: Collection[int] | None) -> list[Segment]:
    if indices is None:
        return list(manifest.segments)
    unknown = sorted(set(indices) - {segment.index for segment in manifest.segments})
    if unknown:
        raise TranscriptionError(
            f"segment {unknown[0]} not in the manifest of {manifest.key}; "
            f"it has segments 1 to {len(manifest.segments)}"
        )
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


def _outcome(
    reference: ReferenceTranscript, status: str, attempts: int = 0
) -> SegmentOutcome:
    words = reference.words
    return SegmentOutcome(
        index=reference.segment.index,
        status=status,
        passages=len(reference.passages),
        words=len(words),
        words_with_confidence=sum(word.confidence is not None for word in words),
        language=reference.asr.language,
        elapsed_ms=reference.processing.elapsed_ms if status == "transcribed" else None,
        attempts=attempts,
    )


def _ignore(outcome: SegmentOutcome) -> None:
    pass
