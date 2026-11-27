"""Clips for faster-whisper's batched pipeline, cut from diarization turns (TOOL-112).

`build` turns the exclusive turns of a diarization into the ranges the batched
pipeline decodes one by one instead of its VAD's: one clip per turn, optionally
with same-label neighbours joined, padded into the free gaps, short clips merged
into a neighbour, or packed across labels. Every clip longer than the decoder's
30 s is split, since the pipeline would drop the rest. The thresholds were fixed
in the plan, before any count was seen.

Privacy (TOOL-66): clips are times only; labels decide the joins and are not kept.
"""

import hashlib
import itertools
import json
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from denoise import SpikeError

MAX_MS = 30_000  # the batched pipeline decodes only the first 30 s of a clip
JOIN_MS = 500  # same-label turns this close are one clip (TOOL-96)
PAD_MS = 400  # `speech_pad_ms` of the pipeline's VAD
MIN_MS = 2_000  # a clip under this is merged into a neighbour
MIN_GAP_MS = 1_000  # ... if the neighbour is this close
PACK_GAP_MS = 2_000  # `min_silence_duration_ms` of the pipeline's VAD
EDGE_MS = 1_000  # a cut at a pause leaves at least this much on both sides

Span = tuple[int, int]


class _Turn(Protocol):
    start_ms: int
    end_ms: int
    label: str


@dataclass(frozen=True)
class Clip:
    start_ms: int
    end_ms: int
    turns: tuple[Span, ...]  # the turns it was made from, sorted

    @property
    def length(self) -> int:
        return self.end_ms - self.start_ms


def build(
    turns: Sequence[_Turn],
    params: Mapping[str, int],
    end_ms: int,
    pauses: Sequence[Span] = (),
) -> list[Clip]:
    """The clips of `params` for sorted, disjoint `turns` of a segment `end_ms` long.

    `pauses` are silences a long turn may be cut at.
    """
    max_ms = params["max_ms"]
    clips = from_turns(turns, params.get("join_ms"))
    if "pad_ms" in params:
        clips = padded(clips, params["pad_ms"], end_ms)
    if "min_ms" in params:
        clips = without_short(clips, params["min_ms"], params["min_gap_ms"], max_ms)
    if "pack_gap_ms" in params:
        clips = packed(clips, params["pack_gap_ms"], max_ms)
    clips = [piece for clip in clips for piece in split(clip, max_ms, pauses)]
    check(clips, turns, max_ms)
    return clips


def from_turns(turns: Sequence[_Turn], join_ms: int | None) -> list[Clip]:
    """One clip per turn; with `join_ms`, same-label neighbours that close are one."""
    found: list[Clip] = []
    last_label = None
    for turn in turns:
        if turn.end_ms <= turn.start_ms:
            continue
        span = (turn.start_ms, turn.end_ms)
        if (
            join_ms is not None
            and found
            and last_label == turn.label
            and turn.start_ms - found[-1].end_ms <= join_ms
        ):
            found[-1] = Clip(found[-1].start_ms, turn.end_ms, (*found[-1].turns, span))
        else:
            found.append(Clip(*span, (span,)))
        last_label = turn.label
    return found


def padded(clips: Sequence[Clip], pad_ms: int, end_ms: int) -> list[Clip]:
    """Each clip widened by `pad_ms`, at most to the middle of the gap to its
    neighbour: clips never overlap, or their words would be decoded twice."""
    found = []
    for n, clip in enumerate(clips):
        # the free room on each side: half the gap, or all of it at the edges
        before = (clip.start_ms - clips[n - 1].end_ms) // 2 if n else clip.start_ms
        after = (
            (clips[n + 1].start_ms - clip.end_ms) // 2
            if n + 1 < len(clips)
            else end_ms - clip.end_ms
        )
        found.append(
            Clip(
                clip.start_ms - max(min(pad_ms, before), 0),
                clip.end_ms + max(min(pad_ms, after), 0),
                clip.turns,
            )
        )
    return found


def without_short(
    clips: Sequence[Clip], min_ms: int, gap_ms: int, max_ms: int
) -> list[Clip]:
    """A clip under `min_ms` merged into the nearer neighbour within `gap_ms`, if
    both fit in `max_ms`; otherwise it stays. No clip is dropped."""
    todo = deque(clips)
    found: list[Clip] = []
    while todo:
        clip = todo.popleft()
        if clip.length >= min_ms:
            found.append(clip)
            continue
        gaps = []  # (gap, 0: the clip before, 1: the clip after)
        if found and _fits(found[-1], clip, gap_ms, max_ms):
            gaps.append((clip.start_ms - found[-1].end_ms, 0))
        if todo and _fits(clip, todo[0], gap_ms, max_ms):
            gaps.append((todo[0].start_ms - clip.end_ms, 1))
        if not gaps:
            found.append(clip)
        elif min(gaps)[1] == 0:
            found[-1] = _merged(found[-1], clip)
        else:  # judged again: it may still be short
            todo.appendleft(_merged(clip, todo.popleft()))
    return found


