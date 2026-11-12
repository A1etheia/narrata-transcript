import dataclasses
import json
import unittest
from collections.abc import Iterator
from pathlib import Path

from test_candidates import _SessionCase
from test_speakers import FIRST, NAME, PARTICIPANTS, SECOND, entry, participant

from transcript.speaker_assign import Console, queue, run
from transcript.speaker_player import Played
from transcript.speaker_samples import LabelSamples, Sample, ordered
from transcript.speakers import (
    SpeakerAssignment,
    check,
    load_assignment,
    write_assignment,
)

# Every name, id and text below is made up.


def labelled(segment: int, label: str, speech_ms: int) -> LabelSamples:
    sample = Sample(
        passage=1,
        speech_ms=speech_ms,
        local_start_ms=4_000,
        local_end_ms=6_500,
        span=None,
        text="Beispielsatz",
    )
    return LabelSamples(
        segment, f"segment-{segment:02d}.wav", label, speech_ms, 0.5, (sample,)
    )


# FIRST has SPEAKER_00 and SPEAKER_01, SECOND has SPEAKER_00
LABELS = (
    labelled(1, "SPEAKER_00", 1_000),
    labelled(1, "SPEAKER_01", 5_000),
    labelled(2, "SPEAKER_00", 2_000),
)
REFERENCES = (FIRST, SECOND)


class Script:
    """Answers in order; an exception in the list is raised instead."""

    def __init__(self, *answers: str | BaseException) -> None:
        self._answers: Iterator[str | BaseException] = iter(answers)
        self.said: list[str] = []
        self.played: list[tuple[Path, int, int | None]] = []
        self.result: Played = "played"
        self.now = 0.0

    def ask(self, prompt: str) -> str:
        self.said.append(prompt)
        answer = next(self._answers)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def play(self, wav: Path, start: int, end: int | None) -> Played:
        self.played.append((wav, start, end))
        return self.result

    def clock(self) -> float:
        self.now += 90  # each look at the clock is 1.5 minutes later
        return self.now

    def console(self) -> Console:
        return Console(self.ask, self.said.append, self.play, self.clock)


class QueueTest(unittest.TestCase):
    def test_per_segment_the_label_with_most_speech_comes_first(self) -> None:
        applied = check(SpeakerAssignment(), REFERENCES, PARTICIPANTS)

        order = [(f.segment, f.label) for f in queue(LABELS, applied, every=False)]

        self.assertEqual(
            order, [(1, "SPEAKER_01"), (1, "SPEAKER_00"), (2, "SPEAKER_00")]
        )

    def test_only_labels_without_an_applied_decision_unless_all(self) -> None:
        assignment = SpeakerAssignment(
            (
                entry(FIRST, "SPEAKER_00", 11),  # applied
                entry(FIRST, "SPEAKER_01", 12, version="0" * 16),  # stale
                entry(SECOND, "SPEAKER_00"),  # open
            )
        )
        applied = check(assignment, REFERENCES, PARTICIPANTS)

        asked = [(f.segment, f.label) for f in queue(LABELS, applied, every=False)]
        every = queue(LABELS, applied, every=True)

        self.assertEqual(asked, [(1, "SPEAKER_01"), (2, "SPEAKER_00")])
        self.assertEqual(len(every), 3)

    def test_present_then_active_then_former_participants(self) -> None:
        present = dataclasses.replace(participant(14), present=True)

        order = [p.user_id for p in ordered((*PARTICIPANTS, present))]

        # 13 is a former member; within a group by name
        self.assertEqual(order, [14, 11, 12, 13])


