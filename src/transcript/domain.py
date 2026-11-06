"""The domain context: one read-only view of a session's knowledge (TOOL-43).

Pipeline steps ask a `DomainContext`, never Narrata, the raw context or the
snapshot file. `from_snapshot` is the only code that knows the snapshot's shape;
another source of knowledge needs another factory, not new consumers.

Every query returns Narrata's spelling and changes neither knowledge nor
transcript text. A term several entries share returns all of them: the context
never decides which one is meant. It holds real names, so it logs nothing.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from transcript.glossary import (
    GlossaryIndex,
    Match,
    MatchKind,
    entry_terms,
    keyword_terms,
    normalize,
)
from transcript.knowledge import KEYWORD_TIERS, Snapshot, load_snapshot
from transcript.narrata import (
    Character,
    EntryRef,
    GlossaryEntry,
    NarrataGlossary,
    Participant,
)
from transcript.session import SessionPaths


@dataclass(frozen=True)
class Origin:
    """Where all knowledge of one context comes from."""

    snapshot_id: str | None  # None when the knowledge is not from a snapshot
    source_file: str
    contract_version: str
    play_session_id: int | str


@dataclass(frozen=True)
class TermHit:
    """One term of one entry, with what is known about it."""

    entry: GlossaryEntry  # `entry.ref` and `entry.relevance` locate and rank it
    kind: MatchKind
    field: str  # where the term sits in the entry, e.g. `aliases[1]`
    term: str  # as Narrata spells it
    keyword: bool  # the entry is an ASR keyword of the session
    origin: Origin


class DomainContext:
    """Participants, glossary and keyword choice of one session, read-only."""

    def __init__(
        self,
        participants: Iterable[Participant],
        glossary: NarrataGlossary,
        keyword_refs: Collection[EntryRef],
        origin: Origin,
    ) -> None:
        self.origin = origin
        self.participants = tuple(participants)
        self.entries = glossary.entries  # Narrata's order, nearest tier first
        self.ambiguities = glossary.ambiguities
        self._ambiguous = frozenset(normalize(a.variant) for a in self.ambiguities)
        self._index = GlossaryIndex(glossary)
        self._entries = {entry.ref: entry for entry in self.entries}
        self._keyword_refs = frozenset(keyword_refs)
        self._keywords = tuple(e for e in self.entries if e.ref in self._keyword_refs)

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot) -> "DomainContext":
        return cls(
            snapshot.participants,
            snapshot.glossary,
            {entry.ref for entry in snapshot.keyword_entries},
            Origin(
                snapshot_id=snapshot.snapshot_id,
                source_file=snapshot.source.file,
                contract_version=snapshot.source.contract_version,
                play_session_id=snapshot.source.play_session_id,
            ),
        )

    @classmethod
    def load(cls, paths: SessionPaths) -> "DomainContext":
        """The context of the session's knowledge snapshot; `SnapshotError` if none."""
        return cls.from_snapshot(load_snapshot(paths))

    def lookup(self, term: str) -> tuple[TermHit, ...]:
        """Every entry `term` names as name, alias or known misrecognition."""
        return tuple(self._hit(match) for match in self._index.lookup(term))

    def is_ambiguous(self, term: str) -> bool:
        """Whether Narrata reports `term` as a misrecognition of several entries."""
        return normalize(term) in self._ambiguous

    def entry(self, ref: EntryRef) -> GlossaryEntry | None:
        return self._entries.get(ref)

    def participant(self, user_id: int | str) -> Participant | None:
        return next((p for p in self.participants if p.user_id == user_id), None)

    def character(self, person_id: int | str) -> tuple[Participant, Character] | None:
        """The player character with this archive id and who plays it."""
        for participant in self.participants:
            for character in participant.characters:
                if character.person_id == person_id:
                    return participant, character
        return None

    def relevant_entries(self) -> tuple[GlossaryEntry, ...]:
        """Entries nearer than `archive`, in Narrata's order."""
        return tuple(e for e in self.entries if e.relevance in KEYWORD_TIERS)

    def keyword_entries(self) -> tuple[GlossaryEntry, ...]:
        return self._keywords

    def transcription_keywords(self) -> tuple[str, ...]:
        """ASR hints, most important first; no misrecognitions, no token cut."""
        return keyword_terms(self._keywords)

    def match_candidates(self) -> tuple[TermHit, ...]:
        """Every term of every entry, misrecognitions included, in glossary order."""
        return tuple(
            self._hit(Match(entry, kind, field, term))
            for entry in self.entries
            for kind, field, term in entry_terms(entry)
        )

    def _hit(self, match: Match) -> TermHit:
        return TermHit(
            match.entry,
            match.kind,
            match.field,
            match.term,
            match.entry.ref in self._keyword_refs,
            self.origin,
        )
