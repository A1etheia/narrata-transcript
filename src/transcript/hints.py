"""Review hints: where the ASR text may name a glossary entry (TOOL-44).

After the ASR, the recognised words are compared with the session's knowledge.
A known misrecognition of an entry is a strong signal (`known_variant`); a
spelling or sound close to a name or alias is a weak one (`similar`). A hint is
only a pointer for the review: it never changes the transcript, and when more
than one entry fits it lists all of them as `ambiguous` and picks none.

The thresholds are first values, to be calibrated in TOOL-35. Hints hold real
names, so this module logs nothing.
"""

import difflib
import unicodedata
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from transcript.domain import DomainContext, TermHit
from transcript.glossary import MatchKind, normalize
from transcript.narrata import EntryRef, EntryType, Relevance
from transcript.reference import Passage, ReferenceTranscript

Signal = Literal["known_variant", "similar"]
Method = Literal["spelling", "sound"]

MAX_SPAN_WORDS = 4  # longest word sequence compared with a term
MIN_SIMILAR_LENGTH = 4  # letters a term and a span need for `similar`
MAX_LENGTH_DEVIATION = 0.3  # of the term's length
MIN_SPELLING_RATIO = 0.85
MIN_SOUND_CODE = 3  # shorter Cologne codes collide too often


@dataclass(frozen=True)
class Candidate:
    """One entry a hint may point to, with the term that matched."""

    type: EntryType
    id: int | str
    term: str  # as Narrata spells it
    kind: MatchKind
    field: str  # where the term sits in the entry, e.g. `aliases[1]`
    relevance: Relevance
    biased: bool  # the term was among the ASR hints of the run

    @property
    def ref(self) -> EntryRef:
        return (self.type, self.id)


@dataclass(frozen=True)
class Hint:
    """A stretch of recognised words that may name one of `candidates`.

    `first_word` and `last_word` index `Passage.words`; both are `None` when the
    passage has no words and the hint was found in its text.
    """

    passage: int
    first_word: int | None
    last_word: int | None
    start_ms: int | None
    end_ms: int | None
    heard: str  # the recognised words, unchanged
    signal: Signal
    method: Method | None  # how `similar` matched; `None` for `known_variant`
    score: float | None  # spelling ratio of `similar`, 0..1
    candidates: tuple[Candidate, ...]  # in glossary order
    ambiguous: bool


@dataclass(frozen=True)
class _Token:
    text: str  # as recognised
    key: str  # normalized, punctuation at the edges removed
    word: int | None  # position in `Passage.words`
    start_ms: int | None
    end_ms: int | None


@dataclass(frozen=True, eq=False)
class _Term:
    hit: TermHit
    compact: str  # normalized without spaces
    code: str  # Cologne phonetics
    spelling: difflib.SequenceMatcher  # with `compact` as the side it analyses


@dataclass(frozen=True)
class _Found:
    first: int  # token positions, inclusive
    last: int
    hint: Hint | None  # None: a correctly recognised name or alias

    @property
    def size(self) -> int:
        return self.last - self.first + 1


def find_hints(
    reference: ReferenceTranscript, domain: DomainContext
) -> tuple[Hint, ...]:
    """The review hints of `reference`, in transcript order; reads, never writes."""
    matcher = _Matcher(domain, reference.asr.keywords_used)
    return tuple(
        hint for passage in reference.passages for hint in matcher.passage(passage)
    )


