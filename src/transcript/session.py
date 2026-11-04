"""Session keys and the per-session directory layout.

A session key mirrors a Narrata play session: `<group slug>/<ordinal>`. It is the
readable address of a session; its identity is the `play_session_id` in the manifest,
because Narrata can reassign an ordinal after the latest session is deleted.
"""

import re
from dataclasses import dataclass
from pathlib import Path

_GROUP_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_ORDINAL_PATTERN = re.compile(r"[0-9]+")
_GROUP_MAX_LENGTH = 64


@dataclass(frozen=True)
class SessionKey:
    group: str
    ordinal: int

    def __post_init__(self) -> None:
        if (
            len(self.group) > _GROUP_MAX_LENGTH
            or _GROUP_PATTERN.fullmatch(self.group) is None
        ):
            raise ValueError(f"invalid group slug: {self.group!r}")
        if self.ordinal < 1:
            raise ValueError(f"invalid session ordinal: {self.ordinal!r}")

    @classmethod
    def parse(cls, raw: str) -> "SessionKey":
        """Parse `<group>/<ordinal>`, so `x/42` and `x/042` are the same session."""
        group, _, ordinal = raw.partition("/")
        if _ORDINAL_PATTERN.fullmatch(ordinal) is None:
            raise ValueError(f"invalid session key: {raw!r}")
        return cls(group, int(ordinal))

    def __str__(self) -> str:
        return f"{self.group}/{self.ordinal:03d}"


@dataclass(frozen=True)
class SessionPaths:
    """Directories of one session. `input_dir` is read-only by convention."""

    key: SessionKey
    root: Path

    @property
    def input_dir(self) -> Path:
        return self.root / "input" / str(self.key)

    @property
    def work_dir(self) -> Path:
        return self.root / "work" / str(self.key)

    @property
    def output_dir(self) -> Path:
        return self.root / "output" / str(self.key)

    @property
    def audio_dir(self) -> Path:
        return self.work_dir / "audio"

    def segment_wav(self, index: int) -> Path:
        """Working WAV of the `index`-th recording of the session, counted from 1."""
        if index < 1:
            raise ValueError(f"invalid segment index: {index!r}")
        return self.audio_dir / f"segment-{index:02d}.wav"

    def segment_wavs(self) -> list[Path]:
        """All segment WAVs currently in the audio dir, including stale ones."""
        return sorted(self.audio_dir.glob("segment-*.wav"))

    @property
    def audio_metadata(self) -> Path:
        return self.audio_dir / "audio.json"

    @property
    def manifest(self) -> Path:
        return self.work_dir / "manifest.json"

    @property
    def narrata_context(self) -> Path:
        """Raw transcription-context response from Narrata (IOA-1215), see TOOL-67."""
        return self.work_dir / "narrata" / "transcription-context.json"

    @property
    def debug_log(self) -> Path:
        return self.work_dir / "debug.log"
