"""Review hints: where the ASR text may name a glossary entry (TOOL-44).

After the ASR, the recognised words are compared with the session's knowledge.
A known misrecognition of an entry is a strong signal (`known_variant`); a
spelling or sound close to a name or alias is a weak one (`similar`). A hint is
only a pointer for the review: it never changes the transcript, and when more
than one entry fits it lists all of them as `ambiguous` and picks none.

The `similar` thresholds come from `review.similar` in the configuration
(`SimilarThresholds`), calibrated in TOOL-35. Hints hold real
names, so this module logs nothing, and its error messages name file, field and
position, never a value.

`write_hints` stores the hints of one segment as `review/segment-NN.hints.json`,
together with the snapshot and the reference they came from.
"""

import dataclasses
import datetime
import difflib
import functools
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from transcript import jsonfile
from transcript.config import SimilarThresholds
from transcript.domain import DomainContext, TermHit
from transcript.glossary import MatchKind, normalize, word_key
from transcript.jsonfile import DataFileError, write_atomic
from transcript.narrata import (
    ENTRY_TYPES,
    RELEVANCE_TIERS,
    EntryRef,
    EntryType,
    Relevance,
    is_narrata_id,
)
from transcript.reference import Passage, ReferenceTranscript, load_reference
from transcript.session import SessionPaths

HINTS_FORMAT_VERSION = 1


class HintsError(DataFileError):
    """A hint file is missing, invalid or belongs to another segment."""


Signal = Literal["known_variant", "similar"]
Method = Literal["spelling", "sound"]

MAX_SPAN_WORDS = 4  # longest word sequence compared with a term
MIN_SOUND_CODE = 3  # shorter Cologne codes collide too often
DEFAULT_SIMILAR = SimilarThresholds()


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

    @property
    def nearest_relevance(self) -> Relevance:
        """The nearest tier among the candidates; a hint has at least one."""
        return min((c.relevance for c in self.candidates), key=RELEVANCE_TIERS.index)


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
    reference: ReferenceTranscript,
    domain: DomainContext,
    similar: SimilarThresholds = DEFAULT_SIMILAR,
) -> tuple[Hint, ...]:
    """The review hints of `reference`, in transcript order; reads, never writes."""
    matcher = _Matcher(domain, reference.asr.keywords_used, similar)
    return tuple(
        hint for passage in reference.passages for hint in matcher.passage(passage)
    )


class _Matcher:
    def __init__(
        self,
        domain: DomainContext,
        keywords_used: Sequence[str],
        similar: SimilarThresholds,
    ) -> None:
        self._domain = domain
        self._limits = similar
        self._biased = {normalize(term) for term in keywords_used}
        self._order = {entry.ref: n for n, entry in enumerate(domain.entries)}
        self._by_letter: dict[tuple[str, int], list[_Term]] = defaultdict(list)
        self._by_code: dict[str, list[_Term]] = defaultdict(list)
        self._close: dict[str, tuple[Method, float | None, list[TermHit]] | None] = {}
        span = 1
        for hit in domain.match_candidates():
            key = normalize(hit.term)
            compact = key.replace(" ", "")
            if len(compact) < similar.min_length:
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
        if len(compact) < self._limits.min_length or not initial.isupper():
            return None
        if compact not in self._close:  # speech repeats its words
            self._close[compact] = self._closest(compact)
        return self._close[compact]

    def _closest(
        self, compact: str
    ) -> tuple[Method, float | None, list[TermHit]] | None:
        spelled: list[tuple[float, TermHit]] = []
        min_ratio = self._limits.min_ratio
        for term in self._near(compact):
            matcher = term.spelling
            matcher.set_seq1(compact)
            if matcher.quick_ratio() < min_ratio:
                continue
            ratio = matcher.ratio()
            if ratio >= min_ratio:
                spelled.append((ratio, term.hit))
        if spelled:
            return "spelling", max(r for r, _ in spelled), [h for _, h in spelled]
        code = cologne_phonetic(compact)
        if len(code) < MIN_SOUND_CODE:
            return None
        sounded = [
            term.hit
            for term in self._by_code.get(code, ())
            if self._close_in_length(len(compact), len(term.compact))
        ]
        return ("sound", None, sounded) if sounded else None

    def _near(self, compact: str) -> Iterator[_Term]:
        """Terms starting with the same letter and close enough in length."""
        length = len(compact)
        longest = int(length / (1 - self._limits.max_length_deviation)) + 1
        for size in range(self._limits.min_length, longest + 1):
            if self._close_in_length(length, size):
                yield from self._by_letter.get((compact[0], size), ())

    def _close_in_length(self, length: int, term_length: int) -> bool:
        deviation = self._limits.max_length_deviation
        return abs(length - term_length) <= deviation * term_length

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
            _Token(word.text, word_key(word.text), n, word.start_ms, word.end_ms)
            for n, word in enumerate(passage.words)
        ]
    return [
        _Token(text, word_key(text), None, None, None) for text in passage.text.split()
    ]


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


