import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from test_reference import KEY, MANIFEST, SECRET, SEGMENT

from transcript.asr import (
    AudioInputError,
    BackendError,
    BackendResult,
    BackendUnavailableError,
    Capabilities,
    ResourceError,
    ResultSegment,
    ResultWord,
    TranscriptionRequest,
)
from transcript.asr.fake import FAKE_INFO, FakeBackend
from transcript.audio import sha256_file
from transcript.reference import ReferenceError, load_reference
from transcript.retry import SegmentFailure
from transcript.session import SessionPaths
from transcript.transcription import (
    SegmentOutcome,
    TranscriptionError,
    transcribe_session,
)

SEGMENT_1 = dataclasses.replace(SEGMENT, index=1, file="segment-01.wav")
MANIFEST_1 = dataclasses.replace(MANIFEST, segments=(SEGMENT_1,))
RESULT = BackendResult(
    info=dataclasses.replace(FAKE_INFO, model_version="rev1"),
    segments=(
        ResultSegment(
            text=f" Zum {SECRET}.",
            start=0.0,
            end=1.5,
            words=(
                ResultWord("Zum", 0.0, 0.4, confidence=0.9),
                ResultWord(SECRET, 0.4, 1.5),
            ),
            signals={"avg_logprob": -0.2},
        ),
    ),
    language="de",
    language_probability=0.98,
    settings={"beam_size": 5},
    raw={"segments": [{"text": f" Zum {SECRET}."}]},
)


class FailingLoad(FakeBackend):
    def load(self) -> None:
        super().load()
        raise BackendUnavailableError("fake: model not in the local cache")


