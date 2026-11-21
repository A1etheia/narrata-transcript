"""Speaker-turn spike (TOOL-96): cut passages at speaker changes, in memory.

    turns.py <group>/<ordinal> [--config PATH]

Reads the stored reference transcripts of a session, which must be diarized,
and the hand references A and B under `review/calibration/` (see
`denoise.CLIPS`). For the stored passages and for each cut threshold it cuts
every passage with `diarization.turns.split_at_speaker_changes` and prints
Markdown tables: the speaker error at A and B on passage level (each word takes
its passage's label, as the export does) and on word level (the diarization's
own word labels, which no cut changes), the share of passages with more than
one hand speaker, count and length of the passages, mixed passages, review
candidates and hints, all after rating the cut transcript again with freshly
found hints. Nothing is written.

Privacy (TOOL-66): the console gets counts, shares and times only, no text, no
names and no speaker labels.
"""

import argparse
import statistics
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

import denoise
from denoise import CLIPS, SEGMENT, HandClip, SpikeError, _pct

from transcript import calibration
from transcript.config import DEFAULT_CONFIG, Config, load_config
from transcript.diarization.turns import MinTurn, can_split, split_at_speaker_changes
from transcript.domain import DomainContext
from transcript.hints import segment_hints
from transcript.jsonfile import DataFileError
from transcript.manifest import load_manifest
from transcript.reference import Passage, ReferenceTranscript, Word, load_transcribed
from transcript.session import SessionKey, SessionPaths
from transcript.uncertainty import segment_assessment


@dataclass(frozen=True)
class Variant:
    name: str
    min_turn: MinTurn | None  # None: the stored passages, uncut


VARIANTS = (
    Variant("heute (ungeteilt)", None),
    Variant("0", MinTurn()),
    *(Variant(f"{ms} ms", MinTurn(ms=ms)) for ms in (250, 500, 1000, 1500, 2000)),
    *(Variant(f"{n} Wörter", MinTurn(words=n)) for n in (2, 3, 4)),
)


@dataclass(frozen=True)
class Result:
    variant: str
    passage_wder: dict[str, tuple[float | None, int]]  # per clip
    multi_speaker: dict[str, tuple[int, int]]  # per clip: passages with >1, rated
    passages: int
    seconds: list[float]  # passage durations
    mixed: int  # passages whose words carry more than one label
    off_label: int  # labelled words whose label differs from their passage
    labelled: int
    candidates: int
    flagged_ms: int
    total_ms: int
    hints: int


def cut(reference: ReferenceTranscript, min_turn: MinTurn) -> ReferenceTranscript:
    parts = [
        part
        for passage in reference.passages
        for part in split_at_speaker_changes(passage, min_turn)
    ]
    return replace(
        reference,
        passages=tuple(replace(p, index=n) for n, p in enumerate(parts, start=1)),
    )


def measure(
    variant: Variant,
    references: Sequence[ReferenceTranscript],
    hands: dict[str, calibration.HandReference],
    domain: DomainContext | None,
    config: Config,
) -> Result:
    shown = [
        r if variant.min_turn is None else cut(r, variant.min_turn) for r in references
    ]
    first = _first(shown)
    passage_wder = {c.name: wder(first, hands[c.name], c, by_passage) for c in CLIPS}
    multi = {c.name: multi_speaker(first, hands[c.name], c) for c in CLIPS}
    passages = [p for r in shown for p in r.passages]
    candidates = flagged = total = hint_count = 0
    for reference in shown:
        hints = (
            None
            if domain is None
            else segment_hints(reference, domain, config.review_similar)
        )
        hint_count += 0 if hints is None else len(hints.hints)
        rated = segment_assessment(reference, hints, config.review_uncertainty)
        spans = {p.index: _duration(p) for p in reference.passages}
        total += sum(spans.values())
        for rating in rated.ratings:
            if rating.level != "confident":
                candidates += 1
                flagged += spans[rating.passage]
    words = [(w, p) for p in passages for w in p.words if w.speaker is not None]
    return Result(
        variant=variant.name,
        passage_wder=passage_wder,
        multi_speaker=multi,
        passages=len(passages),
        seconds=[_duration(p) / 1000 for p in passages if p.start_ms is not None],
        mixed=sum(len(_labels(p)) > 1 for p in passages),
        off_label=sum(w.speaker != p.speaker for w, p in words),
        labelled=len(words),
        candidates=candidates,
        flagged_ms=flagged,
        total_ms=total,
        hints=hint_count,
    )


def by_passage(word: Word, passage: Passage) -> str | None:
    return passage.speaker


def wder(
    reference: ReferenceTranscript,
    hand: calibration.HandReference,
    clip: HandClip,
    label_of: Callable[[Word, Passage], str | None] = denoise._word_label,
) -> tuple[float | None, int]:
    """`denoise._wder`, n/a for a hand reference with fewer than two speakers.

    By default each word is scored with its own label, as denoise does.
    """
    if len(set(hand.speakers) - {"S?"}) < 2:
        return None, 0
    return denoise._wder(reference, hand, clip, label_of)


