import unittest

from test_reference import minimal
from test_session_time import MANIFEST
from test_speakers import NAME, PARTICIPANTS, entry, segment

from transcript.reference import Diarization, Passage, SegmentRef, Word
from transcript.speaker_samples import (
    MERGE_SHARE,
    SAMPLES_PER_LABEL,
    label_samples,
    render,
    speech_ms,
)
from transcript.speakers import SpeakerAssignment, check

# Every word below is made up.
A, B = "SPEAKER_00", "SPEAKER_01"


def spoken(index: int, start_ms: int, length_ms: int, *labels: str) -> Passage:
    """A passage of one timed word per label, `length_ms` each, back to back."""
    words = tuple(
        Word(
            f" wort{n}",
            start_ms + n * length_ms,
            start_ms + (n + 1) * length_ms,
            0.9,
            label,
        )
        for n, label in enumerate(labels)
    )
    return Passage(
        index=index,
        text=f"  Satz   {index} ",
        start_ms=start_ms,
        end_ms=start_ms + len(labels) * length_ms,
        words=words,
        speaker=labels[0],
    )


def diarized(*passages: Passage, labels: tuple[str, ...] = (A, B)):
    return minimal(
        segment=SegmentRef(1, "segment-01.wav", "ab" * 32),
        passages=passages,
        diarization=Diarization(backend_id="fake", model="fake", labels=labels),
    )


class SpeechTimeTest(unittest.TestCase):
    def test_timed_words_count_for_their_own_label_only(self) -> None:
        mixed = spoken(1, 0, 500, A, A, B)

        self.assertEqual(speech_ms(mixed), {A: 1000, B: 500})

    def test_without_word_times_the_passage_counts_for_its_majority_label(
        self,
    ) -> None:
        untimed = Passage(index=1, text=" x", start_ms=0, end_ms=700, speaker=A)

        self.assertEqual(speech_ms(untimed), {A: 700})


class LabelSamplesTest(unittest.TestCase):
    def test_the_longest_passages_come_first_with_session_time(self) -> None:
        lengths = [300, 900, 100, 700, 500, 800, 200]
        passages = [
            spoken(n, n * 10_000, ms, A) for n, ms in enumerate(lengths, start=1)
        ]

        (found_a, _) = label_samples(MANIFEST, [diarized(*passages)])

        self.assertEqual(len(found_a.samples), SAMPLES_PER_LABEL)
        self.assertEqual(
            [s.speech_ms for s in found_a.samples], [900, 800, 700, 500, 300]
        )
        first = found_a.samples[0]
        self.assertEqual(
            (first.passage, first.local_start_ms, first.local_end_ms),
            (2, 20_000, 20_900),
        )
        assert first.span is not None
        self.assertEqual(first.span.start_ms, 20_000)
        self.assertEqual(first.text, "Satz 2")
        self.assertEqual(found_a.speech_ms, sum(lengths))

    def test_a_label_with_little_speech_is_a_merge_candidate(self) -> None:
        reference = diarized(spoken(1, 0, 10_000, A), spoken(2, 20_000, 200, B))

        found_a, found_b = label_samples(MANIFEST, [reference])

        self.assertFalse(found_a.merge_candidate)
        self.assertTrue(found_b.merge_candidate)
        assert found_b.share is not None
        self.assertLess(found_b.share, MERGE_SHARE)

    def test_a_label_speaking_only_inside_others_passages_has_no_sample(self) -> None:
        found_a, found_b = label_samples(
            MANIFEST, [diarized(spoken(1, 0, 500, A, A, B))]
        )

        self.assertEqual(found_b.speech_ms, 500)
        self.assertEqual(found_b.samples, ())
        self.assertEqual(len(found_a.samples), 1)

    def test_a_label_of_the_diarization_without_words_is_listed(self) -> None:
        reference = diarized(spoken(1, 0, 500, A), labels=(A, B))

        (_, found_b) = label_samples(MANIFEST, [reference])

        self.assertEqual((found_b.speech_ms, found_b.samples), (0, ()))


class RenderTest(unittest.TestCase):
    def test_sheet_lists_participants_labels_assignment_and_samples(self) -> None:
        reference = segment(1, A, B)
        assignment = check(
            SpeakerAssignment((entry(reference, A, 11),)), [reference], PARTICIPANTS
        )

        sheet = render(
            minimal().key,
            label_samples(MANIFEST, [reference]),
            PARTICIPANTS,
            assignment,
        )

        self.assertIn("## Segment 1 (`segment-01.wav`)", sheet)
        self.assertIn(f"### {A}", sheet)
        self.assertIn("assigned: person 11", sheet)
        self.assertIn("assigned: open", sheet)
        self.assertIn("00:00:01.000–00:00:01.800 (WAV 00:00:01.000, passage 1", sheet)
        self.assertIn(f"| 11 | {NAME} 11 | player | active |", sheet)
        # active participants first, former ones still to choose
        self.assertLess(sheet.index(f"{NAME} 12"), sheet.index(f"{NAME} 13"))
        self.assertIn(f"| 13 | {NAME} 13 | player | former |", sheet)


if __name__ == "__main__":
    unittest.main()
