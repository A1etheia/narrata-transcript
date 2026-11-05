"""The Narrata transcription context (IOA-1215) as stored in the session's work dir.

The raw endpoint response lies at `SessionPaths.narrata_context`. `store_context`
is its only writer, whether the bytes come from the endpoint or from a local file.
This module reads the `session`, `participants` and `glossary` blocks. Participants
and glossary carry real names, so no message names a field's value.

`parse_participants` and `parse_glossary` check one block of an already parsed
object and name the given file in messages; the knowledge snapshot (TOOL-41) stores
both blocks in the same shape and reads them through these functions.
`parse_session` belongs to the context file alone.
"""

import datetime
import re
from collections.abc import Hashable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar, get_args

from transcript.jsonfile import (
    DataFileError,
    field,
    parse_object,
    write_bytes_atomic,
)
from transcript.session import SessionPaths

_WHAT = "Narrata context"  # names the file in messages
_T = TypeVar("_T")

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


EntryType = Literal["place", "person", "artifact", "organisation", "event", "lore"]
ENTRY_TYPES: tuple[EntryType, ...] = get_args(EntryType)
Relevance = Literal["pc", "session", "recent", "archive"]
RELEVANCE_TIERS: tuple[Relevance, ...] = get_args(Relevance)  # nearest first


@dataclass(frozen=True)
class GlossaryEntry:
    """One world-archive entry; strings keep Narrata's spelling unchanged.

    `asr_variants` are known misrecognitions of the name, kept by the GM.
    """

    type: EntryType
    id: int | str
    name: str
    aliases: tuple[str, ...]
    asr_variants: tuple[str, ...]
    summary: str | None
    relevance: Relevance


@dataclass(frozen=True)
class Ambiguity:
    """A misrecognition two or more entries share; Narrata never resolves it."""

    variant: str
    entries: tuple[tuple[EntryType, int | str], ...]


@dataclass(frozen=True)
class NarrataGlossary:
    """The glossary of one context file, in Narrata's tier order, with its origin."""

    source: Path
    contract_version: str
    play_session_id: int | str
    entries: tuple[GlossaryEntry, ...]
    archive_total: int
    archive_returned: int
    ambiguities: tuple[Ambiguity, ...]


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
    session = parse_session(data, paths)
    parse_participants(data, path)
    parse_glossary(data, path, session.play_session_id)
    write_bytes_atomic(path, raw)
    return session


def read_session(paths: SessionPaths) -> NarrataSession:
    """Read the `session` block and check its ordinal against the session key."""
    return parse_session(_read(paths), paths)


def read_participants(paths: SessionPaths) -> NarrataParticipants:
    """Read the `participants` block together with the session it belongs to."""
    data = _read(paths)
    session = parse_session(data, paths)
    return NarrataParticipants(
        source=paths.narrata_context,
        contract_version=data["contract_version"],
        play_session_id=session.play_session_id,
        participants=parse_participants(data, paths.narrata_context),
    )


def read_glossary(paths: SessionPaths) -> NarrataGlossary:
    """Read `glossary`, `glossary_meta` and `asr_ambiguities` with their session."""
    data = _read(paths)
    session = parse_session(data, paths)
    return parse_glossary(data, paths.narrata_context, session.play_session_id)


def read_raw(paths: SessionPaths) -> tuple[bytes, dict[str, Any]]:
    """The stored context as bytes and as parsed object, from one read."""
    path = paths.narrata_context
    if not path.is_file():
        raise NarrataContextError(
            f"{path}: Narrata transcription context not found; "
            "run transcript context first"
        )
    try:
        raw = path.read_bytes()
    except OSError as cause:
        raise NarrataContextError(f"{path}: {_WHAT} is unreadable ({cause})") from None
    return raw, parse_object(raw, path, _WHAT, NarrataContextError)


def _read(paths: SessionPaths) -> dict[str, Any]:
    return read_raw(paths)[1]


def parse_session(data: dict[str, Any], paths: SessionPaths) -> NarrataSession:
    """Check `contract_version` and `session`, whose ordinal must match the key."""
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


def parse_participants(data: dict[str, Any], path: Path) -> tuple[Participant, ...]:
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
    entry = _object(entry, where, path)
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
    characters = _optional_list(entry, "characters", f"{where}.characters", path)
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
    entry = _object(entry, where, path)
    person_id = entry.get("person_id")
    if not is_narrata_id(person_id):
        raise _invalid(path, f"{where}.person_id")
    name = entry.get("name")
    if not _is_text(name):
        raise _invalid(path, f"{where}.name")
    return Character(person_id, name, _strings(entry, "aliases", where, path))