def multi_speaker(
    reference: ReferenceTranscript, hand: calibration.HandReference, clip: HandClip
) -> tuple[int, int]:
    """Passages with matched words of more than one hand speaker, and all rated."""
    texts, origins, _ = calibration._clip_tokens(reference, clip.start_ms, clip.end_ms)
    matcher = SequenceMatcher(a=hand.tokens, b=texts, autojunk=False)
    speakers: dict[int, set[str]] = {}
    for block in matcher.get_matching_blocks():
        for n in range(block.size):
            speaker = hand.speakers[block.a + n]
            if speaker != "S?":
                speakers.setdefault(origins[block.b + n].passage, set()).add(speaker)
    return sum(len(s) > 1 for s in speakers.values()), len(speakers)


def _first(references: Sequence[ReferenceTranscript]) -> ReferenceTranscript:
    """The segment the hand references A and B lie in."""
    return next(r for r in references if r.segment.index == SEGMENT)


def _labels(passage: Passage) -> set[str]:
    return {w.speaker for w in passage.words if w.speaker is not None}


def _duration(passage: Passage) -> int:
    return denoise._duration(passage.start_ms, passage.end_ms)


def unsplittable(references: Sequence[ReferenceTranscript]) -> tuple[int, int]:
    """Passages with more than one label that cannot be cut, and all such."""
    mixed = [p for r in references for p in r.passages if len(_labels(p)) > 1]
    return sum(not can_split(p) for p in mixed), len(mixed)


def print_tables(
    results: Sequence[Result],
    word_wder: dict[str, tuple[float | None, int]],
    hours: float,
    blocked: tuple[int, int],
) -> None:
    print("## Sprecherfehler an A und B\n")
    print(
        "Wortebene (unabhängig vom Schnitt): "
        + ", ".join(f"{c.name} {_value(word_wder[c.name])}" for c in CLIPS)
        + "\n"
    )
    print(
        "| Schnitt | "
        + " | ".join(
            f"Passagenebene {c.name} | mehrere Sprecher {c.name}" for c in CLIPS
        )
        + " |"
    )
    print("| --- |" + " --- | --- |" * len(CLIPS))
    for r in results:
        cells = []
        for c in CLIPS:
            many, rated = r.multi_speaker[c.name]
            cells += [
                _value(r.passage_wder[c.name]),
                f"{many} von {rated} ({_share(many, rated)})",
            ]
        print(f"| {r.variant} | " + " | ".join(cells) + " |")

    print("\n## Ganze Sitzung\n")
    print(
        "| Schnitt | Passagen | pro h | Länge P10 / Median / P90 (s) | gemischt "
        "| Wörter mit fremdem Label | Kandidaten | markierte Zeit | Hinweise |"
    )
    print("| --- |" + " --- |" * 8)
    for r in results:
        p10, p50, p90 = _quantiles(r.seconds)
        print(
            f"| {r.variant} | {r.passages} | {r.passages / hours:.0f} "
            f"| {p10:.1f} / {p50:.1f} / {p90:.1f} "
            f"| {r.mixed} ({_share(r.mixed, r.passages)}) "
            f"| {_share(r.off_label, r.labelled)} "
            f"| {r.candidates} ({_share(r.candidates, r.passages)}) "
            f"| {_share(r.flagged_ms, r.total_ms)} | {r.hints} |"
        )
    cannot, mixed = blocked
    print(
        f"\nUngeteilt, weil die Wortfolge nicht den Text ergibt: {cannot} von "
        f"{mixed} Passagen mit mehr als einem Label."
    )


def _value(found: tuple[float | None, int]) -> str:
    share, words = found
    return "n/a" if share is None else f"{_pct(share)} (n = {words})"


def _share(part: int, whole: int) -> str:
    return _pct(part / (whole or 1))


def _quantiles(values: list[float]) -> tuple[float, float, float]:
    if len(values) < 2:
        v = values[0] if values else 0.0
        return v, v, v
    deciles = statistics.quantiles(values, n=10)
    return deciles[0], statistics.median(values), deciles[-1]


def load(paths: SessionPaths) -> list[ReferenceTranscript]:
    references = []
    for segment in load_manifest(paths).segments:
        reference = load_transcribed(paths, segment.index)
        if reference is None:
            raise SpikeError(f"segment {segment.index} is not transcribed")
        if reference.diarization is None:
            raise SpikeError(f"segment {segment.index} is not diarized")
        references.append(reference)
    return references


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("session", help="session key <group>/<ordinal>")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        paths = config.session_paths(SessionKey.parse(args.session))
        references = load(paths)
        hands = {
            clip.name: calibration.read_hand_reference(
                paths.review_dir / "calibration" / clip.file
            )
            for clip in CLIPS
        }
        domain = (
            DomainContext.load(paths) if paths.knowledge_snapshot.is_file() else None
        )
        first = _first(references)
        word_wder = {c.name: wder(first, hands[c.name], c) for c in CLIPS}
        results = [measure(v, references, hands, domain, config) for v in VARIANTS]
        hours = sum(_duration(p) for r in references for p in r.passages) / 3_600_000
        print_tables(results, word_wder, hours or 1, unsplittable(references))
    except (SpikeError, ValueError, OSError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
