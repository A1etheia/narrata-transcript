"""The end-to-end run of a session: step order, reuse, halts and the exit code.

The steps are the single commands; this module only decides which of them run
and what their exit codes mean for the run. It prints nothing and does none of
the steps' work, so each step stays a command of its own (TOOL-55).

The state lives in the session's files, not here: a step is skipped when what
it writes is already there, and a manual step halts the run when it has just
written a file for a person to fill in. Running again picks up from the files.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, get_args

StepName = Literal[
    "preflight",
    "extract",
    "context",
    "snapshot",
    "manifest",
    "transcribe",
    "review",
    "speakers",
    "working",
    "export",
    "txt",
    "docx",
    "report",
]
STEPS: tuple[StepName, ...] = get_args(StepName)
# the steps `--redo` forces; every later step runs anyway
REDOABLE: tuple[StepName, ...] = (
    "extract",
    "context",
    "snapshot",
    "manifest",
    "transcribe",
)

Status = Literal["ran", "reused", "incomplete", "halted", "failed"]

# Exit codes: a step returns OK, INCOMPLETE, FAILED or, if manual, HALTED.
OK = 0
INCOMPLETE = 1  # it ran, but left something out
FAILED = 2
HALTED = 3  # it wrote a file for a person to fill in


@dataclass(frozen=True)
class Step:
    name: StepName
    run: Callable[[bool], int]  # True: forced by `--redo`; returns an exit code
    # True: what the step writes is in place, so it is skipped unless forced
    reusable: Callable[[], bool] | None = None
    manual: bool = False  # may halt; the run stops after the last manual step
    stop_on_incomplete: bool = False  # INCOMPLETE stops the run, like FAILED


@dataclass(frozen=True)
class Result:
    step: StepName
    status: Status


@dataclass(frozen=True)
class Outcome:
    exit_code: int
    results: tuple[Result, ...]  # the steps reached, in order
    stopped_at: StepName | None = None  # the step that stopped the run early

    @property
    def halted(self) -> tuple[StepName, ...]:
        return tuple(r.step for r in self.results if r.status == "halted")


_STATUS: dict[int, Status] = {
    OK: "ran",
    INCOMPLETE: "incomplete",
    FAILED: "failed",
    HALTED: "halted",
}


def run(steps: Sequence[Step], redo: StepName | None = None) -> Outcome:
    """Run `steps`, one for each of `STEPS` in that order.

    `redo` forces that step and makes every later one run, reusable or not.
    """
    if tuple(step.name for step in steps) != STEPS:
        raise ValueError(f"steps must be {', '.join(STEPS)} in this order")
    if redo is not None and redo not in REDOABLE:
        raise ValueError(f"{redo} cannot be redone; it runs every time")
    forced_from = len(STEPS) if redo is None else STEPS.index(redo)
    results: list[Result] = []
    final = OK  # raised to INCOMPLETE, or to HALTED, by the steps that ran
    for position, step in enumerate(steps):
        if final == HALTED and not step.manual:
            return Outcome(HALTED, tuple(results))
        if position < forced_from and step.reusable is not None and step.reusable():
            results.append(Result(step.name, "reused"))
            continue
        code = step.run(position == forced_from)
        if code not in _STATUS or (code == HALTED and not step.manual):
            raise ValueError(f"step {step.name} returned exit code {code}")
        results.append(Result(step.name, _STATUS[code]))
        if code == FAILED or (code == INCOMPLETE and step.stop_on_incomplete):
            return Outcome(code, tuple(results), step.name)
        final = max(final, code)  # OK < INCOMPLETE < HALTED; FAILED returned
    return Outcome(final, tuple(results))
