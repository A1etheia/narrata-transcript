"""Preflight for the external audio tools: ffmpeg and ffprobe must be present and run."""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_TOOLS = ("ffmpeg", "ffprobe")
_VERSION_TIMEOUT_SECONDS = 10
_VERSION_PATTERN = re.compile(r"^\S+ version (\S+)")
_INSTALL_HINT = "install with: sudo apt install ffmpeg (provides ffmpeg and ffprobe)"

_logger = logging.getLogger(__name__)


class AudioToolError(Exception):
    """A required audio tool is missing or broken; the message is meant for the user."""


@dataclass(frozen=True)
class ToolInfo:
    name: str
    path: Path
    version: str


@dataclass(frozen=True)
class AudioTools:
    ffmpeg: ToolInfo
    ffprobe: ToolInfo


def check_audio_tools(search_path: str | None = None) -> AudioTools:
    """Find and run ffmpeg and ffprobe; `search_path` replaces PATH, for tests."""
    found: dict[str, ToolInfo] = {}
    problems: list[str] = []
    for name in _TOOLS:
        try:
            found[name] = _probe(name, search_path)
        except AudioToolError as error:
            problems.append(str(error))
    if problems:
        raise AudioToolError("; ".join(problems) + f"; {_INSTALL_HINT}")
    return AudioTools(ffmpeg=found["ffmpeg"], ffprobe=found["ffprobe"])


def _probe(name: str, search_path: str | None) -> ToolInfo:
    location = shutil.which(name, path=search_path)
    if location is None:
        raise AudioToolError(f"{name} not found on PATH")

    try:
        result = subprocess.run(
            [location, "-version"],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AudioToolError(f"{name} at {location} did not answer -version") from error
    except OSError as error:
        raise AudioToolError(
            f"{name} at {location} cannot run ({error.strerror})"
        ) from error
    if result.returncode != 0:
        raise AudioToolError(
            f"{name} at {location} failed with exit code {result.returncode}"
        )

    first_line = result.stdout.lstrip().partition("\n")[0].strip()
    match = _VERSION_PATTERN.match(first_line)
    version = match.group(1) if match else first_line or "unknown"
    _logger.info("%s %s at %s", name, version, location)
    return ToolInfo(name=name, path=Path(location), version=version)
