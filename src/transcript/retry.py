"""Bounded retries of one backend call per segment, for ASR and diarization alike.

Only a `BackendError` whose `retryable` is set is tried again: memory that ran out
or a runtime that failed unexpectedly may work on the next call, a missing file
or model never does. `retries` is capped by the configuration, so a run cannot
loop forever.
"""

import time
from collections.abc import Callable
from typing import TypeVar

from transcript.asr import BackendError

_T = TypeVar("_T")

RETRY_DELAY_S = 5.0  # gives the device a moment to release memory


def attempt(
    call: Callable[[], _T],
    retries: int,
    on_failure: Callable[[BackendError, int, bool], None],
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[_T, int]:
    """Run `call`, again up to `retries` times while it raises a retryable error.

    Returns the result and the number of attempts it took. `on_failure` gets
    each error with its attempt number, counted from 1, and whether it is the
    last one; then the last error is raised again.
    """
    if retries < 0:
        raise ValueError("retries must not be negative")
    for number in range(1, retries + 2):
        try:
            return call(), number
        except BackendError as error:
            final = not error.retryable or number > retries
            on_failure(error, number, final)
            if final:
                raise
        sleep(RETRY_DELAY_S)
    raise AssertionError("unreachable: the last attempt returns or raises")
