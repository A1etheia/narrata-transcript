import dataclasses
import json
import tempfile
import types
import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

from test_reference import MANIFEST, SECRET, SEGMENT

from transcript.asr import (
    AudioInputError,
    BackendRuntimeError,
    BackendUnavailableError,
    ResourceError,
    TranscriptionRequest,
    opened,
    transcribe,
)
from transcript.asr.whisper import HOTWORD_TOKENS, WhisperBackend, fit_hotwords
from transcript.config import Config
from transcript.reference import from_backend_result, load_reference, write_reference
from transcript.session import SessionPaths

REVISION = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"


@dataclasses.dataclass
class Word:  # mirrors faster_whisper.transcribe.Word
    start: float
    end: float
    word: str
    probability: float


@dataclasses.dataclass
class Segment:  # mirrors faster_whisper.transcribe.Segment
    id: int
    seek: int
    start: float
    end: float
    text: str
    tokens: list[int]
    avg_logprob: float
    compression_ratio: float
    no_speech_prob: float
    words: list[Word] | None
    temperature: float | None


SEGMENTS = [
    Segment(
        id=1,
        seek=0,
        start=0.5,
        end=2.0,
        text=" Zum Drachenhort.",
        tokens=[1, 2, 3],
        avg_logprob=-0.2,
        compression_ratio=1.1,
        no_speech_prob=0.01,
        words=[
            Word(0.5, 0.8, " Zum", 0.97),
            Word(0.8, 2.0, " Drachenhort.", 0.61),
        ],
        temperature=0.0,
    )
]
INFO = types.SimpleNamespace(
    language="de", language_probability=1.0, duration=3.0, duration_after_vad=1.5
)


def model_dir(path: Path) -> Path:
    """An empty stand-in for a converted model directory."""
    path.mkdir(parents=True)
    for name in ("model.bin", "tokenizer.json"):
        (path / name).touch()
    return path


class Tokenizer:
    """One token per whitespace-separated word."""

    def encode(self, text: str, add_special_tokens: bool = True) -> Any:
        assert not add_special_tokens
        return types.SimpleNamespace(ids=text.split())


class FakeRuntime:
    """Stand-ins for the faster_whisper and ctranslate2 modules."""

    def __init__(self, cache: Path, cuda_devices: int = 1) -> None:
        self.snapshot = cache / "snapshots" / REVISION
        model_dir(self.snapshot)
        self.cuda_devices = cuda_devices
        self.download_error: Exception | None = None
        self.load_error: Exception | None = None
        self.transcribe_error: Exception | None = None
        self.downloads: list[tuple[str, bool]] = []
        self.models: list[Any] = []

        runtime = self

        class WhisperModel:
            def __init__(self, path: str, device: str, compute_type: str) -> None:
                if runtime.load_error is not None:
                    raise runtime.load_error
                self.args = (path, device, compute_type)
                self.hf_tokenizer = Tokenizer()
                self.calls: list[dict[str, Any]] = []
                runtime.models.append(self)

            def transcribe(self, audio: str, **options: Any) -> Any:
                self.calls.append({"audio": audio, **options})
                return runtime._segments(), INFO

        self.faster_whisper = types.ModuleType("faster_whisper")
        self.faster_whisper.__version__ = "1.2.1"
        self.faster_whisper.WhisperModel = WhisperModel
        self.faster_whisper.download_model = self._download
        self.ctranslate2 = types.ModuleType("ctranslate2")
        self.ctranslate2.get_cuda_device_count = lambda: self.cuda_devices

    def _download(self, name: str, local_files_only: bool = False) -> str:
        self.downloads.append((name, local_files_only))
        if self.download_error is not None:
            raise self.download_error
        return str(self.snapshot)

    def _segments(self) -> Iterator[Segment]:
        """Lazy like faster-whisper: errors surface while iterating."""
        if self.transcribe_error is not None:
            raise self.transcribe_error
        yield from SEGMENTS

    def installed(self) -> Any:
        return mock.patch.dict(
            "sys.modules",
            {"faster_whisper": self.faster_whisper, "ctranslate2": self.ctranslate2},
        )


class WhisperTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.runtime = FakeRuntime(self.root / "cache")
        patcher = self.runtime.installed()
        patcher.start()
        self.addCleanup(patcher.stop)
        self.audio = self.root / "segment-02.wav"
        self.audio.touch()

    def run_backend(self, backend: WhisperBackend, *keywords: str) -> Any:
        request = TranscriptionRequest(self.audio, language="de", keywords=keywords)
        with opened(backend):
            return transcribe(backend, request)


class LoadTest(WhisperTestCase):
    def test_capabilities_match_the_documented_mapping(self) -> None:
        capabilities = WhisperBackend().capabilities.to_dict()

        self.assertEqual(
            capabilities,
            {
                "word_timestamps": True,
                "segment_timestamps": True,
                "speaker_labels": False,
                "keyword_biasing": True,
                "word_confidence": True,
                "segment_signals": True,
                "devices": ["cpu", "cuda"],
                "max_audio_seconds": None,
            },
        )

    def test_auto_prefers_cuda_with_float16(self) -> None:
        backend = WhisperBackend()
        backend.load()

        model = self.runtime.models[0]
        self.assertEqual(model.args, (str(self.runtime.snapshot), "cuda", "float16"))
        self.assertEqual(self.runtime.downloads, [("large-v3-turbo", True)])

    def test_auto_falls_back_to_cpu_with_int8(self) -> None:
        self.runtime.cuda_devices = 0
        WhisperBackend().load()

        self.assertEqual(self.runtime.models[0].args[1:], ("cpu", "int8"))

    def test_configured_values_are_used(self) -> None:
        config = Config(
            language="de",
            root=self.root,
            asr_model="large-v3",
            asr_device="cpu",
            asr_compute_type="float32",
            asr_beam_size=2,
        )
        backend = WhisperBackend.from_config(config)
        self.run_backend(backend)

        model = self.runtime.models[0]
        self.assertEqual(model.args[1:], ("cpu", "float32"))
        self.assertEqual(model.calls[0]["beam_size"], 2)
        self.assertEqual(self.runtime.downloads, [("large-v3", True)])

    def test_info_names_model_revision_and_runtime_after_load(self) -> None:
        backend = WhisperBackend()
        self.assertIsNone(backend.info.model_version)

        backend.load()

        self.assertEqual(backend.info.backend_id, "faster-whisper")
        self.assertEqual(backend.info.model, "large-v3-turbo")
        self.assertEqual(backend.info.model_version, REVISION)
        self.assertEqual(backend.info.runtime_version, "1.2.1")

    def test_local_directory_loads_without_the_cache(self) -> None:
        directory = model_dir(self.root / "my-model")
        backend = WhisperBackend(str(directory))
        backend.load()

        self.assertEqual(self.runtime.downloads, [])
        self.assertEqual(self.runtime.models[0].args[0], str(directory))
        self.assertIsNone(backend.info.model_version)

    def test_missing_prerequisites_are_reported(self) -> None:
        def no_runtime() -> None:
            with mock.patch.dict("sys.modules", {"faster_whisper": None}):
                WhisperBackend().load()

        def not_cached() -> None:
            self.runtime.download_error = FileNotFoundError("cache miss")
            WhisperBackend().load()

        def no_tokenizer() -> None:
            (self.runtime.snapshot / "tokenizer.json").unlink()
            WhisperBackend().load()

        def no_gpu() -> None:
            self.runtime.cuda_devices = 0
            WhisperBackend(device="cuda").load()

        def no_cuda_library() -> None:
            self.runtime.load_error = RuntimeError(
                "Library libcublas.so.12 is not found or cannot be loaded"
            )
            WhisperBackend().load()

        for case, expected in (
            (no_runtime, "pip install -e '.[whisper]'"),
            (not_cached, "large-v3-turbo not in the local cache"),
            (no_tokenizer, "lacks model.bin or tokenizer.json"),
            (no_gpu, "no CUDA device"),
            (no_cuda_library, "LD_LIBRARY_PATH"),
        ):
            self.runtime = FakeRuntime(self.root / case.__name__)
            with (
                self.subTest(case=case.__name__),
                self.runtime.installed(),
                self.assertRaises(BackendUnavailableError) as caught,
            ):
                case()
            self.assertIn(expected, str(caught.exception))

    def test_out_of_memory_while_loading_is_a_resource_error(self) -> None:
        self.runtime.load_error = RuntimeError("CUDA failed with error out of memory")

        with self.assertRaises(ResourceError):
            WhisperBackend().load()