def parse_glossary(
    data: dict[str, Any], path: Path, play_session_id: int | str
) -> NarrataGlossary:
    """Check the glossary blocks; `asr_ambiguities` is absent before contract 1.1."""
    raw_entries = field(data, "glossary", list, path, NarrataContextError)
    entries = tuple(
        _glossary_entry(entry, f"glossary[{index}]", path)
        for index, entry in enumerate(raw_entries)
    )
    _check_unique(
        [(f"glossary[{i}].id", (e.type, e.id)) for i, e in enumerate(entries)], path
    )
    meta = field(data, "glossary_meta", dict, path, NarrataContextError)
    total = meta.get("archive_total")
    returned = meta.get("archive_returned")
    if not is_count(total):
        raise _invalid(path, "glossary_meta.archive_total")
    if not is_count(returned) or returned > total:
        raise _invalid(path, "glossary_meta.archive_returned")
    known = {(e.type, e.id) for e in entries}
    raw_ambiguities = _optional_list(data, "asr_ambiguities", "asr_ambiguities", path)
    return NarrataGlossary(
        source=path,
        contract_version=data["contract_version"],
        play_session_id=play_session_id,
        entries=entries,
        archive_total=total,
        archive_returned=returned,
        ambiguities=tuple(
            _ambiguity(entry, f"asr_ambiguities[{index}]", known, path)
            for index, entry in enumerate(raw_ambiguities)
        ),
    )


def _glossary_entry(entry: Any, where: str, path: Path) -> GlossaryEntry:
    entry = _object(entry, where, path)
    entry_type = _known(entry.get("type"), ENTRY_TYPES, f"{where}.type", path)
    entry_id = entry.get("id")
    if not is_narrata_id(entry_id):
        raise _invalid(path, f"{where}.id")
    name = entry.get("name")
    if not _is_text(name):
        raise _invalid(path, f"{where}.name")
    summary = entry.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise _invalid(path, f"{where}.summary")
    return GlossaryEntry(
        type=entry_type,
        id=entry_id,
        name=name,
        aliases=_strings(entry, "aliases", where, path),
        asr_variants=_strings(entry, "asr_variants", where, path),
        summary=summary if _is_text(summary) else None,
        relevance=_known(
            entry.get("relevance"), RELEVANCE_TIERS, f"{where}.relevance", path
        ),
    )


def _ambiguity(
    entry: Any, where: str, known: set[tuple[EntryType, int | str]], path: Path
) -> Ambiguity:
    """A variant shared by two or more distinct entries the glossary delivers."""
    entry = _object(entry, where, path)
    variant = entry.get("variant")
    if not _is_text(variant):
        raise _invalid(path, f"{where}.variant")
    refs = entry.get("entries")
    if not isinstance(refs, list):
        raise _invalid(path, f"{where}.entries")
    keys: list[tuple[EntryType, int | str]] = []
    for index, ref in enumerate(refs):
        ref_where = f"{where}.entries[{index}]"
        ref = _object(ref, ref_where, path)
        key = (
            _known(ref.get("type"), ENTRY_TYPES, f"{ref_where}.type", path),
            ref.get("id"),
        )
        if not is_narrata_id(key[1]) or key not in known:
            raise NarrataContextError(
                f"{path}: {ref_where} names no entry of the glossary"
            )
        keys.append(key)
    if len(set(keys)) != len(keys) or len(keys) < 2:
        raise NarrataContextError(
            f"{path}: {where}.entries must name two or more distinct entries"
        )
    return Ambiguity(variant, tuple(keys))


def _object(value: Any, where: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NarrataContextError(f"{path}: {where} is not an object")
    return value


def _known(value: Any, allowed: tuple[_T, ...], where: str, path: Path) -> _T:
    """`value` if the contract lists it; a newer Narrata may need a newer pipeline."""
    if value not in allowed:
        raise NarrataContextError(
            f"{path}: {where} missing or not a known value; "
            "if Narrata is newer, update narrata-transcript"
        )
    return value


def _optional_list(
    data: dict[str, Any], name: str, where: str, path: Path
) -> list[Any]:
    """`data[name]` as a list; absent or null is empty."""
    values = data.get(name)
    if values is None:
        return []
    if not isinstance(values, list):
        raise _invalid(path, where)
    return values


def _strings(
    entry: dict[str, Any], name: str, where: str, path: Path
) -> tuple[str, ...]:
    """An optional list of strings; absent or null is empty."""
    values = _optional_list(entry, name, f"{where}.{name}", path)
    if not all(isinstance(v, str) for v in values):
        raise _invalid(path, f"{where}.{name}")
    return tuple(values)


def is_count(value: Any) -> bool:
    """A whole number from 0 up; booleans are none."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_unique(ids: list[tuple[str, Hashable]], path: Path) -> None:
    """Names the second occurrence by position only, never by its id."""
    seen: set[Hashable] = set()
    for where, value in ids:
        if value in seen:
            raise NarrataContextError(f"{path}: {where} repeats an earlier id")
        seen.add(value)


def _invalid(path: Path, where: str) -> NarrataContextError:
    return NarrataContextError(f"{path}: {where} missing or invalid")
