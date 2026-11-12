"""Playing a few seconds of a segment's WAV to hear who speaks (TOOL-86).

`ffplay` ships with ffmpeg. Without it, or without an audio output (WSL without
sound), nothing plays and the caller names file and time instead. ffplay's own
output is dropped: nothing in it is needed. This module logs nothing.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Literal

PLAYER = "ffplay"
MAX_SAMPLE_MS = 12_000  # a sample is the passage, cut to this length
_GRACE_SECONDS = 10  # beyond the sample, before a hanging player is given up

Played = Literal["played", "missing", "failed"]


def find_player(search_path: str | None = None) -> Path | None:
    """Where ffplay is; `search_path` replaces PATH, for tests."""
    found = shutil.which(PLAYER, path=search_path)
    return None if found is None else Path(found)


def sample_ms(start_ms: int, end_ms: int | None) -> int:
    """How long a sample from `start_ms` plays: up to `end_ms`, at most the cap."""
    if end_ms is None or end_ms <= start_ms:
        return MAX_SAMPLE_MS
    return min(end_ms - start_ms, MAX_SAMPLE_MS)


def command(player: Path, wav: Path, start_ms: int, duration_ms: int) -> list[str]:
    """The ffplay call for one sample, positioned in the WAV's own time."""
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
        str(wav),
    ]


def play(player: Path | None, wav: Path, start_ms: int, end_ms: int | None) -> Played:
    """Play one sample and wait for it; Ctrl+C stops the player and propagates."""
    if player is None:
        return "missing"
    duration_ms = sample_ms(start_ms, end_ms)
    try:
        result = subprocess.run(
            command(player, wav, start_ms, duration_ms),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=duration_ms / 1000 + _GRACE_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "failed"
    return "played" if result.returncode == 0 else "failed"
