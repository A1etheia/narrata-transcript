import itertools
import unittest

from transcript.timecode import (
    format_clock,
    format_ms,
    frames_to_ms,
    parse_timecode,
    seconds_to_ms,
)


class TimecodeTest(unittest.TestCase):
    def test_local_time_plus_segment_start_gives_session_time(self) -> None:
        local = parse_timecode("00:02:13.500")
        segment_start = parse_timecode("01:19:45.000")

        self.assertEqual(format_ms(segment_start + local), "01:21:58.500")

    def test_format_keeps_counting_hours(self) -> None:
        self.assertEqual(format_ms(0), "00:00:00.000")
        self.assertEqual(format_ms(10 * 3_600_000 + 1), "10:00:00.001")
        self.assertEqual(format_ms(100 * 3_600_000 + 59_999), "100:00:59.999")

    def test_clock_rounds_down_to_the_second(self) -> None:
        self.assertEqual(format_clock(parse_timecode("01:42:17.999")), "01:42:17")
        self.assertEqual(format_clock(0), "00:00:00")
        self.assertEqual(format_clock(100 * 3_600_000), "100:00:00")
        with self.assertRaises(ValueError):
            format_clock(-1)

    def test_parse_and_format_round_trip(self) -> None:
        for text in ("00:00:00.000", "04:59:59.999", "05:00:00.000", "123:45:06.789"):
            with self.subTest(text=text):
                self.assertEqual(format_ms(parse_timecode(text)), text)

    def test_invalid_values_are_rejected(self) -> None:
        for text in ("1:00:00.000", "00:60:00.000", "00:00:60.000", "00:00:00.5", ""):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_timecode(text)
        with self.assertRaises(ValueError):
            format_ms(-1)

    def test_frames_round_half_up(self) -> None:
        self.assertEqual(frames_to_ms(8, 16000), 1)  # 0.5 ms
        self.assertEqual(frames_to_ms(7, 16000), 0)
        self.assertEqual(frames_to_ms(5 * 3600 * 16000, 16000), 18_000_000)
        self.assertEqual(frames_to_ms(1, 44100), 0)

    def test_cumulative_frames_leave_no_gap(self) -> None:
        parts = (7, 7, 7, 160_001, 3)
        boundaries = [
            frames_to_ms(frames, 16000)
            for frames in itertools.accumulate(parts, initial=0)
        ]

        durations = [b - a for a, b in itertools.pairwise(boundaries)]
        for frames, duration in zip(parts, durations, strict=True):
            with self.subTest(frames=frames):
                self.assertGreaterEqual(duration, 0)
                self.assertLessEqual(abs(duration - frames_to_ms(frames, 16000)), 1)

    def test_seconds_to_ms(self) -> None:
        self.assertEqual(seconds_to_ms(133.5), 133_500)
        self.assertEqual(seconds_to_ms(0.0004), 0)
        for value in (-0.001, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                seconds_to_ms(value)
