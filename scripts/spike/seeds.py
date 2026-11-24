"""Seed spike (TOOL-102): what a second and third Whisper run would give back.

    seeds.py <group>/<ordinal> [--variant base] [--seeds 3] [--clip ...] [--suggest]

Reads the stored runs of `asr.py` (one root per seed) and the hand references
under `review/calibration/`. Over the whole segment it aligns the runs pairwise
and counts where they differ and where one loses a block of words. Per clip it
counts, for every omission of one run, whether another run has the word right
(the oracle), and scores the naive union of the runs against the hand
reference. Three rules that need no reference follow, over the segment and per
clip: R1 takes per 30-second window the run with the most words, R2 offers what
another run has more as an alternative, R3 hints at `confident` passages where
the runs deviate. It writes nothing.

    seeds.py <group>/<ordinal> [--variant base] --with <variant> [--seeds 3] [--clip ...]

With `--with` (TOOL-104) it prints only the oracle and the naive union across
two variants, per clip, in both directions and for every pair of one run each.

Privacy (TOOL-66): the console gets counts, shares, error rates and times only,
no text, no token, no names and no speaker labels.
"""

import argparse
import itertools
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import asr
import denoise
from denoise import SEGMENT, HandClip, SpikeError, _pct
from omissions import MAX_WORD_MS, Ranges

from transcript import calibration
from transcript.config import DEFAULT_CONFIG, LEVELS, Level, load_config
from transcript.hints import stored_hints
from transcript.jsonfile import DataFileError
from transcript.reference import ReferenceTranscript
from transcript.session import SessionKey, SessionPaths
from transcript.timecode import format_clock
from transcript.uncertainty import PassageRating, segment_assessment

# thresholds fixed in the plan, before any count was seen
BLOCK_TOKENS = 20  # a run lacks this many tokens in a row that another run has
RASTER_MS = 30_000
RASTER_TOKENS = 5  # a raster window with this many deviating tokens counts
SUGGEST_MS = 180_000  # length of a window proposed for a new hand reference
SUGGESTIONS = 3
HINT_TOKENS = (1, 2, 3)  # R3: a passage deviating by this many tokens gets a hint
# `--with` (TOOL-104, not in the TOOL-102 plan): omitted tokens in a row count as a block
CROSS_BLOCK_TOKENS = 5

HIT, SUBSTITUTED, DELETED = "hit", "substituted", "deleted"


@dataclass(frozen=True)
class Run:
    """The tokens of one seed over segment 1, each with the start of its word."""

    seed: int
    tokens: tuple[str, ...]
    starts: tuple[int, ...]  # ms on the segment's timeline
    untimed: int  # tokens left out: neither the word nor its passage has a start
    passages: tuple[int, ...]  # per token: the index of its passage
    levels: Mapping[int, Level]  # per passage
    spans: Mapping[int, tuple[int, int]]  # per passage: start and end in ms
    spoken: Ranges  # the time of all passages
    flagged: Ranges  # the time of the passages not rated `confident`
    squeezed: Ranges  # passages at or above the compression ratio for repetition


def timed(
    seed: int,
    reference: ReferenceTranscript,
    ratings: Sequence[PassageRating],
    compression_ratio: float,
) -> Run:
    tokens: list[str] = []
    starts: list[int] = []
    passages: list[int] = []
    spans: dict[int, tuple[int, int]] = {}
    squeezed: list[tuple[int, int]] = []
    untimed = 0
    for passage in reference.passages:
        first = passage.start_ms or 0
        spans[passage.index] = (first, max(first, passage.end_ms or first))
        if passage.signals.get("compression_ratio", 0.0) >= compression_ratio:
            squeezed.append(spans[passage.index])
        for word in passage.words:
            start = word.start_ms if word.start_ms is not None else passage.start_ms
            found = calibration.tokens(word.text)
            if start is None:
                untimed += len(found)
                continue
            tokens += found
            starts += [start] * len(found)
            passages += [passage.index] * len(found)
    levels = {rating.passage: rating.level for rating in ratings}
    return Run(
        seed,
        tuple(tokens),
        tuple(starts),
        untimed,
        tuple(passages),
        levels,
        spans,
        Ranges.union(spans.values()),
        Ranges.union(s for p, s in spans.items() if levels[p] != "confident"),
        Ranges.union(squeezed),
    )


# --- segment ------------------------------------------------------------------------


@dataclass(frozen=True)
class Gap:
    """Tokens one run has in a row where the other has fewer."""

    start_ms: int  # where the run that has them places them
    end_ms: int
    tokens: int  # how many more it has


@dataclass(frozen=True)
class Pair:
    first: int  # seed
    second: int
    changed: int  # tokens both have at the same place, but different ones
    lacking: Mapping[int, Sequence[Gap]]  # seed -> what it lacks against the other
    raster: tuple[int, ...]  # deviating tokens per raster window