class DialogueTest(_SessionCase):
    def setUp(self) -> None:
        super().setUp()
        self.assignment = SpeakerAssignment()

    def store(self, assignment: SpeakerAssignment) -> None:
        write_assignment(self.paths, assignment)
        self.assignment = assignment

    def run_dialogue(self, script: Script, every: bool = False, labels=LABELS):
        return run(
            self.paths, labels, REFERENCES, PARTICIPANTS, self.assignment,
            script.console(), every,
        )  # fmt: skip

    def stored(self) -> dict[tuple[int, str], tuple[str, int | None]]:
        loaded = load_assignment(self.paths)
        assert loaded is not None
        return {e.key: (e.assigned, e.user_id) for e in loaded.entries}

    def test_every_label_is_assigned_without_an_editor(self) -> None:
        script = Script("p", "1", "u", "m", "y")

        outcome = self.run_dialogue(script)

        self.assertEqual((outcome.saved, outcome.skipped), (3, 0))
        self.assertFalse(outcome.interrupted)
        self.assertEqual(
            self.stored(),
            {
                (1, "SPEAKER_01"): ("person", 11),
                (1, "SPEAKER_00"): ("unknown", None),
                (2, "SPEAKER_00"): ("multiple", None),
            },
        )
        loaded = load_assignment(self.paths)
        assert loaded is not None
        applied = check(loaded, REFERENCES, PARTICIPANTS)
        self.assertEqual(applied.findings, ())
        # the scripted clock moves 1.5 minutes from start to end; rounded up
        self.assertEqual(loaded.effort_minutes, 2)

    def test_a_sample_plays_from_the_segment_wav_at_its_own_time(self) -> None:
        script = Script("p", "r", "s", "s", "s", "")

        self.run_dialogue(script)

        wav = self.paths.segment_wav(1)
        self.assertEqual(script.played, [(wav, 4_000, 6_500)] * 2)

    def test_a_letter_plays_that_sample_and_says_audio_is_coming(self) -> None:
        first = LABELS[1].samples[0]
        later = dataclasses.replace(first, local_start_ms=9_000, local_end_ms=30_000)
        labels = (
            LABELS[0],
            dataclasses.replace(LABELS[1], samples=(first, later)),
            LABELS[2],
        )
        script = Script("b", "a", "p", "s", "s", "s", "")

        self.run_dialogue(script, labels=labels)

        self.assertIn("  b) ?", [line[:6] for line in script.said])
        self.assertEqual(
            [start for _, start, _ in script.played], [9_000, 4_000, 9_000]
        )
        self.assertIn(
            "  ▶ playing audio: sample b, 12 s (Ctrl+C stops it) …", script.said
        )
        self.assertTrue(
            any(p.startswith("play audio: [a-b] that sample") for p in script.said)
        )

    def test_every_prompt_lists_the_people_to_choose_from(self) -> None:
        script = Script("p", "s", "s", "s", "")

        self.run_dialogue(script)

        prompts = [line for line in script.said if line.endswith("> ")]
        self.assertEqual(len(prompts), 4)  # twice for the first label, once each
        people = ordered(PARTICIPANTS)
        for prompt in prompts:
            self.assertIn(f"[1] {people[0].display_name} ({people[0].role})", prompt)
            self.assertIn(f"[{len(people)}] {people[-1].display_name}", prompt)

    def test_a_stopped_sample_keeps_the_dialogue_going(self) -> None:
        script = Script("p", "1", "s", "s", "")
        script.result = "stopped"

        outcome = self.run_dialogue(script)

        self.assertIn("  ■ stopped", script.said)
        self.assertFalse(outcome.interrupted)
        self.assertEqual(outcome.saved, 1)

    def test_a_number_picks_a_person_never_a_sample(self) -> None:
        script = Script("1", "s", "s", "")

        self.run_dialogue(script)

        self.assertEqual(script.played, [])
        self.assertEqual(self.stored(), {(1, "SPEAKER_01"): ("person", 11)})

    def test_without_player_the_file_and_time_are_named(self) -> None:
        script = Script("p", "s", "s", "s", "")
        script.result = "missing"

        self.run_dialogue(script)

        self.assertIn(
            f"  ffplay not found; listen in {self.paths.segment_wav(1)} at 00:00:04.000",
            script.said,
        )

    def test_an_interrupt_keeps_every_confirmed_choice(self) -> None:
        script = Script("1", KeyboardInterrupt())

        outcome = self.run_dialogue(script)

        self.assertTrue(outcome.interrupted)
        self.assertEqual(outcome.saved, 1)
        self.assertEqual(self.stored(), {(1, "SPEAKER_01"): ("person", 11)})

    def test_skipped_and_untouched_entries_stay_as_they_were(self) -> None:
        stale = entry(FIRST, "SPEAKER_01", 12, version="0" * 16)
        self.store(SpeakerAssignment((stale, entry(SECOND, "SPEAKER_00", 12)), 4))
        before = json.loads(self.paths.speaker_assignment.read_text("utf-8"))
        script = Script("s", "u", "n")  # skip the stale label, settle the open one

        outcome = self.run_dialogue(script)

        self.assertEqual((outcome.saved, outcome.skipped), (1, 1))
        after = json.loads(self.paths.speaker_assignment.read_text("utf-8"))
        self.assertEqual(after["entries"][:2], before["entries"])
        self.assertEqual(after["entries"][2]["assigned"], "unknown")
        self.assertEqual(after["effort_minutes"], 4)  # declined
        self.assertIn(
            f"  now: open (not applied, earlier: {NAME} 12 (person 12))", script.said
        )

    def test_a_second_label_of_one_person_needs_a_yes(self) -> None:
        script = Script("1", "1", "n", "1", "y", "s", "")

        self.run_dialogue(script)

        self.assertEqual(
            self.stored(),
            {(1, "SPEAKER_01"): ("person", 11), (1, "SPEAKER_00"): ("person", 11)},
        )
        self.assertTrue(any("will be merged" in line for line in script.said))

    def test_quit_stops_asking_but_still_offers_the_effort(self) -> None:
        script = Script("q", "y")

        outcome = self.run_dialogue(script)

        self.assertEqual((outcome.saved, outcome.skipped), (0, 3))
        loaded = load_assignment(self.paths)
        assert loaded is not None
        self.assertEqual(loaded.entries, ())
        self.assertEqual(loaded.effort_minutes, 2)

    def test_nothing_chosen_leaves_no_file(self) -> None:
        self.run_dialogue(Script("s", "s", "s", "n"))

        self.assertFalse(self.paths.speaker_assignment.exists())

    def test_every_decided_label_is_asked_only_with_all(self) -> None:
        self.store(
            SpeakerAssignment(
                (
                    entry(FIRST, "SPEAKER_00", 11),
                    entry(FIRST, "SPEAKER_01", 12),
                    entry(SECOND, "SPEAKER_00", 12),
                )
            )
        )

        quiet = Script()
        self.assertEqual(self.run_dialogue(quiet).saved, 0)
        self.assertIn("Every label is decided; --all asks for them again.", quiet.said)

        again = Script("2", "s", "s", "n")
        self.assertEqual(self.run_dialogue(again, every=True).saved, 1)


if __name__ == "__main__":
    unittest.main()
