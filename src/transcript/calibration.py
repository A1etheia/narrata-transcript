"""Measuring the uncertainty rules against a hand-checked reference (TOOL-35).

A hand reference is a plain text file someone wrote while listening to a stretch
of one segment. Its conventions come from the TOOL-62 spike: a line may start
with a one-word speaker label (`Name:`), notes in square brackets are not
speech, and `???` marks an inaudible stretch. Recognised words that fall into
such a stretch are `absorbed`: they count neither as right nor as inserted.

The recognised words are aligned with the reference by difflib, close to but
not exactly a minimal word error rate. Every substitution and insertion points
at a recognised word; every deletion at the place between two recognised
words, and with it at a passage. The report compares that with the passage
ratings. It holds counts and shares only: no text, no names, and the speaker
labels of the reference appear as `S1`, `S2`, … in order of appearance.

The `similar` sheet lists review hints for someone to judge by listening; the
judged sheet gives the precision of the `similar` signal. Both sheets hold real
names and stay under `work/`.
"""

import bisect
import csv
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import astuple, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from transcript.config import LEVELS, Level, UncertaintyThresholds
from transcript.hints import stored_hints
from transcript.jsonfile import DataFileError
from transcript.reference import Passage, ReferenceTranscript, load_reference
from transcript.session import SessionPaths
from transcript.timecode import format_ms
from transcript.uncertainty import PassageRating, Rule, segment_assessment

_TOKEN = re.compile(r"[\w'-]+")
_LABEL = re.compile(r"^\s*([^\s:]+):")
_NOTE = re.compile(r"\[[^\]]*\]")
_UNKNOWN = re.compile(r"\?{3,}")
TOP_SHARES = (0.1, 0.2, 0.3)  # of the words with the lowest confidence
SHEET_SIZE = 50  # most hints on a `similar` sheet
SHEET_COLUMNS = (
    "hint",
    "segment",
    "time",
    "heard",
    "candidates",
    "method",
    "score",
    "ambiguous",
    "correct",
)
_YES = {"j", "ja", "y", "yes", "1", "true"}
_NO = {"n", "nein", "no", "0", "false"}
SCORE_BANDS = (0.9, 0.95)  # `spelling` scores below, between and above


class CalibrationError(DataFileError):
    """A hand reference or sheet is missing or invalid; never names its content."""


def tokens(text: str) -> list[str]:
    """Lower-cased words as the alignment compares them."""
    return [token.casefold() for token in _TOKEN.findall(text)]


@dataclass(frozen=True)
class HandReference:
    tokens: tuple[str, ...]
    speakers: tuple[str, ...]  # `S1`, `S2`, … per token; `S?` before any label
    gaps: frozenset[int]  # token positions where an inaudible stretch sits


def parse_hand_reference(text: str) -> HandReference:
    words: list[str] = []
    speakers: list[str] = []
    gaps: set[int] = set()
    names: dict[str, str] = {}
    speaker = "S?"
    for line in text.splitlines():
        label = _LABEL.match(line)
        if label:
            name = label.group(1)
            speaker = names.setdefault(name, f"S{len(names) + 1}")
            line = line[label.end() :]
        for number, piece in enumerate(_UNKNOWN.split(_NOTE.sub(" ", line))):
            if number:
                gaps.add(len(words))
            found = tokens(piece)
            words += found
            speakers += [speaker] * len(found)
    return HandReference(tuple(words), tuple(speakers), frozenset(gaps))


def read_hand_reference(path: Path) -> HandReference:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        raise CalibrationError(f"{path}: hand reference is unreadable") from None
    reference = parse_hand_reference(text)
    if not reference.tokens:
        raise CalibrationError(f"{path}: hand reference has no words")
    return reference


@dataclass(frozen=True)
class Alignment:
    """How recognised tokens relate to the reference tokens."""

    wrong: tuple[bool, ...]  # per recognised token: substituted or inserted
    absorbed: tuple[bool, ...]  # per recognised token: inside an inaudible stretch
    # per deleted reference token: (its position, the recognised token next to it)
    deletions: tuple[tuple[int, int | None], ...]
    substituted: tuple[int, ...]  # reference positions of substitutions
    counts: Counter[str]  # hits, substitutions, deletions, insertions, absorbed


