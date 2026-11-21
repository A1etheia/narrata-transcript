"""Cut a passage where the speaker changes (TOOL-96).

A backend passage, e.g. a Whisper segment, often holds more than one speaker;
its majority label hides every change inside it. `split_at_speaker_changes`
cuts it into parts with one label each, using the word labels of the
diarization. `rejoin` undoes the cut.

Nothing is invented: a part's text is its words joined by single spaces, and a
passage is cut only when that join of all its words is exactly its text. The
parts joined again therefore always give the recognised text. A run of one
label shorter than `MinTurn` is drawn into its neighbour, so that a stray label
does not shred a passage: into the previous run, at the start into the next.
Words without a label stay with the run before them, at the start with the
first labelled run.

This module logs nothing and its errors name no text and no label.
"""

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from transcript.reference import Passage, Word, majority_speaker


@dataclass(frozen=True)
class MinTurn:
    """Below which a run of one label is drawn into its neighbour.

    A run is short when it lasts less than `ms` or has fewer labelled words than
    `words`; 0 switches either rule off.
    """

    ms: int = 0
    words: int = 0

    def __post_init__(self) -> None:
        if self.ms < 0 or self.words < 0:
            raise ValueError("minimum turn must not be negative")

    def is_short(self, words: Sequence[Word]) -> bool:
        labelled = [w for w in words if w.speaker is not None]
        if len(labelled) < self.words:
            return True
        start, end = labelled[0].start_ms, labelled[-1].end_ms
        # a word gets a label only with times, see diarization._word_label
        assert start is not None and end is not None
        return end - start < self.ms


NO_MIN_TURN = MinTurn()  # every label change cuts


@dataclass
class _Run:
    label: str
    words: list[Word]


def can_split(passage: Passage) -> bool:
    """Whether the words joined by single spaces are exactly the passage text."""
    return bool(passage.words) and _joined(passage.words) == passage.text


def split_at_speaker_changes(
    passage: Passage, min_turn: MinTurn = NO_MIN_TURN
) -> tuple[Passage, ...]:
    """`passage` cut into parts of one label each; itself if nothing is cut.

    Every part keeps the passage's index, `asr_passage` and signals;
    renumbering is the caller's. The first part starts where the passage starts, the last ends
    where it ends, the others start and end with their first and last timed
    word. A part's speaker is the majority of its word labels.
    """
    if not can_split(passage):
        return (passage,)
    runs = _absorb(_runs(passage.words), min_turn)
    if len(runs) < 2:
        return (passage,)
    last = len(runs) - 1
    return tuple(
        Passage(
            index=passage.index,
            text=_joined(run.words),
            start_ms=passage.start_ms if n == 0 else _first_start(run.words),
            end_ms=passage.end_ms if n == last else _last_end(run.words),
            words=tuple(run.words),
            speaker=majority_speaker(run.words) or run.label,
            signals=dict(passage.signals),
            asr_passage=passage.asr_passage,
        )
        for n, run in enumerate(runs)
    )


def rejoin(parts: Sequence[Passage]) -> Passage:
    """The passage `split_at_speaker_changes` cut into `parts`, in order."""
    if not parts:
        raise ValueError("nothing to rejoin")
    if len(parts) == 1:
        return parts[0]
    words = tuple(word for part in parts for word in part.words)
    return replace(
        parts[0],
        text=" ".join(part.text for part in parts),
        end_ms=parts[-1].end_ms,
        words=words,
        speaker=majority_speaker(words),
    )


def backend_passages(passages: Iterable[Passage]) -> list[Passage]:
    """The passages as the backend delivered them, undoing an earlier cut."""
    return [
        rejoin(list(parts))
        for _, parts in itertools.groupby(passages, key=lambda p: p.asr_passage)
    ]


def _runs(words: Sequence[Word]) -> list[_Run]:
    """Consecutive words of one label; unlabelled words join the run before."""
    # leading unlabelled words take the first label
    label = next((w.speaker for w in words if w.speaker is not None), None)
    runs: list[_Run] = []
    for word in words:
        label = word.speaker or label
        if runs and runs[-1].label == label:
            runs[-1].words.append(word)
        elif label is not None:
            runs.append(_Run(label, [word]))
    return runs


def _absorb(runs: list[_Run], min_turn: MinTurn) -> list[_Run]:
    """Draw short runs into their neighbour, left to right, in one pass.

    A run that takes words in only grows, so none becomes short again.
    """
    out: list[_Run] = []
    pending: list[Word] = []  # short runs at the start, waiting for the next
    for n, run in enumerate(runs):
        run.words[:0] = pending
        pending = []
        if out and (run.label == out[-1].label or min_turn.is_short(run.words)):
            out[-1].words.extend(run.words)
        elif not out and n < len(runs) - 1 and min_turn.is_short(run.words):
            pending = run.words
        else:
            out.append(run)
    return out


def _joined(words: Sequence[Word]) -> str:
    return " ".join(word.text for word in words)


def _first_start(words: Sequence[Word]) -> int | None:
    return next((w.start_ms for w in words if w.start_ms is not None), None)


def _last_end(words: Sequence[Word]) -> int | None:
    return next((w.end_ms for w in reversed(words) if w.end_ms is not None), None)
