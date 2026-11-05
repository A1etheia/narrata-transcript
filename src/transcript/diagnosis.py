"""Cross-entry checks of a session's knowledge and the diagnosis report (TOOL-42).

The parsers in `narrata` already reject what is technically unusable: repeated ids,
empty required fields, unknown types, ambiguities pointing nowhere. A snapshot with
such a defect is neither built nor loaded. `diagnose` looks at what they let
through and reports what is ambiguous or inconsistent but still usable, as
warnings: Narrata's data stays as it is and the review decides.

A finding names entries by type, Narrata id and field path, never by a name, so
the console and the report hold no real names (TOOL-66).
"""

import datetime
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from transcript.glossary import entry_terms, normalize
from transcript.jsonfile import DataFileError, write_atomic
from transcript.knowledge import Snapshot
from transcript.narrata import EntryRef, NarrataGlossary, Participant

REPORT_FORMAT_VERSION = 1

Severity = Literal["error", "warning"]
Code = Literal[
    "unusable_knowledge",  # the one error: the snapshot could not be built or read
    "empty_term",
    "shared_term",
    "ambiguous_asr_variant",
    "unreported_asr_variant",
    "stale_ambiguity",
    "variant_shadows_term",
    "unknown_character",
    "character_not_pc",
    "orphan_pc",
]


@dataclass(frozen=True)
class Finding:
    """One problem; `where` holds the field paths involved, `entries` the entries.

    Only an error carries a `message`: the parser's, which names file and field.
    """

    severity: Severity
    code: Code
    where: tuple[str, ...]
    entries: tuple[EntryRef, ...] = ()
    message: str | None = None


def unusable(error: DataFileError) -> Finding:
    """The finding for knowledge the parsers rejected."""
    return Finding("error", "unusable_knowledge", (), message=str(error))


@dataclass(frozen=True)
class _Term:
    path: str
    entry: EntryRef


@dataclass
class _Terms:
    """The glossary's terms by normalized key, first occurrence per entry and key."""

    names: dict[str, list[_Term]]  # names and aliases
    variants: dict[str, list[_Term]]
    empty: list[_Term]  # aliases and variants with nothing left after `normalize`


def diagnose(
    participants: Sequence[Participant], glossary: NarrataGlossary
) -> tuple[Finding, ...]:
    """Every finding for one knowledge state; each check reports in glossary order."""
    terms = _collect(glossary)
    return (
        *(_from_terms("empty_term", [term]) for term in terms.empty),
        *_shared_terms(terms),
        *_shared_variants(terms, glossary),
        *_stale_ambiguities(terms, glossary),
        *_shadowing_variants(terms),
        *_characters(participants, glossary),
    )


def _collect(glossary: NarrataGlossary) -> _Terms:
    terms = _Terms(names={}, variants={}, empty=[])
    for index, entry in enumerate(glossary.entries):
        for kind, field, text in entry_terms(entry):
            term = _Term(f"glossary[{index}].{field}", entry.ref)
            key = normalize(text)
            if not key:
                terms.empty.append(term)
                continue
            found = terms.variants if kind == "asr_variant" else terms.names
            shared = found.setdefault(key, [])
            if all(t.entry != entry.ref for t in shared):
                shared.append(term)
    return terms


def _shared_terms(terms: _Terms) -> Iterator[Finding]:
    for shared in terms.names.values():
        if len(shared) > 1:
            yield _from_terms("shared_term", shared)


def _shared_variants(terms: _Terms, glossary: NarrataGlossary) -> Iterator[Finding]:
    """A variant several entries carry, and whether Narrata reported it."""
    reported: dict[str, set[EntryRef]] = {}
    for ambiguity in glossary.ambiguities:
        reported.setdefault(normalize(ambiguity.variant), set()).update(
            ambiguity.entries
        )
    for key, shared in terms.variants.items():
        if len(shared) < 2:
            continue
        if {t.entry for t in shared} <= reported.get(key, set()):
            yield _from_terms("ambiguous_asr_variant", shared)
        else:
            yield _from_terms("unreported_asr_variant", shared)


