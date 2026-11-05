"""Looking up glossary terms and picking keyword candidates for ASR hints.

Works on `narrata.NarrataGlossary` only and does no file I/O. Matching compares a
normalized key; every returned string keeps Narrata's spelling. A term several
entries share returns all of them: the glossary never decides which one is meant.
"""

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from transcript.narrata import GlossaryEntry, NarrataGlossary

MatchKind = Literal["name", "alias", "asr_variant"]

_WHITESPACE = re.compile(r"\s+")


def normalize(term: str) -> str:
    """The comparison key: case-folded `tidy` form.

    Composed and decomposed umlauts compare equal, as do `ß` and `SS`. NFC rather
    than NFKC, so ligatures and superscripts in fantasy names stay distinct.
    """
    # casefold can leave a string that is no longer NFC, hence tidy twice
    return tidy(tidy(term).casefold())


def tidy(term: str) -> str:
    """NFC without invisible format characters, whitespace collapsed and trimmed.

    Keeps letters and case, so the result is still Narrata's spelling.
    """
    visible = "".join(
        c for c in unicodedata.normalize("NFC", term) if unicodedata.category(c) != "Cf"
    )
    return _WHITESPACE.sub(" ", visible).strip()


@dataclass(frozen=True)
class Match:
    entry: GlossaryEntry
    kind: MatchKind


class GlossaryIndex:
    """Finds entries by name, alias or known misrecognition."""

    def __init__(self, glossary: NarrataGlossary) -> None:
        self._matches: dict[str, list[Match]] = {}
        for entry in glossary.entries:
            seen: set[str] = set()  # one match per entry and key, the strongest kind
            for kind, _, term in entry_terms(entry):
                key = normalize(term)
                if key and key not in seen:
                    seen.add(key)
                    self._matches.setdefault(key, []).append(Match(entry, kind))

    def lookup(self, term: str) -> tuple[Match, ...]:
        """Every entry `term` names, in glossary order; empty if none."""
        return tuple(self._matches.get(normalize(term), ()))


def keyword_terms(glossary: NarrataGlossary) -> tuple[str, ...]:
    """Names and aliases, tidied, in glossary order, without repeats.

    Narrata delivers the glossary nearest tier first, so the order carries over.
    Misrecognitions are left out: biasing towards them would invite the error.
    Neither cuts to a token budget nor picks tiers.
    """
    seen: set[str] = set()
    terms: list[str] = []
    for entry in glossary.entries:
        for term in (entry.name, *entry.aliases):
            key = normalize(term)
            if key and key not in seen:
                seen.add(key)
                terms.append(tidy(term))
    return tuple(terms)


def entry_terms(entry: GlossaryEntry) -> Iterator[tuple[MatchKind, str, str]]:
    """(kind, field, term) for every term of `entry`, strongest kind first.

    `field` locates the term within the entry, e.g. `aliases[1]`.
    """
    yield "name", "name", entry.name
    for position, alias in enumerate(entry.aliases):
        yield "alias", f"aliases[{position}]", alias
    for position, variant in enumerate(entry.asr_variants):
        yield "asr_variant", f"asr_variants[{position}]", variant
