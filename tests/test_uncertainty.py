import time
import unittest
from typing import Any

from test_reference import minimal

from transcript.asr.backend import FEATURES
from transcript.config import UncertaintyThresholds
from transcript.hints import Candidate, Hint, SegmentHints
from transcript.reference import (
    TIME_CAPABILITIES,
    AsrInfo,
    Diarization,
    Overlap,
    Passage,
    ReferenceTranscript,
    Word,
)
from transcript.uncertainty import PassageRating, Reason, assess

LIMITS = UncertaintyThresholds()
WHISPER = {"word_timestamps": True, "segment_timestamps": True}
CALM = {"no_speech_prob": 0.01, "avg_logprob": -0.2, "compression_ratio": 1.3}
PROCESSED_AT = "2026-11-04T20:00:00+01:00"  # as in test_reference.minimal


def words(*confidences: float | None, step: int = 300) -> tuple[Word, ...]:
    """Made-up words, each `step` ms after the previous one and 250 ms long."""
    return tuple(
        Word(f"wort{n}", n * step, n * step + 250, confidence, "SPEAKER_00")
        for n, confidence in enumerate(confidences)
    )


def passage(found: tuple[Word, ...] = (), index: int = 1, **changes: Any) -> Passage:
    values: dict[str, Any] = {
        "index": index,
        "text": " ".join(w.text for w in found),
        "start_ms": found[0].start_ms if found else 0,
        "end_ms": found[-1].end_ms if found else 0,
        "words": found,
        "speaker": "SPEAKER_00",
        "signals": dict(CALM),
    }
    values.update(changes)
    return Passage(**values)


def transcript(
    *passages: Passage,
    capabilities: dict[str, bool] | None = None,
    diarization: Diarization | None = None,
) -> ReferenceTranscript:
    return minimal(
        passages=passages,
        asr=AsrInfo(
            backend_id="fake",
            model="fake",
            capabilities=WHISPER if capabilities is None else capabilities,
        ),
        diarization=diarization,
    )


def diarized(*overlaps: Overlap) -> Diarization:
    return Diarization("fake", "fake", ("SPEAKER_00", "SPEAKER_01"), overlaps=overlaps)


def hint(signal: str = "known_variant", ambiguous: bool = False) -> Hint:
    candidate = Candidate("place", 1, "Grauwasser", "name", "name", "session", False)
    return Hint(
        passage=1,
        first_word=1,
        last_word=2,
        start_ms=300,
        end_ms=850,
        heard="Grau Wasser",
        signal=signal,  # type: ignore[arg-type]
        method=None if signal == "known_variant" else "spelling",
        score=None if signal == "known_variant" else 0.9,
        candidates=(candidate,),
        ambiguous=ambiguous,
    )


def hints(*found: Hint, processed_at: str = PROCESSED_AT) -> SegmentHints:
    return SegmentHints(1, "ab" * 32, processed_at, 0, found)


def rate(
    reference: ReferenceTranscript,
    found: SegmentHints | None = None,
    limits: UncertaintyThresholds = LIMITS,
) -> PassageRating:
    (rating,) = assess(reference, found, limits)
    return rating


def rules(rating: PassageRating) -> list[str]:
    return [reason.rule for reason in rating.reasons]


class LevelTest(unittest.TestCase):
    def test_a_clean_passage_with_every_signal_is_confident(self) -> None:
        rating = rate(transcript(passage(words(0.9, 0.95, 0.8))), hints())

        self.assertEqual(rating.level, "confident")
        self.assertEqual(rating.reasons, ())
        self.assertEqual(rating.missing, ("speaker",))

    def test_the_level_is_the_highest_of_the_reasons(self) -> None:
        reference = transcript(
            passage(
                words(0.1, 0.9, 0.9, 0.9, 0.9, 0.9),
                signals={**CALM, "compression_ratio": 3.0},
            )
        )

        rating = rate(reference)

        self.assertEqual(rating.level, "uncertain")
        self.assertEqual(rules(rating), ["very_low_confidence", "repetition"])

    def test_one_rating_per_passage_in_order(self) -> None:
        reference = transcript(
            passage(words(0.9), index=1), passage(words(0.9), index=2)
        )

        ratings = assess(reference, None, LIMITS)

        self.assertEqual([r.passage for r in ratings], [1, 2])

    def test_equal_input_gives_equal_output_and_leaves_the_input_alone(self) -> None:
        reference = transcript(passage(words(0.3, 0.9, 0.1), speaker=None))
        found = hints(hint())
        before = repr((reference, found))

        first = assess(reference, found, LIMITS)

        self.assertEqual(assess(reference, found, LIMITS), first)
        self.assertEqual(repr((reference, found)), before)