def _stale_ambiguities(terms: _Terms, glossary: NarrataGlossary) -> Iterator[Finding]:
    """An ambiguity naming an entry that does not carry the variant."""
    for index, ambiguity in enumerate(glossary.ambiguities):
        shared = terms.variants.get(normalize(ambiguity.variant), [])
        carriers = {t.entry for t in shared}
        missing = [ref for ref in ambiguity.entries if ref not in carriers]
        if missing:
            yield _finding("stale_ambiguity", [f"asr_ambiguities[{index}]"], missing)


def _shadowing_variants(terms: _Terms) -> Iterator[Finding]:
    """A misrecognition that is another entry's name or alias."""
    for key, carriers in terms.variants.items():
        named = terms.names.get(key, [])
        for variant in carriers:
            others = [t for t in named if t.entry != variant.entry]
            if others:
                yield _from_terms("variant_shadows_term", [variant, *others])


def _characters(
    participants: Sequence[Participant], glossary: NarrataGlossary
) -> Iterator[Finding]:
    """Characters of active participants against the glossary's `pc` tier.

    The rule is Narrata's (ios-archiv docs/transcripts.md, "Relevanz"). A former
    participant's character may sit in the capped archive tier, so it is not checked.
    """
    indexes = {entry.ref: index for index, entry in enumerate(glossary.entries)}
    active: set[EntryRef] = set()
    for p_index, participant in enumerate(participants):
        if participant.is_former:
            continue
        for c_index, character in enumerate(participant.characters):
            path = f"participants[{p_index}].characters[{c_index}]"
            ref: EntryRef = ("person", character.person_id)
            active.add(ref)
            index = indexes.get(ref)
            if index is None:
                yield _finding("unknown_character", [path], [ref])
            elif glossary.entries[index].relevance != "pc":
                yield _finding("character_not_pc", [path, f"glossary[{index}]"], [ref])
    for index, entry in enumerate(glossary.entries):
        if entry.relevance == "pc" and entry.ref not in active:
            yield _finding("orphan_pc", [f"glossary[{index}]"], [entry.ref])


def _from_terms(code: Code, terms: Sequence[_Term]) -> Finding:
    return _finding(code, (t.path for t in terms), (t.entry for t in terms))


def _finding(code: Code, where: Iterable[str], entries: Iterable[EntryRef]) -> Finding:
    """Every code is a warning: the parsers turn what is unusable into errors."""
    return Finding("warning", code, tuple(where), tuple(entries))


def write_report(
    path: Path,
    findings: Sequence[Finding],
    snapshot: Snapshot | None = None,
    now: datetime.datetime | None = None,
) -> None:
    """Replace the report; `snapshot` is None when it could not be built or read."""
    moment = now or datetime.datetime.now().astimezone()
    snapshot_id, snapshot_file, context_file = (
        (snapshot.snapshot_id, snapshot.path.name, snapshot.source.file)
        if snapshot
        else (None, None, None)
    )
    errors, warnings = counts(findings)
    write_atomic(
        path,
        {
            "format_version": REPORT_FORMAT_VERSION,
            "created_at": moment.isoformat(timespec="seconds"),
            "snapshot_id": snapshot_id,
            "source": {"snapshot": snapshot_file, "context": context_file},
            "errors": errors,
            "warnings": warnings,
            "findings": [_finding_json(f) for f in findings],
        },
    )


def counts(findings: Sequence[Finding]) -> tuple[int, int]:
    """(errors, warnings) among `findings`."""
    errors = sum(f.severity == "error" for f in findings)
    return errors, len(findings) - errors


def describe(finding: Finding) -> str:
    """One console line: severity, code, positions and ids, never a name."""
    if finding.message is not None:
        return f"{finding.severity} {finding.code}: {finding.message}"
    entries = ", ".join(f"{kind} {entry_id}" for kind, entry_id in finding.entries)
    return f"{finding.severity} {finding.code}: {', '.join(finding.where)} ({entries})"


def _finding_json(finding: Finding) -> dict[str, Any]:
    data: dict[str, Any] = {
        "severity": finding.severity,
        "code": finding.code,
        "where": list(finding.where),
        "entries": [{"type": t, "id": i} for t, i in finding.entries],
    }
    if finding.message is not None:
        data["message"] = finding.message
    return data