def packed(clips: Sequence[Clip], gap_ms: int, max_ms: int) -> list[Clip]:
    """Consecutive clips within `gap_ms` as one, as long as it fits in `max_ms`."""
    found: list[Clip] = []
    for clip in clips:
        if found and _fits(found[-1], clip, gap_ms, max_ms):
            found[-1] = _merged(found[-1], clip)
        else:
            found.append(clip)
    return found


def split(clip: Clip, max_ms: int, pauses: Sequence[Span]) -> list[Clip]:
    """`clip` in pieces of at most `max_ms`.

    Cut at the widest gap between its turns; without one at the pause nearest to
    its middle; without one in equal parts.
    """
    if clip.length <= max_ms:
        return [clip]
    cut = _cut(clip, max_ms, pauses)
    left = Clip(
        clip.start_ms,
        cut,
        tuple((start, min(end, cut)) for start, end in clip.turns if start < cut),
    )
    right = Clip(
        cut,
        clip.end_ms,
        tuple((max(start, cut), end) for start, end in clip.turns if end > cut),
    )
    return [*split(left, max_ms, pauses), *split(right, max_ms, pauses)]


def _cut(clip: Clip, max_ms: int, pauses: Sequence[Span]) -> int:
    middle = (clip.start_ms + clip.end_ms) / 2
    # (width, where): between two turns, cut in the middle of the gap
    gaps = [
        (b[0] - a[1], (a[1] + b[0]) // 2) for a, b in itertools.pairwise(clip.turns)
    ]
    gaps = [gap for gap in gaps if clip.start_ms < gap[1] < clip.end_ms]
    if gaps:
        return max(gaps, key=lambda gap: (gap[0], -abs(gap[1] - middle), gap[1]))[1]
    quiet = [(start + end) // 2 for start, end in pauses]
    quiet = [
        at for at in quiet if clip.start_ms + EDGE_MS <= at <= clip.end_ms - EDGE_MS
    ]
    if quiet:
        return min(quiet, key=lambda at: (abs(at - middle), at))
    parts = -(-clip.length // max_ms)
    return clip.start_ms + clip.length // parts


def _fits(first: Clip, second: Clip, gap_ms: int, max_ms: int) -> bool:
    return (
        second.start_ms - first.end_ms <= gap_ms
        and second.end_ms - first.start_ms <= max_ms
    )


def _merged(first: Clip, second: Clip) -> Clip:
    return Clip(first.start_ms, second.end_ms, first.turns + second.turns)


def check(clips: Sequence[Clip], turns: Sequence[_Turn], max_ms: int) -> None:
    """Sorted, disjoint, none longer than `max_ms`, and every turn is covered."""
    if any(not 0 < clip.length <= max_ms for clip in clips):
        raise SpikeError("clips: one is empty or longer than the decoder takes")
    if any(b.start_ms < a.end_ms for a, b in itertools.pairwise(clips)):
        raise SpikeError("clips: two overlap or are out of order")
    spoken = sum(max(turn.end_ms - turn.start_ms, 0) for turn in turns)
    covered = 0
    todo = iter(clips)
    clip = next(todo, None)
    for turn in turns:  # sorted and disjoint, as the clips
        while clip is not None and clip.end_ms <= turn.start_ms:
            clip = next(todo, None)
        while clip is not None and clip.start_ms < turn.end_ms:
            covered += min(clip.end_ms, turn.end_ms) - max(clip.start_ms, turn.start_ms)
            if clip.end_ms > turn.end_ms:
                break  # it reaches into the next turn
            clip = next(todo, None)
    if covered != spoken:
        raise SpikeError("clips: they do not cover every turn")


def record(clips: Sequence[Clip], params: Mapping[str, int]) -> dict[str, object]:
    """What a root stores: the parameters, the clips in ms and their hash, which
    goes into `asr.settings` so a root with other clips is transcribed again."""
    spans = [[clip.start_ms, clip.end_ms] for clip in clips]
    sha = hashlib.sha256(json.dumps(spans).encode()).hexdigest()
    return {"params": dict(params), "sha": sha, "clips": spans}