@dataclass(frozen=True)
class SegmentHints:
    """The hints of one segment and what they were made from."""

    segment: int
    knowledge_snapshot_id: str | None
    reference_processed_at: str  # of the reference transcript that was read
    keywords_used: int  # ASR hints of that transcript
    hints: tuple[Hint, ...]

    def matches(self, reference: ReferenceTranscript) -> bool:
        """Whether these hints were made from this version of `reference`."""
        return (
            self.segment == reference.segment.index
            and self.reference_processed_at == reference.processing.processed_at
        )

    def by_passage(self) -> dict[int, tuple[Hint, ...]]:
        """The hints per passage index, each in transcript order."""
        grouped: dict[int, list[Hint]] = defaultdict(list)
        for hint in self.hints:
            grouped[hint.passage].append(hint)
        return {passage: tuple(found) for passage, found in grouped.items()}

    def counts(self) -> Counter[str]:
        """Hints per signal, plus `ambiguous` across both."""
        counts = Counter(hint.signal for hint in self.hints)
        counts["ambiguous"] = sum(hint.ambiguous for hint in self.hints)
        return counts


def segment_hints(
    reference: ReferenceTranscript,
    domain: DomainContext,
    similar: SimilarThresholds = DEFAULT_SIMILAR,
) -> SegmentHints:
    return SegmentHints(
        segment=reference.segment.index,
        knowledge_snapshot_id=domain.origin.snapshot_id,
        reference_processed_at=reference.processing.processed_at,
        keywords_used=len(reference.asr.keywords_used),
        hints=find_hints(reference, domain, similar),
    )


def review_session(
    paths: SessionPaths,
    indices: Iterable[int],
    domain: DomainContext | None,
    similar: SimilarThresholds,
) -> Counter[str] | None:
    """Write the hints of the transcribed segments among `indices`; their counts.

    Without knowledge there are no hints: stale files of `indices` are removed
    and the result is `None`. A segment without a transcribed reference keeps
    what it has, which still matches the reference that was kept.
    """
    selected = list(indices)
    if domain is None:
        for index in selected:
            paths.review_hints(index).unlink(missing_ok=True)
        return None
    total: Counter[str] = Counter()
    for index in selected:
        if not paths.reference(index).is_file():
            continue
        reference = load_reference(paths, index)
        if reference.status == "transcribed":
            found = segment_hints(reference, domain, similar)
            write_hints(paths, found)
            total += found.counts()
    return total


