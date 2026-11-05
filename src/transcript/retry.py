"""Bounded retries of one backend call per segment, for ASR and diarization alike.

Only a `BackendError` whose `retryable` is set is tried again: memory that ran out
or a runtime that failed unexpectedly may work on the next call, a missing file
or model never does. `retries` is capped by the configuration, so a run cannot
loop forever.

`FailureLog` logs every failed attempt with the error class and its message.
Backend messages name backend, action and file, never transcript text; the
original exception in `__cause__` may hold such text and is never logged.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from transcript.asr import BackendError

_T = TypeVar("_T")

RETRY_DELAY_S = 5.0  # gives the device a moment to release memory


@dataclass(frozen=True)
class Attempted(Generic[_T]):
    """How a call ended: its `result`, or the last `error` once retries ran out."""

    result: _T | None
    error: BackendError | None
    attempts: int  # calls made, counted from 1
    elapsed_ms: int  # of the last call


def attempt(
    call: Callable[[], _T],
    retries: int,
    on_failure: Callable[[BackendError, int, bool], None],
    sleep: Callable[[float], None] = time.sleep,
) -> Attempted[_T]:
    """Run `call`, again up to `retries` times while it raises a retryable error.

    `on_failure` gets each error with its attempt number, counted from 1, and
    whether it is the last one. Exceptions other than `BackendError` pass.
    """
    if retries < 0:
        raise ValueError("retries must not be negative")
    for number in range(1, retries + 2):
        started = time.perf_counter()
        try:
            return Attempted(call(), None, number, _elapsed_ms(started))
        except BackendError as error:
            final = not error.retryable or number > retries
            on_failure(error, number, final)
            if final:
                return Attempted(None, error, number, _elapsed_ms(started))
        sleep(RETRY_DELAY_S)
    raise AssertionError("unreachable: the last attempt returns")


class FailureLog:
    """An `on_failure` for `attempt` that logs a warning per failed attempt.

    `context` names session, segment and backend.
    """

    def __init__(self, logger: logging.Logger, context: str, retries: int) -> None:
        self._logger = logger
        self._context = context
        self._limit = retries + 1

    def __call__(self, error: BackendError, number: int, final: bool) -> None:
        if not final:
            then = f"retrying in {RETRY_DELAY_S:g} s"
        elif error.retryable:
            then = "giving up"
        else:
            then = "not retryable"
        # Never exc_info: the traceback would show the runtime's own message.
        self._logger.warning(
            "%s: attempt %d/%d failed: %s: %s; %s",
            self._context,
            number,
            self._limit,
            type(error).__name__,
            error,
            then,
        )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