class IdentityTest(WhisperTestCase):
    def test_identity_matches_info_and_settings_after_load(self) -> None:
        for cuda_devices in (1, 0):
            self.runtime.cuda_devices = cuda_devices
            with self.subTest(cuda_devices=cuda_devices):
                backend = WhisperBackend(beam_size=3)
                before = backend.identity()
                result = self.run_backend(backend)

                self.assertEqual(before.info, backend.info)
                self.assertEqual(before.info.model_version, REVISION)
                self.assertEqual(dict(before.settings), result.settings)

    def test_identity_builds_no_model(self) -> None:
        identity = WhisperBackend(device="cpu").identity()

        self.assertEqual(self.runtime.models, [])
        self.assertEqual(identity.settings["device"], "cpu")
        self.assertEqual(identity.settings["compute_type"], "int8")
        self.assertEqual(identity.info.runtime_version, "1.2.1")

    def test_identity_reports_missing_prerequisites(self) -> None:
        def no_runtime() -> None:
            with mock.patch.dict("sys.modules", {"faster_whisper": None}):
                WhisperBackend().identity()

        def not_cached() -> None:
            self.runtime.download_error = FileNotFoundError("cache miss")
            WhisperBackend().identity()

        def no_gpu() -> None:
            self.runtime.cuda_devices = 0
            WhisperBackend(device="cuda").identity()

        for case in (no_runtime, not_cached, no_gpu):
            self.runtime = FakeRuntime(self.root / case.__name__)
            with (
                self.subTest(case=case.__name__),
                self.runtime.installed(),
                self.assertRaises(BackendUnavailableError),
            ):
                case()


