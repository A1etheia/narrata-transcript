"""A backend without a model, for tests of the steps that call a backend."""

from collections.abc import Callable

from transcript.asr.backend import (
    BackendInfo,
    BackendResult,
    BackendRuntimeError,
    Capabilities,
    ResultSegment,
    TranscriptionRequest,
)

FAKE_INFO = BackendInfo(backend_id="fake", model="fake", runtime_version="0")

Answer = BackendResult | Callable[[TranscriptionRequest], BackendResult]


class FakeBackend:
    """Answers with a fixed result or a function of the request, or raises `error`.

    Without an answer it returns one fixed segment and, like a real adapter,
    reports the request's keywords as used only when it declares
    `keyword_biasing`. It records requests and load/close calls.
    """

    def __init__(
        self,
        answer: Answer | None = None,
        *,
        capabilities: Capabilities | None = None,
        error: Exception | None = None,
        info: BackendInfo = FAKE_INFO,
    ) -> None:
        self.info = info
        self.capabilities = capabilities or Capabilities(segment_timestamps=True)
        self._answer = answer
        self._error = error
        self.requests: list[TranscriptionRequest] = []
        self.load_calls = 0
        self.close_calls = 0

    @property
    def loaded(self) -> bool:
        return self.load_calls > self.close_calls

    def load(self) -> None:
        self.load_calls += 1

    def transcribe(self, request: TranscriptionRequest) -> BackendResult:
        if not self.loaded:
            raise BackendRuntimeError(f"{self.info.backend_id}: not loaded")
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        if callable(self._answer):
            return self._answer(request)
        if self._answer is not None:
            return self._answer
        segment = ResultSegment(text="Fake-Transkript.", start=0.0, end=1.0)
        used = request.keywords if self.capabilities.keyword_biasing else ()
        return BackendResult(info=self.info, segments=(segment,), keywords_used=used)

    def close(self) -> None:
        if self.loaded:
            self.close_calls += 1
