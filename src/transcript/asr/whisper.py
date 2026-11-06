"""The V0.1 backend: Whisper via faster-whisper, from the local model cache only.

Settings follow the TOOL-62 decision (docs/spikes/TOOL-62-asr-vergleich.md): VAD,
word timestamps, beam search, no conditioning on previous text. The model is never
downloaded here; `load` fails with a hint when it is not cached.

Messages never repeat a runtime message, which may quote hotwords.
"""

import dataclasses
import gc
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from transcript.asr.backend import (
    AudioInputError,
    BackendError,
    BackendIdentity,
    BackendInfo,
    BackendResult,
    BackendRuntimeError,
    BackendUnavailableError,
    Capabilities,
    ResultSegment,
    ResultWord,
    TranscriptionRequest,
    cached_model_dir,
    hub_revision,
    resolve_device,
    runtime_error,
)
from transcript.config import Config

BACKEND_ID = "faster-whisper"
CAPABILITIES = Capabilities(
    word_timestamps=True,
    segment_timestamps=True,
    keyword_biasing=True,
    word_confidence=True,
    segment_signals=True,
    devices=frozenset({"cpu", "cuda"}),
)
# faster-whisper keeps at most max_length // 2 - 1 hotword tokens (448 // 2 - 1).
HOTWORD_TOKENS = 223
FIXED_SETTINGS = {
    "vad_filter": True,
    "word_timestamps": True,  # TOOL-76 assigns speakers per word
    "condition_on_previous_text": False,
}
# Without tokenizer.json faster-whisper would fetch one from the Hub.
_MODEL_FILES = ("model.bin", "tokenizer.json")
_DEFAULT_COMPUTE_TYPES = {"cuda": "float16", "cpu": "int8"}
_INSTALL_HINT = "install it with pip install -e '.[whisper]'"
_LIBRARY_HINT = "CUDA libraries not found, set LD_LIBRARY_PATH as in the README"