class SegmentWritingTest(unittest.TestCase):
    """What one transcribed segment leaves on disk and in its outcome."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(KEY, Path(directory.name))
        self.paths.audio_dir.mkdir(parents=True)
        self.wav = self.paths.segment_wav(1)
        self.wav.write_bytes(b"RIFF fake audio")
        self.paths.input_dir.mkdir(parents=True)
        self.original = self.paths.input_dir / SEGMENT_1.source.file
        self.original.write_bytes(b"original recording")

    def run_segment(
        self,
        backend: FakeBackend | None = None,
        keywords: tuple[str, ...] = (),
        force: bool = False,
    ) -> SegmentOutcome:
        backend = backend or FakeBackend(
            RESULT, info=RESULT.info, settings=RESULT.settings
        )
        run = transcribe_session(
            self.paths, MANIFEST_1, backend, "de", keywords, force=force
        )
        return run.outcomes[0]

    def test_writes_normal_and_raw_form_with_provenance(self) -> None:
        outcome = self.run_segment()

        reference = load_reference(self.paths, 1)
        self.assertEqual(reference.status, "transcribed")
        self.assertEqual(
            (
                reference.asr.backend_id,
                reference.asr.model,
                reference.asr.model_version,
            ),
            ("fake", "fake", "rev1"),
        )
        self.assertEqual(reference.asr.settings, {"beam_size": 5})
        self.assertEqual(reference.processing.elapsed_ms, outcome.elapsed_ms)
        passage = reference.passages[0]
        self.assertEqual(passage.text, f" Zum {SECRET}.")
        self.assertEqual([w.confidence for w in passage.words], [0.9, None])
        self.assertEqual(passage.signals, {"avg_logprob": -0.2})
        raw = json.loads(self.paths.reference_raw(1).read_text(encoding="utf-8"))
        self.assertEqual(raw, {"backend_id": "fake", "raw": RESULT.raw})

    def test_outcome_holds_counts_but_no_text(self) -> None:
        outcome = self.run_segment()

        self.assertEqual(
            (outcome.index, outcome.status, outcome.passages, outcome.words),
            (1, "transcribed", 1, 2),
        )
        self.assertEqual(outcome.words_with_confidence, 1)
        self.assertEqual(outcome.language, "de")
        self.assertNotIn(SECRET, repr(outcome))

    def test_language_and_keywords_reach_the_backend(self) -> None:
        backend = FakeBackend(capabilities=Capabilities(keyword_biasing=True))

        self.run_segment(backend, keywords=("Beispielfigur", "Beispielort"))

        request = backend.requests[0]
        self.assertEqual(request.audio, self.wav)
        self.assertEqual(request.language, "de")
        self.assertEqual(request.keywords, ("Beispielfigur", "Beispielort"))
        self.assertEqual(
            load_reference(self.paths, 1).asr.keywords_used,
            ("Beispielfigur", "Beispielort"),
        )

    def test_audio_is_not_changed(self) -> None:
        before = (sha256_file(self.wav), sha256_file(self.original))

        self.run_segment()

        self.assertEqual((sha256_file(self.wav), sha256_file(self.original)), before)

    def test_failure_is_recorded_with_its_class_only(self) -> None:
        backend = FakeBackend(error=ResourceError("fake: out of memory"))

        outcome = self.run_segment(backend)

        self.assertEqual(outcome.status, "failed")
        reference = load_reference(self.paths, 1)
        self.assertEqual(reference.status, "failed")
        self.assertEqual(
            (reference.error.category, reference.error.retryable),
            ("ResourceError", True),
        )
        self.assertEqual(reference.passages, ())
        self.assertEqual((backend.load_calls, backend.close_calls), (1, 1))

    def test_failure_with_force_keeps_the_transcribed_result(self) -> None:
        self.run_segment()
        files = {
            path: path.read_bytes()
            for path in (self.paths.reference(1), self.paths.reference_raw(1))
        }

        self.run_segment(
            FakeBackend(error=ResourceError("fake: out of memory")), force=True
        )

        for path, content in files.items():
            self.assertEqual(path.read_bytes(), content)

    def test_unreadable_result_is_replaced_only_with_force(self) -> None:
        self.paths.asr_dir.mkdir()
        self.paths.reference(1).write_text("{}", encoding="utf-8")

        with self.assertRaises(ReferenceError):
            self.run_segment()

        self.run_segment(force=True)
        self.assertEqual(load_reference(self.paths, 1).status, "transcribed")


SEGMENTS = tuple(
    dataclasses.replace(SEGMENT, index=index, file=f"segment-0{index}.wav")
    for index in (1, 2, 3)
)
MANIFEST_3 = dataclasses.replace(MANIFEST, segments=SEGMENTS)
SETTINGS = {"beam_size": 5}


def session_backend(
    revision: str = "rev1",
    settings: dict[str, Any] = SETTINGS,
    fail_on: int | None = None,
    language: str = "de",
    errors: dict[int, list[BackendError]] | None = None,
    biasing: bool = False,
    cut: int | None = None,
) -> FakeBackend:
    """A backend whose identity matches its results.

    `fail_on` segment always raises; segment `n` raises `errors[n]` in turn,
    then answers. Each raised error carries `SECRET` in its `__cause__`. With
    `biasing` it uses the first `cut` keywords, all of them by default.
    """
    info = dataclasses.replace(FAKE_INFO, model_version=revision)
    pending = {index: list(queue) for index, queue in (errors or {}).items()}

    def answer(request: TranscriptionRequest) -> BackendResult:
        index = int(request.audio.stem.removeprefix("segment-"))
        queue = pending.get(index)
        if index == fail_on or queue:
            error = queue.pop(0) if queue else ResourceError("fake: out of memory")
            raise error from RuntimeError(SECRET)
        return BackendResult(
            info=info,
            segments=(ResultSegment(text=f" Zum {SECRET}.", start=0.0, end=1.0),),
            language=language,
            settings=settings,
            keywords_used=request.keywords[:cut] if biasing else (),
        )

    capabilities = Capabilities(segment_timestamps=True, keyword_biasing=biasing)
    return FakeBackend(answer, info=info, settings=settings, capabilities=capabilities)


class FailingIdentity(FakeBackend):
    def identity(self) -> Any:
        raise BackendUnavailableError("fake: model not in the local cache")


class TranscribeSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(KEY, Path(directory.name))
        self.paths.audio_dir.mkdir(parents=True)
        for segment in SEGMENTS:
            self.paths.segment_wav(segment.index).write_bytes(b"RIFF fake audio")
        self.sleeps: list[float] = []

    def run_session(self, backend: FakeBackend, **options: Any):
        options.setdefault("sleep", self.sleeps.append)
        return transcribe_session(self.paths, MANIFEST_3, backend, "de", **options)

    def statuses(self, run) -> list[str]:
        return [outcome.status for outcome in run.outcomes]

    def test_all_segments_in_manifest_order_with_one_load(self) -> None:
        backend = session_backend()

        run = self.run_session(backend)

        self.assertEqual(self.statuses(run), ["transcribed"] * 3)
        self.assertTrue(run.complete)
        self.assertEqual((backend.load_calls, backend.close_calls), (1, 1))
        self.assertEqual(
            [request.audio.name for request in backend.requests],
            ["segment-01.wav", "segment-02.wav", "segment-03.wav"],
        )
        for segment in SEGMENTS:
            self.assertEqual(
                load_reference(self.paths, segment.index).status, "transcribed"
            )
        self.assertEqual(run.identity.info.model_version, "rev1")

    def test_rerun_reuses_matching_results_without_loading(self) -> None:
        self.run_session(session_backend())
        backend = session_backend()

        run = self.run_session(backend)

        self.assertEqual(self.statuses(run), ["reused"] * 3)
        self.assertEqual(backend.load_calls, 0)
        self.assertEqual(run.outcomes[0].passages, 1)
        self.assertIsNone(run.outcomes[0].elapsed_ms)

    def test_other_revision_settings_or_language_transcribe_again(self) -> None:
        for name, backend, language in (
            ("revision", session_backend(revision="rev2"), "de"),
            ("settings", session_backend(settings={"beam_size": 1}), "de"),
            ("language", session_backend(), "en"),
        ):
            with self.subTest(changed=name):
                self.run_session(session_backend())

                run = transcribe_session(self.paths, MANIFEST_3, backend, language)

                self.assertEqual(self.statuses(run), ["transcribed"] * 3)
                self.assertEqual(backend.load_calls, 1)

    def test_same_snapshot_reuses_and_another_one_transcribes_again(self) -> None:
        self.run_session(session_backend(), knowledge_snapshot_id="a" * 64)

        same = self.run_session(session_backend(), knowledge_snapshot_id="a" * 64)
        other = self.run_session(session_backend(), knowledge_snapshot_id="b" * 64)

        self.assertEqual(self.statuses(same), ["reused"] * 3)
        self.assertEqual(self.statuses(other), ["transcribed"] * 3)
        self.assertEqual(
            load_reference(self.paths, 1).asr.knowledge_snapshot_id, "b" * 64
        )

    def test_same_keywords_reuse_and_other_ones_transcribe_again(self) -> None:
        keywords = ("Beispielfigur", "Beispielort")
        self.run_session(session_backend(biasing=True), keywords=keywords)

        same = self.run_session(session_backend(biasing=True), keywords=keywords)
        other = self.run_session(
            session_backend(biasing=True), keywords=("Beispielfigur", "Nebelau")
        )

        self.assertEqual(self.statuses(same), ["reused"] * 3)
        self.assertEqual(self.statuses(other), ["transcribed"] * 3)

    def test_a_result_without_hints_transcribes_again_once_there_are_some(
        self,
    ) -> None:
        self.run_session(session_backend(biasing=True), knowledge_snapshot_id="a" * 64)

        run = self.run_session(
            session_backend(biasing=True),
            keywords=("Beispielfigur",),
            knowledge_snapshot_id="a" * 64,
        )

        self.assertEqual(self.statuses(run), ["transcribed"] * 3)
        self.assertEqual(
            load_reference(self.paths, 1).asr.keywords_used, ("Beispielfigur",)
        )

    def test_keywords_the_backend_cut_still_reuse(self) -> None:
        keywords = ("Beispielfigur", "Beispielort", "Nebelau")
        self.run_session(session_backend(biasing=True, cut=2), keywords=keywords)

        run = self.run_session(session_backend(biasing=True, cut=2), keywords=keywords)

        self.assertEqual(self.statuses(run), ["reused"] * 3)

    def test_a_backend_without_biasing_reuses_despite_keywords(self) -> None:
        self.run_session(session_backend())

        run = self.run_session(session_backend(), keywords=("Beispielfigur",))

        self.assertEqual(self.statuses(run), ["reused"] * 3)

    def test_a_first_snapshot_transcribes_again(self) -> None:
        self.run_session(session_backend())

        run = self.run_session(session_backend(), knowledge_snapshot_id="a" * 64)

        self.assertEqual(self.statuses(run), ["transcribed"] * 3)

    def test_a_failed_segment_records_the_snapshot_id(self) -> None:
        self.run_session(session_backend(fail_on=2), knowledge_snapshot_id="a" * 64)

        reference = load_reference(self.paths, 2)
        self.assertEqual(reference.status, "failed")
        self.assertEqual(reference.asr.knowledge_snapshot_id, "a" * 64)

    def test_no_configured_language_accepts_any_detected_one(self) -> None:
        self.run_session(session_backend(language="en"))

        run = transcribe_session(self.paths, MANIFEST_3, session_backend(), None)

        self.assertEqual(self.statuses(run), ["reused"] * 3)

    def test_force_transcribes_matching_results_again(self) -> None:
        self.run_session(session_backend())
        backend = session_backend()

        run = self.run_session(backend, force=True)

        self.assertEqual(self.statuses(run), ["transcribed"] * 3)
        self.assertEqual(len(backend.requests), 3)

    def test_failure_in_one_segment_does_not_stop_the_run(self) -> None:
        run = self.run_session(session_backend(fail_on=2))

        self.assertEqual(self.statuses(run), ["transcribed", "failed", "transcribed"])
        self.assertFalse(run.complete)
        failed = run.outcomes[1]
        self.assertEqual(
            (failed.failure.error, failed.failure.retryable), ("ResourceError", True)
        )
        self.assertEqual(load_reference(self.paths, 2).status, "failed")

    def test_failed_segment_is_retried_and_finished_ones_reused(self) -> None:
        self.run_session(session_backend(fail_on=2))
        backend = session_backend()

        run = self.run_session(backend)

        self.assertEqual(self.statuses(run), ["reused", "transcribed", "reused"])
        self.assertEqual([r.audio.name for r in backend.requests], ["segment-02.wav"])

    def test_failure_after_a_mismatch_keeps_the_transcribed_result(self) -> None:
        self.run_session(session_backend())
        before = self.paths.reference(2).read_bytes()

        run = self.run_session(session_backend(revision="rev2", fail_on=2))

        self.assertEqual(run.outcomes[1].status, "failed")
        self.assertEqual(self.paths.reference(2).read_bytes(), before)

    def test_load_failure_leaves_every_segment_open(self) -> None:
        backend = FailingLoad()
        seen: list[SegmentOutcome] = []

        run = self.run_session(backend, progress=seen.append)

        self.assertEqual(self.statuses(run), ["open"] * 3)
        self.assertEqual(list(run.outcomes), seen)
        self.assertIsInstance(run.load_error, BackendUnavailableError)
        self.assertFalse(backend.loaded)  # closed after the failed load
        self.assertFalse(self.paths.asr_dir.exists())

    def test_problems_found_before_loading(self) -> None:
        def unavailable() -> FakeBackend:
            backend = FailingIdentity()
            with self.assertRaises(BackendUnavailableError):
                self.run_session(backend)
            return backend

        def unknown_segment() -> FakeBackend:
            backend = session_backend()
            with self.assertRaisesRegex(TranscriptionError, "segment 4 not in"):
                self.run_session(backend, indices={4})
            return backend

        def missing_audio() -> FakeBackend:
            self.paths.segment_wav(3).unlink()
            backend = session_backend()
            with self.assertRaisesRegex(TranscriptionError, "segment 3 audio"):
                self.run_session(backend)
            return backend

        def unreadable_result() -> FakeBackend:
            self.paths.asr_dir.mkdir(exist_ok=True)
            self.paths.reference(1).write_text("{}", encoding="utf-8")
            backend = session_backend()
            with self.assertRaises(ReferenceError):
                self.run_session(backend)
            return backend

        for case in (unavailable, unknown_segment, unreadable_result, missing_audio):
            with self.subTest(case=case.__name__):
                self.assertEqual(case().load_calls, 0)

    def test_indices_select_segments(self) -> None:
        backend = session_backend()

        run = self.run_session(backend, indices={2})

        self.assertEqual([o.index for o in run.outcomes], [2])
        self.assertFalse(self.paths.reference(1).exists())

    def test_progress_gets_every_outcome_without_text(self) -> None:
        self.run_session(session_backend(), indices={1})
        seen: list[SegmentOutcome] = []

        run = self.run_session(session_backend(fail_on=3), progress=seen.append)

        self.assertEqual(
            [(o.index, o.status) for o in seen],
            [(1, "reused"), (2, "transcribed"), (3, "failed")],
        )
        self.assertNotIn(SECRET, repr(run))

    def test_retryable_failure_is_tried_again_with_the_loaded_backend(self) -> None:
        backend = session_backend(errors={2: [ResourceError("fake: out of memory")]})

        with self.assertLogs("transcript.transcription", "WARNING") as logs:
            run = self.run_session(backend, retries=2)

        self.assertEqual(self.statuses(run), ["transcribed"] * 3)
        self.assertEqual([o.attempts for o in run.outcomes], [1, 2, 1])
        self.assertEqual(backend.load_calls, 1)
        self.assertEqual(len(self.sleeps), 1)
        self.assertEqual(load_reference(self.paths, 2).status, "transcribed")
        self.assertEqual(len(logs.output), 1)
        self.assertIn(f"{KEY} segment 2: fake: attempt 1/3 failed", logs.output[0])
        self.assertIn("ResourceError: fake: out of memory; retrying", logs.output[0])

    def test_exhausted_retries_fail_the_segment_and_the_run_goes_on(self) -> None:
        with self.assertLogs("transcript.transcription", "WARNING") as logs:
            run = self.run_session(session_backend(fail_on=2), retries=2)

        self.assertEqual(self.statuses(run), ["transcribed", "failed", "transcribed"])
        failed = run.outcomes[1]
        self.assertEqual(
            failed.failure,
            SegmentFailure("ResourceError", "fake: out of memory", True, 3),
        )
        self.assertEqual(failed.attempts, 3)
        self.assertEqual(load_reference(self.paths, 2).status, "failed")
        self.assertEqual(len(logs.output), 3)
        self.assertIn("attempt 3/3 failed", logs.output[-1])
        self.assertIn("giving up", logs.output[-1])

    def test_error_that_cannot_succeed_is_not_tried_again(self) -> None:
        backend = session_backend(errors={1: [AudioInputError("fake: bad audio")]})

        with self.assertLogs("transcript.transcription", "WARNING") as logs:
            run = self.run_session(backend, retries=5)

        failed = run.outcomes[0]
        self.assertEqual((failed.status, failed.attempts), ("failed", 1))
        self.assertFalse(failed.failure.retryable)
        self.assertEqual(self.sleeps, [])
        self.assertIn("not retryable", logs.output[0])

    def test_logs_and_outcomes_never_show_the_original_error(self) -> None:
        with self.assertLogs("transcript.transcription", "WARNING") as logs:
            run = self.run_session(session_backend(fail_on=1), retries=1)

        self.assertNotIn(SECRET, "\n".join(logs.output))
        self.assertNotIn(SECRET, repr(run))
        self.assertNotIn(SECRET, self.paths.reference(1).read_text(encoding="utf-8"))

    def test_next_run_after_exhausted_retries_retries_only_the_failed(self) -> None:
        with self.assertLogs("transcript.transcription", "WARNING"):
            self.run_session(session_backend(fail_on=2), retries=1)
        backend = session_backend()

        run = self.run_session(backend, retries=1)

        self.assertEqual(self.statuses(run), ["reused", "transcribed", "reused"])
        self.assertEqual([r.audio.name for r in backend.requests], ["segment-02.wav"])


if __name__ == "__main__":
    unittest.main()
