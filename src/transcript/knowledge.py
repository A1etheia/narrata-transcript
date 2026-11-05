"""The knowledge snapshot: a session's Narrata context, frozen for its runs (TOOL-41).

`build_snapshot` turns the stored transcription context into
`work/<key>/narrata/snapshot.json`; `load_snapshot` reads it back without the
context file or Narrata. Later steps read the snapshot, never the raw context.

Relevance is Narrata's tier per glossary entry (ios-archiv docs/transcripts.md,
"Relevanz"); the pipeline does not recompute it. Here only the keyword candidates
are chosen: every `pc` entry, then `session` and `recent` entries in Narrata's
order up to a budget per entry type. `archive` entries stay in the snapshot for
matching but never become keywords. Ambiguities are kept as Narrata reports them.

Every entry comes from the one context file named in `source`. The snapshot holds
real names, so messages name the file and the field, never a value.
"""

import datetime
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcript import narrata
from transcript.jsonfile import (
    DataFileError,
    field,
    read_object,
    write_atomic,
)
from transcript.narrata import (
    GlossaryEntry,
    NarrataContextError,
    NarrataGlossary,
    Participant,
    Relevance,
)
from transcript.session import SessionPaths

SNAPSHOT_FORMAT_VERSION = 1
KEYWORD_TIERS: tuple[Relevance, ...] = ("pc", "session", "recent")
_UNBUDGETED: tuple[Relevance, ...] = ("pc",)  # always keywords, never counted
_WHAT = "knowledge snapshot"
_REFRESH = "run transcript snapshot --refresh"
_UNHASHED = ("snapshot_id", "created_at")  # same knowledge, same id


class SnapshotError(DataFileError):
    """The knowledge snapshot is missing or invalid."""


@dataclass(frozen=True)
class SnapshotSource:
    """The context file the snapshot was built from."""

    file: str
    contract_version: str
    sha256: str
    play_session_id: int | str


@dataclass(frozen=True)
class Snapshot:
    """One frozen state of a session's knowledge; `glossary` keeps Narrata's order."""

    path: Path
    snapshot_id: str
    created_at: str
    source: SnapshotSource
    keyword_budget: Mapping[str, int]
    participants: tuple[Participant, ...]
    glossary: NarrataGlossary
    keyword_entries: tuple[GlossaryEntry, ...]  # in glossary order


@dataclass(frozen=True)
class Drift:
    """How the current inputs differ from those a snapshot was built from."""

    context_changed: bool  # the stored context file is no longer the source
    budget_changed: bool  # the configured keyword budget is another

    @property
    def any(self) -> bool:
        return self.context_changed or self.budget_changed


def select_keywords(
    entries: Sequence[GlossaryEntry], budget: Mapping[str, int]
) -> tuple[GlossaryEntry, ...]:
    """The keyword candidates among `entries`, in their order.

    `pc` entries always; `session` and `recent` ones while their type is under
    budget, so the nearer tier fills first; a type missing from `budget` gets none.
    """
    used: Counter[str] = Counter()
    chosen = []
    for entry in entries:
        if entry.relevance in _UNBUDGETED:
            chosen.append(entry)
        elif entry.relevance in KEYWORD_TIERS and used[entry.type] < budget.get(
            entry.type, 0
        ):
            used[entry.type] += 1
            chosen.append(entry)
    return tuple(chosen)


def build_snapshot(
    paths: SessionPaths,
    budget: Mapping[str, int],
    now: datetime.datetime | None = None,
) -> Snapshot:
    """Build the snapshot from the stored context, replace the file and return it.

    The stored context is checked as `narrata` reads it; nothing is written
    unless it passes. Unchanged knowledge and budget give the same `snapshot_id`.
    """
    raw, data = narrata.read_raw(paths)
    context = paths.narrata_context
    session = narrata.parse_session(data, paths)
    participants = narrata.parse_participants(data, context)
    glossary = narrata.parse_glossary(data, context, session.play_session_id)
    keywords = {_key(entry) for entry in select_keywords(glossary.entries, budget)}
    moment = now or datetime.datetime.now().astimezone()
    content: dict[str, Any] = {
        "format_version": SNAPSHOT_FORMAT_VERSION,
        "session": {"group": paths.key.group, "ordinal": paths.key.ordinal},
        "source": {
            "file": context.name,
            "contract_version": data["contract_version"],
            "sha256": _sha256(raw),
            "play_session_id": session.play_session_id,
        },
        "keyword_budget": dict(budget),
        "participants": [_participant_json(p) for p in participants],
        "glossary": [_entry_json(e, _key(e) in keywords) for e in glossary.entries],
        "glossary_meta": {
            "archive_total": glossary.archive_total,
            "archive_returned": glossary.archive_returned,
        },
        "asr_ambiguities": [
            {
                "variant": ambiguity.variant,
                "entries": [{"type": t, "id": i} for t, i in ambiguity.entries],
            }
            for ambiguity in glossary.ambiguities
        ],
    }
    write_atomic(
        paths.knowledge_snapshot,
        {
            "format_version": SNAPSHOT_FORMAT_VERSION,  # stays first in the file
            "snapshot_id": _snapshot_id(content),
            "created_at": moment.isoformat(timespec="seconds"),
            **content,
        },
    )
    return load_snapshot(paths)


