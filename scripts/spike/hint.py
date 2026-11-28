"""Hint spike (TOOL-107): what "speech without words" shows beyond `gap` and `sparse`.

    hint.py <group>/<ordinal> [--variant norm] [--seeds 3] [--clip ...]
    hint.py <group>/<ordinal> --sample N [--clip ...]
    hint.py <group>/<ordinal> --sampled

Reads the stored runs of `asr.py`, the session's diarization of segment 1 and
the hand references under `review/calibration/`. Every run gets its passages cut
at the speaker changes in memory, as `transcript diarize` would, and is rated
with the thresholds of `--config` and without knowledge hints, so all seeds are
comparable. A spot is where the diarization hears speech and the run has no
word. Over the segment it counts per setting what the rating already shows at
the spots and which `confident` passages the hint would flag; per clip it
counts the omissions at a pause `gap` names, in a passage `sparse` names and in
a spot.

`--sample` draws spots of seed 1 outside the clips and writes their time
windows to `review/calibration/hint-sample.txt` of the session, unless the file
exists. `--sampled` counts what was typed there. Nothing else is written.

Privacy (TOOL-66): the console gets counts, shares and times only, no text, no
token, no names and no speaker labels.
"""

import argparse
import bisect
import itertools
import math
import random
import re
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import asr
import denoise
import omissions
import seeds
import spots
from denoise import SEGMENT, HandClip, SpikeError, _pct
from omissions import BRIDGE_WORDS_MS, LONG_SILENT_MS, MAX_WORD_MS, Ranges

from transcript import calibration, diarization, uncertainty
from transcript.config import DEFAULT_CONFIG, Config, load_config
from transcript.hints import stored_hints
from transcript.jsonfile import DataFileError
from transcript.reference import ReferenceTranscript
from transcript.session import SessionKey, SessionPaths
from transcript.timecode import format_clock

# fixed in the plan, before any count was seen
LEAST_MS = (1_000, 2_000, 3_000)  # a spot is at least this long
BRIDGES_MS = (500, 1_000, 2_000)  # a pause between words up to this is no spot
SAMPLE_MARGIN_MS = 3_000  # audio around a sampled spot
SAMPLE_SEED = 107
SAMPLE_FILE = "hint-sample.txt"
MISSING_WORDS = 2  # typed words the run lacks before a spot counts as lost speech
NO_SPEECH = "keine sprache"

GAP, SPARSE, FLAGGED, CONFIDENT, BETWEEN = (
    "in einer `gap`-Pause",
    "in einer `sparse`-Passage",
    "in einer sonst markierten Passage",
    "nur in `confident`-Passagen",
    "zwischen zwei Passagen",
)
PLACES = (GAP, SPARSE, FLAGGED, CONFIDENT, BETWEEN)


@dataclass(frozen=True)
class Setting:
    least_ms: int
    bridge_ms: int
    cap_ms: float = math.inf  # a word counts as at most this long

    @property
    def name(self) -> str:
        cap = "" if self.cap_ms == math.inf else ", Wortlänge gekappt"
        return (
            f"ab {asr._decimal(self.least_ms / 1000)} s, Brücke "
            f"{asr._decimal(self.bridge_ms / 1000)} s{cap}"
        )


RULE = Setting(LONG_SILENT_MS, BRIDGE_WORDS_MS)  # what the go rule is measured at
SETTINGS = (
    *(Setting(least, bridge) for least in LEAST_MS for bridge in BRIDGES_MS),
    Setting(RULE.least_ms, RULE.bridge_ms, cap_ms=MAX_WORD_MS),
)


