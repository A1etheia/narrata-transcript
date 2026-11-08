"""ASR-variant suggestions: new misrecognitions from review corrections (TOOL-80).

A `corrected` decision (TOOL-46) holds the right wording of a passage beside the
recognised one. Where a correction replaces some recognised words by exactly
the name or alias of a glossary entry, the recognised words are a likely
misrecognition of that entry. They are collected per session in
`review/asr-variant-suggestions.json`, for the GM to keep in Narrata's
`asr_variants` (IOA-1217). Nothing is taken over automatically, and neither
decisions nor transcript change.

A variant Narrata already keeps for the entry is not suggested again; nor is one
for an `event`, which keeps no misrecognitions. A corrected term several entries
share yields one suggestion naming all of them, marked `ambiguous`, and picks
none.

The file holds real names and corrected text, so it stays under `work/`; this
module logs nothing.
"""

import dataclasses
import difflib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from transcript.candidates import SessionCandidates
from transcript.decisions import SessionDecisions, review_items
from transcript.domain import DomainContext, TermHit
from transcript.glossary import MatchKind, normalize, tidy, trim_edges, word_key
from transcript.hints import MAX_SPAN_WORDS
from transcript.jsonfile import write_atomic
from transcript.narrata import VARIANT_TYPES, EntryRef, EntryType
from transcript.session import SessionPaths

SUGGESTIONS_FORMAT_VERSION = 1
TARGET_FIELD = "asr_variants"  # the Narrata field the suggestions are meant for


@dataclass(frozen=True)
class SuggestedEntry:
    """The entry a variant is suggested for, with the term the correction used."""

    type: EntryType
    id: int | str
    term: str  # as Narrata spells it
    field: str  # where the term sits in the entry, e.g. `aliases[1]`


@dataclass(frozen=True)
class OtherName:
    """Another entry the variant already names."""

    type: EntryType
    id: int | str
    kind: MatchKind


@dataclass(frozen=True)
class DecisionRef:
    candidate: str  # the review ID, e.g. `s01-p0042`
    decided_at: str


@dataclass(frozen=True)
class Suggestion:
    variant: str  # the recognised words, edges trimmed, case kept
    entries: tuple[SuggestedEntry, ...]  # in glossary order
    ambiguous: bool
    also_names: tuple[OtherName, ...]
    decisions: tuple[DecisionRef, ...]  # in recording order


@dataclass(frozen=True)
class VariantSuggestions:
    knowledge_snapshot_id: str | None
    corrected: int  # corrected decisions in force
    known: int  # replacements Narrata already keeps as misrecognition
    no_term: int  # replacements whose correction is no name or alias
    suggestions: tuple[Suggestion, ...]  # in order of their first decision

    def counts(self) -> dict[str, int]:
        return {
            "corrected": self.corrected,
            "suggested": len(self.suggestions),
            "known": self.known,
            "no_term": self.no_term,
        }


_GroupKey = tuple[str, tuple[EntryRef, ...]]  # normalized variant, entries


def suggest(
    found: SessionCandidates, decisions: SessionDecisions, domain: DomainContext
) -> VariantSuggestions:
    """The suggestions from the corrected decisions still in force; reads only."""
    items = [
        item
        for item in review_items(found, decisions).items
        if item.decision is not None and item.decision.status == "corrected"
    ]
    items.sort(key=lambda item: (item.candidate.segment, item.candidate.passage))
    suggestions: dict[_GroupKey, Suggestion] = {}  # without decisions yet
    made_by: dict[_GroupKey, list[DecisionRef]] = {}
    known = no_term = 0
    for item in items:
        decision = item.decision
        assert decision is not None and decision.target_text is not None
        reference = DecisionRef(decision.id, decision.decided_at)
        for heard, target in _replacements(item.candidate.text, decision.target_text):
            hits = _terms(domain, target)
            if not hits:
                no_term += 1
                continue
            variant = " ".join(trim_edges(tidy(word)) for word in heard)
            named = domain.lookup(variant)
            carrying = {hit.entry.ref for hit in named}
            open_hits = [hit for hit in hits if hit.entry.ref not in carrying]
            if not open_hits:
                known += 1
                continue
            key = (normalize(variant), tuple(hit.entry.ref for hit in open_hits))
            if key not in suggestions:
                suggestions[key] = _suggestion(variant, open_hits, named)
                made_by[key] = []
            if reference not in made_by[key]:
                made_by[key].append(reference)
    return VariantSuggestions(
        knowledge_snapshot_id=domain.origin.snapshot_id,
        corrected=len(items),
        known=known,
        no_term=no_term,
        suggestions=tuple(
            dataclasses.replace(suggestion, decisions=tuple(made_by[key]))
            for key, suggestion in suggestions.items()
        ),
    )


