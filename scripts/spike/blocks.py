"""Block spike (TOOL-108): is a block another run has more a loss or an invention?

    blocks.py <group>/<ordinal> [--main base] [--source base] [--seeds 3]
              [--least 20] [--clip ...] [--suggest]

Reads the stored runs of `asr.py`, the session's diarization and the hand
references under `review/calibration/`. Every run of `--main` is the main run
once; the runs of `--source` (the other seeds, if both are the same variant)
offer it the blocks of words they have more at one place. Each offer gets
signals that need no reference: how the source decoded the block, what the main
run looks like at the place, whether the diarization hears speech there, and
whether further runs have the same words. Per signal and clip it counts the
accepted blocks, how many of their words are right, and the error rate of the
main run with these blocks put in. It writes nothing.

A batched variant is read with seed 1 only: its seeds are word for word the
same (TOOL-104).

Privacy (TOOL-66): the console gets counts, shares, error rates and times only,
no text, no token, no names and no speaker labels.
"""

import argparse
import bisect
import itertools
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import asr
import denoise
import omissions
import seeds
from denoise import HandClip, SpikeError, _pct
from omissions import LONG_SILENT_MS, MAX_WORD_MS, N_A, Ranges

from transcript import calibration
from transcript.config import DEFAULT_CONFIG, UncertaintyThresholds, load_config
from transcript.jsonfile import DataFileError
from transcript.reference import ReferenceTranscript
from transcript.session import SessionKey, SessionPaths

# thresholds fixed in the plan, before any count was seen
BLOCK_TOKENS = seeds.BLOCK_TOKENS  # what the go rule counts
AGREE_MARGIN_MS = 5_000  # another run has the block if its words lie this close
AGREE_SHARE = 0.5  # ... and this share of the block's words recurs there in order
STRETCHED_MS = MAX_WORD_MS  # a word before the gap at least this long is stretched

Values = Mapping[str, float | None]
Test = Callable[[Values], bool | None]  # None: the signal does not exist for the run


@dataclass(frozen=True, eq=False)
class Loaded:
    """One stored run with what the signals read from it."""

    name: str
    run: seeds.Run
    reference: ReferenceTranscript
    signals: Mapping[int, Mapping[str, float]]  # per passage
    # decoding windows by start; None for a batched run, which has none
    windows: Sequence[asr.DecodeWindow] | None
    window_starts: Sequence[int]
    quiet: Ranges  # speech without words

    @property
    def label(self) -> str:
        return f"{self.name}#{self.run.seed}"

    def window(self, ms: int) -> asr.DecodeWindow:
        """The decoding window at a time; only for a run that has windows."""
        return self.windows[max(bisect.bisect_right(self.window_starts, ms) - 1, 0)]


def load(
    paths: SessionPaths, name: str, count: int, speech: Ranges
) -> tuple[list[Loaded], list[asr.Sections]]:
    batched = asr.variant(name).batched
    stored = seeds._stored(paths, name, 1 if batched else count)
    found = []
    for run in seeds._timed_runs(paths, name, stored):
        reference = stored[run.seed]
        windows = None
        if not batched:
            windows = sorted(
                asr.decode_windows(paths, name, run.seed), key=lambda w: w.start_ms
            )
        found.append(
            Loaded(
                name,
                run,
                reference,
                {p.index: p.signals for p in reference.passages},
                windows,
                [w.start_ms for w in windows or ()],
                omissions.silence(reference, speech),
            )
        )
    return found, seeds._sections(paths, name, stored)


def besides(main: Loaded, sources: Sequence[Loaded]) -> list[Loaded]:
    return [source for source in sources if source is not main]


# --- offers -------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Offer:
    """Tokens `source` has in a row where `main` has fewer."""

    main: Loaded
    source: Loaded
    low: int  # the main run's tokens [low, high) stand where the block belongs
    high: int
    indices: range  # in the source
    start_ms: int  # where the source places the block
    end_ms: int

    @property
    def tokens(self) -> tuple[str, ...]:
        return self.source.run.tokens[self.indices.start : self.indices.stop]


