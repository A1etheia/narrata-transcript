"""Omission spike (TOOL-101): where the words Whisper leaves out lie.

    omissions.py <group>/<ordinal> [--variant base] [--seeds 3] [--clip ...]

Reads the stored runs of `asr.py` (one root per seed), the session's diarization
of segment 1 and the hand references under `review/calibration/`. Every
reference word gets one time for all seeds: the median over the seeds that
heard it, or a place between its neighbours if none did. Per clip it prints Markdown tables that set
the omissions against all reference words: overlap, turn length, speaker and
level, decoding windows with temperature fallback, audio the VAD removed,
stability over the seeds and speech without words. The only file it writes is
`work/<s>/experiments/asr/vad.json`, the speech ranges of the VAD as numbers.

Privacy (TOOL-66): the console gets counts, shares, levels and times only, no
text, no names and no speaker labels; speakers appear as ranks by word count.
"""

import argparse
import bisect
import itertools
import json
import math
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import asr
import denoise
import numpy as np
from denoise import RATE, SEGMENT, HandClip, SpikeError, _pct

from transcript import calibration, diarization
from transcript.config import DEFAULT_CONFIG, load_config
from transcript.jsonfile import DataFileError
from transcript.reference import ReferenceTranscript
from transcript.session import SessionKey, SessionPaths
from transcript.timecode import frames_to_ms

# thresholds fixed in the plan, before any count was seen
JOIN_TURNS_MS = 500  # same-label turns this close are one turn (TOOL-96)
SHORT_TURN_MS = 2_000
LONG_TURN_MS = 10_000
QUIET_DB = 6.0  # a turn this far below the loudest speaker is quiet
BRIDGE_WORDS_MS = 1_000  # a pause between words up to this is not missing speech
LONG_SILENT_MS = 2_000  # speech without words: stretches counted over the segment
MAX_WORD_MS = 1_000  # a recognised word counts as at most this long
LEVEL_MARGIN_MS = 30_000  # audio read around a clip for the level of its turns
MIN_LEVEL_MS = 1_000  # a label needs this much audio in the clip to count as loudest
VAD_TOLERANCE_S = 1.0
# faster-whisper 1.2.1, `WhisperModel.transcribe` with `vad_filter` and no
# `vad_parameters`, as the pipeline runs it; spelled out so the cache records them
VAD_OPTIONS = {"threshold": 0.5, "min_silence_duration_ms": 2000, "speech_pad_ms": 400}

YES, NO = "ja", "nein"
NO_TURN = "kein Turn"
OVERLAP = "Überlappung"
TURN_LENGTH = "Beitragslänge (Diarisierung)"
HAND_TURN = "Beitrag laut Handreferenz"
LEVEL = "Pegel des Beitrags"
FALLBACK = "Fallback-Fenster"
SPARSE = "dünnes Fenster"
VAD = "von der VAD entfernt"
SILENT = "Sprache ohne Wörter"
EXPLAINED = "erklärt (Überlappung, kurz, leise oder Fallback)"
SHORT, MEDIUM, LONG = "unter 2 s", "2–10 s", "über 10 s"
QUIET, LOUD = f"mind. {QUIET_DB:.0f} dB leiser", "lauter"
FEATURES: dict[str, tuple[str, ...]] = {
    OVERLAP: (YES, NO),
    TURN_LENGTH: (SHORT, MEDIUM, LONG, NO_TURN),
    HAND_TURN: ("1–3 Wörter", "4–10 Wörter", "über 10 Wörter"),
    LEVEL: (QUIET, LOUD, NO_TURN),
    FALLBACK: (YES, NO),
    SPARSE: (YES, NO),
    VAD: (YES, NO),
    SILENT: (YES, NO),
    EXPLAINED: (YES, NO),
}


