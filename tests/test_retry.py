import unittest
from collections.abc import Callable

from transcript.asr import (
    AudioInputError,
    BackendError,
    BackendRuntimeError,
    ResourceError,
)
from transcript.retry import RETRY_DELAY_S, Attempted, attempt


def failing(*errors: BackendError) -> Callable[[], str]:
    """A call that raises `errors` in turn, then answers "done"."""
    pending = list(errors)

    def call() -> str:
        if pending:
            raise pending.pop(0)
        return "done"

    return call


class AttemptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.failures: list[tuple[str, int, bool]] = []
        self.sleeps: list[float] = []

    def run_call(self, call: Callable[[], str], retries: int) -> Attempted[str]:
        return attempt(
            call,
            retries,
            lambda error, number, final: self.failures.append(
                (type(error).__name__, number, final)
            ),
            sleep=self.sleeps.append,
        )

    def test_success_needs_one_attempt(self) -> None:
        done = self.run_call(failing(), retries=2)

        self.assertEqual((done.result, done.error, done.attempts), ("done", None, 1))
        self.assertGreaterEqual(done.elapsed_ms, 0)
        self.assertEqual((self.failures, self.sleeps), ([], []))

    def test_retryable_error_is_tried_again(self) -> None:
        result = self.run_call(
            failing(ResourceError("out of memory"), BackendRuntimeError("x")),
            retries=2,
        )

        self.assertEqual((result.result, result.attempts), ("done", 3))
        self.assertEqual(
            self.failures,
            [("ResourceError", 1, False), ("BackendRuntimeError", 2, False)],
        )
        self.assertEqual(self.sleeps, [RETRY_DELAY_S, RETRY_DELAY_S])

    def test_retries_are_capped_and_the_last_error_is_returned(self) -> None:
        last = ResourceError("third")
        call = failing(ResourceError("first"), ResourceError("second"), last)

        done = self.run_call(call, retries=2)

        self.assertEqual((done.result, done.error, done.attempts), (None, last, 3))
        self.assertEqual([number for _, number, _ in self.failures], [1, 2, 3])
        self.assertEqual([final for _, _, final in self.failures], [False, False, True])
        self.assertEqual(len(self.sleeps), 2)

    def test_error_that_cannot_succeed_runs_once(self) -> None:
        done = self.run_call(failing(AudioInputError("missing")), retries=5)

        self.assertEqual(done.attempts, 1)
        self.assertEqual(self.failures, [("AudioInputError", 1, True)])
        self.assertEqual(self.sleeps, [])

    def test_zero_retries_turns_retrying_off(self) -> None:
        done = self.run_call(failing(ResourceError("x")), retries=0)

        self.assertIsInstance(done.error, ResourceError)
        self.assertEqual(self.failures, [("ResourceError", 1, True)])

    def test_other_exceptions_are_not_caught(self) -> None:
        def broken() -> str:
            raise ValueError("bug")

        with self.assertRaises(ValueError):
            self.run_call(broken, retries=2)
        self.assertEqual(self.failures, [])

    def test_negative_retries_are_a_programming_error(self) -> None:
        with self.assertRaises(ValueError):
            self.run_call(failing(), retries=-1)


if __name__ == "__main__":
    unittest.main()