def offers(
    main: Loaded, source: Loaded, diffs: Sequence[seeds.Diff], least: int
) -> list[Offer]:
    """`diffs` with the main run on the left."""
    found = []
    for low, high, j1, j2 in diffs:
        more = (j2 - j1) - (high - low)
        if more < least:
            continue
        starts = source.run.starts[j2 - more : j2]
        found.append(
            Offer(
                main,
                source,
                low,
                high,
                range(j2 - more, j2),
                min(starts),
                max(starts) + MAX_WORD_MS,
            )
        )
    return found


def _recurs(offer: Offer, other: Loaded) -> bool:
    """Whether `other` has the block's words, in order, near the same time."""
    low, high = offer.start_ms - AGREE_MARGIN_MS, offer.end_ms + AGREE_MARGIN_MS
    timed = zip(other.run.tokens, other.run.starts, strict=True)
    near = [token for token, start in timed if low <= start < high]
    matcher = SequenceMatcher(a=offer.tokens, b=near, autojunk=False)
    same = sum(block.size for block in matcher.get_matching_blocks())
    return same >= AGREE_SHARE * len(offer.tokens)


def values(offer: Offer, others: Sequence[Loaded], end_ms: int) -> Values:
    """The signals of one offer; `others` are the runs besides main and source."""
    main, source = offer.main.run, offer.source
    passages = {source.run.passages[n] for n in offer.indices}

    def extreme(pick: Callable[[list[float]], float], key: str) -> float | None:
        found = [source.signals[p][key] for p in passages if key in source.signals[p]]
        return pick(found) if found else None

    confident = [
        c for n in offer.indices if (c := source.run.confidences[n]) is not None
    ]
    # the main run's word before the place, if there is one
    before = offer.low - 1 if offer.low else None
    before_end = main.ends[before] if before is not None else 0
    before_start = main.starts[before] if before is not None else offer.start_ms
    after = main.starts[offer.high] if offer.high < len(main.tokens) else end_ms
    fallback = sparse = None
    if source.windows:
        hit = [source.window(source.run.starts[n]).fallback for n in offer.indices]
        fallback = sum(hit) / len(hit)
    if offer.main.windows:
        sparse = float(offer.main.window(before_start).sparse)
    return {
        "compression": extreme(max, "compression_ratio"),
        "logprob": extreme(min, "avg_logprob"),
        "no_speech": extreme(max, "no_speech_prob"),
        "fallback": fallback,
        "confidence": statistics.fmean(confident) if confident else None,
        "repetition": denoise._repetition(offer.tokens),
        "gap": float(max(after - before_end, 0)),
        "stretched": None if before is None else float(before_end - before_start),
        "sparse": sparse,
        "silent": float(offer.main.quiet.within(offer.start_ms, offer.end_ms).total),
        "agree": float(sum(_recurs(offer, o) for o in others)) if others else None,
    }


@dataclass(frozen=True, eq=False)
class Rated:
    offer: Offer
    values: Values


def rated(
    main: Loaded,
    sources: Sequence[Loaded],
    diffs: Callable[[Loaded, Loaded], Sequence[seeds.Diff]],
    end_ms: int,
    least: int,
) -> list[Rated]:
    others = besides(main, sources)
    return [
        Rated(offer, values(offer, besides(source, others), end_ms))
        for source in others
        for offer in offers(main, source, diffs(main, source), least)
    ]


# --- signals ------------------------------------------------------------------------


def _test(key: str, check: Callable[[float], bool]) -> Test:
    return lambda found: None if found[key] is None else check(found[key])


def _at_least(key: str, least: float) -> Test:
    return _test(key, lambda value: value >= least)


def _median_test(key: str, name: str, middle: float, higher: bool) -> tuple[str, Test]:
    if higher:
        return f"Quelle: {name} mindestens Median", _at_least(key, middle)
    return f"Quelle: {name} höchstens Median", _test(key, lambda value: value <= middle)


def _number(value: float) -> str:
    return f"{value:g}".replace(".", ",").replace("-", "−")


