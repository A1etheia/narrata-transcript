"""The Narrata transcription context (IOA-1215) as stored in the session's work dir.

The raw endpoint response lies at `SessionPaths.narrata_context`. `store_context`
is its only writer, whether the bytes come from the endpoint or from a local file.
This module reads the `session` and `participants` blocks; the glossary is left to
later steps. Participants carry real names, so no message names a field's value.
"""

import datetime
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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


Role = Literal["gm", "player"]
_ROLES: tuple[Role, ...] = ("gm", "player")


@dataclass(frozen=True)
class Character:
    """A player character: a Narrata archive person tied to the participant."""

    person_id: int | str
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Participant:
    """One group membership; `present` is None while Narrata keeps no attendance."""

    user_id: int | str
    display_name: str
    role: Role
    is_former: bool
    characters: tuple[Character, ...]
    present: bool | None = None


@dataclass(frozen=True)
class NarrataParticipants:
    """The participants of one context file, in Narrata's order, with their origin."""

    source: Path
    contract_version: str
    play_session_id: int | str
    participants: tuple[Participant, ...]


def is_narrata_id(value: Any) -> bool:
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
    _participants(data, path)
    write_bytes_atomic(path, raw)
    return session


def read_session(paths: SessionPaths) -> NarrataSession:
    """Read the `session` block and check its ordinal against the session key."""
    return _session(_read(paths), paths)


def read_participants(paths: SessionPaths) -> NarrataParticipants:
    """Read the `participants` block together with the session it belongs to."""
    data = _read(paths)
    session = _session(data, paths)
    return NarrataParticipants(
        source=paths.narrata_context,
        contract_version=data["contract_version"],
        play_session_id=session.play_session_id,
        participants=_participants(data, paths.narrata_context),
    )


def _read(paths: SessionPaths) -> dict[str, Any]:
    path = paths.narrata_context
    if not path.is_file():
        raise NarrataContextError(
            f"{path}: Narrata transcription context not found; "
            "run transcript context first"
        )
    return read_object(path, _WHAT, NarrataContextError)


def _session(data: dict[str, Any], paths: SessionPaths) -> NarrataSession:
    path = paths.narrata_context
    check_contract(data, path)
    session = field(data, "session", dict, path, NarrataContextError)
    play_session_id = session.get("play_session_id")
    if not is_narrata_id(play_session_id):
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


def _participants(data: dict[str, Any], path: Path) -> tuple[Participant, ...]:
    """Check `participants` against the contract; `characters`, `aliases` may be absent."""
    entries = field(data, "participants", list, path, NarrataContextError)
    participants = tuple(
        _participant(entry, f"participants[{index}]", path)
        for index, entry in enumerate(entries)
    )
    _check_unique(
        [(f"participants[{i}].user_id", p.user_id) for i, p in enumerate(participants)],
        path,
    )
    _check_unique(
        [
            (f"participants[{i}].characters[{j}].person_id", c.person_id)
            for i, p in enumerate(participants)
            for j, c in enumerate(p.characters)
        ],
        path,
    )
    return participants


def _participant(entry: Any, where: str, path: Path) -> Participant:
    if not isinstance(entry, dict):
        raise NarrataContextError(f"{path}: {where} is not an object")
    user_id = entry.get("user_id")
    if not is_narrata_id(user_id):
        raise _invalid(path, f"{where}.user_id")
    display_name = entry.get("display_name")
    if not _is_text(display_name):
        raise _invalid(path, f"{where}.display_name")
    role = entry.get("role")
    if role not in _ROLES:
        raise _invalid(path, f"{where}.role")
    is_former = entry.get("is_former")
    if not isinstance(is_former, bool):
        raise _invalid(path, f"{where}.is_former")
    characters = entry.get("characters")
    if characters is None:
        characters = []
    if not isinstance(characters, list):
        raise _invalid(path, f"{where}.characters")
    return Participant(
        user_id=user_id,
        display_name=display_name,
        role=role,
        is_former=is_former,
        characters=tuple(
            _character(character, f"{where}.characters[{index}]", path)
            for index, character in enumerate(characters)
        ),
    )


def _character(entry: Any, where: str, path: Path) -> Character:
    if not isinstance(entry, dict):
        raise NarrataContextError(f"{path}: {where} is not an object")
    person_id = entry.get("person_id")
    if not is_narrata_id(person_id):
        raise _invalid(path, f"{where}.person_id")
    name = entry.get("name")
    if not _is_text(name):
        raise _invalid(path, f"{where}.name")
    aliases = entry.get("aliases")
    if aliases is None:
        aliases = []
    if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
        raise _invalid(path, f"{where}.aliases")
    return Character(person_id, name, tuple(aliases))


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_unique(ids: list[tuple[str, int | str]], path: Path) -> None:
    """Names the second occurrence by position only, never by its id."""
    seen: set[int | str] = set()
    for where, value in ids:
        if value in seen:
            raise NarrataContextError(f"{path}: {where} repeats an earlier id")
        seen.add(value)


def _invalid(path: Path, where: str) -> NarrataContextError:
    return NarrataContextError(f"{path}: {where} missing or invalid")