def write_hints(
    paths: SessionPaths, hints: SegmentHints, now: datetime.datetime | None = None
) -> None:
    """Replace the hint file of `hints.segment` atomically."""
    moment = now or datetime.datetime.now().astimezone()
    write_atomic(
        paths.review_hints(hints.segment),
        {
            "format_version": HINTS_FORMAT_VERSION,
            "session": str(paths.key),
            "segment": hints.segment,
            "created_at": moment.isoformat(timespec="seconds"),
            "knowledge_snapshot_id": hints.knowledge_snapshot_id,
            "reference": {
                "file": paths.reference(hints.segment).name,
                "processed_at": hints.reference_processed_at,
            },
            "keywords_used": hints.keywords_used,
            # an overview for people reading the file; `load_hints` ignores it
            "counts": dict(sorted(hints.counts().items())),
            "hints": [dataclasses.asdict(hint) for hint in hints.hints],
        },
    )


def stored_hints(paths: SessionPaths, index: int) -> SegmentHints | None:
    """The hints of segment `index`, or `None` without a hint file."""
    if not paths.review_hints(index).is_file():
        return None
    return load_hints(paths, index)


def load_hints(paths: SessionPaths, index: int) -> SegmentHints:
    """The stored hints of segment `index`; `HintsError` if absent or invalid."""
    path = paths.review_hints(index)
    data = _read_json(path, "review hints")
    if data.get("format_version") != HINTS_FORMAT_VERSION:
        raise HintsError(
            f"{path}: unsupported format_version; run transcript transcribe again"
        )
    if data.get("session") != str(paths.key) or data.get("segment") != index:
        raise HintsError(f"{path}: belongs to another session or segment")
    reference = _field(data, "reference", dict, path)
    return SegmentHints(
        segment=index,
        knowledge_snapshot_id=_optional(data, "knowledge_snapshot_id", str, path),
        reference_processed_at=_field(reference, "processed_at", str, path),
        keywords_used=_field(data, "keywords_used", int, path),
        hints=tuple(
            hint_from(item, number, path)
            for number, item in enumerate(
                jsonfile.list_of(data, "hints", dict, path, HintsError), start=1
            )
        ),
    )


def hint_from(data: dict[str, Any], number: int, path: Path) -> Hint:
    """One hint; an error from it names the hint number."""
    try:
        method = _optional(data, "method", str, path)
        return Hint(
            passage=_field(data, "passage", int, path),
            first_word=_optional(data, "first_word", int, path),
            last_word=_optional(data, "last_word", int, path),
            start_ms=_optional(data, "start_ms", int, path),
            end_ms=_optional(data, "end_ms", int, path),
            heard=_field(data, "heard", str, path),
            signal=_one_of(data, "signal", get_args(Signal), path),
            method=None if method is None else _one_of(data, "method", _METHODS, path),
            score=_number(data, "score", path),
            candidates=tuple(
                _candidate_from(item, path)
                for item in jsonfile.list_of(data, "candidates", dict, path, HintsError)
            ),
            ambiguous=_field(data, "ambiguous", bool, path),
        )
    except HintsError as error:
        detail = str(error).removeprefix(f"{path}: ")
        raise HintsError(f"{path}: hint {number}: {detail}") from None


def _candidate_from(data: dict[str, Any], path: Path) -> Candidate:
    if not is_narrata_id(data.get("id")):
        raise HintsError(f"{path}: field 'id' missing or invalid")
    return Candidate(
        type=_one_of(data, "type", ENTRY_TYPES, path),
        id=data["id"],
        term=_field(data, "term", str, path),
        kind=_one_of(data, "kind", get_args(MatchKind), path),
        field=_field(data, "field", str, path),
        relevance=_one_of(data, "relevance", RELEVANCE_TIERS, path),
        biased=_field(data, "biased", bool, path),
    )


_METHODS: tuple[Method, ...] = get_args(Method)
_field = functools.partial(jsonfile.field, error=HintsError)
_one_of = functools.partial(jsonfile.one_of, error=HintsError)
_optional = functools.partial(jsonfile.optional_field, error=HintsError)
_number = functools.partial(jsonfile.optional_number, error=HintsError)
_read_json = functools.partial(jsonfile.read_object, error=HintsError)