def signal_tests(
    limits: UncertaintyThresholds, everything: Sequence[Rated], most_others: int
) -> list[tuple[str, Test]]:
    """What accepts an offer, per signal. The limits are the pipeline's own; a
    second row per decoder value takes the median over all offers of the call."""

    def median(key: str) -> float:
        found = [v for r in everything if (v := r.values[key]) is not None]
        return statistics.median(found) if found else 0.0

    tests: list[tuple[str, Test]] = [("alle Blöcke", lambda found: True)]
    # key, name, the pipeline's limit as words and as a check, higher is better
    decoder = (
        (
            "compression",
            "Kompression",
            f"unter {_number(limits.compression_ratio)}",
            _test("compression", lambda v: v < limits.compression_ratio),
            False,
        ),
        (
            "logprob",
            "avg_logprob",
            f"über {_number(limits.avg_logprob)}",
            _test("logprob", lambda v: v > limits.avg_logprob),
            True,
        ),
        (
            "no_speech",
            "no_speech_prob",
            f"unter {_number(limits.no_speech_prob)}",
            _test("no_speech", lambda v: v < limits.no_speech_prob),
            False,
        ),
        (
            "confidence",
            "Wort-Confidence",
            f"ab {_number(limits.word_low)}",
            _at_least("confidence", limits.word_low),
            True,
        ),
    )
    for key, name, limit, test, higher in decoder:
        tests.append((f"Quelle: {name} {limit}", test))
        tests.append(_median_test(key, name, median(key), higher))
    tests += [
        ("Quelle: kein Fallback", _test("fallback", lambda v: v == 0)),
        ("Quelle: keine Wiederholung", _test("repetition", lambda v: v == 0)),
        (
            f"Hauptlauf: Lücke ab {_number(limits.gap_ms / 1000)} s",
            _at_least("gap", limits.gap_ms),
        ),
        (
            f"Hauptlauf: Wort vor der Lücke ab {_number(STRETCHED_MS / 1000)} s",
            _at_least("stretched", STRETCHED_MS),
        ),
        ("Hauptlauf: dünnes Fenster", _test("sparse", lambda v: v == 1)),
        (
            f"Sprache ohne Wörter ab {_number(LONG_SILENT_MS / 1000)} s",
            _at_least("silent", LONG_SILENT_MS),
        ),
    ]
    for count, name in ((1, "einem weiteren Lauf"), (2, "zwei weiteren Läufen")):
        if most_others >= count:
            tests.append((f"in {name}", _at_least("agree", count)))
    return tests


def taken(found: Sequence[Rated], test: Test) -> list[Rated] | None:
    """The offers of one main run a signal accepts, the largest per place; None
    if the signal does not exist for this pairing."""
    kept: list[Rated] = []
    for one in sorted(found, key=lambda r: (-len(r.offer.indices), r.offer.start_ms)):
        accepted = test(one.values)
        if accepted is None:
            return None
        if accepted and not seeds._touches(
            (one.offer.start_ms, one.offer.end_ms), _spots(kept)
        ):
            kept.append(one)
    return kept


# per signal: its label and, per main run, the offers it accepts
Picks = Sequence[tuple[str, Mapping[Loaded, Sequence[Rated] | None]]]


# --- segment ------------------------------------------------------------------------


def _spots(found: Sequence[Rated]) -> Ranges:
    return Ranges.union((r.offer.start_ms, r.offer.end_ms) for r in found)


def print_segment(
    mains: Sequence[Loaded],
    found: Mapping[Loaded, Sequence[Rated]],
    picks: Picks,
    least: int,
) -> None:
    print("## Segment")
    print()
    print(f"Angebote ab {least} Wörtern, je Hauptlauf und Quelle.")
    print()
    print("| Hauptlauf | Quelle | Angebote | Wörter | größtes | Zeit (min) |")
    print("| --- | --- | --- | --- | --- | --- |")
    for main in mains:
        by_source: dict[str, list[Rated]] = {}
        for one in found[main]:
            by_source.setdefault(one.offer.source.label, []).append(one)
        for label, own in by_source.items():
            sizes = [len(r.offer.indices) for r in own]
            print(
                f"| {main.label} | {label} | {len(own)} | {sum(sizes)} | "
                f"{max(sizes)} | {seeds._minutes(_spots(own).total)} |"
            )
    print()
    print(
        "Angenommene Blöcke je Signal, der größte je Stelle: Blöcke / Wörter / "
        "Zeit (min)."
    )
    print()
    print("| Signal | " + " | ".join(main.label for main in mains) + " |")
    print("| --- |" + " --- |" * len(mains))
    for label, kept in picks:
        cells = [
            N_A
            if kept[main] is None
            else f"{len(kept[main])} / "
            f"{sum(len(r.offer.indices) for r in kept[main])} / "
            f"{seeds._minutes(_spots(kept[main]).total)}"
            for main in mains
        ]
        print(f"| {label} | " + " | ".join(cells) + " |")
    print()