# --- one run ------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Rated:
    """One run with its passages cut and rated in memory."""

    label: str
    run: seeds.Run
    reference: ReferenceTranscript
    starts: tuple[int, ...]  # per passage with a span, sorted
    ends: tuple[int, ...]
    reach: tuple[int, ...]  # the latest end up to each passage
    confident: tuple[bool, ...]
    gaps: Ranges  # the pauses `gap` names
    sparse: Ranges  # the passages `sparse` names
    total_ms: int  # the time of all passages
    flagged: float  # the share of it in passages not rated `confident`

    def passages(self, spot: tuple[int, int]) -> tuple[list[int], bool]:
        """The passages a spot touches, else the one before and the one after.

        Positions in `starts`; the flag says whether the spot touches any.
        """
        start, end = spot
        last = bisect.bisect_left(self.starts, end)
        first = bisect.bisect_right(self.reach, start)
        touched = [n for n in range(first, last) if self.ends[n] > start]
        if touched:
            return touched, True
        return [n for n in (last - 1, last) if 0 <= n < len(self.starts)], False


def _spans(
    reference: ReferenceTranscript, ratings: Sequence[uncertainty.PassageRating]
) -> list[tuple[int, int, bool]]:
    """Start, end and "is confident" of every passage with times, sorted."""
    found = []
    for passage, rating in zip(reference.passages, ratings, strict=True):
        start, end = uncertainty._span(passage)
        if start is not None and end is not None:
            found.append((start, max(start, end), rating.level == "confident"))
    return sorted(found)


def _flagged(spans: Sequence[tuple[int, int, bool]]) -> tuple[int, float]:
    """The time of all passages and the share of it not rated `confident`."""
    total = sum(end - start for start, end, _ in spans)
    flagged = sum(end - start for start, end, sure in spans if not sure)
    return total, flagged / (total or 1)


def rated(
    label: str,
    seed: int,
    stored: ReferenceTranscript,
    turns: diarization.DiarizationRun,
    config: Config,
) -> Rated:
    reference = diarization.assign_speakers(
        stored, turns, config.diarization_min_turn_ms
    )
    limits = config.review_uncertainty
    ratings = uncertainty.assess(reference, None, limits)
    gaps: list[tuple[int, int]] = []
    sparse: list[tuple[int, int]] = []
    for passage, rating in zip(reference.passages, ratings, strict=True):
        for reason in rating.reasons:
            if reason.rule == "sparse":
                sparse.append(uncertainty._span(passage))
            elif reason.rule == "gap":
                # the reason names the word after the pause and the pause's length
                later = passage.words[reason.words[0]].start_ms
                gaps.append((later - int(reason.value), later))
    spans = _spans(reference, ratings)
    ends = tuple(end for _, end, _ in spans)
    total_ms, flagged = _flagged(spans)
    return Rated(
        label=label,
        run=seeds.timed(seed, reference, ratings, limits.compression_ratio),
        reference=reference,
        starts=tuple(start for start, _, _ in spans),
        ends=ends,
        reach=tuple(itertools.accumulate(ends, max)),
        confident=tuple(sure for _, _, sure in spans),
        gaps=Ranges.union(gaps),
        sparse=Ranges.union(sparse),
        total_ms=total_ms,
        flagged=flagged,
    )


def found_spots(one: Rated, speech: Ranges, setting: Setting) -> Ranges:
    return omissions.silence(
        one.reference, speech, setting.bridge_ms, setting.cap_ms, setting.least_ms
    )


def place(one: Rated, spot: tuple[int, int]) -> tuple[str, list[int]]:
    """What the rating shows at a spot, and the `confident` passages it would flag."""
    passages, touched = one.passages(spot)
    fresh = [n for n in passages if one.confident[n]]
    if seeds._touches(spot, one.gaps):
        return GAP, fresh
    if seeds._touches(spot, one.sparse):
        return SPARSE, fresh
    if not touched:
        return BETWEEN, fresh
    if len(fresh) < len(passages):
        return FLAGGED, fresh
    return CONFIDENT, fresh