def align(reference: HandReference, hypothesis: Sequence[str]) -> Alignment:
    wrong = [False] * len(hypothesis)
    absorbed = [False] * len(hypothesis)
    deletions: list[tuple[int, int | None]] = []
    substituted: list[int] = []
    counts: Counter[str] = Counter(
        dict.fromkeys(
            ("hits", "substitutions", "deletions", "insertions", "absorbed"), 0
        )
    )
    matcher = SequenceMatcher(a=reference.tokens, b=hypothesis, autojunk=False)
    for tag, ref_start, ref_end, hyp_start, hyp_end in matcher.get_opcodes():
        ref_len, hyp_len = ref_end - ref_start, hyp_end - hyp_start
        if tag == "equal":
            counts["hits"] += ref_len
            continue
        paired = min(ref_len, hyp_len)
        for n in range(paired):
            wrong[hyp_start + n] = True
            substituted.append(ref_start + n)
        counts["substitutions"] += paired
        # the last recognised token of the block, else the one after it
        near = (
            None
            if not hypothesis
            else min(hyp_end - 1 if hyp_len else hyp_start, len(hypothesis) - 1)
        )
        for position in range(ref_start + paired, ref_end):
            deletions.append((position, near))
        counts["deletions"] += ref_len - paired
        at_gap = any(ref_start <= gap <= ref_end for gap in reference.gaps)
        for n in range(hyp_start + paired, hyp_end):
            if at_gap:
                absorbed[n] = True
            else:
                wrong[n] = True
        counts["absorbed" if at_gap else "insertions"] += hyp_len - paired
    return Alignment(
        tuple(wrong), tuple(absorbed), tuple(deletions), tuple(substituted), counts
    )


@dataclass(frozen=True)
class _Token:
    passage: int
    word: int
    confidence: float | None


def _clip_tokens(
    reference: ReferenceTranscript, start_ms: int, end_ms: int
) -> tuple[list[str], list[_Token], dict[int, int]]:
    """Tokens of the words starting in the range, and passage time in it."""
    texts: list[str] = []
    origins: list[_Token] = []
    durations: dict[int, int] = {}
    for passage in reference.passages:
        for number, word in enumerate(passage.words):
            if word.start_ms is None or not start_ms <= word.start_ms < end_ms:
                continue
            durations.setdefault(passage.index, _overlap(passage, start_ms, end_ms))
            for token in tokens(word.text):
                texts.append(token)
                origins.append(_Token(passage.index, number, word.confidence))
    return texts, origins, durations


def _overlap(passage: Passage, start_ms: int, end_ms: int) -> int:
    first = passage.start_ms if passage.start_ms is not None else start_ms
    last = passage.end_ms if passage.end_ms is not None else first
    return max(0, min(last, end_ms) - max(first, start_ms))


@dataclass(frozen=True)
class Tally:
    """Passages of one level or rule and the errors they hold."""

    passages: int = 0
    ms: int = 0  # passage time inside the measured range
    errors: int = 0
    deletions: int = 0
    with_errors: int = 0  # passages holding at least one error

    def __add__(self, other: "Tally") -> "Tally":
        return Tally(
            *(a + b for a, b in zip(astuple(self), astuple(other), strict=True))
        )


@dataclass(frozen=True)
class Report:
    words: int  # reference words
    recognised: int  # recognised tokens in the range
    counts: Counter[str]
    speaker_words: Counter[str]  # per reference label
    speaker_errors: Counter[str]  # substitutions + deletions per reference label
    by_level: dict[Level, Tally]
    by_rule: dict[Rule, Tally]
    unplaced_deletions: int
    auc: float | None
    lowest: dict[float, float] = field(default_factory=dict)

    @property
    def errors(self) -> int:
        return sum(self.counts[k] for k in ("substitutions", "deletions", "insertions"))

    @property
    def flagged(self) -> Tally:
        """The passages rated `needs_review` or `uncertain`."""
        return sum(
            (t for level, t in self.by_level.items() if level != "confident"), Tally()
        )

    def lines(self) -> list[str]:
        errors = self.errors
        out = [
            f"reference: {self.words} word(s), recognised: {self.recognised} token(s)",
            (
                f"errors: {errors} ({_share(errors, self.words)} WER): "
                f"{self.counts['substitutions']} substitution(s), "
                f"{self.counts['deletions']} deletion(s), "
                f"{self.counts['insertions']} insertion(s), "
                f"{self.counts['absorbed']} absorbed"
            ),
        ]
        for label, words in sorted(self.speaker_words.items()):
            wrong = self.speaker_errors[label]
            out.append(
                f"speaker {label}: {words} word(s), {_share(wrong, words)} wrong"
            )
        total = sum(self.by_level.values(), Tally())
        for level in LEVELS:
            out.append(_tally_line(level, self.by_level[level], total, errors))
        flagged = self.flagged
        out.append(_tally_line("flagged", flagged, total, errors))
        out.append(
            f"missed: {self.by_level['confident'].errors} error(s) in confident "
            f"passages, {self.by_level['confident'].deletions} of them deletion(s); "
            f"false alarms: {flagged.passages - flagged.with_errors} flagged "
            f"passage(s) without error"
        )
        for rule, tally in sorted(self.by_rule.items()):
            out.append(
                f"rule {rule}: {tally.passages} passage(s), "
                f"{tally.with_errors} with error(s), {tally.errors} error(s), "
                f"{tally.deletions} deletion(s)"
            )
        if self.unplaced_deletions:
            out.append(
                f"deletions without a recognised word: {self.unplaced_deletions}"
            )
        if self.auc is not None:
            shares = ", ".join(
                f"lowest {share:.0%}: {_percent(found)}"
                for share, found in self.lowest.items()
            )
            out.append(f"confidence AUC {self.auc:.2f}; wrong words in {shares}")
        return out