def _suggestion(
    variant: str, hits: Sequence[TermHit], named: Sequence[TermHit]
) -> Suggestion:
    """`variant` for the entries of `hits`; `named` are all entries it names."""
    refs = {hit.entry.ref for hit in hits}
    return Suggestion(
        variant=variant,
        entries=tuple(
            SuggestedEntry(h.entry.type, h.entry.id, h.term, h.field) for h in hits
        ),
        ambiguous=len(hits) > 1,
        also_names=tuple(
            OtherName(h.entry.type, h.entry.id, h.kind)
            for h in named
            if h.entry.ref not in refs
        ),
        decisions=(),
    )


def _replacements(
    heard_text: str, target_text: str
) -> Iterator[tuple[Sequence[str], str]]:
    """(recognised words, corrected key) for every replacement in the correction.

    Words are compared by their key, so case and edge punctuation alone are no
    change. Insertions and deletions are no misrecognition and are skipped.
    """
    heard = [(key, word) for word in heard_text.split() if (key := word_key(word))]
    target = [key for word in target_text.split() if (key := word_key(word))]
    matcher = difflib.SequenceMatcher(
        None, [key for key, _ in heard], target, autojunk=False
    )
    for tag, first, last, target_first, target_last in matcher.get_opcodes():
        if tag == "replace":
            yield (
                [word for _, word in heard[first:last]],
                " ".join(target[target_first:target_last]),
            )


def _terms(domain: DomainContext, target: str) -> list[TermHit]:
    """The names and aliases `target` is, of entries that keep misrecognitions."""
    if len(target.split(" ")) > MAX_SPAN_WORDS:
        return []
    return [
        hit
        for hit in domain.lookup(target)
        if hit.kind != "asr_variant" and hit.entry.type in VARIANT_TYPES
    ]


def write_suggestions(paths: SessionPaths, suggestions: VariantSuggestions) -> None:
    """Replace the session's suggestion file atomically.

    It holds no time of writing: the same decisions and knowledge give the same
    bytes, so importing an unchanged review sheet changes nothing.
    """
    write_atomic(
        paths.review_variant_suggestions,
        {
            "format_version": SUGGESTIONS_FORMAT_VERSION,
            "session": str(paths.key),
            "knowledge_snapshot_id": suggestions.knowledge_snapshot_id,
            "target_field": TARGET_FIELD,
            "counts": suggestions.counts(),
            "suggestions": [
                dataclasses.asdict(suggestion) for suggestion in suggestions.suggestions
            ],
        },
    )


def review_session(
    paths: SessionPaths,
    found: SessionCandidates,
    decisions: SessionDecisions,
    domain: DomainContext | None,
) -> VariantSuggestions | None:
    """Write the session's suggestions; what was written.

    Without knowledge there is nothing to suggest for: an older file is removed
    and the result is `None`.
    """
    if domain is None:
        paths.review_variant_suggestions.unlink(missing_ok=True)
        return None
    suggestions = suggest(found, decisions, domain)
    write_suggestions(paths, suggestions)
    return suggestions