@dataclass(frozen=True)
class Cost:
    """What the hint adds over the segment for one run and one setting."""

    spots: int
    spot_ms: int
    places: Mapping[str, int]  # spots per place
    fresh: Ranges  # the `confident` passages the hint would flag
    passages: int  # how many those are
    flagged: float  # share of the passage time flagged today
    added: float  # ... and what the hint adds to it, as a share of that time


def cost(one: Rated, found: Ranges) -> Cost:
    places: Counter[str] = Counter()
    fresh: set[int] = set()
    for spot in found.spans():
        where, new = place(one, spot)
        places[where] += 1
        fresh.update(new)
    spans = [(one.starts[n], one.ends[n]) for n in sorted(fresh)]
    return Cost(
        spots=len(found.starts),
        spot_ms=found.total,
        places=places,
        fresh=Ranges.union(spans),
        passages=len(fresh),
        flagged=one.flagged,
        added=sum(end - start for start, end in spans) / (one.total_ms or 1),
    )


# --- tables -------------------------------------------------------------------------


def _mean(values: Iterable[float]) -> str:
    return asr._decimal(statistics.fmean(values))


def _cost_cells(costs: Sequence[Cost]) -> str:
    cells = [
        _mean(c.spots for c in costs),
        _mean(c.spot_ms / 60_000 for c in costs),
        *(_mean(c.places[name] for c in costs) for name in PLACES),
        _mean(c.passages for c in costs),
        _mean(c.fresh.total / 60_000 for c in costs),
        _pct(statistics.fmean(c.flagged for c in costs)),
        seeds._points(statistics.fmean(c.added for c in costs)),
    ]
    return " | ".join(cells)


def print_segment(
    runs: Sequence[Rated],
    costs: Mapping[Setting, Mapping[Rated, Cost]],
    stored_share: float | None,
) -> None:
    head = (
        "Stellen | Zeit in den Stellen (min) | "
        + " | ".join(PLACES)
        + " | neu markierte Passagen | deren Zeit (min) | markierte Zeit heute | "
        "Zuwachs (Punkte)"
    )
    print("## Segment")
    print()
    print(
        f"Passagen je Lauf: {' / '.join(str(len(r.starts)) for r in runs)}, im "
        "Speicher am Sprecherwechsel geteilt und ohne Wissens-Hinweise bewertet."
    )
    if stored_share is not None:
        print()
        print(
            f"Kontrolle: Die gespeicherte Fassung von {runs[0].label} markiert mit "
            f"ihren Wissens-Hinweisen und denselben Schwellen {_pct(stored_share)} "
            "der Zeit."
        )
    print()
    print(f"Mittel über {len(runs)} Läufe:")
    print()
    rule = "| --- |" + " --- |" * (head.count("|") + 1)
    print(f"| Stellen | {head} |")
    print(rule)
    for setting in SETTINGS:
        print(f"| {setting.name} | {_cost_cells(list(costs[setting].values()))} |")
    print()
    print(f"Je Lauf, Stellen {RULE.name}:")
    print()
    print(f"| Lauf | {head} |")
    print(rule)
    for one in runs:
        print(f"| {one.label} | {_cost_cells([costs[RULE][one]])} |")
    print()


@dataclass(frozen=True)
class Shown:
    """The omissions of one run at one clip, by what shows their place."""

    omitted: int
    gap: int
    sparse: int
    rating: int  # at a `gap` pause or in a `sparse` passage
    hint: int  # in a spot
    both: int  # any of the three
    fresh: int  # in a `confident` passage the hint would flag
    longest: int  # omitted reference words in a row
    longest_hint: int  # of that row in a spot
    words: int  # reference words in a spot, omitted or not

    @property
    def more(self) -> int:
        return self.both - self.rating