@dataclass(frozen=True)
class Ranges:
    """Sorted, disjoint, half-open time ranges in ms."""

    starts: tuple[int, ...] = ()
    ends: tuple[int, ...] = ()

    @classmethod
    def union(cls, spans: Iterable[tuple[int, int]], bridge_ms: int = 0) -> "Ranges":
        """`spans` merged; ranges at most `bridge_ms` apart become one."""
        merged: list[list[int]] = []
        for start, end in sorted(span for span in spans if span[1] > span[0]):
            if merged and start - merged[-1][1] <= bridge_ms:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return cls(tuple(m[0] for m in merged), tuple(m[1] for m in merged))

    def spans(self) -> list[tuple[int, int]]:
        return list(zip(self.starts, self.ends, strict=True))

    def index(self, ms: float) -> int | None:
        n = bisect.bisect_right(self.starts, ms) - 1
        return n if n >= 0 and ms < self.ends[n] else None

    def __contains__(self, ms: float) -> bool:
        return self.index(ms) is not None

    def minus(self, other: "Ranges") -> "Ranges":
        found: list[tuple[int, int]] = []
        for start, end in self.spans():
            cursor = start
            n = bisect.bisect_right(other.ends, start)  # the first ending after it
            while n < len(other.starts) and other.starts[n] < end:
                if other.starts[n] > cursor:
                    found.append((cursor, other.starts[n]))
                cursor = max(cursor, other.ends[n])
                n += 1
            if cursor < end:
                found.append((cursor, end))
        return Ranges.union(found)

    def within(self, start_ms: int, end_ms: int) -> "Ranges":
        return Ranges.union(
            (max(start, start_ms), min(end, end_ms)) for start, end in self.spans()
        )

    def longer(self, ms: int) -> "Ranges":
        return Ranges.union(span for span in self.spans() if span[1] - span[0] >= ms)

    @property
    def total(self) -> int:
        return sum(end - start for start, end in self.spans())


# --- word times ---------------------------------------------------------------------


def heard(
    reference: ReferenceTranscript, hand: calibration.HandReference, clip: HandClip
) -> tuple[float | None, ...]:
    """Per token of the hand reference the time one run heard it at, None if omitted.

    Aligned as `calibration.measure` does. A matched or substituted token takes
    the start of its recognised word plus half its length, the length capped:
    Whisper stretches the word before skipped speech over the gap.
    """
    texts, origins, _ = calibration._clip_tokens(reference, clip.start_ms, clip.end_ms)
    passages = {passage.index: passage for passage in reference.passages}
    times: list[float | None] = [None] * len(hand.tokens)
    matcher = SequenceMatcher(a=hand.tokens, b=texts, autojunk=False)
    for _, ref_start, ref_end, hyp_start, hyp_end in matcher.get_opcodes():
        for n in range(min(ref_end - ref_start, hyp_end - hyp_start)):
            origin = origins[hyp_start + n]
            word = passages[origin.passage].words[origin.word]
            length = max((word.end_ms or word.start_ms) - word.start_ms, 0)
            times[ref_start + n] = word.start_ms + min(length, MAX_WORD_MS) / 2
    expected = [position for position, _ in calibration.align(hand, texts).deletions]
    if [n for n, ms in enumerate(times) if ms is None] != expected:
        raise SpikeError(f"{clip.name}: omissions differ from calibration.align")
    return tuple(times)


@dataclass(frozen=True)
class Timeline:
    """One time per token of the hand reference, shared by all seeds."""

    times: tuple[float, ...]  # ms on the segment's timeline
    guessed: tuple[bool, ...]  # no seed heard the token: placed between neighbours
    spreads: tuple[float, ...]  # per token several seeds heard: latest minus earliest


def timeline(runs: Sequence[Sequence[float | None]], clip: HandClip) -> Timeline:
    """The median of the times the seeds heard a token at.

    A run of tokens no seed heard is spread evenly between its timed neighbours,
    or the clip's edge.
    """
    found = [[ms for ms in at if ms is not None] for at in zip(*runs, strict=True)]
    times = [statistics.median(at) if at else None for at in found]
    position = 0
    while position < len(times):
        if times[position] is not None:
            position += 1
            continue
        end = position
        while end < len(times) and times[end] is None:
            end += 1
        left = times[position - 1] if position else clip.start_ms
        right = max(left, times[end] if end < len(times) else clip.end_ms)
        for n in range(position, end):
            times[n] = left + (right - left) * (n - position + 1) / (end - position + 1)
        position = end
    return Timeline(
        tuple(times),
        tuple(not at for at in found),
        tuple(max(at) - min(at) for at in found if len(at) > 1),
    )


# --- diarization and level ----------------------------------------------------------


