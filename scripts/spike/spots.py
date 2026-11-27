"""Spot spike (TOOL-113): what decoding only the suspicious spots again could win.

    spots.py <group>/<ordinal> [--variant norm] [--seeds 3] [--with VARIANT]...
             [--clip ...]

Reads the stored runs of `asr.py`, the session's diarization of segment 1 and
the hand references under `review/calibration/`. Every run of `--variant` is the
main run once. Its suspicious spots need no reference: S1 is where the
diarization hears speech for at least two seconds and the run has no word, S2
adds the passages the decoder itself rated badly. A spot padded on both sides
is a piece, the audio a second decoding would get. Per clip it counts the main
run's omissions that lie in a piece (the hard ceiling: all of them come back
right and nothing wrong comes along) and how many of those another stored run
has right (the oracle). It writes nothing.

A batched variant given with `--with` is read with seed 1 only: its seeds are
word for word the same (TOOL-104).

Privacy (TOOL-66): the console gets counts, shares, error rates and times only,
no text, no token, no names and no speaker labels.
"""

import argparse
import itertools
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import asr
import denoise
import omissions
import seeds
from denoise import HandClip, SpikeError, _pct
from omissions import LONG_SILENT_MS, Ranges

from transcript import calibration
from transcript.config import DEFAULT_CONFIG, load_config
from transcript.jsonfile import DataFileError
from transcript.reference import ReferenceTranscript
from transcript.session import SessionKey, SessionPaths

# thresholds fixed in the plan, before any count was seen
PAD_MS = 2_000  # a piece is its spot with this much audio on both sides
# the pipeline's limits when TOOL-108 measured; TOOL-109 moved the config since
COMPRESSION_RATIO = 2.4
AVG_LOGPROB = -1.0
SILENT = "S1"  # speech without words
RATED = "S2"  # ... and the passages the decoder rated badly
KINDS = (SILENT, RATED)
KIND_NAMES = {
    SILENT: f"S1: Sprache ohne Wörter ab {LONG_SILENT_MS // 1000} s",
    RATED: "S2: dazu Passagen mit schlechten Dekodierwerten",
}


# --- spots and pieces ---------------------------------------------------------------


def rated_spots(reference: ReferenceTranscript) -> Ranges:
    """The passages at or beyond a limit of the decoder's own values."""
    return Ranges.union(
        (passage.start_ms, passage.end_ms)
        for passage in reference.passages
        if passage.start_ms is not None
        and passage.end_ms is not None
        and (
            passage.signals.get("compression_ratio", 0.0) >= COMPRESSION_RATIO
            or passage.signals.get("avg_logprob", 0.0) <= AVG_LOGPROB
        )
    )


def spots(reference: ReferenceTranscript, speech: Ranges) -> dict[str, Ranges]:
    silent = omissions.silence(reference, speech).longer(LONG_SILENT_MS)
    return {
        SILENT: silent,
        RATED: Ranges.union(silent.spans() + rated_spots(reference).spans()),
    }


def pieces(found: Ranges, end_ms: int) -> Ranges:
    """The spots padded and cut at the segment's edges; pieces that meet are one."""
    padded = Ranges.union(
        (max(start - PAD_MS, 0), min(end + PAD_MS, end_ms))
        for start, end in found.spans()
    )
    check(padded, end_ms)
    return padded


def check(found: Ranges, end_ms: int) -> None:
    spans = found.spans()
    if any(start < 0 or end > end_ms or end <= start for start, end in spans):
        raise SpikeError("a piece lies outside the segment")
    if any(a[1] >= b[0] for a, b in itertools.pairwise(spans)):
        raise SpikeError("pieces are not sorted and apart")


# --- runs ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Loaded:
    name: str
    run: seeds.Run
    reference: ReferenceTranscript

    @property
    def label(self) -> str:
        return f"{self.name}#{self.run.seed}"


