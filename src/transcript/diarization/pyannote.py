"""The V0.1 diarizer: pyannote `speaker-diarization-community-1`, local cache only.

Decision and measurements: docs/spikes/TOOL-20-diarisierung.md. The model is
gated; it is downloaded once with a Hugging Face token (README) and never here.
pyannote's telemetry and Hub access are switched off for the whole process in
`transcript/__init__.py`, so no run metadata leaves the machine.

Messages never repeat a runtime message.
"""

import gc
import importlib.metadata
import wave
from pathlib import Path
from typing import Any

from transcript.asr.backend import (
    AudioInputError,
    BackendInfo,
    BackendRuntimeError,
    BackendUnavailableError,
    cached_model_dir,
    hub_revision,
    resolve_device,
    runtime_error,
)
from transcript.config import Config
from transcript.diarization import DiarizationRun, Turn
from transcript.timecode import seconds_to_ms

BACKEND_ID = "pyannote"
_RUNTIME = "pyannote.audio"
_RUNTIME_MISSING = (
    f"{BACKEND_ID}: runtime missing, install it with pip install -e '.[diarization]'"
)


class PyannoteDiarizer:
    """Loads the pyannote pipeline once and diarizes segment WAVs with it."""

    def __init__(
        self,
        model: str = Config.diarization_model,
        *,
        device: str = Config.diarization_device,
    ) -> None:
        self._model_name = model
        self._requested_device = device
        self._pipeline: Any = None
        self._device: str | None = None  # resolved by load

    @classmethod
    def from_config(cls, config: Config) -> "PyannoteDiarizer":
        return cls(config.diarization_model, device=config.diarization_device)

    @property
    def settings(self) -> dict[str, Any]:
        """What, besides the model, decides the turns; known before `load`."""
        return {"device": self._requested_device}

    def identity(self) -> BackendInfo:
        """Model, revision and runtime from the local cache, without loading torch."""
        try:
            runtime_version = importlib.metadata.version(_RUNTIME)
        except importlib.metadata.PackageNotFoundError as error:
            raise BackendUnavailableError(_RUNTIME_MISSING) from error
        return BackendInfo(
            backend_id=BACKEND_ID,
            model=self._model_name,
            model_version=hub_revision(self._model_path()),
            runtime_version=runtime_version,
        )

    def load(self) -> None:
        try:
            import torch
            from pyannote.audio import Pipeline
        except ImportError as error:
            raise BackendUnavailableError(_RUNTIME_MISSING) from error

        device = resolve_device(
            self._requested_device, torch.cuda.is_available(), BACKEND_ID
        )
        model_path = self._model_path()
        try:
            pipeline = Pipeline.from_pretrained(str(model_path))
            pipeline.to(torch.device(device))
        except Exception as error:
            raise _error(error, f"cannot load model on {device}") from error
        self._pipeline = pipeline
        self._device = device

    def diarize(
        self,
        audio: Path,
        info: BackendInfo,
        audio_sha256: str,
        num_speakers: int | None = None,
    ) -> DiarizationRun:
        """Turns of `audio`, a 16-bit PCM WAV; `info` comes from `identity`."""
        if self._pipeline is None:
            raise BackendRuntimeError(f"{BACKEND_ID}: not loaded")
        waveform, sample_rate = _read_waveform(audio)
        try:
            output = self._pipeline(
                {"waveform": waveform, "sample_rate": sample_rate},
                num_speakers=num_speakers,
            )
        except Exception as error:
            raise _error(error, f"cannot diarize {audio}") from error
        return DiarizationRun(
            info=info,
            audio_sha256=audio_sha256,
            turns=_turns(output.speaker_diarization),
            exclusive_turns=_turns(output.exclusive_speaker_diarization),
            settings=self.settings,
            num_speakers=num_speakers,
        )

    def close(self) -> None:
        self._pipeline = None
        gc.collect()
        if self._device == "cuda":
            import torch

            torch.cuda.empty_cache()

    def _model_path(self) -> Path:
        """The pipeline directory; a name resolves only from the local cache."""
        return cached_model_dir(
            self._model_name, _snapshot_from_cache, ("config.yaml",), BACKEND_ID
        )


def _snapshot_from_cache(name: str) -> str:
    try:
        import huggingface_hub
    except ImportError as error:
        raise BackendUnavailableError(_RUNTIME_MISSING) from error
    return huggingface_hub.snapshot_download(name, local_files_only=True)


def _read_waveform(audio: Path) -> tuple[Any, int]:
    """The WAV as a float32 tensor (channel, time), averaged down to mono."""
    import numpy
    import torch

    try:
        with wave.open(str(audio), "rb") as file:
            if file.getsampwidth() != 2:
                raise AudioInputError(f"{BACKEND_ID}: {audio} is not 16-bit PCM")
            channels = file.getnchannels()
            sample_rate = file.getframerate()
            frames = file.readframes(file.getnframes())
    except (OSError, EOFError, wave.Error) as error:
        raise AudioInputError(
            f"{BACKEND_ID}: cannot read {audio} ({type(error).__name__})"
        ) from error
    samples = numpy.frombuffer(frames, dtype=numpy.int16).reshape(-1, channels)
    mono = samples.mean(axis=1, dtype=numpy.float32)
    mono /= 32768  # in place: five hours of float32 are over 1 GB
    return torch.from_numpy(mono).unsqueeze(0), sample_rate


def _turns(annotation: Any) -> tuple[Turn, ...]:
    return tuple(
        Turn(
            start_ms=seconds_to_ms(segment.start),
            end_ms=seconds_to_ms(segment.end),
            label=label,
        )
        for segment, _, label in annotation.itertracks(yield_label=True)
    )


def _error(error: Exception, action: str) -> BackendRuntimeError:
    return runtime_error(error, f"{BACKEND_ID}: {action} ({type(error).__name__})")