@dataclass(frozen=True)
class Turns:
    """Exclusive turns with close same-label neighbours joined."""

    ranges: Ranges
    labels: tuple[str, ...]

    @classmethod
    def joined(cls, turns: Sequence[diarization.Turn]) -> "Turns":
        found: list[list] = []
        for turn in turns:  # exclusive turns are sorted and never overlap
            last = found[-1] if found else None
            if (
                last
                and last[2] == turn.label
                and turn.start_ms - last[1] <= JOIN_TURNS_MS
            ):
                last[1] = turn.end_ms
            elif turn.end_ms > turn.start_ms:
                found.append([turn.start_ms, turn.end_ms, turn.label])
        return cls(
            Ranges(tuple(f[0] for f in found), tuple(f[1] for f in found)),
            tuple(f[2] for f in found),
        )

    def by_label(self, start_ms: int, end_ms: int) -> dict[str, Ranges]:
        """Per label its turns, cut to `start_ms`..`end_ms`."""
        spans: dict[str, list[tuple[int, int]]] = {}
        for label, (start, end) in zip(self.labels, self.ranges.spans(), strict=True):
            spans.setdefault(label, []).append((start, end))
        found = {
            label: Ranges.union(own).within(start_ms, end_ms)
            for label, own in spans.items()
        }
        return {label: ranges for label, ranges in found.items() if ranges.starts}