def shown(
    one: Rated,
    omitted: Sequence[bool],
    times: Sequence[float],
    found: Ranges,
    fresh: Ranges,
) -> Shown:
    in_gap = [ms in one.gaps for ms in times]
    in_sparse = [ms in one.sparse for ms in times]
    in_hint = [ms in found for ms in times]
    longest = spots._longest(omitted)

    def count(*flags: Sequence[bool]) -> int:
        return sum(
            gone and any(flag[n] for flag in flags) for n, gone in enumerate(omitted)
        )

    return Shown(
        omitted=sum(omitted),
        gap=count(in_gap),
        sparse=count(in_sparse),
        rating=count(in_gap, in_sparse),
        hint=count(in_hint),
        both=count(in_gap, in_sparse, in_hint),
        fresh=count([ms in fresh for ms in times]),
        longest=len(longest),
        longest_hint=sum(in_hint[n] for n in longest),
        words=sum(in_hint),
    )


def print_clip(
    clip: HandClip,
    words: int,
    runs: Sequence[Rated],
    found: Mapping[Setting, Mapping[Rated, Shown]],
) -> None:
    print(f"## Referenz {clip.name}")
    print()
    print(f"{words} Referenzwörter, Stellen {RULE.name}")
    print()
    print(
        "| Lauf | Auslassungen | an einer `gap`-Pause | in einer `sparse`-Passage | "
        "`gap` oder `sparse` | in einer Stelle | alles zusammen | Zuwachs | in neu "
        "markierter Passage | längste Folge ausgelassener Wörter | davon in einer "
        "Stelle | Referenzwörter in Stellen |"
    )
    print("| --- |" + " --- |" * 11)
    for one in runs:
        s = found[RULE][one]
        print(
            f"| {one.label} | {s.omitted} | {s.gap} | {s.sparse} | {s.rating} | "
            f"{s.hint} | {s.both} | {s.more} | {s.fresh} | {s.longest} | "
            f"{s.longest_hint} | {s.words} |"
        )
    print()


def _total(found: Iterable[Iterable[Shown]], pick: Callable[[Shown], int]) -> float:
    """The sum over the clips of the mean over the runs."""
    return sum(statistics.fmean(pick(s) for s in at_clip) for at_clip in found)


def print_rule(
    clips: Sequence[HandClip],
    found: Mapping[str, Mapping[Setting, Mapping[Rated, Shown]]],  # per clip
) -> None:
    """Per setting the sum over the clips of the mean over the runs."""
    print("## Auslassungen an einer gezeigten Stelle")
    print()
    print(
        f"Summe über die Referenzen {', '.join(clip.name for clip in clips)}, je "
        "Referenz das Mittel der Läufe."
    )
    print()
    print(
        "| Stellen | Auslassungen | `gap` oder `sparse` | in einer Stelle | alles "
        "zusammen | Zuwachs | Zuwachs in Prozent | in neu markierter Passage | "
        "Referenzwörter in Stellen |"
    )
    print("| --- |" + " --- |" * 8)
    for setting in SETTINGS:
        own = [list(found[clip.name][setting].values()) for clip in clips]
        rating = _total(own, lambda s: s.rating)
        more = _total(own, lambda s: s.more)
        print(
            f"| {setting.name} | {asr._decimal(_total(own, lambda s: s.omitted))} | "
            f"{asr._decimal(rating)} | {asr._decimal(_total(own, lambda s: s.hint))} | "
            f"{asr._decimal(_total(own, lambda s: s.both))} | {asr._decimal(more)} | "
            f"{_pct(more / rating) if rating else '–'} | "
            f"{asr._decimal(_total(own, lambda s: s.fresh))} | "
            f"{asr._decimal(_total(own, lambda s: s.words))} |"
        )
    print()


# --- sample -------------------------------------------------------------------------

_ENTRY = re.compile(r"^\[\d+\] \S+ window=(\d+)-(\d+) spot=(\d+)-(\d+)$")


@dataclass(frozen=True)
class Entry:
    window: tuple[int, int]
    spot: tuple[int, int]
    text: str


