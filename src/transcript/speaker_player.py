"""Playing a few seconds of a segment's WAV to hear who speaks (TOOL-86).

`ffplay` ships with ffmpeg. Without it, or without an audio output (WSL without
sound), nothing plays and the caller names file and time instead. ffplay's own
output is dropped: nothing in it is needed. Samples play through the configured
filter chain (TOOL-91); it acts on playback only and writes nothing, so the WAV
stays as it is. Ctrl+C stops the sample only, and
keys typed while it plays are discarded, so they are not taken as the next
answer. This module logs nothing.
"""

import shutil
import subprocess
import sys
import termios
from pathlib import Path
from typing import Literal

PLAYER = "ffplay"
FILTER_CHECKER = "ffmpeg"  # same package as ffplay, and already required
MAX_SAMPLE_MS = 12_000  # a sample is the passage, cut to this length
_GRACE_SECONDS = 10  # beyond the sample, before a hanging player is given up
_SILENCE = ("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.1")

Played = Literal["played", "stopped", "missing", "failed"]


def find_player(search_path: str | None = None) -> Path | None:
    """Where ffplay is; `search_path` replaces PATH, for tests."""
    found = shutil.which(PLAYER, path=search_path)
    return None if found is None else Path(found)


def sample_ms(start_ms: int, end_ms: int | None) -> int:
    """How long a sample from `start_ms` plays: up to `end_ms`, at most the cap."""
    if end_ms is None or end_ms <= start_ms:
        return MAX_SAMPLE_MS
    return min(end_ms - start_ms, MAX_SAMPLE_MS)


def usable_filter(chain: str, search_path: str | None = None) -> str | None:
    """`chain` if ffmpeg can build it, else None: the samples then play unfiltered.

    ffplay plays nothing on a filter it cannot build but still exits 0, so the
    chain is tried once with ffmpeg on generated silence instead.
    """
    ffmpeg = shutil.which(FILTER_CHECKER, path=search_path)
    if ffmpeg is None:
        return None
    try:
        result = subprocess.run(
            [ffmpeg, "-loglevel", "quiet", *_SILENCE, "-af", chain, "-f", "null", "-"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_GRACE_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return chain if result.returncode == 0 else None


def command(
    player: Path,
    wav: Path,
    start_ms: int,
    duration_ms: int,
    audio_filter: str | None = None,
) -> list[str]:
    """The ffplay call for one sample, positioned in the WAV's own time."""
    filtering = [] if audio_filter is None else ["-af", audio_filter]
    return [
        str(player),
        "-nodisp",
        "-autoexit",
        "-loglevel",
        "quiet",
        "-ss",
        f"{start_ms / 1000:.3f}",
        "-t",
        f"{duration_ms / 1000:.3f}",
        *filtering,
        str(wav),
    ]


def play(
    player: Path | None,
    wav: Path,
    start_ms: int,
    end_ms: int | None,
    audio_filter: str | None = None,
) -> Played:
    """Play one sample and wait for it; Ctrl+C stops the sample, not the caller."""
    if player is None:
        return "missing"
    duration_ms = sample_ms(start_ms, end_ms)
    try:
        result = subprocess.run(
            command(player, wav, start_ms, duration_ms, audio_filter),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=duration_ms / 1000 + _GRACE_SECONDS,
            check=False,
        )
    except KeyboardInterrupt:  # subprocess.run has killed the player
        return "stopped"
    except (OSError, subprocess.TimeoutExpired):
        return "failed"
    finally:
        _drop_typeahead()
    return "played" if result.returncode == 0 else "failed"


def _drop_typeahead() -> None:
    """Discard what was typed at the terminal while the sample played."""
    try:
        if sys.stdin.isatty():
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except (OSError, ValueError):
        pass
