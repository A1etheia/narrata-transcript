"""Session time values: integer milliseconds and their `HH:MM:SS.mmm` form.

Times are stored as whole milliseconds so that sums over long sessions do not drift
and adjacent segments share their boundary exactly.
"""

import math
import re

_TIMECODE_PATTERN = re.compile(r"([0-9]{2,}):([0-5][0-9]):([0-5][0-9])\.([0-9]{3})")
_MS_PER_SECOND = 1000
_MS_PER_MINUTE = 60 * _MS_PER_SECOND
_MS_PER_HOUR = 60 * _MS_PER_MINUTE


def format_ms(ms: int) -> str:
    """Render milliseconds as `HH:MM:SS.mmm`; hours grow past 99 instead of wrapping."""
    if ms < 0:
        raise ValueError(f"negative time: {ms} ms")
    hours, rest = divmod(ms, _MS_PER_HOUR)
    minutes, rest = divmod(rest, _MS_PER_MINUTE)
    seconds, millis = divmod(rest, _MS_PER_SECOND)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def parse_timecode(text: str) -> int:
    """Parse `HH:MM:SS.mmm` into milliseconds; the inverse of `format_ms`."""
    match = _TIMECODE_PATTERN.fullmatch(text)
    if match is None:
        raise ValueError(f"invalid timecode: {text!r}, expected HH:MM:SS.mmm")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return (
        hours * _MS_PER_HOUR
        + minutes * _MS_PER_MINUTE
        + seconds * _MS_PER_SECOND
        + millis
    )


def frames_to_ms(frames: int, sample_rate: int) -> int:
    """Convert a sample count to milliseconds, rounding half up in integer arithmetic.

    The conversion is monotonic, so cumulative frame counts never yield a negative
    duration or a gap between segments.
    """
    if frames < 0:
        raise ValueError(f"negative frame count: {frames}")
    if sample_rate <= 0:
        raise ValueError(f"invalid sample rate: {sample_rate}")
    return (2 * frames * _MS_PER_SECOND + sample_rate) // (2 * sample_rate)


def seconds_to_ms(seconds: float) -> int:
    """Convert a time in seconds, as ASR backends report it, to milliseconds."""
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"invalid time: {seconds!r} s")
    return round(seconds * _MS_PER_SECOND)
