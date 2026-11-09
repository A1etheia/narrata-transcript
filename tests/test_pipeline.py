"""The run order, reuse, halts and exit codes of `transcript process`, with fake steps."""

import unittest
from collections.abc import Mapping

from transcript.pipeline import (
    FAILED,
    HALTED,
    INCOMPLETE,
    OK,
    STEPS,
    Outcome,
    Result,
    Step,
    StepName,
    run,
)

MANUAL: frozenset[StepName] = frozenset({"review", "speakers"})
STOPPING: frozenset[StepName] = frozenset({"transcribe", "speakers"})


class _Run(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[StepName, bool]] = []  # (step, forced)

    def run_steps(
        self,
        codes: Mapping[StepName, int] | None = None,
        reusable: frozenset[StepName] = frozenset(),
        redo: StepName | None = None,
    ) -> Outcome:
        codes = codes or {}
        return run([self.step(n, codes.get(n, OK), n in reusable) for n in STEPS], redo)

    def step(self, name: StepName, code: int, reusable: bool) -> Step:
        def call(forced: bool) -> int:
            self.calls.append((name, forced))
            return code

        return Step(
            name,
            call,
            reusable=(lambda: True) if reusable else None,
            manual=name in MANUAL,
            stop_on_incomplete=name in STOPPING,
        )

    def ran(self) -> list[StepName]:
        return [name for name, _ in self.calls]


class OrderTest(_Run):
    def test_every_step_runs_once_in_order(self) -> None:
        outcome = self.run_steps()

        self.assertEqual(outcome.exit_code, OK)
        self.assertEqual(self.ran(), list(STEPS))
        self.assertEqual(outcome.results, tuple(Result(n, "ran") for n in STEPS))
        self.assertIsNone(outcome.stopped_at)

    def test_steps_in_another_order_are_refused(self) -> None:
        steps = [self.step(name, OK, False) for name in reversed(STEPS)]

        with self.assertRaises(ValueError):
            run(steps)

    def test_a_halt_from_a_step_that_is_not_manual_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.run_steps({"working": HALTED})


class ReuseTest(_Run):
    def test_steps_whose_files_are_in_place_are_skipped(self) -> None:
        outcome = self.run_steps(reusable=frozenset({"extract", "context"}))

        self.assertNotIn("extract", self.ran())
        self.assertNotIn("context", self.ran())
        self.assertIn(Result("extract", "reused"), outcome.results)
        self.assertEqual(outcome.exit_code, OK)
        self.assertTrue(all(not forced for _, forced in self.calls))

    def test_redo_forces_the_step_and_runs_every_later_one(self) -> None:
        reusable = frozenset({"extract", "context", "manifest"})

        outcome = self.run_steps(reusable=reusable, redo="context")

        self.assertNotIn("extract", self.ran())  # before the redo, still reused
        self.assertIn(("context", True), self.calls)
        self.assertIn(("manifest", False), self.calls)  # later: runs, not forced
        self.assertEqual([n for n, forced in self.calls if forced], ["context"])
        self.assertEqual(outcome.exit_code, OK)

    def test_only_the_early_steps_can_be_redone(self) -> None:
        with self.assertRaises(ValueError):
            self.run_steps(redo="working")


class StopTest(_Run):
    def test_a_failed_step_stops_the_run_and_is_named(self) -> None:
        outcome = self.run_steps({"snapshot": FAILED})

        self.assertEqual(outcome.exit_code, FAILED)
        self.assertEqual(outcome.stopped_at, "snapshot")
        self.assertEqual(self.ran()[-1], "snapshot")
        self.assertEqual(outcome.results[-1], Result("snapshot", "failed"))

    def test_an_incomplete_transcription_stops_the_run(self) -> None:
        outcome = self.run_steps({"transcribe": INCOMPLETE})

        self.assertEqual(outcome.exit_code, INCOMPLETE)
        self.assertEqual(outcome.stopped_at, "transcribe")
        self.assertNotIn("review", self.ran())

    def test_other_incomplete_steps_run_on_and_mark_the_run(self) -> None:
        outcome = self.run_steps({"working": INCOMPLETE, "report": INCOMPLETE})

        self.assertEqual(outcome.exit_code, INCOMPLETE)
        self.assertEqual(self.ran(), list(STEPS))
        self.assertIsNone(outcome.stopped_at)


class HaltTest(_Run):
    def test_the_run_halts_after_the_last_manual_step(self) -> None:
        outcome = self.run_steps({"review": HALTED})

        self.assertEqual(outcome.exit_code, HALTED)
        self.assertEqual(self.ran()[-2:], ["review", "speakers"])
        self.assertNotIn("working", self.ran())
        self.assertEqual(outcome.halted, ("review",))
        self.assertIsNone(outcome.stopped_at)

    def test_both_manual_steps_are_named(self) -> None:
        outcome = self.run_steps({"review": HALTED, "speakers": HALTED})

        self.assertEqual(outcome.halted, ("review", "speakers"))

    def test_a_failure_after_a_halt_still_stops_with_its_code(self) -> None:
        outcome = self.run_steps({"review": HALTED, "speakers": FAILED})

        self.assertEqual(outcome.exit_code, FAILED)
        self.assertEqual(outcome.stopped_at, "speakers")


if __name__ == "__main__":
    unittest.main()