class _Matcher:
    def __init__(self, domain: DomainContext, keywords_used: Sequence[str]) -> None:
        self._domain = domain
        self._biased = {normalize(term) for term in keywords_used}
        self._order = {entry.ref: n for n, entry in enumerate(domain.entries)}
        self._by_letter: dict[tuple[str, int], list[_Term]] = defaultdict(list)
        self._by_code: dict[str, list[_Term]] = defaultdict(list)
        self._close: dict[str, tuple[Method, float | None, list[TermHit]] | None] = {}
        span = 1
        for hit in domain.match_candidates():
            key = normalize(hit.term)
            compact = key.replace(" ", "")
            if len(compact) < MIN_SIMILAR_LENGTH:
                continue
            span = max(span, len(key.split(" ")))
            term = _Term(
                hit,
                compact,
                cologne_phonetic(compact),
                difflib.SequenceMatcher(None, b=compact, autojunk=False),
            )
            self._by_letter[(compact[0], len(compact))].append(term)
            if len(term.code) >= MIN_SOUND_CODE:
                self._by_code[term.code].append(term)
        self._span = min(span, MAX_SPAN_WORDS)

    def passage(self, passage: Passage) -> Iterator[Hint]:
        tokens = _tokens(passage)
        found: list[_Found] = []
        for first in range(len(tokens)):
            keys: list[str] = []
            for last in range(first, min(first + self._span, len(tokens))):
                if not tokens[last].key:
                    break  # a span never bridges a bare punctuation mark
                keys.append(tokens[last].key)
                match = self._match(passage, tokens[first : last + 1], keys)
                if match is not False:
                    found.append(_Found(first, last, match))
        # A recognised term wins, then a strong signal, then the longer span.
        found.sort(key=lambda f: (_rank(f), -f.size, f.first))
        taken: list[_Found] = []
        occupied: set[int] = set()
        for match in found:
            positions = range(match.first, match.last + 1)
            if occupied.isdisjoint(positions):
                taken.append(match)
                occupied.update(positions)
        for match in sorted(taken, key=lambda f: f.first):
            if match.hint is not None:
                yield match.hint

    def _match(
        self, passage: Passage, span: Sequence[_Token], keys: Sequence[str]
    ) -> Hint | None | Literal[False]:
        """The hint for `span`; `None` for a recognised term, `False` for no match."""
        key = " ".join(keys)
        hits: Sequence[TermHit] = self._domain.lookup(key)
        method: Method | None = None
        score: float | None = None
        if hits:
            if all(hit.kind != "asr_variant" for hit in hits):
                return None
            signal: Signal = "known_variant"
            shared = self._domain.is_ambiguous(key)
        else:
            similar = self._similar("".join(keys), span[0].text)
            if similar is None:
                return False
            signal, shared = "similar", False
            method, score, hits = similar
        candidates = self._candidates(hits)
        return Hint(
            passage=passage.index,
            first_word=span[0].word,
            last_word=span[-1].word,
            start_ms=span[0].start_ms,
            end_ms=span[-1].end_ms,
            heard=" ".join(token.text for token in span),
            signal=signal,
            method=method,
            score=None if score is None else round(score, 3),
            candidates=candidates,
            ambiguous=shared or len({c.ref for c in candidates}) > 1,
        )

    def _similar(
        self, compact: str, heard: str
    ) -> tuple[Method, float | None, list[TermHit]] | None:
        """Terms close to `compact`; only for a capitalised span, as names are."""
        initial = next((c for c in heard if c.isalpha()), "")
        if len(compact) < MIN_SIMILAR_LENGTH or not initial.isupper():
            return None
        if compact not in self._close:  # speech repeats its words
            self._close[compact] = self._closest(compact)
        return self._close[compact]

    def _closest(
        self, compact: str
    ) -> tuple[Method, float | None, list[TermHit]] | None:
        spelled: list[tuple[float, TermHit]] = []
        for term in self._near(compact):
            matcher = term.spelling
            matcher.set_seq1(compact)
            if matcher.quick_ratio() < MIN_SPELLING_RATIO:
                continue
            ratio = matcher.ratio()
            if ratio >= MIN_SPELLING_RATIO:
                spelled.append((ratio, term.hit))
        if spelled:
            return "spelling", max(r for r, _ in spelled), [h for _, h in spelled]
        code = cologne_phonetic(compact)
        if len(code) < MIN_SOUND_CODE:
            return None
        sounded = [
            term.hit
            for term in self._by_code.get(code, ())
            if _close_in_length(len(compact), len(term.compact))
        ]
        return ("sound", None, sounded) if sounded else None

    def _near(self, compact: str) -> Iterator[_Term]:
        """Terms starting with the same letter and close enough in length."""
        length = len(compact)
        longest = int(length / (1 - MAX_LENGTH_DEVIATION)) + 1
        for size in range(MIN_SIMILAR_LENGTH, longest + 1):
            if _close_in_length(length, size):
                yield from self._by_letter.get((compact[0], size), ())

    def _candidates(self, hits: Sequence[TermHit]) -> tuple[Candidate, ...]:
        """One candidate per entry, the first matching term, in glossary order."""
        first: dict[EntryRef, TermHit] = {}
        for hit in hits:
            first.setdefault(hit.entry.ref, hit)
        return tuple(
            Candidate(
                type=hit.entry.type,
                id=hit.entry.id,
                term=hit.term,
                kind=hit.kind,
                field=hit.field,
                relevance=hit.entry.relevance,
                biased=normalize(hit.term) in self._biased,
            )
            for hit in sorted(first.values(), key=lambda h: self._order[h.entry.ref])
        )