class TranscribeTest(WhisperTestCase):
    def test_result_keeps_times_confidence_and_signals(self) -> None:
        result = self.run_backend(WhisperBackend())

        (segment,) = result.segments
        self.assertEqual(segment.text, "Zum Drachenhort.")
        self.assertEqual((segment.start, segment.end), (0.5, 2.0))
        self.assertEqual(
            [(w.text, w.start, w.end, w.confidence) for w in segment.words],
            [("Zum", 0.5, 0.8, 0.97), ("Drachenhort.", 0.8, 2.0, 0.61)],
        )
        self.assertEqual(
            segment.signals,
            {"avg_logprob": -0.2, "no_speech_prob": 0.01, "compression_ratio": 1.1},
        )
        self.assertIsNone(segment.speaker)
        self.assertEqual((result.language, result.language_probability), ("de", 1.0))

    def test_tool_62_settings_are_passed_and_recorded(self) -> None:
        result = self.run_backend(WhisperBackend())

        call = self.runtime.models[0].calls[0]
        self.assertEqual(call["audio"], str(self.audio))
        self.assertEqual(call["language"], "de")
        expected = {
            "beam_size": 5,
            "vad_filter": True,
            "word_timestamps": True,
            "condition_on_previous_text": False,
        }
        self.assertLessEqual(expected.items(), call.items())
        self.assertEqual(
            dict(result.settings),
            {"model": "large-v3-turbo", "device": "cuda", "compute_type": "float16"}
            | expected,
        )

    def test_raw_is_the_unchanged_answer(self) -> None:
        result = self.run_backend(WhisperBackend())

        self.assertEqual(
            result.raw["segments"], [dataclasses.asdict(s) for s in SEGMENTS]
        )
        self.assertEqual(result.raw["info"]["duration_after_vad"], 1.5)
        json.dumps(result.raw)

    def test_keywords_become_hotwords_and_are_reported_as_used(self) -> None:
        result = self.run_backend(WhisperBackend(), "Drachenhort", "Beispielfigur")

        self.assertEqual(
            self.runtime.models[0].calls[0]["hotwords"], "Drachenhort Beispielfigur"
        )
        self.assertEqual(result.keywords_used, ("Drachenhort", "Beispielfigur"))

    def test_no_keywords_means_no_hotwords(self) -> None:
        result = self.run_backend(WhisperBackend())

        self.assertIsNone(self.runtime.models[0].calls[0]["hotwords"])
        self.assertEqual(result.keywords_used, ())

    def test_runtime_failures_map_to_categories_without_their_message(self) -> None:
        decode_error = type(
            "InvalidDataError", (ValueError,), {"__module__": "av.error"}
        )
        for error, category in (
            (
                RuntimeError(f"CUDA failed with error out of memory {SECRET}"),
                ResourceError,
            ),
            (MemoryError(SECRET), ResourceError),
            (
                RuntimeError(f"Library libcudnn_ops_infer.so.8 not found {SECRET}"),
                BackendUnavailableError,
            ),
            (decode_error(SECRET), AudioInputError),
            (ValueError(SECRET), BackendRuntimeError),
        ):
            self.runtime.transcribe_error = error
            with (
                self.subTest(error=repr(error)),
                self.assertRaises(category) as caught,
            ):
                self.run_backend(WhisperBackend(), SECRET)
            self.assertNotIn(SECRET, str(caught.exception))
            self.assertIs(caught.exception.__cause__, error)

    def test_result_converts_into_the_reference_format(self) -> None:
        backend = WhisperBackend()
        result = self.run_backend(backend, SECRET)
        paths = SessionPaths(MANIFEST.key, self.root)

        reference = from_backend_result(result, backend, MANIFEST, SEGMENT, 900)
        write_reference(paths, reference, result.raw)
        loaded = load_reference(paths, SEGMENT.index)

        self.assertEqual(loaded, reference)
        self.assertEqual(loaded.asr.model_version, REVISION)
        self.assertEqual(loaded.asr.keywords_used, (SECRET,))
        self.assertEqual(loaded.passages[0].words[1].confidence, 0.61)
        raw = json.loads(paths.reference_raw(SEGMENT.index).read_text("utf-8"))
        self.assertEqual(raw["raw"]["segments"][0]["text"], " Zum Drachenhort.")


class LifecycleTest(WhisperTestCase):
    def test_close_releases_the_model(self) -> None:
        backend = WhisperBackend()
        self.run_backend(backend)

        with self.assertRaises(BackendRuntimeError):
            backend.transcribe(TranscriptionRequest(self.audio))

    def test_close_is_safe_without_load(self) -> None:
        WhisperBackend().close()

    def test_failed_load_still_closes(self) -> None:
        self.runtime.download_error = FileNotFoundError()

        with self.assertRaises(BackendUnavailableError):
            self.run_backend(WhisperBackend())


class FitHotwordsTest(unittest.TestCase):
    def count(self, text: str) -> int:
        return len(text.split())

    def test_keywords_up_to_the_token_limit_are_kept(self) -> None:
        keywords = [f"Begriff{n}" for n in range(HOTWORD_TOKENS + 5)]

        used = fit_hotwords(keywords, self.count)

        self.assertEqual(used, tuple(keywords[:HOTWORD_TOKENS]))

    def test_first_keyword_that_does_not_fit_ends_the_list(self) -> None:
        long_term = " ".join(["lang"] * HOTWORD_TOKENS)

        used = fit_hotwords(["Drachenhort", long_term, "Beispielfigur"], self.count)

        self.assertEqual(used, ("Drachenhort",))

    def test_blank_keywords_are_skipped(self) -> None:
        self.assertEqual(
            fit_hotwords(["", "  ", "Drachenhort"], self.count), ("Drachenhort",)
        )


if __name__ == "__main__":
    unittest.main()
