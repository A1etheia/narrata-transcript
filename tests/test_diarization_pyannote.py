import importlib
import os
import tempfile
import types
import unittest
import wave
from pathlib import Path
from typing import Any
from unittest import mock

import transcript
from transcript.asr import (
    AudioInputError,
    BackendInfo,
    BackendRuntimeError,
    BackendUnavailableError,
    ResourceError,
)
from transcript.config import Config
from transcript.diarization import Turn
from transcript.diarization import pyannote as adapter
from transcript.diarization.pyannote import PyannoteDiarizer

try:
    import numpy
except ImportError:
    numpy = None

REVISION = "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"
MODEL = "pyannote/speaker-diarization-community-1"
AUDIO = "cd" * 32


class Annotation:
    """Mirrors the part of pyannote.core.Annotation the adapter reads."""

    def __init__(self, *tracks: tuple[float, float, str]) -> None:
        self.tracks = tracks

    def itertracks(self, yield_label: bool = False) -> Any:
        assert yield_label
        for index, (start, end, label) in enumerate(self.tracks):
            yield types.SimpleNamespace(start=start, end=end), index, label


OUTPUT = types.SimpleNamespace(
    speaker_diarization=Annotation((0.5, 2.0, "SPEAKER_00"), (1.8, 3.25, "SPEAKER_01")),
    exclusive_speaker_diarization=Annotation(
        (0.5, 1.8, "SPEAKER_00"), (2.0, 3.25, "SPEAKER_01")
    ),
)


class FakeRuntime:
    """Stand-ins for torch, pyannote.audio and huggingface_hub."""

    def __init__(self, cache: Path) -> None:
        self.snapshot = cache / "snapshots" / REVISION
        self.snapshot.mkdir(parents=True)
        (self.snapshot / "config.yaml").touch()
        self.cuda_available = True
        self.download_error: Exception | None = None
        self.load_error: Exception | None = None
        self.diarize_error: Exception | None = None
        self.downloads: list[tuple[str, bool]] = []
        self.pipelines: list[Any] = []
        self.emptied = 0

        runtime = self

        class Pipeline:
            def __init__(self, checkpoint: str) -> None:
                self.checkpoint = checkpoint
                self.calls: list[dict[str, Any]] = []
                self.device: Any = None

            @classmethod
            def from_pretrained(cls, checkpoint: str) -> "Pipeline":
                if runtime.load_error is not None:
                    raise runtime.load_error
                pipeline = cls(checkpoint)
                runtime.pipelines.append(pipeline)
                return pipeline

            def to(self, device: Any) -> "Pipeline":
                self.device = device
                return self

            def __call__(self, file: dict[str, Any], num_speakers: Any) -> Any:
                self.calls.append({**file, "num_speakers": num_speakers})
                if runtime.diarize_error is not None:
                    raise runtime.diarize_error
                return OUTPUT

        self.torch = types.ModuleType("torch")
        self.torch.device = lambda name: f"device:{name}"
        self.torch.cuda = types.SimpleNamespace(
            is_available=lambda: self.cuda_available,
            empty_cache=self._empty_cache,
        )
        self.torch.from_numpy = lambda array: types.SimpleNamespace(
            unsqueeze=lambda dim: ("tensor", dim, array)
        )
        self.pyannote = types.ModuleType("pyannote")
        self.pyannote_audio = types.ModuleType("pyannote.audio")
        self.pyannote_audio.Pipeline = Pipeline
        self.pyannote.audio = self.pyannote_audio
        self.huggingface_hub = types.ModuleType("huggingface_hub")
        self.huggingface_hub.snapshot_download = self._download

    def _download(self, name: str, local_files_only: bool = False) -> str:
        self.downloads.append((name, local_files_only))
        if self.download_error is not None:
            raise self.download_error
        return str(self.snapshot)

    def _empty_cache(self) -> None:
        self.emptied += 1

    def installed(self) -> Any:
        return mock.patch.dict(
            "sys.modules",
            {
                "torch": self.torch,
                "pyannote": self.pyannote,
                "pyannote.audio": self.pyannote_audio,
                "huggingface_hub": self.huggingface_hub,
            },
        )


class PyannoteTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.runtime = FakeRuntime(self.root / "cache")
        for patcher in (
            self.runtime.installed(),
            mock.patch.object(
                adapter.importlib.metadata, "version", return_value="4.0.7"
            ),
            mock.patch.object(
                adapter, "_read_waveform", return_value=("waveform", 16000)
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.audio = self.root / "segment-01.wav"


class OfflineEnvironmentTest(unittest.TestCase):
    def test_importing_the_package_switches_hub_and_telemetry_off(self) -> None:
        with mock.patch.dict(
            os.environ, {"PYANNOTE_METRICS_ENABLED": "true", "HF_HUB_OFFLINE": "0"}
        ):
            importlib.reload(transcript)

            self.assertEqual(os.environ["PYANNOTE_METRICS_ENABLED"], "false")
            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")


class IdentityTest(PyannoteTestCase):
    def test_names_model_revision_and_runtime_from_the_local_cache(self) -> None:
        info = PyannoteDiarizer().identity()

        self.assertEqual(
            info,
            BackendInfo(
                backend_id="pyannote",
                model=MODEL,
                model_version=REVISION,
                runtime_version="4.0.7",
            ),
        )
        self.assertEqual(self.runtime.downloads, [(MODEL, True)])
        self.assertEqual(self.runtime.pipelines, [])  # nothing loaded

    def test_local_directory_is_used_without_the_cache(self) -> None:
        local = self.root / "pyannote-model"
        local.mkdir()
        (local / "config.yaml").touch()

        info = PyannoteDiarizer(str(local)).identity()

        self.assertIsNone(info.model_version)
        self.assertEqual(self.runtime.downloads, [])

    def test_missing_model_or_runtime_is_reported_with_the_next_step(self) -> None:
        self.runtime.download_error = FileNotFoundError("Drachenhort")
        with self.assertRaises(BackendUnavailableError) as caught:
            PyannoteDiarizer().identity()
        self.assertIn("not in the local cache", str(caught.exception))
        self.assertIn("README", str(caught.exception))
        self.assertNotIn("Drachenhort", str(caught.exception))

        self.runtime.download_error = None
        (self.runtime.snapshot / "config.yaml").unlink()
        with self.assertRaises(BackendUnavailableError) as caught:
            PyannoteDiarizer().identity()
        self.assertIn("config.yaml", str(caught.exception))

        not_installed = importlib_error()
        with (
            mock.patch.object(
                adapter.importlib.metadata, "version", side_effect=not_installed
            ),
            self.assertRaises(BackendUnavailableError) as caught,
        ):
            PyannoteDiarizer().identity()
        self.assertIn("pip install", str(caught.exception))

    def test_settings_are_the_requested_device(self) -> None:
        config = Config(language="de", root=self.root, diarization_device="cpu")

        self.assertEqual(
            PyannoteDiarizer.from_config(config).settings, {"device": "cpu"}
        )
        self.assertEqual(PyannoteDiarizer().settings, {"device": "auto"})


class LoadTest(PyannoteTestCase):
    def test_auto_prefers_cuda_and_loads_from_the_snapshot(self) -> None:
        PyannoteDiarizer().load()

        pipeline = self.runtime.pipelines[0]
        self.assertEqual(pipeline.checkpoint, str(self.runtime.snapshot))
        self.assertEqual(pipeline.device, "device:cuda")

    def test_auto_falls_back_to_cpu(self) -> None:
        self.runtime.cuda_available = False
        PyannoteDiarizer().load()

        self.assertEqual(self.runtime.pipelines[0].device, "device:cpu")

    def test_cuda_without_a_gpu_is_unavailable(self) -> None:
        self.runtime.cuda_available = False

        with self.assertRaises(BackendUnavailableError):
            PyannoteDiarizer(device="cuda").load()

    def test_missing_runtime_is_reported(self) -> None:
        with (
            mock.patch.dict("sys.modules", {"pyannote.audio": None}),
            self.assertRaises(BackendUnavailableError) as caught,
        ):
            PyannoteDiarizer().load()
        self.assertIn("pip install", str(caught.exception))

    def test_load_errors_are_mapped_without_the_runtime_message(self) -> None:
        for error, expected in (
            (RuntimeError("CUDA out of memory. Drachenhort"), ResourceError),
            (MemoryError(), ResourceError),
            (ValueError("Drachenhort"), BackendRuntimeError),
        ):
            with self.subTest(error=type(error).__name__):
                self.runtime.load_error = error
                with self.assertRaises(expected) as caught:
                    PyannoteDiarizer().load()
                self.assertNotIn("Drachenhort", str(caught.exception))
                self.assertIn(type(error).__name__, str(caught.exception))


class DiarizeTest(PyannoteTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.diarizer = PyannoteDiarizer()
        self.info = self.diarizer.identity()
        self.diarizer.load()

    def test_turns_become_milliseconds_with_their_inputs(self) -> None:
        run = self.diarizer.diarize(self.audio, self.info, AUDIO, num_speakers=2)

        self.assertEqual(
            run.turns,
            (Turn(500, 2000, "SPEAKER_00"), Turn(1800, 3250, "SPEAKER_01")),
        )
        self.assertEqual(
            run.exclusive_turns,
            (Turn(500, 1800, "SPEAKER_00"), Turn(2000, 3250, "SPEAKER_01")),
        )
        self.assertEqual(
            (run.info, run.audio_sha256, run.settings, run.num_speakers),
            (self.info, AUDIO, {"device": "auto"}, 2),
        )
        self.assertEqual(
            self.runtime.pipelines[0].calls,
            [{"waveform": "waveform", "sample_rate": 16000, "num_speakers": 2}],
        )

    def test_diarize_errors_are_mapped(self) -> None:
        self.runtime.diarize_error = RuntimeError("CUDA out of memory")

        with self.assertRaises(ResourceError) as caught:
            self.diarizer.diarize(self.audio, self.info, AUDIO)
        self.assertTrue(caught.exception.retryable)
        self.assertIn(str(self.audio), str(caught.exception))

    def test_diarize_before_load_fails(self) -> None:
        with self.assertRaises(BackendRuntimeError):
            PyannoteDiarizer().diarize(self.audio, self.info, AUDIO)

    def test_close_frees_the_pipeline_and_the_gpu_cache(self) -> None:
        self.diarizer.close()

        self.assertEqual(self.runtime.emptied, 1)
        with self.assertRaises(BackendRuntimeError):
            self.diarizer.diarize(self.audio, self.info, AUDIO)


@unittest.skipIf(numpy is None, "numpy comes with the diarization extra")
class ReadWaveformTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.audio = Path(directory.name) / "segment-01.wav"
        patcher = FakeRuntime(Path(directory.name) / "cache").installed()
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, samples: list[int], channels: int = 1, width: int = 2) -> None:
        with wave.open(str(self.audio), "wb") as file:
            file.setnchannels(channels)
            file.setsampwidth(width)
            file.setframerate(16000)
            data = b"".join(s.to_bytes(width, "little", signed=True) for s in samples)
            file.writeframes(data)

    def test_mono_and_stereo_become_one_float_channel(self) -> None:
        for samples, channels, expected in (
            ([16384, -32768], 1, [0.5, -1.0]),
            ([16384, 0, -32768, -32768], 2, [0.25, -1.0]),
        ):
            with self.subTest(channels=channels):
                self.write(samples, channels)
                (kind, dim, mono), rate = adapter._read_waveform(self.audio)

                self.assertEqual((kind, dim, rate), ("tensor", 0, 16000))
                self.assertEqual(mono.dtype, numpy.float32)
                self.assertEqual(mono.tolist(), expected)

    def test_unreadable_or_wrong_width_audio_is_an_input_error(self) -> None:
        self.audio.write_bytes(b"not a wav")
        with self.assertRaises(AudioInputError):
            adapter._read_waveform(self.audio)

        self.write([1, 2], width=1)
        with self.assertRaises(AudioInputError) as caught:
            adapter._read_waveform(self.audio)
        self.assertIn("16-bit", str(caught.exception))


def importlib_error() -> Exception:
    return adapter.importlib.metadata.PackageNotFoundError("pyannote.audio")


if __name__ == "__main__":
    unittest.main()