def load(
    paths: SessionPaths, name: str, count: int
) -> tuple[list[Loaded], list[asr.Sections]]:
    stored = seeds._stored(paths, name, 1 if asr.variant(name).batched else count)
    runs = seeds._timed_runs(paths, name, stored)
    return (
        [Loaded(name, run, stored[run.seed]) for run in runs],
        seeds._sections(paths, name, stored),
    )


# --- segment ------------------------------------------------------------------------


def print_segment(
    mains: Sequence[Loaded],
    found: Mapping[Loaded, Mapping[str, Ranges]],
    cut: Mapping[Loaded, Mapping[str, Ranges]],
    end_ms: int,
) -> None:
    print("## Segment")
    print()
    print(
        f"Stück: die Stelle mit {PAD_MS // 1000} s Polster je Seite, sich berührende "
        "Stücke verbunden."
    )
    print()
    print(
        "| Stellen | Hauptlauf | Stellen | Zeit in den Stellen (min) | Stücke | "
        "Median Stück (s) | längstes Stück (s) | Summe der Stücke (min) | "
        "Anteil am Segment |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for kind in KINDS:
        for main in mains:
            lengths = [end - start for start, end in cut[main][kind].spans()]
            print(
                f"| {KIND_NAMES[kind]} | {main.label} | {len(found[main][kind].starts)} | "
                f"{seeds._minutes(found[main][kind].total)} | {len(lengths)} | "
                f"{asr._decimal(statistics.median(lengths) / 1000 if lengths else 0)} | "
                f"{asr._decimal(max(lengths, default=0) / 1000)} | "
                f"{seeds._minutes(sum(lengths))} | "
                f"{_pct(sum(lengths) / end_ms)} |"
            )
    print()


# --- clip ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ceiling:
    """What one main run could win at one clip from one kind of spots."""

    words: int  # of the hand reference
    errors: int
    omitted: int
    in_pieces: int  # omissions with their word time in a piece
    elsewhere: int  # ... that another stored run has right
    longest: int  # omitted reference words in a row
    longest_in_pieces: int  # of that row

    @property
    def hard(self) -> float:
        """The share of the error rate the pieces could win at most."""
        return self.in_pieces / self.words

    @property
    def oracle(self) -> float:
        return self.elsewhere / self.words


def _longest(omitted: Sequence[bool]) -> range:
    best = range(0)
    for missing, group in itertools.groupby(
        range(len(omitted)), key=lambda position: omitted[position]
    ):
        row = list(group)
        if missing and len(row) > len(best):
            best = range(row[0], row[-1] + 1)
    return best


def ceiling(
    main: seeds.ClipRun,
    others: Sequence[seeds.ClipRun],
    times: Sequence[float],
    cut: Ranges,
) -> Ceiling:
    omitted = [status == seeds.DELETED for status in main.status]
    inside = [missing and times[n] in cut for n, missing in enumerate(omitted)]
    fate = seeds._fate(main, others)
    longest = _longest(omitted)
    return Ceiling(
        words=len(omitted),
        errors=seeds._errors(main.counts),
        omitted=sum(omitted),
        in_pieces=sum(inside),
        elsewhere=sum(fate[n] == seeds.HIT for n, hit in enumerate(inside) if hit),
        longest=len(longest),
        longest_in_pieces=sum(inside[n] for n in longest),
    )


def print_clip(
    clip: HandClip,
    words: int,
    mains: Sequence[Loaded],
    found: Mapping[str, Mapping[Loaded, Ceiling]],
) -> None:
    print(f"## Referenz {clip.name}")
    print()
    print(f"{words} Referenzwörter")
    print()
    print(
        "| Stellen | Hauptlauf | WER | Auslassungen | davon in einem Stück | harte "
        "Obergrenze (Punkte) | davon in einem anderen Lauf richtig | Orakel (Punkte) | "
        "längste Folge ausgelassener Wörter | davon in einem Stück |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for kind in KINDS:
        for main in mains:
            one = found[kind][main]
            print(
                f"| {KIND_NAMES[kind]} | {main.label} | {_pct(one.errors / words)} | "
                f"{one.omitted} | {one.in_pieces} | "
                f"{seeds._points(one.hard)} | {one.elsewhere} | "
                f"{seeds._points(one.oracle)} | {one.longest} | "
                f"{one.longest_in_pieces} |"
            )
    print()


def print_gate(
    clips: Sequence[HandClip],
    mains: Sequence[Loaded],
    found: Mapping[str, Mapping[str, Mapping[Loaded, Ceiling]]],  # per clip and kind
) -> None:
    """Per kind and clip the mean over the main runs, in points of the error rate."""
    print("## Obergrenzen im Mittel der Hauptläufe")
    print()
    print(
        "Je Zelle harte Obergrenze · Orakel aus den vorhandenen Läufen, in Punkten "
        f"WER, Mittel über {len(mains)} Hauptläufe."
    )
    print()
    print("| Stellen | " + " | ".join(clip.name for clip in clips) + " |")
    print("| --- |" + " --- |" * len(clips))
    for kind in KINDS:
        cells = []
        for clip in clips:
            own = found[clip.name][kind].values()
            cells.append(
                f"{seeds._points(seeds._mean([one.hard for one in own]))} · "
                f"{seeds._points(seeds._mean([one.oracle for one in own]))}"
            )
        print(f"| {KIND_NAMES[kind]} | " + " | ".join(cells) + " |")
    print()


# --- main ---------------------------------------------------------------------------


def measure(
    paths: SessionPaths,
    name: str,
    count: int,
    others: Sequence[str],
    clips: Sequence[HandClip],
) -> None:
    _, speech, _ = omissions.heard_speech(omissions.diarized(paths))
    mains, sections = load(paths, name, count)
    everyone = list(mains)
    for other in others:
        runs, more = load(paths, other, count)
        everyone += runs
        sections += more
    asr.check_provenance(sections)
    end_ms = asr._end_ms(paths)
    found = {main: spots(main.reference, speech) for main in mains}
    cut = {
        main: {kind: pieces(found[main][kind], end_ms) for kind in KINDS}
        for main in mains
    }
    print_segment(mains, found, cut, end_ms)
    per_clip: dict[str, dict[str, dict[Loaded, Ceiling]]] = {}
    for clip in clips:
        hand = calibration.read_hand_reference(
            paths.review_dir / "calibration" / clip.file
        )
        words = len(hand.tokens)
        at_clip = {
            one: seeds.clip_run(one.run, one.reference, hand, clip) for one in everyone
        }
        # one time per reference word, from every run that heard it
        times = omissions.timeline(
            [omissions.heard(one.reference, hand, clip) for one in everyone], clip
        ).times
        ceilings = {
            kind: {
                main: ceiling(
                    at_clip[main],
                    [at_clip[one] for one in everyone if one is not main],
                    times,
                    cut[main][kind],
                )
                for main in mains
            }
            for kind in KINDS
        }
        print_clip(clip, words, mains, ceilings)
        per_clip[clip.name] = ceilings
    print_gate(clips, mains, per_clip)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("session", help="session key <group>/<ordinal>")
    parser.add_argument("--variant", default="norm", type=asr._variant_arg)
    parser.add_argument("--seeds", type=int, default=3, help="seeds 1..N")
    parser.add_argument(
        "--with",
        dest="others",
        action="append",
        type=asr._variant_arg,
        help="a further variant whose runs count for the oracle (repeatable)",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--clip",
        action="append",
        type=asr.parse_clip,
        help="NAME=FILE@H:MM:SS-H:MM:SS (default: pilot clips A and B)",
    )
    args = parser.parse_args(argv)
    try:
        paths = load_config(args.config).session_paths(SessionKey.parse(args.session))
        measure(
            paths,
            args.variant,
            args.seeds,
            args.others or (),
            args.clip or denoise.CLIPS,
        )
    except (SpikeError, ValueError, OSError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