def _tally_line(name: str, tally: Tally, total: Tally, errors: int) -> str:
    return (
        f"{name}: {tally.passages} passage(s) ({_share(tally.passages, total.passages)}),"
        f" {_share(tally.ms, total.ms)} of the time, {tally.errors} error(s) "
        f"({_share(tally.errors, errors)}), {tally.deletions} deletion(s)"
    )


def _share(part: int, whole: int) -> str:
    return _percent(part / whole if whole else None)


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def measure(
    paths: SessionPaths,
    segment: int,
    hand: HandReference,
    start_ms: int,
    end_ms: int,
    thresholds: UncertaintyThresholds,
) -> Report:
    """Rate the stored transcript of `segment` anew and compare it with `hand`.

    Nothing is written, so changed thresholds take effect on the next call.
    """
    if end_ms <= start_ms:
        raise ValueError("--end must lie after --start")
    reference = load_reference(paths, segment)
    if reference.status != "transcribed":
        raise ValueError(f"segment {segment} is not transcribed")
    assessment = segment_assessment(reference, stored_hints(paths, segment), thresholds)
    return evaluate(reference, assessment.ratings, hand, start_ms, end_ms)


def evaluate(
    reference: ReferenceTranscript,
    ratings: Sequence[PassageRating],
    hand: HandReference,
    start_ms: int,
    end_ms: int,
) -> Report:
    """Compare the ratings of the passages in `start_ms`..`end_ms` with `hand`."""
    texts, origins, durations = _clip_tokens(reference, start_ms, end_ms)
    alignment = align(hand, texts)
    errors: Counter[int] = Counter()
    deletions: Counter[int] = Counter()
    for n, origin in enumerate(origins):
        errors[origin.passage] += alignment.wrong[n]
    unplaced = 0
    for _, near in alignment.deletions:
        if near is None:
            unplaced += 1
        else:
            errors[origins[near].passage] += 1
            deletions[origins[near].passage] += 1

    by_level = {level: Tally() for level in LEVELS}
    by_rule: dict[Rule, Tally] = {}
    for rating in ratings:
        number = rating.passage
        if number not in durations:
            continue
        one = Tally(
            1, durations[number], errors[number], deletions[number], errors[number] > 0
        )
        by_level[rating.level] += one
        for rule in dict.fromkeys(r.rule for r in rating.reasons):
            by_rule[rule] = by_rule.get(rule, Tally()) + one

    speaker_errors = Counter(hand.speakers[p] for p in alignment.substituted)
    speaker_errors.update(hand.speakers[p] for p, _ in alignment.deletions)
    words = _word_labels(origins, alignment)
    auc, lowest = _confidence_metrics(words)
    return Report(
        words=len(hand.tokens),
        recognised=len(texts),
        counts=alignment.counts,
        speaker_words=Counter(hand.speakers),
        speaker_errors=speaker_errors,
        by_level=by_level,
        by_rule=by_rule,
        unplaced_deletions=unplaced,
        auc=auc,
        lowest=lowest,
    )


def _word_labels(
    origins: Sequence[_Token], alignment: Alignment
) -> list[tuple[float, bool]]:
    """(confidence, wrong) per recognised word; absorbed words are left out."""
    confidence: dict[tuple[int, int], float] = {}
    wrong: dict[tuple[int, int], bool] = {}
    for n, origin in enumerate(origins):
        if origin.confidence is None or alignment.absorbed[n]:
            continue
        key = (origin.passage, origin.word)
        confidence[key] = origin.confidence
        wrong[key] = wrong.get(key, False) or alignment.wrong[n]
    return [(confidence[key], wrong[key]) for key in confidence]


