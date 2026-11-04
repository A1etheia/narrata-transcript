import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from test_reference import KEY, MANIFEST, SECRET, SEGMENT

from transcript.asr import (
    BackendResult,
    BackendUnavailableError,
    Capabilities,
    ResourceError,
    ResultSegment,
    ResultWord,
)
from transcript.asr.fake import FAKE_INFO, FakeBackend
from transcript.audio import sha256_file
from transcript.reference import ReferenceError, load_reference
from transcript.session import SessionPaths
from transcript.transcription import TranscriptionError, transcribe_segment

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


class TranscribeSegmentTest(unittest.TestCase):
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
        backend: FakeBackend,
        index: int = 1,
        keywords: tuple[str, ...] = (),
        force: bool = False,
    ):
        return transcribe_segment(
            self.paths, MANIFEST_1, index, backend, "de", keywords, force=force
        )

    def test_writes_normal_and_raw_form_with_provenance(self) -> None:
        summary = self.run_segment(FakeBackend(RESULT))

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
        self.assertEqual(reference.processing.elapsed_ms, summary.elapsed_ms)
        passage = reference.passages[0]
        self.assertEqual(passage.text, f" Zum {SECRET}.")
        self.assertEqual([w.confidence for w in passage.words], [0.9, None])
        self.assertEqual(passage.signals, {"avg_logprob": -0.2})
        raw = json.loads(self.paths.reference_raw(1).read_text(encoding="utf-8"))
        self.assertEqual(raw, {"backend_id": "fake", "raw": RESULT.raw})

    def test_summary_holds_counts_but_no_text(self) -> None:
        summary = self.run_segment(FakeBackend(RESULT))

        self.assertEqual(
            (summary.index, summary.passages, summary.words),
            (1, 1, 2),
        )
        self.assertEqual(summary.words_with_confidence, 1)
        self.assertEqual((summary.language, summary.model_version), ("de", "rev1"))
        self.assertNotIn(SECRET, repr(summary))

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

        self.run_segment(FakeBackend(RESULT))

        self.assertEqual((sha256_file(self.wav), sha256_file(self.original)), before)

    def test_unknown_segment_fails_before_loading(self) -> None:
        backend = FakeBackend()

        with self.assertRaisesRegex(
            TranscriptionError, "segment 3 not in the manifest"
        ):
            self.run_segment(backend, index=3)
        self.assertEqual(backend.load_calls, 0)

    def test_missing_audio_fails_before_loading(self) -> None:
        self.wav.unlink()
        backend = FakeBackend()

        with self.assertRaisesRegex(TranscriptionError, "audio not found"):
            self.run_segment(backend)
        self.assertEqual(backend.load_calls, 0)
        self.assertFalse(self.paths.reference(1).exists())

    def test_existing_result_needs_force(self) -> None:
        self.run_segment(FakeBackend(RESULT))
        backend = FakeBackend()

        with self.assertRaisesRegex(TranscriptionError, "--force"):
            self.run_segment(backend)
        self.assertEqual(backend.load_calls, 0)

        self.run_segment(backend, force=True)
        self.assertEqual(load_reference(self.paths, 1).text, "Fake-Transkript.")

    def test_transcribe_failure_is_recorded_as_failed(self) -> None:
        backend = FakeBackend(error=ResourceError("fake: out of memory"))

        with self.assertRaises(ResourceError):
            self.run_segment(backend)

        reference = load_reference(self.paths, 1)
        self.assertEqual(reference.status, "failed")
        self.assertEqual(
            (reference.error.category, reference.error.retryable),
            ("ResourceError", True),
        )
        self.assertEqual(reference.passages, ())
        self.assertEqual((backend.load_calls, backend.close_calls), (1, 1))

    def test_failed_result_is_retried_without_force(self) -> None:
        with self.assertRaises(ResourceError):
            self.run_segment(FakeBackend(error=ResourceError("fake: out of memory")))

        self.run_segment(FakeBackend(RESULT))

        self.assertEqual(load_reference(self.paths, 1).status, "transcribed")

    def test_load_failure_writes_nothing(self) -> None:
        backend = FailingLoad()

        with self.assertRaises(BackendUnavailableError):
            self.run_segment(backend)

        self.assertFalse(self.paths.asr_dir.exists())
        self.assertEqual(backend.requests, [])

    def test_failure_with_force_keeps_the_transcribed_result(self) -> None:
        self.run_segment(FakeBackend(RESULT))
        files = {
            path: path.read_bytes()
            for path in (self.paths.reference(1), self.paths.reference_raw(1))
        }

        with self.assertRaises(ResourceError):
            self.run_segment(
                FakeBackend(error=ResourceError("fake: out of memory")), force=True
            )

        for path, content in files.items():
            self.assertEqual(path.read_bytes(), content)

    def test_unreadable_existing_result_needs_force(self) -> None:
        self.paths.asr_dir.mkdir()
        self.paths.reference(1).write_text("{}", encoding="utf-8")

        with self.assertRaises(ReferenceError):
            self.run_segment(FakeBackend())

        self.run_segment(FakeBackend(RESULT), force=True)
        self.assertEqual(load_reference(self.paths, 1).status, "transcribed")


if __name__ == "__main__":
    unittest.main()
