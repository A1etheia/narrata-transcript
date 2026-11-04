"""Who spoke when: stored diarization turns and their transfer onto the words.

A diarizer (pyannote, see `transcript.diarization.pyannote`) answers per segment
WAV with turns: time ranges with a generic label such as `SPEAKER_00`. Its answer
is stored unchanged under `work/<session>/diarization/segment-NN.json`, apart
from the reference transcript, so it can be reused without the model.

`assign_speakers` copies the labels onto the words of a reference transcript.
Only speaker fields and the `diarization` block change; text, times and
confidence stay as the ASR backend delivered them. Labels hold within one
segment only; matching them across segments is TOOL-68.

Error messages name the file and the field, never a label or any text.
"""

import bisect
import functools
import itertools
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from transcript import jsonfile
from transcript.asr import BackendInfo
from transcript.jsonfile import DataFileError
from transcript.reference import (
    Diarization,
    Overlap,
    Passage,
    ReferenceTranscript,
    Word,
    check_span,
    majority_speaker,
)
from transcript.session import SessionPaths

DIARIZATION_FORMAT_VERSION = 1


class DiarizationError(DataFileError):
    """A stored diarization is unreadable or invalid."""


@dataclass(frozen=True)
class Turn:
    """A time range, local to the segment WAV, in which `label` speaks."""

    start_ms: int
    end_ms: int
    label: str

    def __post_init__(self) -> None:
        check_span(self.start_ms, self.end_ms, "turn time")
        if not self.label:
            raise ValueError("turn label is empty")


@dataclass(frozen=True)
class DiarizationRun:
    """A diarizer's answer for one segment WAV, as stored in the raw file.

    `turns` may overlap where people talk at once; they only yield the overlap
    ranges. `exclusive_turns` never overlap and alone decide the word labels;
    they are kept sorted by start. `info.model_version` is the model revision.
    """

    info: BackendInfo
    audio_sha256: str  # of the segment WAV the turns belong to
    turns: tuple[Turn, ...]
    exclusive_turns: tuple[Turn, ...] = ()
    settings: Mapping[str, Any] = field(default_factory=dict)
    num_speakers: int | None = None  # the hint given, not the number found

    def __post_init__(self) -> None:
        if self.num_speakers is not None and self.num_speakers < 1:
            raise ValueError("num_speakers must be positive")
        exclusive = tuple(sorted(self.exclusive_turns, key=_start))
        object.__setattr__(self, "exclusive_turns", exclusive)
        for previous, current in itertools.pairwise(exclusive):
            if current.start_ms < previous.end_ms:
                raise ValueError("exclusive turns overlap")

    @property
    def labels(self) -> tuple[str, ...]:
        """Every label of the segment, sorted."""
        return tuple(
            sorted({turn.label for turn in (*self.turns, *self.exclusive_turns)})
        )

    def matches(
        self,
        info: BackendInfo,
        settings: Mapping[str, Any],
        num_speakers: int | None,
        audio_sha256: str,
    ) -> bool:
        """Whether a new run with these inputs would repeat this one.

        The runtime version is left out: it is provenance, while model, revision
        and settings decide the turns.
        """
        return (
            (self.info.backend_id, self.info.model, self.info.model_version)
            == (info.backend_id, info.model, info.model_version)
            and dict(self.settings) == dict(settings)
            and self.num_speakers == num_speakers
            and self.audio_sha256 == audio_sha256
        )


def assign_speakers(
    reference: ReferenceTranscript, run: DiarizationRun
) -> ReferenceTranscript:
    """`reference` with word, passage and diarization speaker data from `run`.

    A word gets the label of the exclusive turn its midpoint lies in, half-open
    `[start, end)`. Without times or outside every turn it keeps no label, which
    stays visible. A passage takes the majority of its word labels. Labels the
    reference carried before are replaced.
    """
    if reference.status != "transcribed":
        raise ValueError("only a transcribed segment can get speaker labels")
    passages = tuple(
        _labelled(passage, run.exclusive_turns) for passage in reference.passages
    )
    return replace(
        reference,
        passages=passages,
        diarization=Diarization(
            backend_id=run.info.backend_id,
            model=run.info.model,
            model_version=run.info.model_version,
            settings=dict(run.settings),
            num_speakers=run.num_speakers,
            labels=run.labels,
            overlaps=overlaps(run.turns),
        ),
    )


