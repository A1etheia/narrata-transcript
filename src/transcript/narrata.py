"""The Narrata transcription context (IOA-1215) as stored in the session's work dir.

The raw endpoint response lies at `SessionPaths.narrata_context`. `store_context`
is its only writer, whether the bytes come from the endpoint or from a local file.
This module reads only the `session` block; participants and glossary hold personal
data and are left to later steps.
"""

import datetime
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcript.jsonfile import (
    DataFileError,
    field,
    parse_object,
    read_object,
    write_bytes_atomic,
)
from transcript.session import SessionPaths

_WHAT = "Narrata context"  # names the file in messages

# Mirrors TranscriptContract::SUPPORTED_MAJORS in ios-archiv: minor versions only
# add fields, so every 1.x response is read the same way.
SUPPORTED_MAJOR = 1
_VERSION_PATTERN = re.compile(r"([1-9][0-9]*)\.(0|[1-9][0-9]*)")


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


def check_contract(data: dict[str, Any], path: Path) -> None:
    """Reject a context whose `contract_version` this pipeline cannot read."""
    version = data.get("contract_version")
    match = _VERSION_PATTERN.fullmatch(version) if isinstance(version, str) else None
    if match is None:
        raise NarrataContextError(
            f"{path}: contract_version missing or invalid; "
            f"supported is {SUPPORTED_MAJOR}.x"
        )
    if int(match.group(1)) != SUPPORTED_MAJOR:
        raise NarrataContextError(
            f"{path}: contract_version {version} is not supported; "
            f"supported is {SUPPORTED_MAJOR}.x, update narrata-transcript"
        )


def store_context(paths: SessionPaths, raw: bytes) -> NarrataSession:
    """Check a transcription-context response and save it unchanged.

    Nothing is written unless the response passes every check `read_session`
    makes, so a bad response never replaces a good file.
    """
    path = paths.narrata_context
    data = parse_object(raw, path, _WHAT, NarrataContextError)
    session = _session(data, paths)
    write_bytes_atomic(path, raw)
    return session


def read_session(paths: SessionPaths) -> NarrataSession:
    """Read the `session` block and check its ordinal against the session key."""
    path = paths.narrata_context
    if not path.is_file():
        raise NarrataContextError(
            f"{path}: Narrata transcription context not found; "
            "run transcript context first"
        )
    return _session(read_object(path, _WHAT, NarrataContextError), paths)


def _session(data: dict[str, Any], paths: SessionPaths) -> NarrataSession:
    path = paths.narrata_context
    check_contract(data, path)
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
