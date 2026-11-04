import ast
import dataclasses
import tempfile
import unittest
from pathlib import Path

from transcript.asr import (
    AudioInputError,
    BackendResult,
    BackendRuntimeError,
    BackendUnavailableError,
    Capabilities,
    ResourceError,
    ResultSegment,
    ResultWord,
    TranscriptionRequest,
    opened,
    transcribe,
)
from transcript.asr.fake import FAKE_INFO, FakeBackend

SRC = Path(__file__).resolve().parents[1] / "src" / "transcript"
MODEL_LIBRARIES = {
    "faster_whisper",
    "ctranslate2",
    "nemo",
    "numpy",
    "pyannote",
    "torch",
    "transformers",
}
# Per package, the modules that are not adapters and so never import a model library.
GENERIC_MODULES = {
    "asr": {"__init__.py", "backend.py", "fake.py"},
    "diarization": {"__init__.py"},
}


def result_with(*words: ResultWord, start: float = 0.0) -> BackendResult:
    segment = ResultSegment(text="Zum Drachenhort.", start=start, end=2.0, words=words)
    return BackendResult(info=FAKE_INFO, segments=(segment,))


class FailingLoad(FakeBackend):
    def load(self) -> None:
        raise ImportError("no ctranslate2")


class TranscribeTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.audio = Path(directory.name) / "segment-01.wav"
        self.audio.write_bytes(b"")

    def request(self, *keywords: str) -> TranscriptionRequest:
        return TranscriptionRequest(audio=self.audio, language="de", keywords=keywords)

    def run_fake(self, backend: FakeBackend, *keywords: str) -> BackendResult:
        with opened(backend):
            return transcribe(backend, self.request(*keywords))

    def test_fake_answers_without_a_model_and_is_closed(self) -> None:
        expected = result_with(ResultWord("Drachenhort", 0.4, 1.1, confidence=0.8))
        backend = FakeBackend(expected)

        result = self.run_fake(backend)

        self.assertEqual(result, expected)
        self.assertEqual(backend.requests, [self.request()])
        self.assertEqual((backend.load_calls, backend.close_calls), (1, 1))

    def test_answer_may_depend_on_the_request(self) -> None:
        backend = FakeBackend(lambda request: result_with(start=0.5))

        self.assertEqual(self.run_fake(backend).segments[0].start, 0.5)

    def test_keywords_without_biasing_are_ignored_not_an_error(self) -> None:
        result = self.run_fake(FakeBackend(), "Beispielfigur")

        self.assertEqual(result.keywords_used, ())

    def test_keywords_with_biasing_are_reported(self) -> None:
        backend = FakeBackend(capabilities=Capabilities(keyword_biasing=True))

        result = self.run_fake(backend, "Beispielfigur")

        self.assertEqual(result.keywords_used, ("Beispielfigur",))

    def test_foreign_exception_loses_its_message(self) -> None:
        backend = FakeBackend(error=ValueError("geheimer Text"))

        with self.assertRaises(BackendRuntimeError) as caught:
            self.run_fake(backend)

        self.assertEqual(str(caught.exception), "fake: ValueError")
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(backend.close_calls, 1)

    def test_foreign_exceptions_map_to_categories(self) -> None:
        for error, category in (
            (MemoryError(), ResourceError),
            (ModuleNotFoundError("faster_whisper"), BackendUnavailableError),
        ):
            name = type(error).__name__
            with self.subTest(error=name), self.assertRaises(category):
                self.run_fake(FakeBackend(error=error))

    def test_backend_error_passes_unchanged(self) -> None:
        error = ResourceError("fake: CUDA out of memory")

        with self.assertRaises(ResourceError) as caught:
            self.run_fake(FakeBackend(error=error))

        self.assertIs(caught.exception, error)

    def test_failing_load_is_filtered(self) -> None:
        backend = FailingLoad()

        with self.assertRaises(BackendUnavailableError):
            self.run_fake(backend)
        self.assertEqual(backend.requests, [])

    def test_inconsistent_results_are_rejected(self) -> None:
        cases = {
            "negative time": result_with(start=-0.1),
            "end before start": result_with(ResultWord("Hort", 1.5, 1.0)),
            "confidence above 1": result_with(ResultWord("Hort", 0.0, 1.0, 1.2)),
            "infinite time": result_with(ResultWord("Hort", 0.0, float("inf"))),
        }
        for name, result in cases.items():
            with self.subTest(name), self.assertRaises(BackendRuntimeError) as caught:
                self.run_fake(FakeBackend(result))
            self.assertNotIn("Hort", str(caught.exception))

    def test_keywords_used_must_match_capability_and_request(self) -> None:
        trimmed = dataclasses.replace(result_with(), keywords_used=("Beispielfigur",))
        biasing = Capabilities(keyword_biasing=True)
        cases = (
            (FakeBackend(trimmed), ("Beispielfigur",)),
            (FakeBackend(trimmed, capabilities=biasing), ("Drachenhort",)),
        )
        for backend, keywords in cases:
            with self.subTest(), self.assertRaises(BackendRuntimeError) as caught:
                self.run_fake(backend, *keywords)
            self.assertNotIn("Beispielfigur", str(caught.exception))

    def test_missing_audio_is_an_input_error(self) -> None:
        self.audio.unlink()

        with self.assertRaises(AudioInputError) as caught:
            self.run_fake(FakeBackend())
        self.assertFalse(caught.exception.retryable)

    def test_transcribe_before_load_fails(self) -> None:
        with self.assertRaises(BackendRuntimeError):
            transcribe(FakeBackend(), self.request())


class ImportBoundaryTest(unittest.TestCase):
    """Generic code never imports a model library; adapters only inside functions."""

    def test_model_libraries_stay_out_of_generic_code(self) -> None:
        for path in sorted(SRC.rglob("*.py")):
            generic = GENERIC_MODULES.get(path.parent.name)
            adapter = generic is not None and path.name not in generic
            tree = ast.parse(path.read_text(encoding="utf-8"))
            nodes = _module_level(tree) if adapter else ast.walk(tree)
            with self.subTest(module=str(path.relative_to(SRC))):
                self.assertEqual(_model_imports(nodes), set())


def _module_level(tree: ast.Module):
    """Every node outside function bodies, where an adapter's import would run early."""
    pending = list(tree.body)
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pending.extend(ast.iter_child_nodes(node))


def _model_imports(nodes) -> set[str]:
    found = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module]
        else:
            continue
        found |= {name.split(".")[0] for name in names} & MODEL_LIBRARIES
    return found