class ConfidenceTest(unittest.TestCase):
    def test_a_share_of_low_words_raises_the_level(self) -> None:
        cases = (
            ((0.9, 0.9, 0.9, 0.9, 0.9), None),
            ((0.4, 0.9, 0.9, 0.9, 0.9), "needs_review"),
            ((0.4, 0.4, 0.4, 0.9, 0.9), "uncertain"),
        )
        for confidences, level in cases:
            with self.subTest(confidences=confidences):
                rating = rate(transcript(passage(words(*confidences))))
                found = [r for r in rating.reasons if r.rule == "low_confidence"]
                self.assertEqual([r.level for r in found], [level] if level else [])

    def test_the_reason_names_share_threshold_and_words(self) -> None:
        rating = rate(transcript(passage(words(0.4, 0.9, 0.9, 0.9, 0.3))))

        self.assertEqual(
            rating.reasons,
            (Reason("low_confidence", "needs_review", 0.4, 0.2, (0, 4)),),
        )

    def test_one_very_low_word_is_enough_for_needs_review(self) -> None:
        rating = rate(transcript(passage(words(0.1, *[0.9] * 9))))

        self.assertEqual(
            rating.reasons,
            (Reason("very_low_confidence", "needs_review", 0.1, 0.2, (0,)),),
        )

    def test_thresholds_come_from_the_configuration(self) -> None:
        reference = transcript(passage(words(0.6, 0.9, 0.9, 0.9)))

        self.assertEqual(rate(reference).level, "confident")
        strict = UncertaintyThresholds(word_low=0.7, low_share_review=0.25)
        self.assertEqual(rate(reference, limits=strict).level, "needs_review")

    def test_without_confidence_the_rule_does_not_fire(self) -> None:
        rating = rate(transcript(passage(words(None, None))))

        self.assertNotIn("low_confidence", rules(rating))
        self.assertIn("word_confidence", rating.missing)


class SegmentSignalTest(unittest.TestCase):
    def test_each_signal_fires_past_its_threshold(self) -> None:
        cases = (
            ("no_speech_prob", 0.7, "no_speech", "needs_review"),
            ("avg_logprob", -1.2, "low_logprob", "needs_review"),
            ("compression_ratio", 2.6, "repetition", "uncertain"),
        )
        for name, value, rule, level in cases:
            with self.subTest(name=name):
                rating = rate(
                    transcript(passage(words(0.9), signals={**CALM, name: value}))
                )
                self.assertEqual(rules(rating), [rule])
                self.assertEqual(rating.level, level)

    def test_calm_signals_do_not_fire(self) -> None:
        self.assertEqual(rate(transcript(passage(words(0.9)))).reasons, ())

    def test_without_signals_the_rule_does_not_fire(self) -> None:
        rating = rate(transcript(passage(words(0.9), signals={})))

        self.assertEqual(rating.reasons, ())
        self.assertIn("segment_signals", rating.missing)


class TimingTest(unittest.TestCase):
    def test_a_long_pause_between_words_is_a_gap(self) -> None:
        found = (*words(0.9, 0.9), Word("spät", 2500, 2700, 0.9, "SPEAKER_00"))

        rating = rate(transcript(passage(found)))

        self.assertEqual(
            rating.reasons, (Reason("gap", "needs_review", 1950, 1500, (2,)),)
        )

    def test_sparse_speech_over_a_long_passage_needs_review(self) -> None:
        found = words(0.9, 0.9)
        rating = rate(transcript(passage(found, end_ms=4000)))

        self.assertEqual(rules(rating), ["sparse"])
        self.assertEqual(rating.reasons[0].value, 0.5)

    def test_a_short_passage_is_never_sparse(self) -> None:
        self.assertEqual(rate(transcript(passage(words(0.9)))).reasons, ())

    def test_backend_without_times_is_missing_not_flagged(self) -> None:
        untimed = (Word("wort", confidence=0.9),)
        reference = transcript(
            passage(untimed, start_ms=None, end_ms=None), capabilities={}
        )

        rating = rate(reference)

        self.assertEqual(rating.reasons, ())
        self.assertIn("word_times", rating.missing)

    def test_time_capabilities_are_backend_features(self) -> None:
        self.assertLessEqual(set(TIME_CAPABILITIES), set(FEATURES))
        for capabilities, expected in (
            ({}, False),
            ({"word_timestamps": "yes"}, False),
            ({"segment_timestamps": True}, True),
        ):
            with self.subTest(capabilities=capabilities):
                info = AsrInfo("fake", "fake", capabilities=capabilities)
                self.assertIs(info.delivers_times, expected)

    def test_times_a_backend_promises_but_lacks_need_review(self) -> None:
        found = (*words(0.9), Word("wort", confidence=0.9))

        rating = rate(transcript(passage(found, end_ms=250)))

        self.assertEqual(
            rating.reasons, (Reason("missing_times", "needs_review", 1, None, (1,)),)
        )