def agreed_raster(found: Mapping[Loaded, Sequence[Rated]], end_ms: int) -> list[int]:
    """Per raster window the words in blocks a further run has too, for the main
    run with the most."""
    rasters = []
    for own in found.values():
        raster = [0] * -(-end_ms // seeds.RASTER_MS)
        for one in own:
            if one.values["agree"]:
                window = min(one.offer.start_ms // seeds.RASTER_MS, len(raster) - 1)
                raster[window] += len(one.offer.indices)
        rasters.append(raster)
    return [max(counts) for counts in zip(*rasters, strict=True)]


# --- clip ---------------------------------------------------------------------------


def filled(main: seeds.ClipRun, kept: Sequence[Rated], clip: HandClip) -> list[str]:
    """The main run's tokens at the clip with the accepted blocks put in."""
    inserts: dict[int, list[str]] = {}
    for one in sorted(kept, key=lambda r: r.offer.start_ms):
        run = one.offer.source.run
        tokens = [
            run.tokens[n]
            for n in one.offer.indices
            if clip.start_ms <= run.starts[n] < clip.end_ms
        ]
        if tokens:
            position = bisect.bisect_left(main.indices, one.offer.high)
            inserts.setdefault(position, []).extend(tokens)
    out: list[str] = []
    for position, token in enumerate(main.tokens):
        out += inserts.get(position, [])
        out.append(token)
    return out + inserts.get(len(main.tokens), [])


def fates(
    main: seeds.ClipRun, kept: Sequence[Rated], at_clip: Mapping[Loaded, seeds.ClipRun]
) -> tuple[int, Counter[str]]:
    """How many accepted blocks reach into the clip, and what their words there
    are against the hand reference (as R2 in `seeds.py` counts them)."""
    blocks = 0
    fate: Counter[str] = Counter()
    for one in kept:
        other = at_clip[one.offer.source]
        local = {index: n for n, index in enumerate(other.indices)}
        inside = [local[i] for i in one.offer.indices if i in local]
        blocks += bool(inside)
        for n in inside:
            if other.found.absorbed[n]:
                fate["absorbed"] += 1
            elif n not in other.hits:
                fate["wrong"] += 1
            elif main.status[other.hits[n]] == seeds.DELETED:
                fate["fills"] += 1
            else:
                fate["right"] += 1
    return blocks, fate


def print_clip(
    clip: HandClip,
    hand: calibration.HandReference,
    mains: Sequence[Loaded],
    picks: Picks,
    at_clip: Mapping[Loaded, seeds.ClipRun],
) -> None:
    words = len(hand.tokens)
    print(f"## Referenz {clip.name}")
    print()
    print(f"{words} Referenzwörter")
    print()
    rows: list[str] = []
    summary: list[str] = []
    for label, picked in picks:
        total: Counter[str] = Counter()
        gains: list[float] = []
        for main in mains:
            kept = picked[main]
            if kept is None:
                continue
            base = at_clip[main]
            blocks, fate = fates(base, kept, at_clip)
            before = seeds._errors(base.counts)
            after = seeds._errors(
                calibration.align(hand, filled(base, kept, clip)).counts
            )
            gains.append((before - after) / words)
            total.update(fate)
            total["blocks"] += blocks
            rows.append(
                f"| {label} | {main.label} | {blocks} | {sum(fate.values())} | "
                f"{fate['fills']} | {fate['right']} | {fate['wrong']} | "
                f"{fate['absorbed']} | {_pct(before / words)} | "
                f"{_pct(after / words)} | {seeds._points(gains[-1])} |"
            )
        if not gains:
            summary.append(f"| {label} |" + f" {N_A} |" * 5)
            continue
        summary.append(
            f"| {label} | {total['blocks']} | {total['fills'] + total['right']} | "
            f"{total['wrong']} | {seeds._points(seeds._mean(gains))} | "
            f"{seeds._points(min(gains))} |"
        )
    print(
        "| Signal | Blöcke am Clip | richtige Wörter | falsche Wörter | Gewinn im "
        "Mittel der Hauptläufe (Punkte) | kleinster Gewinn (Punkte) |"
    )
    print("| --- | --- | --- | --- | --- | --- |")
    print("\n".join(summary))
    print()
    print(
        "| Signal | Hauptlauf | Blöcke am Clip | Wörter | füllen eine Auslassung | "
        "sonst richtig | falsch | an unverständlicher Stelle | WER Hauptlauf | "
        "WER mit Blöcken | Gewinn (Punkte) |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    print("\n".join(rows))
    print()


# --- main ---------------------------------------------------------------------------


def measure(
    paths: SessionPaths,
    main_name: str,
    source_name: str,
    count: int,
    least: int,
    clips: Sequence[HandClip],
    suggest: bool,
) -> None:
    _, speech, _ = omissions.heard_speech(omissions.diarized(paths))
    mains, sections = load(paths, main_name, count, speech)
    sources = mains
    if source_name != main_name:
        sources, more = load(paths, source_name, count, speech)
        sections += more
    asr.check_provenance(sections)
    most_others = max(len(besides(main, sources)) for main in mains) - 1
    if most_others < 0:
        raise SpikeError("a main run needs another run as the source")
    end_ms = asr._end_ms(paths)
    if sources is mains:
        # one alignment per pair of seeds, the lower seed first, as in `seeds.py`
        pairs = {
            (a.run.seed, b.run.seed): seeds.aligned(a.run, b.run, end_ms)
            for a, b in itertools.combinations(mains, 2)
        }

        def diffs(main: Loaded, source: Loaded) -> Sequence[seeds.Diff]:
            return seeds.towards(main.run, source.run, pairs)
    else:

        def diffs(main: Loaded, source: Loaded) -> Sequence[seeds.Diff]:
            return seeds.aligned(main.run, source.run, end_ms)

    found = {main: rated(main, sources, diffs, end_ms, least) for main in mains}
    if suggest:
        seeds.print_suggestions(
            agreed_raster(found, end_ms),
            clips,
            "Wörter in Blöcken, die ein weiterer Lauf auch hat",
        )
        return
    root = asr.shadow_root(paths, main_name, mains[0].run.seed)
    limits = load_config(root / "config.yaml").review_uncertainty
    everything = [one for own in found.values() for one in own]
    picks = [
        (label, {main: taken(found[main], test) for main in mains})
        for label, test in signal_tests(limits, everything, most_others)
    ]
    print_segment(mains, found, picks, least)
    for clip in clips:
        hand = calibration.read_hand_reference(
            paths.review_dir / "calibration" / clip.file
        )
        at_clip = {
            one: seeds.clip_run(one.run, one.reference, hand, clip)
            for one in {*mains, *sources}
        }
        print_clip(clip, hand, mains, picks, at_clip)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("session", help="session key <group>/<ordinal>")
    parser.add_argument("--main", default="base", type=asr._variant_arg)
    parser.add_argument(
        "--source",
        type=asr._variant_arg,
        help="the variant that offers blocks (default: the other seeds of --main)",
    )
    parser.add_argument("--seeds", type=int, default=3, help="seeds 1..N")
    parser.add_argument(
        "--least", type=int, default=BLOCK_TOKENS, help="words in a block"
    )
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
        help="only propose 3-minute windows for a hand reference where a further "
        "run has the offered block too, outside the clips",
    )
    args = parser.parse_args(argv)
    try:
        paths = load_config(args.config).session_paths(SessionKey.parse(args.session))
        measure(
            paths,
            args.main,
            args.source or args.main,
            args.seeds,
            args.least,
            args.clip or denoise.CLIPS,
            args.suggest,
        )
    except (SpikeError, ValueError, OSError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