# where two runs differ: token ranges (i1, i2) of the one and (j1, j2) of the other
Diff = tuple[int, int, int, int]
Diffs = Mapping[tuple[int, int], Sequence[Diff]]  # per pair of seeds, lower first


def aligned(a: Run, b: Run, end_ms: int) -> list[Diff]:
    """Align two runs section by section and keep where they differ."""
    found: list[Diff] = []
    cuts_a = _cuts(a, asr.SECTION_MS, end_ms)
    cuts_b = _cuts(b, asr.SECTION_MS, end_ms)
    for (a0, a1), (b0, b1) in zip(cuts_a, cuts_b, strict=True):
        matcher = SequenceMatcher(a=a.tokens[a0:a1], b=b.tokens[b0:b1], autojunk=False)
        found += [
            (a0 + i1, a0 + i2, b0 + j1, b0 + j2)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes()
            if tag != "equal"
        ]
    return found


def towards(base: Run, other: Run, diffs: Diffs) -> Sequence[Diff]:
    """The differences of a pair with `base` on the left."""
    if (base.seed, other.seed) in diffs:
        return diffs[base.seed, other.seed]
    return [(j1, j2, i1, i2) for i1, i2, j1, j2 in diffs[other.seed, base.seed]]


def compare(a: Run, b: Run, found: Sequence[Diff], end_ms: int) -> Pair:
    """Count the differences of two runs; a token counts where its word starts."""
    changed = 0
    lacking: dict[int, list[Gap]] = {a.seed: [], b.seed: []}
    raster = [0] * -(-end_ms // RASTER_MS)
    for i1, i2, j1, j2 in found:
        own, other = i2 - i1, j2 - j1
        changed += min(own, other)
        # the longer side says where the deviation lies
        lacks, starts = (a, b.starts[j1:j2]) if other >= own else (b, a.starts[i1:i2])
        for start in starts:
            raster[min(start // RASTER_MS, len(raster) - 1)] += 1
        if own != other:
            lacking[lacks.seed].append(
                Gap(min(starts), max(starts) + MAX_WORD_MS, abs(own - other))
            )
    return Pair(a.seed, b.seed, changed, lacking, tuple(raster))


def _cuts(run: Run, step_ms: int, end_ms: int) -> list[tuple[int, int]]:
    """Token ranges per step of the timeline, in the order of the transcript."""
    count = -(-end_ms // step_ms)
    cuts = [0] * (count + 1)
    step = 0
    for position, start in enumerate(run.starts):
        # a word timed before its predecessor stays in the predecessor's step
        target = min(start // step_ms, count - 1)
        while step < target:
            step += 1
            cuts[step] = position
    for later in range(step + 1, count + 1):
        cuts[later] = len(run.starts)
    return list(itertools.pairwise(cuts))


def _blocks(gaps: Sequence[Gap]) -> list[Gap]:
    return [gap for gap in gaps if gap.tokens >= BLOCK_TOKENS]


def _touches(spot: tuple[int, int], ranges: Ranges) -> bool:
    return any(start < spot[1] and end > spot[0] for start, end in ranges.spans())


def deviation(pairs: Sequence[Pair]) -> list[int]:
    """Per raster window the most deviating tokens any pair of runs has there."""
    return [max(counts) for counts in zip(*(p.raster for p in pairs), strict=True)]


def block_spots(seed: int, pairs: Sequence[Pair]) -> tuple[Ranges, int]:
    """Where `seed` loses a block against any other run, and how many of these
    places it loses against every other run."""
    against = [
        Ranges.union((g.start_ms, g.end_ms) for g in _blocks(p.lacking[seed]))
        for p in pairs
        if seed in (p.first, p.second)
    ]
    spots = Ranges.union(span for ranges in against for span in ranges.spans())
    everywhere = sum(
        all(_touches(spot, ranges) for ranges in against) for spot in spots.spans()
    )
    return spots, everywhere


def suggestions(
    found: Sequence[int], clips: Sequence[HandClip]
) -> list[tuple[int, int, int]]:
    """The windows where the runs deviate most, away from the clips and from
    each other: (start in ms, deviating tokens, most in one raster window)."""
    width = SUGGEST_MS // RASTER_MS
    taken = Ranges.union((clip.start_ms, clip.end_ms) for clip in clips)
    sums = [sum(found[n : n + width]) for n in range(len(found) - width + 1)]
    picked: list[tuple[int, int, int]] = []
    for first in sorted(range(len(sums)), key=lambda n: (-sums[n], n)):
        span = (first * RASTER_MS, first * RASTER_MS + SUGGEST_MS)
        if len(picked) == SUGGESTIONS:
            break
        if not _touches(span, taken):
            taken = Ranges.union([*taken.spans(), span])
            picked.append((span[0], sums[first], max(found[first : first + width])))
    return picked


def print_segment(runs: Sequence[Run], pairs: Sequence[Pair]) -> None:
    print("## Segment")
    print()
    print("| Seed | Wörter | ohne Zeit | Wiederholungsanteil |")
    print("| --- | --- | --- | --- |")
    for run in runs:
        print(
            f"| {run.seed} | {len(run.tokens)} | {run.untimed} | "
            f"{_pct(denoise._repetition(run.tokens))} |"
        )
    print()

    words = {run.seed: len(run.tokens) for run in runs}
    print(
        "| Seed | gegen Seed | andere Wörter an derselben Stelle | fehlt, steht im "
        "anderen | Anteil an dessen Wörtern | "
        f"Blöcke ab {BLOCK_TOKENS} Wörtern | Wörter in Blöcken | größter Block |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for pair in pairs:
        for seed, other in ((pair.first, pair.second), (pair.second, pair.first)):
            gaps = pair.lacking[seed]
            lost = sum(gap.tokens for gap in gaps)
            sizes = [gap.tokens for gap in _blocks(gaps)]
            print(
                f"| {seed} | {other} | {pair.changed} | {lost} | "
                f"{_pct(lost / (words[other] or 1))} | {len(sizes)} | {sum(sizes)} | "
                f"{max(sizes, default=0)} |"
            )
    print()

    print(
        "| Seed | Stellen mit Blockverlust | davon gegen alle anderen Seeds | "
        "Zeit in diesen Stellen (min) |"
    )
    print("| --- | --- | --- | --- |")
    for run in runs:
        spots, everywhere = block_spots(run.seed, pairs)
        print(
            f"| {run.seed} | {len(spots.starts)} | {everywhere} | "
            f"{asr._decimal(spots.total / 60_000)} |"
        )
    print()

    found = deviation(pairs)
    filled = {start // RASTER_MS for run in runs for start in run.starts}
    loud = sum(count >= RASTER_TOKENS for count in found)
    print(
        f"Raster: {loud} von {len(filled)} Fenstern à {RASTER_MS // 1000} s mit Wörtern "
        f"haben eine Abweichung ab {RASTER_TOKENS} Wörtern "
        f"({_pct(loud / (len(filled) or 1))})."
    )
    print()


def print_suggestions(found: Sequence[int], clips: Sequence[HandClip]) -> None:
    """Times and counts only."""
    print(
        f"| Vorschlag ({SUGGEST_MS // 60_000} min) | abweichende Wörter | "
        "größtes 30-s-Fenster |"
    )
    print("| --- | --- | --- |")
    for start, tokens, peak in suggestions(found, clips):
        print(
            f"| {format_clock(start)}–{format_clock(start + SUGGEST_MS)} | {tokens} | "
            f"{peak} |"
        )
    print()


# --- oracle -------------------------------------------------------------------------


@dataclass(frozen=True)
class ClipRun:
    run: Run
    indices: tuple[int, ...]  # the run's tokens whose words start in the clip
    tokens: tuple[str, ...]  # the same as text
    status: tuple[str, ...]  # per token of the hand reference
    found: calibration.Alignment
    hits: Mapping[int, int]  # position in `tokens` -> the reference token it hits
    durations: Mapping[int, int]  # per passage with a word in the clip: its time there

    @property
    def seed(self) -> int:
        return self.run.seed

    @property
    def counts(self) -> Counter[str]:
        return self.found.counts


def clip_run(
    run: Run,
    reference: ReferenceTranscript,
    hand: calibration.HandReference,
    clip: HandClip,
) -> ClipRun:
    texts, _, durations = calibration._clip_tokens(
        reference, clip.start_ms, clip.end_ms
    )
    indices = tuple(
        n for n, start in enumerate(run.starts) if clip.start_ms <= start < clip.end_ms
    )
    if [run.tokens[n] for n in indices] != texts:
        # `calibration` takes words with their own start only
        raise SpikeError(f"seed {run.seed}, clip {clip.name}: a word has no start")
    found = calibration.align(hand, texts)
    status = [HIT] * len(hand.tokens)
    for position in found.substituted:
        status[position] = SUBSTITUTED
    for position, _ in found.deletions:
        status[position] = DELETED
    # hits come in the same order on both sides
    hits = dict(
        zip(
            (n for n in range(len(texts)) if not (found.wrong[n] or found.absorbed[n])),
            (position for position, kind in enumerate(status) if kind == HIT),
            strict=True,
        )
    )
    return ClipRun(run, indices, tuple(texts), tuple(status), found, hits, durations)


def merged(base: Sequence[str], other: Sequence[str]) -> list[str]:
    """`base` with the tokens added that `other` has more at the same place."""
    out: list[str] = []
    matcher = SequenceMatcher(a=base, b=other, autojunk=False)
    for _, i1, i2, j1, j2 in matcher.get_opcodes():
        out += base[i1:i2]
        more = (j2 - j1) - (i2 - i1)
        if more > 0:
            out += other[j2 - more : j2]
    return out


def _fate(base: ClipRun, others: Sequence[ClipRun]) -> dict[int, str]:
    """Per reference token `base` omits: the best any of `others` has for it."""
    return {
        n: HIT
        if any(run.status[n] == HIT for run in others)
        else SUBSTITUTED
        if any(run.status[n] == SUBSTITUTED for run in others)
        else DELETED
        for n, status in enumerate(base.status)
        if status == DELETED
    }


def _errors(counts: Mapping[str, int]) -> int:
    return sum(counts[k] for k in ("substitutions", "deletions", "insertions"))


def _eai(counts: Mapping[str, int]) -> str:
    return f"{counts['substitutions']} / {counts['deletions']} / {counts['insertions']}"


def _signed(value: int) -> str:
    return str(value).replace("-", "−")


def _points(value: float) -> str:
    return f"{value * 100:.1f}".replace(".", ",").replace("-", "−")


def print_clip(
    clip: HandClip, hand: calibration.HandReference, runs: Sequence[ClipRun]
) -> None:
    words = len(hand.tokens)
    print(f"## Referenz {clip.name}")
    print()
    print(f"{words} Referenzwörter")
    print()

    print(
        "| Basis-Seed | WER | E / A / Ei | Auslassungen: ein anderer Seed hat das "
        "Wort richtig | nur als Ersetzung | fehlt in allen Seeds | WER Orakel | "
        "Gewinn (Punkte) |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    oracle: list[float] = []
    for base in runs:
        fate = Counter(_fate(base, [run for run in runs if run is not base]).values())
        errors = _errors(base.counts)
        oracle.append(fate[HIT] / words)
        print(
            f"| {base.seed} | {_pct(errors / words)} | {_eai(base.counts)} | "
            f"{fate[HIT]} | {fate[SUBSTITUTED]} | {fate[DELETED]} | "
            f"{_pct((errors - fate[HIT]) / words)} | {_points(oracle[-1])} |"
        )
    print()

    print(
        "| Basis-Seed | Wörter dazu | E / A / Ei | WER Vereinigung | Gewinn (Punkte) | "
        "Auslassungen weniger | Einfügungen mehr | Ersetzungen mehr |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    union: list[float] = []
    for base in runs:
        tokens = list(base.tokens)
        for run in runs:
            if run is not base:
                tokens = merged(tokens, run.tokens)
        counts = calibration.align(hand, tokens).counts
        union.append((_errors(base.counts) - _errors(counts)) / words)
        print(
            f"| {base.seed} | {len(tokens) - len(base.tokens)} | {_eai(counts)} | "
            f"{_pct(_errors(counts) / words)} | {_points(union[-1])} | "
            f"{_signed(base.counts['deletions'] - counts['deletions'])} | "
            f"{_signed(counts['insertions'] - base.counts['insertions'])} | "
            f"{_signed(counts['substitutions'] - base.counts['substitutions'])} |"
        )
    print()
    print(
        f"Im Mittel über die Basis-Seeds: Orakel {_points(sum(oracle) / len(oracle))} "
        f"Punkte, naive Vereinigung {_points(sum(union) / len(union))} Punkte."
    )
    print()


def _in_blocks(status: Sequence[str]) -> set[int]:
    """The omitted reference tokens in a row of at least `CROSS_BLOCK_TOKENS`."""
    found: set[int] = set()
    for omitted, group in itertools.groupby(
        enumerate(status), key=lambda item: item[1] == DELETED
    ):
        row = [position for position, _ in group]
        if omitted and len(row) >= CROSS_BLOCK_TOKENS:
            found.update(row)
    return found


def print_cross(
    clip: HandClip,
    hand: calibration.HandReference,
    sides: Mapping[str, Sequence[ClipRun]],
) -> None:
    """The oracle and the naive union of one run with one run of the other variant.

    Both directions, every pair of seeds; a pair with the same tokens as an
    earlier one is left out.
    """
    words = len(hand.tokens)
    print(f"## Referenz {clip.name}")
    print()
    print(f"{words} Referenzwörter")
    print()
    print(
        "| Basis | zweiter Lauf | WER | E / A / Ei | Auslassungen: der zweite Lauf hat "
        f"das Wort richtig | davon in Folgen ab {CROSS_BLOCK_TOKENS} Wörtern | nur als "
        "Ersetzung | fehlt auch dort | WER Orakel | Gewinn (Punkte) | "
        "WER Vereinigung | Gewinn (Punkte) |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for (name, runs), (other_name, others) in itertools.permutations(sides.items(), 2):
        seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        for base, other in itertools.product(runs, others):
            if (base.tokens, other.tokens) in seen:
                continue
            seen.add((base.tokens, other.tokens))
            found = _fate(base, [other])
            fate = Counter(found.values())
            in_blocks = sum(found[n] == HIT for n in _in_blocks(base.status))
            union = _errors(
                calibration.align(hand, merged(base.tokens, other.tokens)).counts
            )
            errors = _errors(base.counts)
            print(
                f"| {name}#{base.seed} | {other_name}#{other.seed} | "
                f"{_pct(errors / words)} | {_eai(base.counts)} | {fate[HIT]} | "
                f"{in_blocks} | {fate[SUBSTITUTED]} | {fate[DELETED]} | "
                f"{_pct((errors - fate[HIT]) / words)} | "
                f"{_points(fate[HIT] / words)} | {_pct(union / words)} | "
                f"{_points((errors - union) / words)} |"
            )
    print()


# --- rules without a reference ------------------------------------------------------


@dataclass(frozen=True)
class Choice:
    """R1: per raster window the run with the most words."""

    picks: tuple[tuple[Run, int, int], ...]  # per window: the run and its tokens
    narrowed: int  # windows where a run was left out for repetition
    undecided: int  # of these: every run was left out, so all stayed in

    def tokens(self, start_ms: int = 0, end_ms: int | None = None) -> list[str]:
        return [
            run.tokens[n]
            for run, low, high in self.picks
            for n in range(low, high)
            if start_ms <= run.starts[n] and (end_ms is None or run.starts[n] < end_ms)
        ]


def choose(runs: Sequence[Run], end_ms: int) -> Choice:
    """`runs` in the order of their seeds: the lowest seed wins a tie."""
    cuts = [_cuts(run, RASTER_MS, end_ms) for run in runs]
    picks: list[tuple[Run, int, int]] = []
    narrowed = undecided = 0
    for window, ranges in enumerate(zip(*cuts, strict=True)):
        span = (window * RASTER_MS, (window + 1) * RASTER_MS)
        sound = [
            not _touches(span, run.squeezed)
            and denoise._repetition(run.tokens[low:high]) == 0
            for run, (low, high) in zip(runs, ranges, strict=True)
        ]
        narrowed += not all(sound)
        if not any(sound):
            undecided += 1
            sound = [True] * len(runs)
        run, (low, high) = max(
            itertools.compress(zip(runs, ranges, strict=True), sound),
            key=lambda pair: pair[1][1] - pair[1][0],
        )
        picks.append((run, low, high))
    return Choice(tuple(picks), narrowed, undecided)


@dataclass(frozen=True)
class Alternative:
    """R2: tokens another run has in a row where the base has fewer."""

    indices: range  # in the other run
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class Kind:
    """R2: which alternatives count."""

    label: str
    least: int  # tokens
    agreed: bool = False  # every other run offers one of this size at the place


EVERY = Kind("1", 1)  # as planned, and what the go rule counts
# the two block kinds were added after the first count
KINDS = (
    EVERY,
    Kind(str(BLOCK_TOKENS), BLOCK_TOKENS),
    Kind(f"{BLOCK_TOKENS}, in jedem anderen Seed", BLOCK_TOKENS, agreed=True),
)


def _places(alternatives: Sequence[tuple[int, Alternative]]) -> Ranges:
    return Ranges.union((alt.start_ms, alt.end_ms) for _, alt in alternatives)


@dataclass(frozen=True)
class View:
    """What the other runs say about one run as the base."""

    base: Run
    offers: Mapping[int, Sequence[Alternative]]  # R2: per other seed
    # R3: per passage of the base the tokens that differ, in the run differing most
    deviating: Counter[int]

    def longer(self, kind: Kind) -> list[tuple[int, Alternative]]:
        """The alternatives of a kind, each with the seed that offers it."""
        found = [
            (seed, alt)
            for seed, alts in self.offers.items()
            for alt in alts
            if len(alt.indices) >= kind.least
        ]
        if not kind.agreed:
            return found
        spans = {
            seed: Ranges.union((a.start_ms, a.end_ms) for s, a in found if s == seed)
            for seed in self.offers
        }
        return [
            (seed, alt)
            for seed, alt in found
            if all(
                _touches((alt.start_ms, alt.end_ms), ranges)
                for other, ranges in spans.items()
                if other != seed
            )
        ]

    def hinted(self, tokens: int) -> list[int]:
        """The `confident` passages that deviate by at least `tokens`."""
        return [
            passage
            for passage, level in self.base.levels.items()
            if level == "confident" and self.deviating[passage] >= tokens
        ]


def view(base: Run, runs: Sequence[Run], diffs: Diffs) -> View:
    offers: dict[int, list[Alternative]] = {}
    deviating: Counter[int] = Counter()
    for other in runs:
        if other is base:
            continue
        offers[other.seed] = []
        own_count: Counter[int] = Counter()
        for i1, i2, j1, j2 in towards(base, other, diffs):
            more = (j2 - j1) - (i2 - i1)
            own_count.update(base.passages[i1:i2])
            if more <= 0:
                continue
            starts = other.starts[j2 - more : j2]
            offers[other.seed].append(
                Alternative(
                    range(j2 - more, j2), min(starts), max(starts) + MAX_WORD_MS
                )
            )
            if base.passages:
                # the surplus counts for the passage it follows
                anchor = i2 - 1 if i2 > i1 else max(i1 - 1, 0)
                own_count[base.passages[min(anchor, len(base.passages) - 1)]] += more
        deviating |= own_count  # the most any other run says
    return View(base, offers, deviating)


def _levels(counts: Mapping[str, int]) -> str:
    return " / ".join(str(counts[level]) for level in LEVELS)


def _minutes(ms: int) -> str:
    return asr._decimal(ms / 60_000)


def print_rules_segment(
    runs: Sequence[Run], views: Sequence[View], choice: Choice, end_ms: int
) -> None:
    print("## Regeln über das Segment")
    print()
    print("### R1: Fensterwahl")
    print()
    print(
        "| Lauf | Wörter | Wiederholungsanteil | Passagen "
        f"({' / '.join(LEVELS)}) | markierte Zeit |"
    )
    print("| --- | --- | --- | --- | --- |")
    for label, one in [
        *((f"Seed {run.seed}", choose([run], end_ms)) for run in runs),
        ("R1", choice),
    ]:
        tokens = one.tokens()
        seen = {
            (run.seed, passage): run.levels[passage]
            for run, low, high in one.picks
            for passage in run.passages[low:high]
        }
        flagged = spoken = 0
        for window, (run, _, _) in enumerate(one.picks):
            span = (window * RASTER_MS, (window + 1) * RASTER_MS)
            flagged += run.flagged.within(*span).total
            spoken += run.spoken.within(*span).total
        print(
            f"| {label} | {len(tokens)} | {_pct(denoise._repetition(tokens))} | "
            f"{_levels(Counter(seen.values()))} | {_pct(flagged / (spoken or 1))} |"
        )
    print()
    won = Counter(run.seed for run, low, high in choice.picks if high > low)
    print(
        "R1 nimmt "
        + ", ".join(f"{won[run.seed]} Fenster aus Seed {run.seed}" for run in runs)
        + f". In {choice.narrowed} Fenstern schied ein Lauf wegen Wiederholung aus, "
        f"in {choice.undecided} davon jeder."
    )
    print()

    print("### R2: Alternative an der Lücke")
    print()
    print(
        "| Basis-Seed | Alternative ab Wörtern | Stellen mit Alternative | "
        "Alternativ-Wörter | Zeit der Stellen (min) | davon außerhalb markierter "
        "Passagen (min) | markierte Zeit vorher | mehr (Punkte) |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for found in views:
        base = found.base
        whole = base.spoken.total or 1
        for kind in KINDS:
            offered = found.longer(kind)
            words = sum(len(alt.indices) for _, alt in offered)
            places = _places(offered)
            outside = places.minus(base.flagged).total
            print(
                f"| {base.seed} | {kind.label} | {len(places.starts)} | {words} | "
                f"{_minutes(places.total)} | {_minutes(outside)} | "
                f"{_pct(base.flagged.total / whole)} | {_points(outside / whole)} |"
            )
    print()

    print("### R3: Abweichung als Review-Hinweis")
    print()
    print(
        "| Basis-Seed | Abweichung ab Wörtern | Passagen `confident` | davon mit "
        "Hinweis | Anteil | markierte Zeit vorher | mehr (Punkte) |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for found in views:
        base = found.base
        confident = Counter(base.levels.values())["confident"]
        whole = base.spoken.total or 1
        for tokens in HINT_TOKENS:
            hinted = found.hinted(tokens)
            more = Ranges.union(base.spans[p] for p in hinted).minus(base.flagged).total
            print(
                f"| {base.seed} | {tokens} | {confident} | {len(hinted)} | "
                f"{_pct(len(hinted) / (confident or 1))} | "
                f"{_pct(base.flagged.total / whole)} | {_points(more / whole)} |"
            )
    print()


def _mean(values: Sequence[float]) -> float:
    return sum(values) / (len(values) or 1)


def print_rules_clip(
    clip: HandClip,
    hand: calibration.HandReference,
    runs: Sequence[ClipRun],
    views: Sequence[View],
    choice: Choice,
) -> None:
    words = len(hand.tokens)
    print(f"### R1 an {clip.name}")
    print()
    print("| Lauf | Wörter im Clip | WER | E / A / Ei |")
    print("| --- | --- | --- | --- |")
    rates = []
    for base in runs:
        rates.append(_errors(base.counts) / words)
        print(
            f"| Seed {base.seed} | {len(base.tokens)} | {_pct(rates[-1])} | "
            f"{_eai(base.counts)} |"
        )
    picked = choice.tokens(clip.start_ms, clip.end_ms)
    counts = calibration.align(hand, picked).counts
    rate = _errors(counts) / words
    print(f"| R1 | {len(picked)} | {_pct(rate)} | {_eai(counts)} |")
    print()
    print(
        f"R1 gegenüber dem Mittel der Seeds: {_points(_mean(rates) - rate)} Punkte, "
        f"gegenüber dem besten Seed: {_points(min(rates) - rate)} Punkte."
    )
    print()

    print(f"### R2 an {clip.name}")
    print()
    print(
        "| Basis-Seed | Alternative ab Wörtern | Auslassungen | mit richtiger "
        "Alternative | Auslassungen in `confident` | mit richtiger Alternative | "
        "Alternativ-Wörter | füllen eine Auslassung | sonst richtig | falsch | an "
        "unverständlicher Stelle | Zeit der Stellen am Clip |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    # per run: errors and omissions per passage, omissions in `confident` passages
    passages = [_passage_errors(base) for base in runs]
    local = {
        other.seed: {index: n for n, index in enumerate(other.indices)}
        for other in runs
    }
    by_seed = {other.seed: other for other in runs}
    shares = []
    for base, found, (_, _, quiet) in zip(runs, views, passages, strict=True):
        for kind in KINDS:
            filled: set[int] = set()
            fate: Counter[str] = Counter()
            offered = found.longer(kind)
            for seed, alt in offered:
                other = by_seed[seed]
                for n in (local[seed][i] for i in alt.indices if i in local[seed]):
                    if other.found.absorbed[n]:
                        fate["absorbed"] += 1
                    elif n not in other.hits:
                        fate["wrong"] += 1
                    elif base.status[other.hits[n]] == DELETED:
                        fate["fills"] += 1
                        filled.add(other.hits[n])
                    else:
                        fate["right"] += 1
            if kind == EVERY:
                shares.append(len(quiet & filled) / (len(quiet) or 1))
            time = _places(offered).within(clip.start_ms, clip.end_ms).total
            print(
                f"| {base.seed} | {kind.label} | {base.counts['deletions']} | "
                f"{len(filled)} | {len(quiet)} | {len(quiet & filled)} | "
                f"{sum(fate.values())} | {fate['fills']} | {fate['right']} | "
                f"{fate['wrong']} | {fate['absorbed']} | "
                f"{_pct(time / (clip.end_ms - clip.start_ms))} |"
            )
    print()
    print(
        "Im Mittel über die Basis-Seeds bekommen "
        f"{_pct(_mean(shares))} der Auslassungen in `confident` eine richtige "
        "Alternative."
    )
    print()

    print(f"### R3 an {clip.name}")
    print()
    print(
        "| Basis-Seed | Abweichung ab Wörtern | Fehler in `confident` | davon mit "
        "Hinweis | Auslassungen in `confident` | davon mit Hinweis | Passagen mit "
        "Hinweis | davon ohne Fehler | markierte Zeit am Clip vorher | mehr (Punkte) |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    marked: dict[int, list[float]] = {tokens: [] for tokens in HINT_TOKENS}
    for base, found, (errors, omitted, quiet) in zip(
        runs, views, passages, strict=True
    ):
        run = base.run
        time = base.durations
        whole = sum(time.values()) or 1
        confident = [p for p in time if run.levels[p] == "confident"]
        before = sum(ms for p, ms in time.items() if run.levels[p] != "confident")
        for tokens in HINT_TOKENS:
            hinted = [p for p in found.hinted(tokens) if p in time]
            caught = sum(omitted[p] for p in hinted)
            marked[tokens].append(caught / (len(quiet) or 1))
            print(
                f"| {base.seed} | {tokens} | {sum(errors[p] for p in confident)} | "
                f"{sum(errors[p] for p in hinted)} | {len(quiet)} | {caught} | "
                f"{len(hinted)} | {sum(not errors[p] for p in hinted)} | "
                f"{_pct(before / whole)} | "
                f"{_points(sum(time[p] for p in hinted) / whole)} |"
            )
    print()
    print(
        "Im Mittel über die Basis-Seeds liegen in Passagen mit Hinweis: "
        + ", ".join(
            f"{_pct(_mean(found))} der Auslassungen in `confident` ab {tokens}"
            for tokens, found in marked.items()
        )
        + "."
    )
    print()


def _passage_errors(base: ClipRun) -> tuple[Counter[int], Counter[int], set[int]]:
    """Per passage the errors and the omissions, as `calibration.evaluate` places
    them, and the omitted reference tokens that lie in `confident` passages."""
    run = base.run
    errors: Counter[int] = Counter()
    omitted: Counter[int] = Counter()
    quiet: set[int] = set()
    for n, index in enumerate(base.indices):
        errors[run.passages[index]] += base.found.wrong[n]
    for position, near in base.found.deletions:
        if near is None:
            continue
        passage = run.passages[base.indices[near]]
        errors[passage] += 1
        omitted[passage] += 1
        if run.levels[passage] == "confident":
            quiet.add(position)
    return errors, omitted, quiet


# --- main ---------------------------------------------------------------------------


def _stored(
    paths: SessionPaths, name: str, seeds: int
) -> dict[int, ReferenceTranscript]:
    return {seed: asr.transcribed(paths, name, seed) for seed in range(1, seeds + 1)}


def _sections(
    paths: SessionPaths, name: str, references: Mapping[int, ReferenceTranscript]
) -> list[asr.Sections]:
    return [asr.sections(paths, name, seed, r) for seed, r in references.items()]


def _timed_runs(
    paths: SessionPaths, name: str, references: Mapping[int, ReferenceTranscript]
) -> list[Run]:
    runs = []
    for seed, reference in references.items():
        root = asr.shadow_root(paths, name, seed)
        thresholds = load_config(root / "config.yaml").review_uncertainty
        hints = stored_hints(SessionPaths(paths.key, root), SEGMENT)
        ratings = segment_assessment(reference, hints, thresholds).ratings
        runs.append(timed(seed, reference, ratings, thresholds.compression_ratio))
    return runs


def measure_cross(
    paths: SessionPaths,
    names: Sequence[str],
    seeds: int,
    clips: Sequence[HandClip],
) -> None:
    """What one variant has right where the other omits, per clip."""
    stored = {name: _stored(paths, name, seeds) for name in names}
    asr.check_provenance(
        [s for name, found in stored.items() for s in _sections(paths, name, found)]
    )
    # only tokens and starts are used here; the ratings come along with `timed`
    runs = {name: _timed_runs(paths, name, found) for name, found in stored.items()}
    for clip in clips:
        hand = calibration.read_hand_reference(
            paths.review_dir / "calibration" / clip.file
        )
        print_cross(
            clip,
            hand,
            {
                name: [
                    clip_run(run, stored[name][run.seed], hand, clip)
                    for run in runs[name]
                ]
                for name in names
            },
        )


def measure(
    paths: SessionPaths,
    name: str,
    seeds: int,
    clips: Sequence[HandClip],
    suggest: bool,
) -> None:
    if seeds < 2:
        raise SpikeError("a comparison needs at least two seeds")
    references = _stored(paths, name, seeds)
    asr.check_provenance(_sections(paths, name, references))
    end_ms = asr._end_ms(paths)
    runs = _timed_runs(paths, name, references)
    diffs = {
        (a.seed, b.seed): aligned(a, b, end_ms)
        for a, b in itertools.combinations(runs, 2)
    }
    pairs = [
        compare(a, b, diffs[a.seed, b.seed], end_ms)
        for a, b in itertools.combinations(runs, 2)
    ]
    print_segment(runs, pairs)
    if suggest:
        print_suggestions(deviation(pairs), clips)
    views = [view(base, runs, diffs) for base in runs]
    choice = choose(runs, end_ms)
    print_rules_segment(runs, views, choice, end_ms)
    for clip in clips:
        hand = calibration.read_hand_reference(
            paths.review_dir / "calibration" / clip.file
        )
        found = [clip_run(run, references[run.seed], hand, clip) for run in runs]
        print_clip(clip, hand, found)
        print_rules_clip(clip, hand, found, views, choice)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("session", help="session key <group>/<ordinal>")
    parser.add_argument("--variant", default="base", type=asr._variant_arg)
    parser.add_argument("--seeds", type=int, default=3, help="seeds 1..N")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--clip",
        action="append",
        type=asr.parse_clip,
        help="NAME=FILE@H:MM:SS-H:MM:SS (default: pilot clips A and B)",
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="propose windows for a new hand reference where the seeds deviate most",
    )
    parser.add_argument(
        "--with",
        dest="other",
        type=asr._variant_arg,
        help="a second variant: only the oracle and the union across both, per clip",
    )
    args = parser.parse_args(argv)
    if args.other and args.suggest:
        parser.error("--suggest has no meaning with --with")
    clips = args.clip or denoise.CLIPS
    try:
        paths = load_config(args.config).session_paths(SessionKey.parse(args.session))
        if args.other:
            measure_cross(paths, (args.variant, args.other), args.seeds, clips)
        else:
            measure(paths, args.variant, args.seeds, clips, args.suggest)
    except (SpikeError, ValueError, OSError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
