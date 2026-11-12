"""Assigning speaker labels interactively, one label at a time (TOOL-86).

For each label still open, the console shows its speech time and passages,
plays samples on request and asks who speaks. Every choice is stored at once
(`speakers.set_entry`), so an abort keeps what was confirmed; every other entry
of the hand-made file is written back as it was read.

The console shows participant names and passage text; the caller makes sure it
is an interactive terminal (TOOL-66). This module logs nothing.
"""

import math
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from transcript import speakers
from transcript.narrata import Participant
from transcript.reference import ReferenceTranscript
from transcript.session import SessionPaths
from transcript.speaker_player import Played, sample_ms
from transcript.speaker_samples import LabelSamples, ordered, sample_line
from transcript.speakers import AssignmentEntry, SpeakerAssignment, SpeakerMap, UserId
from transcript.timecode import format_ms

_LETTERS = "abcdefghijkl"  # samples, short of the command keys; numbers are people
_HELP_PLAY = "play audio: [{first}-{last}] that sample, [p] next, [r] again"
_HELP_ASSIGN = "assign: [1-{n}] person, [u]nknown, [m]ultiple; [s]kip, [q]uit"
_SKIP: Literal["skip"] = "skip"
_QUIT: Literal["quit"] = "quit"


@dataclass(frozen=True)
class Console:
    """What the dialogue uses outside this module; tests script it."""

    ask: Callable[[str], str]
    say: Callable[[str], None]
    play: Callable[[Path, int, int | None], Played]
    clock: Callable[[], float] = time.monotonic


@dataclass(frozen=True)
class Outcome:
    saved: int  # labels stored in this run
    skipped: int
    interrupted: bool  # Ctrl+C or end of input; what was saved stays


def queue(
    labels: Iterable[LabelSamples], applied: SpeakerMap, every: bool
) -> list[LabelSamples]:
    """The labels to ask for: per segment, the most speech first.

    Without `every`, only labels without an applied decision: missing, `open`,
    stale or pointing at an unknown person.
    """
    chosen = [
        found
        for found in labels
        if every or applied.resolve(found.segment, found.label).assigned == "open"
    ]
    return sorted(chosen, key=lambda found: (found.segment, -found.speech_ms))


def run(
    paths: SessionPaths,
    labels: Sequence[LabelSamples],
    references: Iterable[ReferenceTranscript],
    participants: Sequence[Participant],
    assignment: SpeakerAssignment,
    console: Console,
    every: bool = False,
) -> Outcome:
    """Ask for each queued label and store every choice at once."""
    dialogue = _Dialogue(paths, tuple(references), participants, assignment, console)
    return dialogue.run(queue(labels, dialogue.applied, every))