class NoSignalTest(unittest.TestCase):
    def test_a_passage_without_any_quality_signal_is_never_confident(self) -> None:
        reference = transcript(
            passage(
                (Word("wort"),), start_ms=None, end_ms=None, signals={}, speaker=None
            ),
            capabilities={},
        )

        rating = rate(reference, hints())

        self.assertEqual(rating.level, "needs_review")
        self.assertEqual(rules(rating), ["no_signals"])
        self.assertEqual(
            rating.missing,
            ("word_confidence", "segment_signals", "word_times", "speaker"),
        )

    def test_a_passage_without_words_is_not_rated_confident(self) -> None:
        rating = rate(transcript(passage(signals={}), capabilities={}))

        self.assertEqual(rating.level, "needs_review")


class SpeakerTest(unittest.TestCase):
    def test_no_majority_label_is_speaker_unclear(self) -> None:
        found = (Word("a", 0, 250, 0.9, "SPEAKER_00"), Word("b", 300, 550, 0.9, None))

        rating = rate(transcript(passage(found, speaker=None), diarization=diarized()))

        self.assertEqual(
            rating.reasons, (Reason("speaker_unclear", "needs_review", 1, None, (1,)),)
        )

    def test_an_overlap_with_the_passage_is_crosstalk(self) -> None:
        reference = transcript(
            passage(words(0.9, 0.9)),
            diarization=diarized(Overlap(400, 700), Overlap(5000, 6000)),
        )

        rating = rate(reference)

        self.assertEqual(rating.reasons, (Reason("crosstalk", "needs_review", 150),))

    def test_overlapping_crosstalk_ranges_count_once(self) -> None:
        reference = transcript(
            passage(words(0.9, 0.9)),
            diarization=diarized(
                Overlap(500, 600), Overlap(100, 300), Overlap(200, 400), Overlap(0, 50)
            ),
        )

        rating = rate(reference)

        self.assertEqual(rating.reasons, (Reason("crosstalk", "needs_review", 400),))

    def test_crosstalk_is_found_among_many_ranges(self) -> None:
        overlaps = tuple(Overlap(n * 1000, n * 1000 + 100) for n in range(20000))
        passages = [
            passage(words(0.9, 0.9), index=1, start_ms=50, end_ms=550),
            passage(words(0.9, 0.9), index=2, start_ms=5200, end_ms=5800),
        ]
        reference = transcript(*passages, diarization=diarized(*overlaps))

        started = time.perf_counter()
        ratings = assess(reference, None, LIMITS)

        self.assertLess(time.perf_counter() - started, 1)
        self.assertEqual([r.level for r in ratings], ["needs_review", "confident"])
        self.assertEqual(ratings[0].reasons[0].value, 50)

    def test_a_clear_speaker_without_overlap_is_fine(self) -> None:
        rating = rate(
            transcript(passage(words(0.9)), diarization=diarized(Overlap(900, 1000)))
        )

        self.assertEqual(rating.reasons, ())
        self.assertNotIn("speaker", rating.missing)

    def test_without_diarization_speakers_are_missing(self) -> None:
        rating = rate(transcript(passage(words(0.9), speaker=None)))

        self.assertEqual(rating.reasons, ())
        self.assertIn("speaker", rating.missing)


class HintTest(unittest.TestCase):
    def test_hint_signals_raise_the_level(self) -> None:
        cases = (
            (hint("known_variant"), "known_variant", "needs_review"),
            (hint("similar"), "similar", "needs_review"),
            (hint("similar", ambiguous=True), "ambiguous", "uncertain"),
            (hint("known_variant", ambiguous=True), "ambiguous", "uncertain"),
        )
        for found, rule, level in cases:
            with self.subTest(rule=rule, signal=found.signal):
                rating = rate(transcript(passage(words(0.9, 0.9, 0.9))), hints(found))
                self.assertEqual(rules(rating), [rule])
                self.assertEqual(rating.level, level)
                self.assertEqual(rating.reasons[0].words, (1, 2))

    def test_the_similar_level_comes_from_the_configuration(self) -> None:
        reference = transcript(passage(words(0.9, 0.9, 0.9)))
        found = hints(hint("similar"))

        quiet = UncertaintyThresholds(similar_level="confident")
        self.assertEqual(rate(reference, found, quiet).reasons, ())
        loud = UncertaintyThresholds(similar_level="uncertain")
        self.assertEqual(rate(reference, found, loud).level, "uncertain")

    def test_hints_of_another_passage_do_not_count(self) -> None:
        reference = transcript(
            passage(words(0.9), index=1), passage(words(0.9), index=2)
        )

        ratings = assess(reference, hints(hint()), LIMITS)

        self.assertEqual([r.level for r in ratings], ["needs_review", "confident"])

    def test_hints_of_another_transcript_version_are_missing(self) -> None:
        found = hints(hint(), processed_at="2026-11-05T08:00:00+01:00")

        rating = rate(transcript(passage(words(0.9, 0.9, 0.9))), found)

        self.assertEqual(rating.reasons, ())
        self.assertIn("hints", rating.missing)

    def test_without_hints_they_are_missing(self) -> None:
        self.assertIn("hints", rate(transcript(passage(words(0.9)))).missing)


if __name__ == "__main__":
    unittest.main()