def _confidence_metrics(
    words: Sequence[tuple[float, bool]],
) -> tuple[float | None, dict[float, float]]:
    wrong = [c for c, bad in words if bad]
    right = [c for c, bad in words if not bad]
    if not wrong or not right:
        return None, {}
    # AUC: chance that a wrong word has lower confidence than a right one.
    ranked = sorted(right)
    below = 0.0
    for value in wrong:
        lower = bisect.bisect_left(ranked, value)
        equal = bisect.bisect_right(ranked, value) - lower
        below += len(ranked) - lower - equal + equal / 2
    auc = below / (len(wrong) * len(right))
    ordered = sorted(words, key=lambda w: w[0])
    lowest = {
        share: sum(bad for _, bad in ordered[: round(share * len(ordered))])
        / len(wrong)
        for share in TOP_SHARES
    }
    return auc, lowest


@dataclass(frozen=True)
class SheetRow:
    hint: str  # `<segment>-<number>`, stable for the same hint files
    segment: int
    time: str
    heard: str
    candidates: str
    method: str
    score: str
    ambiguous: bool


def similar_sheet(paths: SessionPaths, indices: Iterable[int]) -> list[SheetRow]:
    """Up to `SHEET_SIZE` `similar` hints, spread evenly over the session."""
    rows: list[SheetRow] = []
    for index in indices:
        found = stored_hints(paths, index)
        for number, hint in enumerate(found.hints if found else (), start=1):
            if hint.signal != "similar":
                continue
            rows.append(
                SheetRow(
                    hint=f"{index}-{number}",
                    segment=index,
                    time="?" if hint.start_ms is None else format_ms(hint.start_ms),
                    heard=hint.heard,
                    candidates=" | ".join(c.term for c in hint.candidates),
                    method=hint.method or "",
                    score="" if hint.score is None else f"{hint.score:.3f}",
                    ambiguous=hint.ambiguous,
                )
            )
    if len(rows) <= SHEET_SIZE:
        return rows
    step = (len(rows) - 1) / (SHEET_SIZE - 1)
    return [rows[round(n * step)] for n in range(SHEET_SIZE)]


def write_sheet(path: Path, rows: Sequence[SheetRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(SHEET_COLUMNS)
        for row in rows:
            writer.writerow(
                (
                    row.hint,
                    row.segment,
                    row.time,
                    row.heard,
                    row.candidates,
                    row.method,
                    row.score,
                    "ja" if row.ambiguous else "nein",
                    "",
                )
            )


def judged_precision(path: Path) -> list[str]:
    """Precision of the judged `similar` hints per method and score band."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            # Spreadsheets in a German locale save with ';'; extra columns are kept.
            header = handle.readline()
            handle.seek(0)
            delimiter = ";" if header.count(";") > header.count(",") else ","
            reader = csv.DictReader(handle, delimiter=delimiter)
            rows = list(reader)
            columns = set(reader.fieldnames or ())
    except (OSError, UnicodeDecodeError, csv.Error):
        raise CalibrationError(f"{path}: judged sheet is unreadable") from None
    if not {"correct", "method", "score"} <= columns:
        raise CalibrationError(f"{path}: judged sheet lacks the columns of a sheet")
    if not rows:
        raise CalibrationError(f"{path}: judged sheet lists no hints")
    groups: dict[str, list[int]] = {}
    open_rows = 0
    for number, row in enumerate(rows, start=2):
        answer = (row.get("correct") or "").strip().casefold()
        if answer not in _YES | _NO:
            if answer:
                raise CalibrationError(
                    f"{path}: line {number}: field 'correct' invalid"
                )
            open_rows += 1
            continue
        tally = groups.setdefault(_band(row), [0, 0])
        tally[0] += 1
        tally[1] += answer in _YES
    lines = []
    total = [sum(t[0] for t in groups.values()), sum(t[1] for t in groups.values())]
    for name, (judged, right) in sorted(groups.items()) + [("all", tuple(total))]:
        lines.append(
            f"similar {name}: {right} of {judged} right ({_share(right, judged)})"
        )
    lines.append(f"not judged: {open_rows}")
    return lines


def _band(row: dict[str, str]) -> str:
    method = (row.get("method") or "").strip() or "unknown"
    if method != "spelling":
        return method
    try:
        score = float((row.get("score") or "").replace(",", "."))
    except ValueError:
        return "spelling"
    low, high = SCORE_BANDS
    if score < low:
        return f"spelling <{low}"
    return f"spelling {low}-{high}" if score < high else f"spelling >={high}"
