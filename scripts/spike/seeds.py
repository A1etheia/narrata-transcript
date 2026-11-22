"""Seed spike (TOOL-102): what a second and third Whisper run would give back.

    seeds.py <group>/<ordinal> [--variant base] [--seeds 3] [--clip ...] [--suggest]

Reads the stored runs of `asr.py` (one root per seed) and the hand references
under `review/calibration/`. Over the whole segment it aligns the runs pairwise
and counts where they differ and where one loses a block of words. Per clip it
counts, for every omission of one run, whether another run has the word right
(the oracle), and scores the naive union of the runs against the hand
reference. It writes nothing.

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
from denoise import HandClip, SpikeError, _pct
from omissions import MAX_WORD_MS, Ranges

from transcript import calibration
from transcript.config import DEFAULT_CONFIG, load_config
from transcript.jsonfile import DataFileError
from transcript.reference import ReferenceTranscript
from transcript.session import SessionKey, SessionPaths
from transcript.timecode import format_clock

# thresholds fixed in the plan, before any count was seen
BLOCK_TOKENS = 20  # a run lacks this many tokens in a row that another run has
RASTER_MS = 30_000
RASTER_TOKENS = 5  # a raster window with this many deviating tokens counts
SUGGEST_MS = 180_000  # length of a window proposed for a new hand reference
SUGGESTIONS = 3

HIT, SUBSTITUTED, DELETED = "hit", "substituted", "deleted"


@dataclass(frozen=True)
class Run:
    """The tokens of one seed over segment 1, each with the start of its word."""

    seed: int
    tokens: tuple[str, ...]
    starts: tuple[int, ...]  # ms on the segment's timeline
    untimed: int  # tokens left out: neither the word nor its passage has a start


def timed(seed: int, reference: ReferenceTranscript) -> Run:
    tokens: list[str] = []
    starts: list[int] = []
    untimed = 0
    for passage in reference.passages:
        for word in passage.words:
            start = word.start_ms if word.start_ms is not None else passage.start_ms
            found = calibration.tokens(word.text)
            if start is None:
                untimed += len(found)
                continue
            tokens += found
            starts += [start] * len(found)
    return Run(seed, tuple(tokens), tuple(starts), untimed)


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


def compare(a: Run, b: Run, end_ms: int) -> Pair:
    """Align two runs section by section; a token counts where its word starts."""
    changed = 0
    lacking: dict[int, list[Gap]] = {a.seed: [], b.seed: []}
    raster = [0] * -(-end_ms // RASTER_MS)
    cuts_a, cuts_b = _sections(a, end_ms), _sections(b, end_ms)
    for (a0, a1), (b0, b1) in zip(cuts_a, cuts_b, strict=True):
        matcher = SequenceMatcher(a=a.tokens[a0:a1], b=b.tokens[b0:b1], autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            own, other = i2 - i1, j2 - j1
            changed += min(own, other)
            # the longer side says where the deviation lies
            lacks, starts = (
                (a, b.starts[b0 + j1 : b0 + j2])
                if other >= own
                else (b, a.starts[a0 + i1 : a0 + i2])
            )
            for start in starts:
                raster[min(start // RASTER_MS, len(raster) - 1)] += 1
            if own != other:
                lacking[lacks.seed].append(
                    Gap(min(starts), max(starts) + MAX_WORD_MS, abs(own - other))
                )
    return Pair(a.seed, b.seed, changed, lacking, tuple(raster))


def _sections(run: Run, end_ms: int) -> list[tuple[int, int]]:
    """Token ranges per 5-minute section, in the order of the transcript."""
    count = -(-end_ms // asr.SECTION_MS)
    cuts = [0] * (count + 1)
    section = 0
    for position, start in enumerate(run.starts):
        # a word timed before its predecessor stays in the predecessor's section
        target = min(start // asr.SECTION_MS, count - 1)
        while section < target:
            section += 1
            cuts[section] = position
    for later in range(section + 1, count + 1):
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
    seed: int
    tokens: tuple[str, ...]  # recognised in the clip
    status: tuple[str, ...]  # per token of the hand reference
    counts: Counter[str]


def clip_run(
    seed: int,
    reference: ReferenceTranscript,
    hand: calibration.HandReference,
    clip: HandClip,
) -> ClipRun:
    texts, _, _ = calibration._clip_tokens(reference, clip.start_ms, clip.end_ms)
    found = calibration.align(hand, texts)
    status = [HIT] * len(hand.tokens)
    for position in found.substituted:
        status[position] = SUBSTITUTED
    for position, _ in found.deletions:
        status[position] = DELETED
    return ClipRun(seed, tuple(texts), tuple(status), found.counts)


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
        others = [run for run in runs if run is not base]
        fate = Counter(
            HIT
            if any(run.status[n] == HIT for run in others)
            else SUBSTITUTED
            if any(run.status[n] == SUBSTITUTED for run in others)
            else DELETED
            for n, status in enumerate(base.status)
            if status == DELETED
        )
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


# --- main ---------------------------------------------------------------------------


def measure(
    paths: SessionPaths,
    name: str,
    seeds: int,
    clips: Sequence[HandClip],
    suggest: bool,
) -> None:
    if seeds < 2:
        raise SpikeError("a comparison needs at least two seeds")
    references = {
        seed: asr.transcribed(paths, name, seed) for seed in range(1, seeds + 1)
    }
    asr.check_provenance(
        [asr.sections(paths, name, seed, r) for seed, r in references.items()]
    )
    end_ms = asr._end_ms(paths)
    runs = [timed(seed, reference) for seed, reference in references.items()]
    pairs = [compare(a, b, end_ms) for a, b in itertools.combinations(runs, 2)]
    print_segment(runs, pairs)
    if suggest:
        print_suggestions(deviation(pairs), clips)
    for clip in clips:
        hand = calibration.read_hand_reference(
            paths.review_dir / "calibration" / clip.file
        )
        print_clip(
            clip,
            hand,
            [clip_run(seed, r, hand, clip) for seed, r in references.items()],
        )


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
    args = parser.parse_args(argv)
    try:
        paths = load_config(args.config).session_paths(SessionKey.parse(args.session))
        measure(
            paths, args.variant, args.seeds, args.clip or denoise.CLIPS, args.suggest
        )
    except (SpikeError, ValueError, OSError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