class _Dialogue:
    def __init__(
        self,
        paths: SessionPaths,
        references: Sequence[ReferenceTranscript],
        participants: Sequence[Participant],
        assignment: SpeakerAssignment,
        console: Console,
    ) -> None:
        self.paths = paths
        self.references = references
        self.participants = participants
        self.console = console
        self.people = ordered(participants)
        self.help_assign = _HELP_ASSIGN.format(n=len(self.people))
        self.versions = {
            r.segment.index: speakers.labels_version(r) for r in references
        }
        # the assignment as stored, kept in step with every choice
        self.assignment = assignment
        self.applied = speakers.check(assignment, references, participants)

    def run(self, todo: Sequence[LabelSamples]) -> Outcome:
        say = self.console.say
        if not todo:
            say("Every label is decided; --all asks for them again.")
            return Outcome(0, 0, interrupted=False)
        start = self.console.clock()
        saved = 0
        interrupted = False
        say("Participants:")
        for number, person in enumerate(self.people, start=1):
            membership = "former" if person.is_former else person.role
            say(f"  {number}. {person.display_name} ({membership})")
        try:
            for position, found in enumerate(todo, start=1):
                choice = self._ask_label(found, position, len(todo))
                if choice == _QUIT:
                    break
                if choice != _SKIP:
                    self._store(choice)
                    saved += 1
            self._ask_effort(start)
        except (KeyboardInterrupt, EOFError):
            say("")
            interrupted = True
        return Outcome(saved, len(todo) - saved, interrupted)

    def _ask_label(
        self, found: LabelSamples, position: int, total: int
    ) -> AssignmentEntry | Literal["skip", "quit"]:
        say = self.console.say
        say("")
        say(
            f"[{position}/{total}] segment {found.segment}, {found.label}: {_measure(found)}"
        )
        say(f"  now: {self._now(found)}")
        letters = _LETTERS[: len(found.samples)]
        for letter, sample in zip(letters, found.samples, strict=False):
            say(f"  {letter}) {sample_line(sample)}")
        if letters:
            play_help = _HELP_PLAY.format(first=letters[0], last=letters[-1])
            help_line = f"{play_help}\n{self.help_assign}"
        else:
            say("  no passage with speech time")
            help_line = self.help_assign
        played: int | None = None
        while True:
            answer = self.console.ask(f"{help_line}\n> ").strip().lower()
            if letters and (answer in ("p", "", "r") or answer in letters):
                if answer in letters:
                    played = letters.index(answer)
                elif answer == "r":
                    played = played or 0
                else:
                    played = 0 if played is None else (played + 1) % len(letters)
                self._play(found, played)
                continue
            if answer in ("p", "", "r"):
                continue
            if answer == "s":
                return _SKIP
            if answer == "q":
                return _QUIT
            if answer in ("u", "m"):
                return self._entry(found, "unknown" if answer == "u" else "multiple")
            person = self._person(answer)
            if person is None:
                say(f"  not a choice: {answer}")
            elif self._confirm_merge(found, person):
                return self._entry(found, "person", person.user_id)

    def _person(self, answer: str) -> Participant | None:
        if not answer.isdigit():
            return None
        number = int(answer)
        return self.people[number - 1] if 1 <= number <= len(self.people) else None

    def _confirm_merge(self, found: LabelSamples, person: Participant) -> bool:
        """Ask before a second label of the segment goes to the same person."""
        others = [
            label
            for segment, label in self.applied.persons().get(person.user_id, ())
            if segment == found.segment and label != found.label
        ]
        return not others or self._yes(
            f"  {person.display_name} already speaks as {', '.join(others)} in "
            f"segment {found.segment}; the labels will be merged. Assign?"
        )

    def _entry(
        self,
        found: LabelSamples,
        assigned: speakers.Assigned,
        user_id: UserId | None = None,
    ) -> AssignmentEntry:
        return AssignmentEntry(
            found.segment, found.label, self.versions[found.segment], assigned, user_id
        )

    def _store(self, entry: AssignmentEntry) -> None:
        speakers.set_entry(self.paths, entry)
        self.assignment = speakers.with_entry(self.assignment, entry)
        self.applied = speakers.check(
            self.assignment, self.references, self.participants
        )
        self.console.say(f"  saved: {self._who(entry)}")

    def _now(self, found: LabelSamples) -> str:
        key = (found.segment, found.label)
        entry = self.applied.applied.get(key)
        if entry is not None:
            return self._who(entry)
        earlier = next((e for e in self.assignment.entries if e.key == key), None)
        if earlier is None or earlier.assigned == "open":
            return "open"
        # stale or an unknown person: shown, replaced only by a new choice
        return f"open (not applied, earlier: {self._who(earlier)})"

    def _who(self, entry: AssignmentEntry) -> str:
        if entry.user_id is None:
            return entry.assigned
        name = next(
            (p.display_name for p in self.people if p.user_id == entry.user_id),
            "not in the snapshot",
        )
        return f"{name} (person {entry.user_id})"

    def _play(self, found: LabelSamples, index: int) -> None:
        sample = found.samples[index]
        letter = _LETTERS[index]
        if sample.local_start_ms is None:
            self.console.say(f"  sample {letter} has no time to play from")
            return
        wav = self.paths.segment_wav(found.segment)
        seconds = sample_ms(sample.local_start_ms, sample.local_end_ms) / 1000
        self.console.say(
            f"  ▶ playing audio: sample {letter}, {seconds:.0f} s (Ctrl+C stops it) …"
        )
        played = self.console.play(wav, sample.local_start_ms, sample.local_end_ms)
        if played == "stopped":
            self.console.say("  ■ stopped")
        elif played != "played":
            reason = "ffplay not found" if played == "missing" else "playback failed"
            where = f"{wav} at {format_ms(sample.local_start_ms)}"
            self.console.say(f"  {reason}; listen in {where}")

    def _ask_effort(self, start: float) -> None:
        """Offer the measured minutes as effort; stored only on `y`."""
        minutes = math.ceil((self.console.clock() - start) / 60)
        before = self.assignment.effort_minutes
        total = (before or 0) + minutes
        now = "none" if before is None else str(before)
        if self._yes(
            f"\nThis run took about {minutes} minute(s). Store effort_minutes "
            f"{total} (now {now})?"
        ):
            speakers.set_effort(self.paths, total)
            self.console.say(f"  saved: effort_minutes {total}")

    def _yes(self, question: str) -> bool:
        return self.console.ask(f"{question} [y/N] ").strip().lower() == "y"


def _measure(found: LabelSamples) -> str:
    share = "" if found.share is None else f" ({found.share:.0%} of the segment)"
    merge = ", candidate for merging" if found.merge_candidate else ""
    return f"speech {format_ms(found.speech_ms)}{share}{merge}"