def overlaps(turns: Iterable[Turn]) -> tuple[Overlap, ...]:
    """The ranges in which at least two turns run at the same time."""
    # At equal times an end sorts before a start, so touching turns do not overlap.
    events = sorted(
        event
        for turn in turns
        if turn.end_ms > turn.start_ms
        for event in ((turn.start_ms, 1), (turn.end_ms, -1))
    )
    ranges: list[Overlap] = []
    active = 0
    start = 0
    for time, step in events:
        if step > 0 and active == 1:
            start = time
        elif step < 0 and active == 2 and time > start:
            if ranges and ranges[-1].end_ms == start:
                start = ranges.pop().start_ms
            ranges.append(Overlap(start_ms=start, end_ms=time))
        active += step
    return tuple(ranges)


def _start(turn: Turn) -> int:
    return turn.start_ms


def _labelled(passage: Passage, turns: tuple[Turn, ...]) -> Passage:
    words = tuple(
        replace(word, speaker=_word_label(word, turns)) for word in passage.words
    )
    return replace(passage, words=words, speaker=majority_speaker(words))


def _word_label(word: Word, turns: tuple[Turn, ...]) -> str | None:
    """The label at the word's midpoint in sorted, non-overlapping `turns`."""
    if word.start_ms is None or word.end_ms is None:
        return None
    midpoint = (word.start_ms + word.end_ms) / 2
    position = bisect.bisect_right(turns, midpoint, key=_start) - 1
    if position < 0 or midpoint >= turns[position].end_ms:
        return None
    return turns[position].label


def write_run(paths: SessionPaths, index: int, run: DiarizationRun) -> None:
    """Store `run` as the raw diarization of segment `index`, atomically."""
    jsonfile.write_atomic(paths.diarization_raw(index), to_json(run))


def load_run(paths: SessionPaths, index: int) -> DiarizationRun | None:
    """The stored diarization of segment `index`; `None` if absent or outdated.

    A file in another format version counts as absent, so it is recomputed.
    """
    path = paths.diarization_raw(index)
    if not path.exists():
        return None
    data = _read_json(path, "diarization")
    if data.get("format_version") != DIARIZATION_FORMAT_VERSION:
        return None
    try:
        return DiarizationRun(
            info=BackendInfo(
                backend_id=_field(data, "backend_id", str, path),
                model=_field(data, "model", str, path),
                model_version=_optional(data, "model_version", str, path),
                runtime_version=_optional(data, "runtime_version", str, path),
            ),
            audio_sha256=_field(data, "audio_sha256", str, path),
            settings=_field(data, "settings", dict, path),
            num_speakers=_optional(data, "num_speakers", int, path),
            turns=_turns(data, "turns", path),
            exclusive_turns=_turns(data, "exclusive_turns", path),
        )
    except ValueError as error:
        raise DiarizationError(f"{path}: {error}") from None


def to_json(run: DiarizationRun) -> dict[str, Any]:
    return {
        "format_version": DIARIZATION_FORMAT_VERSION,
        **asdict(run.info),
        "settings": dict(run.settings),
        "num_speakers": run.num_speakers,
        "audio_sha256": run.audio_sha256,
        "turns": [asdict(turn) for turn in run.turns],
        "exclusive_turns": [asdict(turn) for turn in run.exclusive_turns],
    }


def _turns(data: dict[str, Any], name: str, path: Path) -> tuple[Turn, ...]:
    return tuple(
        Turn(
            start_ms=_field(entry, "start_ms", int, path),
            end_ms=_field(entry, "end_ms", int, path),
            label=_field(entry, "label", str, path),
        )
        for entry in _field(data, name, list, path)
    )


_field = functools.partial(jsonfile.field, error=DiarizationError)
_optional = functools.partial(jsonfile.optional_field, error=DiarizationError)
_read_json = functools.partial(jsonfile.read_object, error=DiarizationError)