def load_snapshot(paths: SessionPaths) -> Snapshot:
    """Read the snapshot and check that it belongs to the session and is intact."""
    path = paths.knowledge_snapshot
    if not path.is_file():
        raise SnapshotError(f"{path}: {_WHAT} not found; run transcript snapshot")
    data = read_object(path, _WHAT, SnapshotError)
    if not _is_int(data.get("format_version"), SNAPSHOT_FORMAT_VERSION):
        raise SnapshotError(f"{path}: unsupported format_version; {_REFRESH}")
    session = field(data, "session", dict, path, SnapshotError)
    if session.get("group") != paths.key.group or not _is_int(
        session.get("ordinal"), paths.key.ordinal
    ):
        raise SnapshotError(f"{path}: belongs to another session than {paths.key}")
    snapshot_id = field(data, "snapshot_id", str, path, SnapshotError)
    if snapshot_id != _snapshot_id(data):
        raise SnapshotError(
            f"{path}: snapshot_id does not match the content; {_REFRESH}"
        )
    source = _source(data, path)
    # the blocks have the context's shape; the parsers expect its version beside them
    blocks = {**data, "contract_version": source.contract_version}
    try:
        narrata.check_contract(blocks, path)
        glossary = narrata.parse_glossary(blocks, path, source.play_session_id)
        participants = narrata.parse_participants(blocks, path)
    except NarrataContextError as error:
        raise SnapshotError(str(error)) from None
    flags = _keyword_flags(data, path)
    return Snapshot(
        path=path,
        snapshot_id=snapshot_id,
        created_at=field(data, "created_at", str, path, SnapshotError),
        source=source,
        keyword_budget=_budget(data, path),
        participants=participants,
        glossary=glossary,
        keyword_entries=tuple(
            entry for entry, flag in zip(glossary.entries, flags, strict=True) if flag
        ),
    )


def drift(snapshot: Snapshot, paths: SessionPaths, budget: Mapping[str, int]) -> Drift:
    """What changed since `snapshot` was built; a missing context is no change."""
    context = paths.narrata_context
    try:
        changed = (
            context.is_file()
            and _sha256(context.read_bytes()) != snapshot.source.sha256
        )
    except OSError as cause:
        raise NarrataContextError(
            f"{context}: Narrata context is unreadable ({cause})"
        ) from None
    return Drift(
        context_changed=changed,
        budget_changed=dict(budget) != dict(snapshot.keyword_budget),
    )


def _key(entry: GlossaryEntry) -> tuple[str, int | str]:
    return (entry.type, entry.id)


def _snapshot_id(data: Mapping[str, Any]) -> str:
    content = {k: v for k, v in data.items() if k not in _UNHASHED}
    canonical = json.dumps(
        content, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return _sha256(canonical.encode("utf-8"))


def _is_int(value: Any, expected: int) -> bool:
    """`value == expected` without `True` passing for 1."""
    return not isinstance(value, bool) and value == expected


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _participant_json(participant: Participant) -> dict[str, Any]:
    return {
        "user_id": participant.user_id,
        "display_name": participant.display_name,
        "role": participant.role,
        "is_former": participant.is_former,
        "characters": [
            {
                "person_id": character.person_id,
                "name": character.name,
                "aliases": list(character.aliases),
            }
            for character in participant.characters
        ],
    }


def _entry_json(entry: GlossaryEntry, keyword: bool) -> dict[str, Any]:
    return {
        "type": entry.type,
        "id": entry.id,
        "name": entry.name,
        "aliases": list(entry.aliases),
        "asr_variants": list(entry.asr_variants),
        "summary": entry.summary,
        "relevance": entry.relevance,
        "keyword": keyword,
    }


def _source(data: dict[str, Any], path: Path) -> SnapshotSource:
    source = field(data, "source", dict, path, SnapshotError)
    play_session_id = source.get("play_session_id")
    if not narrata.is_narrata_id(play_session_id):
        raise SnapshotError(f"{path}: source.play_session_id missing or invalid")
    for name in ("file", "contract_version", "sha256"):
        if not isinstance(source.get(name), str):
            raise SnapshotError(f"{path}: source.{name} missing or invalid")
    return SnapshotSource(
        file=source["file"],
        contract_version=source["contract_version"],
        sha256=source["sha256"],
        play_session_id=play_session_id,
    )


def _budget(data: dict[str, Any], path: Path) -> dict[str, int]:
    budget = field(data, "keyword_budget", dict, path, SnapshotError)
    for name, limit in budget.items():
        if not narrata.is_count(limit):
            raise SnapshotError(f"{path}: keyword_budget.{name} missing or invalid")
    return budget


def _keyword_flags(data: dict[str, Any], path: Path) -> list[bool]:
    """`glossary[i].keyword` per entry; `parse_glossary` has checked the list."""
    flags = []
    for index, entry in enumerate(data["glossary"]):
        flag = entry.get("keyword")
        if not isinstance(flag, bool):
            raise SnapshotError(f"{path}: glossary[{index}].keyword missing or invalid")
        flags.append(flag)
    return flags
