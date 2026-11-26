"""Level normalisation of a segment WAV before the recognition (TOOL-109).

ffmpeg's `loudnorm` in two passes: the first measures the whole segment, the
second normalises with what was measured. The raw WAV is only read. The
filtered copy has the same length, so times stay valid, and lies with a record
of how it was made in `audio/level/`; a copy without a matching record is made
again.
"""

import json
import logging
import math
import os
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcript.audio import (
    WAV_CODEC,
    AudioError,
    run_tool,
    sha256_file,
    wav_frames,
    wav_shape,
)
from transcript.audio_tools import AudioTools
from transcript.jsonfile import DataFileError, encode, read_object
from transcript.session import SessionPaths

FILTER = "loudnorm"
# The one chain measured in TOOL-103 and TOOL-109; not configurable.
TARGET = {"I": -16.0, "TP": -1.5, "LRA": 11.0}
CHAIN = FILTER + "=" + ":".join(f"{key}={value:g}" for key, value in TARGET.items())
RECORD_FORMAT_VERSION = 1
# loudnorm option of the second pass -> the first pass's statistic that fills it
_MEASURED = {
    "measured_I": "input_i",
    "measured_LRA": "input_lra",
    "measured_TP": "input_tp",
    "measured_thresh": "input_thresh",
    "offset": "target_offset",
}

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Levelled:
    """The filtered WAV of one segment."""

    path: Path
    seconds: float | None  # both ffmpeg passes together; None: a stored copy fitted

    @property
    def reused(self) -> bool:
        return self.seconds is None


def settings(tools: AudioTools) -> dict[str, str]:
    """What decides the filtered audio besides the raw WAV, as in `asr.settings`."""
    return {"chain": CHAIN, "ffmpeg": tools.ffmpeg.version}


def ensure(paths: SessionPaths, index: int, frames: int, tools: AudioTools) -> Levelled:
    """The level-normalised copy of segment `index`, made unless a stored one fits.

    `frames` is the segment's length in the manifest. A stored copy fits when
    its record names this chain, this ffmpeg version and this raw WAV. A failed
    or interrupted run leaves the files of an earlier one as they were.
    """
    raw = paths.segment_wav(index)
    found, rate, channels = wav_shape(raw)
    if found != frames:
        raise AudioError(
            f"{raw.name}: {found} frames, the manifest has {frames}; "
            "run transcript extract and transcript manifest"
        )
    wanted = {
        "format_version": RECORD_FORMAT_VERSION,
        **settings(tools),
        "raw_sha256": sha256_file(raw),
        "frames": frames,
        "sample_rate": rate,
    }
    target, record = paths.level_wav(index), paths.level_record(index)
    if _fits(record, target, wanted):
        return Levelled(target, None)

    paths.level_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(dir=paths.level_dir, prefix=".level-") as tmp:
        options, measured = _measure(raw, tools)
        pending = Path(tmp) / target.name
        _normalise(raw, pending, options, (frames, rate, channels), tools)
        seconds = round(time.monotonic() - started, 1)
        content = {
            **wanted,
            "measured": measured,
            "linear_expected": _linear_expected(measured),
            "filter_seconds": seconds,
        }
        pending_record = Path(tmp) / record.name
        pending_record.write_bytes(encode(content))
        # The old record goes first: it must never describe the new WAV.
        record.unlink(missing_ok=True)
        os.replace(pending, target)
        os.replace(pending_record, record)
    _logger.info(
        "%s segment %d: %s in %.0f s, input %.1f LUFS, range %.1f LU, peak %.1f dBTP",
        paths.key,
        index,
        FILTER,
        seconds,
        measured["input_i"],
        measured["input_lra"],
        measured["input_tp"],
    )
    return Levelled(target, seconds)


def _fits(record: Path, target: Path, wanted: Mapping[str, Any]) -> bool:
    """Whether the stored copy was made as `wanted`; the record is written last."""
    if not target.is_file():
        return False
    try:
        content = read_object(record, "level record")
    except DataFileError:
        return False  # a missing or unreadable record: the copy is made again
    return all(content.get(key) == value for key, value in wanted.items())


def _measure(raw: Path, tools: AudioTools) -> tuple[list[str], dict[str, float]]:
    """The first pass over the whole WAV: loudnorm's options for the second
    pass, digit for digit as ffmpeg printed the values, and the values."""
    args = ["-nostdin", "-hide_banner", "-v", "info", "-i", str(raw)]
    args += ["-af", f"{CHAIN}:print_format=json", "-f", "null", "-"]
    try:
        result = run_tool(tools.ffmpeg, args, raw, timeout=None)
    except AudioError as error:
        raise AudioError(f"{raw.name}: level measurement failed ({error})") from error
    start, end = result.stderr.rfind("{"), result.stderr.rfind("}")
    try:
        stats = json.loads(result.stderr[start : end + 1]) if 0 <= start < end else {}
        measured = {name: float(stats[name]) for name in _MEASURED.values()}
    except (ValueError, KeyError, TypeError) as error:
        raise AudioError(f"{raw.name}: level measurement gave no statistics") from error
    if not all(math.isfinite(value) for value in measured.values()):
        # digital silence or less audio than loudnorm can measure
        raise AudioError(
            f"{raw.name}: level cannot be measured, the audio is silent or too short"
        )
    options = [f"{option}={stats[name]}" for option, name in _MEASURED.items()]
    return options, measured


def _normalise(
    raw: Path,
    target: Path,
    options: list[str],
    shape: tuple[int, int, int],
    tools: AudioTools,
) -> None:
    """The second pass into `target`, padded or cut to the raw WAV's `shape`."""
    frames, rate, channels = shape
    filters = [
        ":".join([CHAIN, *options, "linear=true"]),
        f"aresample={rate}",  # loudnorm works at 192 kHz
        f"apad=whole_len={frames}",
        f"atrim=end_sample={frames}",
    ]
    args = ["-nostdin", "-v", "error", "-y", "-i", str(raw), "-af", ",".join(filters)]
    # without `-ac` ffmpeg 4.4 finds no channel layout behind aresample
    args += ["-ar", str(rate), "-ac", str(channels), "-c:a", WAV_CODEC]
    args += ["-map_metadata", "-1", "-f", "wav", str(target)]
    try:
        run_tool(tools.ffmpeg, args, raw, timeout=None)
    except AudioError as error:
        raise AudioError(f"{raw.name}: level filter failed ({error})") from error
    if wav_frames(target) != (frames, rate):
        raise AudioError(f"{raw.name}: level filter changed the length of the audio")


def _linear_expected(measured: Mapping[str, float]) -> bool:
    """Whether loudnorm applies one fixed gain rather than levelling dynamically.

    As in ffmpeg's af_loudnorm.c: the gain must keep the true peak under the
    target and the measured range must fit the target range.
    """
    peak = measured["input_tp"] + TARGET["I"] - measured["input_i"]
    return peak <= TARGET["TP"] and measured["input_lra"] <= TARGET["LRA"]
