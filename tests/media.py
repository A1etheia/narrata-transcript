"""Media for tests, synthesized with ffmpeg at runtime; no audio lives in the repo."""

import subprocess
import unittest
from pathlib import Path

from transcript.audio_tools import AudioToolError, AudioTools, check_audio_tools

try:
    TOOLS: AudioTools | None = check_audio_tools()
except AudioToolError:
    TOOLS = None


def synth(path: Path, *args: str) -> Path:
    """Run ffmpeg with lavfi sources, e.g. `synth(p, "-f", "lavfi", "-i", "sine")`."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", *args, str(path)], check=True
    )
    return path


def sine(seconds: float = 2, frequency: int = 440, rate: int = 44100) -> list[str]:
    source = f"sine=frequency={frequency}:duration={seconds}:sample_rate={rate}"
    return ["-f", "lavfi", "-i", source]


def video(seconds: float = 2) -> list[str]:
    return ["-f", "lavfi", "-i", f"testsrc=size=64x48:rate=5:duration={seconds}"]


def mp4_with_audio() -> list[str]:
    """Video plus 48 kHz stereo AAC, the shape of a typical session recording."""
    return [*video(), *sine(rate=48000), "-ac", "2", "-c:a", "aac", "-shortest"]


def flite_missing() -> str:
    """Why speech cannot be synthesized here, or "" if ffmpeg has flite."""
    if TOOLS is None:
        return "ffmpeg is needed to synthesize speech"
    filters = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return "" if " flite " in filters else "ffmpeg lacks the flite filter"


def speech(text: str, voice: str = "kal") -> list[str]:
    """ffmpeg input that speaks a made-up English `text` with a flite voice."""
    return ["-f", "lavfi", "-i", f"flite=text='{text}':voice={voice}"]


needs_media = unittest.skipIf(
    TOOLS is None, "ffmpeg and ffprobe are needed to synthesize media"
)