@dataclass(frozen=True)
class Audio:
    """Samples of the segment WAV from `start_ms` on, as floats in -1..1."""

    start_ms: int
    samples: np.ndarray

    def level(self, spans: Iterable[tuple[int, int]]) -> float | None:
        """RMS in dBFS over `spans`, as far as the samples reach."""
        energy, count = 0.0, 0
        for start, end in spans:
            first = max(0, (start - self.start_ms) * RATE // 1000)
            last = min(len(self.samples), (end - self.start_ms) * RATE // 1000)
            if last > first:
                part = self.samples[first:last]
                energy += float(np.dot(part, part))
                count += last - first
        if not count:
            return None
        return 20 * math.log10(max(math.sqrt(energy / count), 1e-9))


def read_audio(wav: Path, start_ms: int, end_ms: int) -> Audio:
    start_ms = max(0, start_ms)
    samples = asr._read_wav(
        wav, start_ms * RATE // 1000, (end_ms - start_ms) * RATE // 1000
    )
    return Audio(start_ms, samples)


def vad_speech(paths: SessionPaths, name: str) -> Ranges:
    """The speech ranges the VAD of variant `name` keeps in segment 1.

    Computed once per set of options on the WAV the variant's roots link, and
    cached as numbers: next to the filtered copy, or for the raw WAV where
    TOOL-101 put it.
    """
    spec = asr.variant(name)
    settings = spec.asr
    if settings.get("vad_filter") is False:
        raise SpikeError(f"{name}: runs without VAD")
    options = {**VAD_OPTIONS, **settings.get("vad_parameters", {})}
    wav = asr.chain_wav(paths, spec.chain)
    record = paths.work_dir / "experiments" / "asr" / "vad.json"
    if spec.chain != denoise.Chain():
        record = wav.with_name("vad.json")
    frames = denoise._manifest_frames(paths)
    stored = asr._read_json(record)
    if stored.get("frames") != frames or stored.get("options") != options:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        audio = read_audio(wav, 0, asr._end_ms(paths) + 1)
        chunks = get_speech_timestamps(audio.samples, VadOptions(**options))
        stored = {
            "frames": frames,
            "options": options,
            "chunks": [[int(c["start"]), int(c["end"])] for c in chunks],
        }
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(stored), encoding="utf-8")
    return Ranges.union(
        (frames_to_ms(start, RATE), frames_to_ms(end, RATE))
        for start, end in stored["chunks"]
    )


# --- one run at one clip ------------------------------------------------------------


@dataclass(frozen=True)
class Context:
    """What all seeds of a session share."""

    overlaps: Ranges
    speech: Ranges  # where the diarization hears anyone
    turns: Turns
    vad: Ranges


@dataclass(frozen=True)
class ClipTurns:
    """What the turns and the audio say at one clip, the same for every seed."""

    lengths: tuple[str, ...]  # per turn: its length class
    levels: tuple[str, ...]  # per turn: its level class
    labels: Mapping[str, float]  # label -> dB against the loudest label
    floor: float | None  # the clip's audio outside every turn, likewise


@dataclass(frozen=True)
class ClipResult:
    seed: int
    deleted: tuple[bool, ...]
    classes: Mapping[str, tuple[str, ...]]  # feature -> class per reference token
    levels: Mapping[str, float | None]  # hand speaker -> dB against the loudest
    silent_share: float  # of the clip's time


def silence(reference: ReferenceTranscript, context: Context) -> Ranges:
    """Where the diarization hears speech and the run has no word."""
    words = Ranges.union(
        (
            (word.start_ms, word.end_ms)
            for word in reference.words
            if word.start_ms is not None and word.end_ms is not None
        ),
        bridge_ms=BRIDGE_WORDS_MS,
    )
    return context.speech.minus(words).longer(BRIDGE_WORDS_MS)


def clip_turns(clip: HandClip, context: Context, audio: Audio) -> ClipTurns:
    found = {
        label: audio.level(ranges.spans())
        for label, ranges in context.turns.by_label(clip.start_ms, clip.end_ms).items()
        if ranges.total >= MIN_LEVEL_MS
    }
    loudest = max((v for v in found.values() if v is not None), default=None)
    if loudest is None:
        raise SpikeError(f"{clip.name}: no diarization turn in the clip")
    lengths, levels = [], []
    for start, end in context.turns.ranges.spans():
        lengths.append(
            SHORT
            if end - start < SHORT_TURN_MS
            else MEDIUM
            if end - start <= LONG_TURN_MS
            else LONG
        )
        level = audio.level([(start, end)])  # None away from the clip
        levels.append(
            NO_TURN if level is None else QUIET if level <= loudest - QUIET_DB else LOUD
        )
    pauses = Ranges.union([(clip.start_ms, clip.end_ms)]).minus(context.speech)
    floor = audio.level(pauses.spans())
    return ClipTurns(
        tuple(lengths),
        tuple(levels),
        {label: level - loudest for label, level in found.items() if level is not None},
        None if floor is None else floor - loudest,
    )


def analyse(
    seed: int,
    deleted: Sequence[bool],
    times: Sequence[float],
    windows: Sequence[asr.DecodeWindow],
    quiet: Ranges,
    clip: HandClip,
    hand: calibration.HandReference,
    context: Context,
    turns: ClipTurns,
) -> ClipResult:
    window_starts = [window.start_ms for window in windows]
    runs = _hand_turns(hand.speakers)
    classes: dict[str, list[str]] = {feature: [] for feature in FEATURES}
    pairs: Counter[tuple[str, str]] = Counter()
    for position, ms in enumerate(times):
        turn = context.turns.ranges.index(ms)
        if turn is None:
            length = level = NO_TURN
        else:
            length, level = turns.lengths[turn], turns.levels[turn]
            if not deleted[position]:
                pairs[(hand.speakers[position], context.turns.labels[turn])] += 1
        window = bisect.bisect_right(window_starts, ms) - 1
        fallback = window >= 0 and windows[window].fallback
        row = {
            OVERLAP: _yes(ms in context.overlaps),
            TURN_LENGTH: length,
            HAND_TURN: runs[position],
            LEVEL: level,
            FALLBACK: _yes(fallback),
            SPARSE: _yes(window >= 0 and windows[window].sparse),
            VAD: _yes(ms not in context.vad),
            SILENT: _yes(ms in quiet),
        }
        row[EXPLAINED] = _yes(
            row[OVERLAP] == YES or length == SHORT or level == QUIET or fallback
        )
        for feature, value in row.items():
            classes[feature].append(value)

    mapping = denoise.best_mapping(
        pairs, sorted({s for s, _ in pairs}), sorted({label for _, label in pairs})
    )
    label_of = {speaker: label for label, speaker in mapping.items()}
    return ClipResult(
        seed=seed,
        deleted=tuple(deleted),
        classes={feature: tuple(values) for feature, values in classes.items()},
        levels={
            speaker: turns.labels.get(label_of.get(speaker, ""))
            for speaker in set(hand.speakers)
        },
        silent_share=quiet.within(clip.start_ms, clip.end_ms).total
        / (clip.end_ms - clip.start_ms),
    )


def _yes(value: bool) -> str:
    return YES if value else NO


def _hand_turns(speakers: Sequence[str]) -> list[str]:
    """Per token the size class of its turn: the run of tokens of one speaker."""
    found: list[str] = []
    start = 0
    for n in range(1, len(speakers) + 1):
        if n == len(speakers) or speakers[n] != speakers[start]:
            size = n - start
            name = FEATURES[HAND_TURN][0 if size <= 3 else 1 if size <= 10 else 2]
            found += [name] * size
            start = n
    return found


# --- tables -------------------------------------------------------------------------


def _counts(values: Sequence[int]) -> str:
    return " / ".join(str(value) for value in values)


def _share(parts: Sequence[int], wholes: Sequence[int]) -> str:
    shares = [part / whole for part, whole in zip(parts, wholes, strict=True) if whole]
    return asr._spread(shares) if shares else "–"


def _db(value: float | None) -> str:
    return "–" if value is None else f"{value:+.1f}".replace(".", ",")


def print_clip(
    clip: HandClip,
    hand: calibration.HandReference,
    results: Sequence[ClipResult],
    placed: Timeline,
    floor: float | None,
) -> None:
    words = [len(hand.tokens)] * len(results)
    gone = [sum(r.deleted) for r in results]
    print(f"## Referenz {clip.name}")
    print()
    print(
        f"{len(hand.tokens)} Referenzwörter, Auslassungen je Seed {_counts(gone)}, "
        f"je Wort {_share(gone, words)}"
    )
    print()

    print(
        "| Merkmal | Klasse | Auslassungen je Seed | Anteil an den Auslassungen | "
        "Referenzwörter je Seed | Anteil an allen Referenzwörtern | "
        "Auslassungen je Wort der Klasse |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for feature, names in FEATURES.items():
        for name in names:
            inside = [[c == name for c in r.classes[feature]] for r in results]
            held = [sum(flags) for flags in inside]
            if not any(held):
                continue
            lost = [
                sum(d and f for d, f in zip(r.deleted, flags, strict=True))
                for r, flags in zip(results, inside, strict=True)
            ]
            print(
                f"| {feature} | {name} | {_counts(lost)} | {_share(lost, gone)} | "
                f"{_counts(held)} | {_share(held, words)} | {_share(lost, held)} |"
            )
    print()

    ranks = _ranks(hand.speakers)
    print(
        "| Sprecher (Rang nach Wortzahl) | Wörter | Auslassungen je Seed | "
        "Auslassungen je Wort | Pegel zum lautesten Sprecher (dB) |"
    )
    print("| --- | --- | --- | --- | --- |")
    for speaker, rank in ranks.items():
        own = sum(s == speaker for s in hand.speakers)
        lost = [
            sum(
                d and s == speaker
                for d, s in zip(r.deleted, hand.speakers, strict=True)
            )
            for r in results
        ]
        levels = " / ".join(dict.fromkeys(_db(r.levels[speaker]) for r in results))
        print(
            f"| {rank} | {own} | {_counts(lost)} | "
            f"{_share(lost, [own] * len(results))} | {levels} |"
        )
    print(f"| ohne Sprache laut Diarisierung | – | – | – | {_db(floor)} |")
    print()

    seeds = len(results)
    times_gone = Counter(
        sum(r.deleted[n] for r in results) for n in range(len(hand.tokens))
    )
    print("| Stabilität | Referenzwörter |")
    print("| --- | --- |")
    for count in range(seeds, 0, -1):
        print(f"| fehlt in {count} von {seeds} Seeds | {times_gone[count]} |")
    print(f"| fehlt in mindestens einem Seed | {len(hand.tokens) - times_gone[0]} |")
    print()

    print(
        "| Seed | Folgen von Auslassungen | längste Folge (Wörter) | Clip-Zeit mit Sprache ohne Wörter |"
    )
    print("| --- | --- | --- | --- |")
    for r in results:
        runs = [
            len(list(group)) for gone, group in itertools.groupby(r.deleted) if gone
        ]
        print(
            f"| {r.seed} | {len(runs)} | {max(runs, default=0)} | "
            f"{_pct(r.silent_share)} |"
        )
    print()

    spreads = sorted(placed.spreads)
    print(
        f"Verortung: {sum(placed.guessed)} Referenzwörter hat kein Seed erkannt, sie "
        f"liegen zwischen ihren Nachbarn. Bei {len(spreads)} Wörtern mit Zeiten aus "
        "mehreren Seeds liegen die Zeiten im Median "
        f"{asr._decimal(statistics.median(spreads) / 1000 if spreads else 0)} s "
        "auseinander, bei den 10 % mit dem größten Abstand mindestens "
        f"{asr._decimal(spreads[len(spreads) * 9 // 10] / 1000 if spreads else 0)} s."
    )
    print()


def _ranks(speakers: Sequence[str]) -> dict[str, int]:
    """Hand speaker -> rank by word count, 1 for the most words."""
    ordered = sorted(Counter(speakers).items(), key=lambda item: (-item[1], item[0]))
    return {speaker: rank for rank, (speaker, _) in enumerate(ordered, start=1)}


def print_segment(
    found: Mapping[int, Ranges], speech_ms: int, vad: Ranges, end_ms: int
) -> None:
    print("## Segment")
    print()
    print(
        f"VAD: {asr._decimal(vad.total / 60_000)} min von "
        f"{asr._decimal(end_ms / 60_000)} min behalten"
    )
    print()
    print(
        "| Seed | Sprache laut Diarisierung (min) | davon ohne Wörter | "
        f"Stellen ab {LONG_SILENT_MS // 1000} s | Zeit in diesen Stellen (min) |"
    )
    print("| --- | --- | --- | --- | --- |")
    for seed, quiet in found.items():
        long = quiet.longer(LONG_SILENT_MS)
        print(
            f"| {seed} | {asr._decimal(speech_ms / 60_000)} | "
            f"{_pct(quiet.total / (speech_ms or 1))} | "
            f"{len(long.starts)} | {asr._decimal(long.total / 60_000)} |"
        )
    print()


# --- main ---------------------------------------------------------------------------


def measure(
    paths: SessionPaths, name: str, seeds: int, clips: Sequence[HandClip]
) -> None:
    run = diarization.load_run(paths, SEGMENT)
    if run is None:
        raise SpikeError(f"segment {SEGMENT} of the session is not diarized")
    vad = vad_speech(paths, name)
    context = Context(
        overlaps=Ranges.union(
            (o.start_ms, o.end_ms) for o in diarization.overlaps(run.turns)
        ),
        speech=Ranges.union((t.start_ms, t.end_ms) for t in run.turns),
        turns=Turns.joined(run.exclusive_turns),
        vad=vad,
    )
    references = {
        seed: asr.transcribed(paths, name, seed) for seed in range(1, seeds + 1)
    }
    asr.check_provenance(
        [asr.sections(paths, name, seed, r) for seed, r in references.items()]
    )
    windows = {seed: asr.decode_windows(paths, name, seed) for seed in references}
    for seed in references:
        raw = asr._read_json(
            SessionPaths(paths.key, asr.shadow_root(paths, name, seed)).reference_raw(
                SEGMENT
            )
        )
        after = raw.get("raw", {}).get("info", {}).get("duration_after_vad")
        if after is None or abs(after - vad.total / 1000) > VAD_TOLERANCE_S:
            raise SpikeError(f"{name}#{seed}: VAD ranges do not match the run's")
    quiet = {
        seed: silence(reference, context) for seed, reference in references.items()
    }
    print_segment(quiet, context.speech.total, vad, asr._end_ms(paths))
    # the level of what Whisper heard: the filtered copy for a filtered variant
    wav = asr.chain_wav(paths, asr.variant(name).chain)
    for clip in clips:
        hand = calibration.read_hand_reference(
            paths.review_dir / "calibration" / clip.file
        )
        audio = read_audio(
            wav, clip.start_ms - LEVEL_MARGIN_MS, clip.end_ms + LEVEL_MARGIN_MS
        )
        turns = clip_turns(clip, context, audio)
        runs = {seed: heard(r, hand, clip) for seed, r in references.items()}
        placed = timeline(list(runs.values()), clip)
        results = [
            analyse(
                seed,
                [ms is None for ms in at],
                placed.times,
                windows[seed],
                quiet[seed],
                clip,
                hand,
                context,
                turns,
            )
            for seed, at in runs.items()
        ]
        print_clip(clip, hand, results, placed, turns.floor)


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
    args = parser.parse_args(argv)
    try:
        paths = load_config(args.config).session_paths(SessionKey.parse(args.session))
        measure(paths, args.variant, args.seeds, args.clip or denoise.CLIPS)
    except (SpikeError, ValueError, OSError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