def _tokens(passage: Passage) -> list[_Token]:
    if passage.words:
        return [
            _Token(word.text, _key(word.text), n, word.start_ms, word.end_ms)
            for n, word in enumerate(passage.words)
        ]
    return [_Token(text, _key(text), None, None, None) for text in passage.text.split()]


def _key(text: str) -> str:
    """`normalize` without punctuation or symbols at either edge."""
    key = normalize(text)
    start, end = 0, len(key)
    while start < end and unicodedata.category(key[start])[0] in "PS":
        start += 1
    while end > start and unicodedata.category(key[end - 1])[0] in "PS":
        end -= 1
    return key[start:end]


def _close_in_length(length: int, term_length: int) -> bool:
    return abs(length - term_length) <= MAX_LENGTH_DEVIATION * term_length


def _rank(found: _Found) -> int:
    """Correctly recognised terms first, then strong, then weak signals."""
    if found.hint is None:
        return 0
    return 1 if found.hint.signal == "known_variant" else 2


_UMLAUTS = str.maketrans({"Ä": "A", "Ö": "O", "Ü": "U", "ß": "S"})


def cologne_phonetic(term: str) -> str:
    """The Kölner Phonetik code of `term`, e.g. `Müller` → `657`.

    Letters outside A-Z after removing accents (such as `Æ`) are dropped.
    """
    upper = term.upper().translate(_UMLAUTS)
    plain = unicodedata.normalize("NFKD", upper)
    letters = [c for c in plain if "A" <= c <= "Z"]
    codes = "".join(
        _code(
            c,
            letters[i - 1] if i > 0 else "",
            letters[i + 1] if i + 1 < len(letters) else "",
            i == 0,
        )
        for i, c in enumerate(letters)
    )
    collapsed = [c for i, c in enumerate(codes) if i == 0 or c != codes[i - 1]]
    return "".join(c for i, c in enumerate(collapsed) if c != "0" or i == 0)


def _code(c: str, before: str, after: str, initial: bool) -> str:
    if c in "AEIJOUY":
        return "0"
    if c == "H":
        return ""
    if c == "B":
        return "1"
    if c == "P":
        return "3" if after == "H" else "1"
    if c in "DT":
        return "8" if after in ("C", "S", "Z") else "2"
    if c in "FVW":
        return "3"
    if c in "GKQ":
        return "4"
    if c == "C":
        if initial:
            return "4" if after in tuple("AHKLOQRUX") else "8"
        if before in ("S", "Z"):
            return "8"
        return "4" if after in tuple("AHKOQUX") else "8"
    if c == "X":
        return "8" if before in ("C", "K", "Q") else "48"
    if c == "L":
        return "5"
    if c in "MN":
        return "6"
    if c == "R":
        return "7"
    return "8"  # S, Z