def draw(found: Ranges, clips: Sequence[HandClip], count: int) -> list[tuple[int, int]]:
    """`count` spots that touch no clip, at random with a fixed seed, by time."""
    free = [
        spot
        for spot in found.spans()
        if not any(spot[0] < clip.end_ms and clip.start_ms < spot[1] for clip in clips)
    ]
    if len(free) < count:
        raise SpikeError(f"only {len(free)} spots outside the clips")
    return sorted(random.Random(SAMPLE_SEED).sample(free, count))


def write_sample(path: Path, label: str, drawn: Sequence[tuple[int, int]]) -> None:
    if path.exists():
        raise SpikeError(f"{path.name} exists and is never replaced")
    lines = [
        f"# Stichprobe TOOL-107, Stellen aus {label}.",
        "# Unter jede Zeile mit [Nummer] tippen, was im Zeitfenster gesagt wird,",
        '# oder "keine Sprache". Die Kopfzeilen bitte nicht ändern.',
        "",
    ]
    print("| Nr. | von | bis |")
    print("| --- | --- | --- |")
    for number, (start, end) in enumerate(drawn, start=1):
        first = max(0, start - SAMPLE_MARGIN_MS) // 1000 * 1000
        last = -(-(end + SAMPLE_MARGIN_MS) // 1000) * 1000
        clock = f"{format_clock(first)}-{format_clock(last)}"
        lines += [
            f"[{number}] {clock} window={first}-{last} spot={start}-{end}",
            "",
            "",
        ]
        print(f"| {number} | {format_clock(first)} | {format_clock(last)} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def read_sample(path: Path) -> list[Entry]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        raise SpikeError(f"{path.name}: sample is unreadable, run --sample") from None
    found: list[tuple[list[int], list[str]]] = []  # head numbers, typed lines
    for line in lines:
        head = _ENTRY.match(line.strip())
        if head:
            found.append(([int(part) for part in head.groups()], []))
        elif found and not line.lstrip().startswith("#"):
            found[-1][1].append(line)
    if not found:
        raise SpikeError(f"{path.name}: no entry, the head lines were changed")
    return [
        Entry((first, last), (start, end), " ".join(typed))
        for (first, last, start, end), typed in found
    ]


LOST, SILENT, HEARD, OPEN = (
    "Sprache fehlt",
    "keine Sprache",
    "Sprache vom Lauf erkannt",
    "unbeantwortet",
)


def print_sampled(one: Rated, entries: Sequence[Entry]) -> None:
    rows: dict[str, Counter[str]] = {name: Counter() for name in (*PLACES, "gesamt")}
    for entry in entries:
        where, _ = place(one, entry.spot)
        typed = calibration.tokens(entry.text)
        if not typed:
            kind, lacking = OPEN, 0
        elif " ".join(typed) == NO_SPEECH:
            kind, lacking, typed = SILENT, 0, []
        else:
            heard = [
                token
                for token, start in zip(one.run.tokens, one.run.starts, strict=True)
                if entry.window[0] <= start < entry.window[1]
            ]
            hand = calibration.HandReference(
                tuple(typed), ("S?",) * len(typed), frozenset()
            )
            lacking = len(calibration.align(hand, heard).deletions)
            kind = LOST if lacking >= MISSING_WORDS else HEARD
        for name in (where, "gesamt"):
            rows[name].update(
                {kind: 1, "spots": 1, "typed": len(typed), "lacking": lacking}
            )
    print(f"## Hörstichprobe, Stellen aus {one.label}")
    print()
    print(
        f"| Stelle liegt | Stellen | {LOST} | {SILENT} | {HEARD} | {OPEN} | "
        "getippte Wörter | davon im Lauf ausgelassen |"
    )
    print("| --- |" + " --- |" * 7)
    for name, row in rows.items():
        if row["spots"]:
            print(
                f"| {name} | {row['spots']} | {row[LOST]} | {row[SILENT]} | "
                f"{row[HEARD]} | {row[OPEN]} | {row['typed']} | {row['lacking']} |"
            )
    print()
    answered = rows["gesamt"]["spots"] - rows["gesamt"][OPEN]
    print(
        f"Beantwortet: {answered}, davon {LOST}: {rows['gesamt'][LOST]} "
        f"({_pct(rows['gesamt'][LOST] / answered) if answered else '–'})."
    )
    print()


# --- main ---------------------------------------------------------------------------


def load(
    paths: SessionPaths, name: str, count: int, config: Config
) -> tuple[list[Rated], Ranges]:
    turns = omissions.diarized(paths)
    _, speech, _ = omissions.heard_speech(turns)
    stored = seeds._stored(paths, name, 1 if asr.variant(name).batched else count)
    asr.check_provenance(seeds._sections(paths, name, stored))
    runs = [
        rated(f"{name}#{seed}", seed, reference, turns, config)
        for seed, reference in stored.items()
    ]
    return runs, speech


def _stored_share(paths: SessionPaths, name: str, config: Config) -> float | None:
    """The flagged time of seed 1 as stored, with its hints; None: not diarized."""
    stored = asr.transcribed(paths, name, 1)
    if stored.diarization is None:
        return None
    shadow = SessionPaths(paths.key, asr.shadow_root(paths, name, 1))
    ratings = uncertainty.segment_assessment(
        stored, stored_hints(shadow, SEGMENT), config.review_uncertainty
    ).ratings
    return _flagged(_spans(stored, ratings))[1]


def measure(
    paths: SessionPaths,
    name: str,
    count: int,
    clips: Sequence[HandClip],
    config: Config,
) -> None:
    runs, speech = load(paths, name, count, config)
    found = {
        setting: {one: found_spots(one, speech, setting) for one in runs}
        for setting in SETTINGS
    }
    costs = {
        setting: {one: cost(one, own[one]) for one in runs}
        for setting, own in found.items()
    }
    print_segment(runs, costs, _stored_share(paths, name, config))
    per_clip: dict[str, dict[Setting, dict[Rated, Shown]]] = {}
    for clip in clips:
        hand = calibration.read_hand_reference(
            paths.review_dir / "calibration" / clip.file
        )
        heard = {one: omissions.heard(one.reference, hand, clip) for one in runs}
        times = omissions.timeline(list(heard.values()), clip).times
        per_clip[clip.name] = {
            setting: {
                one: shown(
                    one,
                    [ms is None for ms in heard[one]],
                    times,
                    own[one],
                    costs[setting][one].fresh,
                )
                for one in runs
            }
            for setting, own in found.items()
        }
        print_clip(clip, len(hand.tokens), runs, per_clip[clip.name])
    if clips:
        print_rule(clips, per_clip)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("session", help="session key <group>/<ordinal>")
    parser.add_argument("--variant", default="norm", type=asr._variant_arg)
    parser.add_argument("--seeds", type=int, default=3, help="seeds 1..N")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--clip",
        action="append",
        type=asr.parse_clip,
        help="NAME=FILE@H:MM:SS-H:MM:SS (default: pilot clips A and B)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="draw N spots of seed 1 outside the clips and write their time "
        "windows for typing; never replaces the file",
    )
    parser.add_argument(
        "--sampled", action="store_true", help="count what was typed for the sample"
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        paths = config.session_paths(SessionKey.parse(args.session))
        clips = args.clip or denoise.CLIPS
        sample = paths.review_dir / "calibration" / SAMPLE_FILE
        if args.sample is not None or args.sampled:
            runs, speech = load(paths, args.variant, 1, config)
            if args.sampled:
                print_sampled(runs[0], read_sample(sample))
            else:
                drawn = draw(found_spots(runs[0], speech, RULE), clips, args.sample)
                write_sample(sample, runs[0].label, drawn)
        else:
            measure(paths, args.variant, args.seeds, clips, config)
    except (SpikeError, ValueError, OSError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
