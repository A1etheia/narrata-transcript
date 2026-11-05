import dataclasses
import datetime
import unittest

from transcript.manifest import Manifest, Segment, SourceRecording
from transcript.reference import (
    AsrInfo,
    Passage,
    Processing,
    ReferenceTranscript,
    SegmentRef,
    Word,
)
from transcript.session import SessionKey
from transcript.session_time import (
    END_TOLERANCE_MS,
    SessionSpan,
    passage_span,
    segment_of,
    time_granularity,
    word_span,
)
from transcript.timecode import parse_timecode

KEY = SessionKey("beispielgruppe", 42)
SOURCE = SourceRecording(
    file="aufnahme.m4a",
    size_bytes=1000,
    sha256="ab" * 32,
    container="mov,mp4,m4a,3gp,3g2,mj2",
    audio_index=0,
    stream_index=0,
)
FIRST = Segment(
    index=1,
    file="segment-01.wav",
    source=SOURCE,
    frames=0,
    start_ms=0,
    end_ms=parse_timecode("01:19:45.000"),
    overlap_before_ms=0,
)
# Starts 2 s before the first ends, as split recordings would.
SECOND = Segment(
    index=2,
    file="segment-02.wav",
    source=SOURCE,
    frames=0,
    start_ms=FIRST.end_ms - 2000,
    end_ms=FIRST.end_ms - 2000 + parse_timecode("00:10:00.000"),
    overlap_before_ms=2000,
)
MANIFEST = Manifest(
    key=KEY,
    play_session_id=4711,  # made up; real ids never enter the repo
    session_date=datetime.date(2026, 11, 4),
    consent=None,
    sample_rate=16000,
    channels=1,
    segments=(FIRST, SECOND),
)


def reference(*passages: Passage, segment: Segment = SECOND) -> ReferenceTranscript:
    return ReferenceTranscript(
        key=KEY,
        play_session_id=4711,
        segment=SegmentRef(
            index=segment.index, file=segment.file, source_sha256=SOURCE.sha256
        ),
        status="transcribed",
        asr=AsrInfo(backend_id="fake", model="fake"),
        processing=Processing(
            pipeline_version="0.0.1", processed_at="2026-11-04T20:00:00+01:00"
        ),
        passages=passages,
    )


class SpanTest(unittest.TestCase):
    def test_word_time_becomes_session_time_and_keeps_local_time(self) -> None:
        segment = dataclasses.replace(
            SECOND,
            start_ms=parse_timecode("01:19:45.000"),
            end_ms=parse_timecode("01:29:45.000"),
        )
        local = parse_timecode("00:02:13.500")
        span = word_span(segment, Word("Wir", start_ms=local, end_ms=local + 300))

        self.assertEqual(
            span,
            SessionSpan(
                granularity="word",
                local_start_ms=133_500,
                local_end_ms=133_800,
                start_ms=parse_timecode("01:21:58.500"),
                end_ms=parse_timecode("01:21:58.800"),
            ),
        )

    def test_event_after_the_first_hour_shows_hours(self) -> None:
        span = passage_span(SECOND, Passage(1, "Text", start_ms=5000, end_ms=6000))

        assert span is not None
        self.assertEqual(span.granularity, "passage")
        self.assertEqual(span.timecode(), "01:19:48.000–01:19:49.000")

    def test_overlap_start_is_not_negative(self) -> None:
        span = passage_span(SECOND, Passage(1, "Text", start_ms=0, end_ms=0))

        assert span is not None
        self.assertEqual(span.start_ms, SECOND.start_ms)

    def test_missing_times_are_not_invented(self) -> None:
        self.assertIsNone(passage_span(SECOND, Passage(1, "Text")))
        self.assertIsNone(word_span(SECOND, Word("Text")))

        span = passage_span(SECOND, Passage(1, "Text", start_ms=1000))
        assert span is not None
        self.assertIsNone(span.end_ms)
        self.assertEqual(span.timecode(), "01:19:44.000–?")

    def test_end_just_past_the_wav_is_set_to_the_segment_end(self) -> None:
        for past in (400, END_TOLERANCE_MS):
            local_end = SECOND.duration_ms + past
            with self.subTest(past=past):
                span = word_span(SECOND, Word("Ende", start_ms=0, end_ms=local_end))

                assert span is not None
                self.assertEqual(span.end_ms, SECOND.end_ms)
                self.assertEqual(span.local_end_ms, local_end)
                self.assertTrue(span.clamped)

    def test_inside_the_wav_is_not_clamped(self) -> None:
        span = word_span(SECOND, Word("Ende", end_ms=SECOND.duration_ms))

        assert span is not None
        self.assertEqual(span.end_ms, SECOND.end_ms)
        self.assertFalse(span.clamped)

    def test_far_past_the_wav_is_an_error(self) -> None:
        local_end = SECOND.duration_ms + END_TOLERANCE_MS + 1
        with self.assertRaises(ValueError) as caught:
            word_span(SECOND, Word("Ende", start_ms=0, end_ms=local_end))

        self.assertIn(f"{local_end} ms lies outside segment 2", str(caught.exception))
        self.assertNotIn("Ende", str(caught.exception))


class GranularityTest(unittest.TestCase):
    def test_word_times_win(self) -> None:
        passage = Passage(
            1, "Wir", start_ms=0, end_ms=300, words=(Word("Wir", 0, 300),)
        )

        self.assertEqual(time_granularity(reference(passage)), "word")

    def test_passage_times_without_word_times(self) -> None:
        passage = Passage(1, "Wir", start_ms=0, end_ms=300, words=(Word("Wir"),))

        self.assertEqual(time_granularity(reference(passage)), "passage")

    def test_text_only_has_no_times(self) -> None:
        self.assertEqual(time_granularity(reference(Passage(1, "Wir"))), "none")
        self.assertEqual(time_granularity(reference()), "none")


class SegmentOfTest(unittest.TestCase):
    def test_finds_the_segment_of_the_transcript(self) -> None:
        self.assertEqual(segment_of(MANIFEST, reference()), SECOND)
        self.assertEqual(segment_of(MANIFEST, reference(segment=FIRST)), FIRST)

    def test_rejects_a_segment_from_another_source(self) -> None:
        changed = dataclasses.replace(
            MANIFEST, segments=(FIRST, dataclasses.replace(SECOND, file="other.wav"))
        )

        with self.assertRaisesRegex(ValueError, "segment 2 of the manifest"):
            segment_of(changed, reference())

    def test_rejects_an_unknown_segment(self) -> None:
        third = dataclasses.replace(SECOND, index=3)

        with self.assertRaisesRegex(ValueError, "segment 3 is not in the manifest"):
            segment_of(MANIFEST, reference(segment=third))


if __name__ == "__main__":
    unittest.main()
