"""The Narrata transcription context (IOA-1215) as stored in the session's work dir.

The raw endpoint response lies at `SessionPaths.narrata_context`. Until TOOL-67
fetches it, it is saved there by hand. This module reads only the `session` block;
participants and glossary hold personal data and are left to later steps.
"""

import datetime
from dataclasses import dataclass
from typing import Any

from transcript.jsonfile import DataFileError, field, read_object
from transcript.session import SessionPaths


class NarrataContextError(DataFileError):
    """The Narrata transcription context is missing or does not fit the session."""


@dataclass(frozen=True)
class NarrataSession:
    play_session_id: int | str
    ordinal: int
    session_date: datetime.date


def is_play_session_id(value: Any) -> bool:
    """Narrata ids are integers or non-empty strings; booleans are neither."""
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, str) and bool(value))


def read_session(paths: SessionPaths) -> NarrataSession:
    """Read the `session` block and check its ordinal against the session key."""
    path = paths.narrata_context
    if not path.is_file():
        raise NarrataContextError(
            f"{path}: Narrata transcription context not found; "
            "save the transcription-context response there"
        )
    data = read_object(path, "Narrata context", NarrataContextError)
    session = field(data, "session", dict, path, NarrataContextError)
    play_session_id = session.get("play_session_id")
    if not is_play_session_id(play_session_id):
        raise NarrataContextError(f"{path}: session.play_session_id missing or invalid")
    ordinal = session.get("ordinal")
    if ordinal != paths.key.ordinal:
        raise NarrataContextError(
            f"{path}: session.ordinal is {ordinal!r}, "
            f"but the session key is {paths.key}"
        )
    try:
        session_date = datetime.date.fromisoformat(session.get("session_date", ""))
    except (TypeError, ValueError):
        raise NarrataContextError(
            f"{path}: session.session_date missing or not YYYY-MM-DD"
        ) from None
    return NarrataSession(play_session_id, paths.key.ordinal, session_date)
