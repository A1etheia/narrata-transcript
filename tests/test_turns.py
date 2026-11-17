import unittest

from transcript.diarization.turns import (
    MinTurn,
    can_split,
    rejoin,
    split_at_speaker_changes,
)
from transcript.reference import Passage, Word

SIGNALS = {"avg_logprob": -0.4, "no_speech_prob": 0.1, "compression_ratio": 1.2}


def passage(*words: Word, text: str | None = None) -> Passage:
    timed = [w for w in words if w.start_ms is not None]
    return Passage(
        index=3,
        text=" ".join(w.text for w in words) if text is None else text,
        start_ms=0 if timed else None,
        end_ms=timed[-1].end_ms + 100 if timed else None,
        words=words,
        speaker="A",
        signals=SIGNALS,
    )


def w(text: str, start: int | None, speaker: str | None) -> Word:
    end = None if start is None else start + 300
    return Word(text, start, end, 0.9, speaker)


def labels(parts: tuple[Passage, ...]) -> list[list[str | None]]:
    return [[word.speaker for word in part.words] for part in parts]


class SplitTest(unittest.TestCase):
    def test_cuts_at_every_label_change(self) -> None:
        p = passage(
            w("eins", 0, "A"),
            w("zwei", 400, "A"),
            w("drei", 800, "B"),
            w("vier", 1200, "A"),
        )
        parts = split_at_speaker_changes(p)
        self.assertEqual(labels(parts), [["A", "A"], ["B"], ["A"]])
        self.assertEqual([part.speaker for part in parts], ["A", "B", "A"])
        self.assertEqual([part.text for part in parts], ["eins zwei", "drei", "vier"])

    def test_parts_keep_index_signals_and_outer_times(self) -> None:
        p = passage(w("eins", 0, "A"), w("zwei", 400, "B"))
        first, second = split_at_speaker_changes(p)
        self.assertEqual((first.index, second.index), (3, 3))
        self.assertEqual(first.signals, SIGNALS)
        self.assertEqual(second.signals, SIGNALS)
        self.assertEqual((first.start_ms, first.end_ms), (p.start_ms, 300))
        self.assertEqual((second.start_ms, second.end_ms), (400, p.end_ms))

    def test_one_label_leaves_the_passage_as_it_is(self) -> None:
        p = passage(w("eins", 0, "A"), w("zwei", 400, "A"))
        self.assertEqual(split_at_speaker_changes(p), (p,))

    def test_unlabelled_words_stay_with_the_run_before(self) -> None:
        p = passage(
            w("eins", None, None),
            w("zwei", 0, "A"),
            w("drei", None, None),
            w("vier", 800, "B"),
        )
        self.assertEqual(
            labels(split_at_speaker_changes(p)), [[None, "A", None], ["B"]]
        )

    def test_a_text_other_than_the_words_is_never_cut(self) -> None:
        p = passage(w("eins", 0, "A"), w("zwei", 400, "B"), text="eins, zwei")
        self.assertFalse(can_split(p))
        self.assertEqual(split_at_speaker_changes(p), (p,))

    def test_a_passage_without_words_is_never_cut(self) -> None:
        p = Passage(index=1, text="")
        self.assertFalse(can_split(p))
        self.assertEqual(split_at_speaker_changes(p), (p,))


class MinTurnTest(unittest.TestCase):
    def test_a_short_run_is_drawn_into_the_previous_one(self) -> None:
        p = passage(
            w("eins", 0, "A"),
            w("zwei", 400, "A"),
            w("drei", 800, "B"),
            w("vier", 1200, "C"),
            w("fünf", 1600, "C"),
        )
        parts = split_at_speaker_changes(p, MinTurn(words=2))
        self.assertEqual(labels(parts), [["A", "A", "B"], ["C", "C"]])
        self.assertEqual([part.speaker for part in parts], ["A", "C"])

    def test_a_short_run_between_equal_labels_merges_all_three(self) -> None:
        p = passage(
            w("eins", 0, "A"),
            w("zwei", 400, "A"),
            w("drei", 800, "B"),  # 300 ms, below the threshold
            w("vier", 1200, "A"),
            w("fünf", 1600, "A"),
        )
        parts = split_at_speaker_changes(p, MinTurn(ms=500))
        self.assertEqual(parts, (p,))

    def test_a_short_first_run_is_drawn_into_the_next_one(self) -> None:
        p = passage(w("eins", 0, "B"), w("zwei", 400, "A"), w("drei", 800, "A"))
        parts = split_at_speaker_changes(p, MinTurn(words=2))
        self.assertEqual(labels(parts), [["B", "A", "A"]])
        self.assertEqual(parts[0].speaker, "A")

    def test_duration_rule_measures_the_labelled_words(self) -> None:
        # B lasts 0..700 ms (two words), A 1200..1500
        p = passage(w("eins", 0, "B"), w("zwei", 400, "B"), w("drei", 1200, "A"))
        self.assertEqual(len(split_at_speaker_changes(p, MinTurn(ms=700))), 1)
        self.assertEqual(len(split_at_speaker_changes(p, MinTurn(ms=300))), 2)

    def test_negative_threshold_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            MinTurn(ms=-1)


class RejoinTest(unittest.TestCase):
    def test_rejoin_undoes_the_split(self) -> None:
        p = passage(
            w("eins", None, None),
            w("zwei", 0, "A"),
            w("drei", 400, "B"),
            w("vier", 800, "B"),
            w("fünf", 1200, "A"),
            w("sechs", 1600, "A"),
        )
        for min_turn in (MinTurn(), MinTurn(words=2), MinTurn(ms=500)):
            with self.subTest(min_turn=min_turn):
                self.assertEqual(rejoin(split_at_speaker_changes(p, min_turn)), p)

    def test_no_part_holds_two_labels_without_a_threshold(self) -> None:
        p = passage(*(w(str(n), n * 400, "AB"[n % 2]) for n in range(6)))
        for part in split_at_speaker_changes(p):
            self.assertEqual(len({word.speaker for word in part.words}), 1)

    def test_nothing_to_rejoin_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            rejoin(())


if __name__ == "__main__":
    unittest.main()