class WhisperBackend:
    """Loads one Whisper model and transcribes segments with it."""

    def __init__(
        self,
        model: str = Config.asr_model,
        *,
        device: str = Config.asr_device,
        compute_type: str | None = Config.asr_compute_type,
        beam_size: int = Config.asr_beam_size,
    ) -> None:
        self._model_name = model
        self.capabilities = dataclasses.replace(
            CAPABILITIES, keyword_biasing=takes_hotwords(model)
        )
        self._requested_device = device
        self._requested_compute_type = compute_type
        self._beam_size = beam_size
        self._model: Any = None
        self.info = BackendInfo(backend_id=BACKEND_ID, model=model)
        self._settings: Mapping[str, Any] = {}  # filled by load

    @classmethod
    def from_config(cls, config: Config) -> "WhisperBackend":
        return cls(
            config.asr_model,
            device=config.asr_device,
            compute_type=config.asr_compute_type,
            beam_size=config.asr_beam_size,
        )

    def identity(self) -> BackendIdentity:
        """Revision from the model cache, device and settings; no model is built."""
        _, _, identity = self._prepare()
        return identity

    def load(self) -> None:
        faster_whisper, model_path, identity = self._prepare()
        device = identity.settings["device"]
        try:
            model = faster_whisper.WhisperModel(
                str(model_path),
                device=device,
                compute_type=identity.settings["compute_type"],
            )
        except Exception as error:
            raise self._error(error, f"cannot load model on {device}") from error

        self._model = model
        self.info = identity.info
        self._settings = identity.settings

    def _prepare(self) -> tuple[Any, Path, BackendIdentity]:
        """The runtime module, the model directory and the identity, all without
        building the model."""
        try:
            import ctranslate2
            import faster_whisper
        except ImportError as error:
            raise BackendUnavailableError(
                f"{BACKEND_ID}: runtime missing, {_INSTALL_HINT}"
            ) from error

        device = resolve_device(
            self._requested_device, ctranslate2.get_cuda_device_count() > 0, BACKEND_ID
        )
        model_path = cached_model_dir(
            self._model_name,
            lambda name: faster_whisper.download_model(name, local_files_only=True),
            _MODEL_FILES,
            BACKEND_ID,
        )
        info = BackendInfo(
            backend_id=BACKEND_ID,
            model=self._model_name,
            model_version=hub_revision(model_path),
            runtime_version=faster_whisper.__version__,
        )
        settings = {
            "model": self._model_name,
            "device": device,
            "compute_type": self._requested_compute_type
            or _DEFAULT_COMPUTE_TYPES[device],
            "beam_size": self._beam_size,
            **FIXED_SETTINGS,
        }
        return faster_whisper, model_path, BackendIdentity(info, settings)

    def transcribe(self, request: TranscriptionRequest) -> BackendResult:
        if self._model is None:
            raise BackendRuntimeError(f"{BACKEND_ID}: not loaded")
        used: tuple[str, ...] = ()
        if self.capabilities.keyword_biasing:
            tokenizer = self._model.hf_tokenizer
            used = fit_hotwords(
                request.keywords,
                lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids),
            )
        try:
            segments, info = self._model.transcribe(
                str(request.audio),
                language=request.language,
                beam_size=self._beam_size,
                hotwords=" ".join(used) or None,
                **FIXED_SETTINGS,
            )
            segments = list(segments)  # decoding runs while iterating
        except Exception as error:
            raise self._error(error, f"cannot transcribe {request.audio}") from error

        return BackendResult(
            info=self.info,
            segments=tuple(_segment(segment) for segment in segments),
            language=info.language,
            language_probability=info.language_probability,
            keywords_used=used,
            settings=dict(self._settings),
            raw=_raw(segments, info),
        )

    def close(self) -> None:
        self._model = None
        gc.collect()  # frees the model before diarization needs the memory

    def _error(self, error: Exception, action: str) -> BackendError:
        """Map a runtime failure to a category; the original message stays out.

        Unlike the generic wrapper, the message names the action and a remedy.
        """
        cause = f"{BACKEND_ID}: {action} ({type(error).__name__})"
        message = str(error).lower() if isinstance(error, RuntimeError) else ""
        if "library" in message and (
            "not found" in message or "cannot be loaded" in message
        ):
            return BackendUnavailableError(f"{cause}, {_LIBRARY_HINT}")
        if type(error).__module__.split(".")[0] == "av":
            return AudioInputError(f"{cause}, audio cannot be decoded")
        return runtime_error(error, cause)


def takes_hotwords(model: str) -> bool:
    """Whether `model`, a name or a local directory, gets hotwords.

    Only turbo models do: TOOL-62 found that hotwords help or do no harm with
    large-v3-turbo, while large-v3 falls apart. A directory counts by its last part.
    """
    return "turbo" in Path(model).name.casefold()


def fit_hotwords(
    keywords: Sequence[str], count_tokens: Callable[[str], int]
) -> tuple[str, ...]:
    """The leading keywords whose joined hotword prompt fits in HOTWORD_TOKENS.

    Order is priority: the first keyword that does not fit ends the list, so the
    runtime never cuts a term in half and `keywords_used` stays exact.
    """
    used: list[str] = []
    for keyword in keywords:
        if not keyword.strip():
            continue
        # faster-whisper encodes the prompt as " " + hotwords.
        if count_tokens(" " + " ".join([*used, keyword])) > HOTWORD_TOKENS:
            break
        used.append(keyword)
    return tuple(used)


def _segment(segment: Any) -> ResultSegment:
    return ResultSegment(
        text=segment.text.strip(),
        start=segment.start,
        end=segment.end,
        words=tuple(
            ResultWord(
                text=word.word.strip(),
                start=word.start,
                end=word.end,
                confidence=word.probability,
            )
            for word in segment.words or ()
        ),
        signals={
            "avg_logprob": segment.avg_logprob,
            "no_speech_prob": segment.no_speech_prob,
            "compression_ratio": segment.compression_ratio,
        },
    )


def _raw(segments: Sequence[Any], info: Any) -> dict[str, Any]:
    """The runtime's answer, unchanged and JSON-ready; options are in `settings`."""
    return {
        "info": {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "duration_after_vad": info.duration_after_vad,
        },
        "segments": [dataclasses.asdict(segment) for segment in segments],
    }
