"""GM spike (TOOL-106): are the passages of two GMs separable by label?

    gms.py <group>/<ordinal> [--clip NAME=FILE@H:MM:SS-H:MM:SS]... [--config PATH]

Reads the session's transcribed and diarized segments, the speaker assignment
(`speakers.check`) and the knowledge snapshot. Each passage speaks as the person
its label is assigned to, as the export shows it. Over the session it counts
per GM the labels, passages and passage time. Per clip (default: the pilot
clips A and B in segment 1) it aligns the hand reference with the words of the
segment, keeps the words recognised exactly (`denoise.clip_pairs`), maps the
hand speakers 1:1 to the persons with the most agreeing words
(`denoise.best_mapping`) and counts, for each hand speaker mapped to a GM,
under whom their words stand: the same GM, the other GM, a player or no person.

Privacy (TOOL-66): the console gets counts and shares only. The GMs are `GM 1`
and `GM 2`, ordered by passage time; no names, ids, labels, text or times of
the clips.
"""

import argparse
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import asr
import denoise
from denoise import CLIPS, HandClip, SpikeError, _duration
from turns import _first, _share, load

from transcript import calibration, speakers
from transcript.config import DEFAULT_CONFIG, load_config
from transcript.jsonfile import DataFileError
from transcript.knowledge import load_snapshot
from transcript.reference import ReferenceTranscript
from transcript.session import SessionKey
from transcript.speakers import SpeakerMap, SpeakerRef

PLAYER = "player"
NOBODY = "no person"
RELATIONS = ("same GM", "other GM", PLAYER, NOBODY)


def _key(ref: SpeakerRef) -> str:
    """One key per person, else the assignment state; never shown."""
    return f"p{ref.user_id}" if ref.user_id is not None else ref.assigned


@dataclass(frozen=True)
class People:
    """The group the report shows for a key: `GM 1`, `GM 2`, player or no person."""

    gms: Mapping[str, str]  # person key -> `GM 1` / `GM 2`

    def group(self, key: str) -> str:
        if key in self.gms:
            return self.gms[key]
        return PLAYER if key.startswith("p") else NOBODY


@dataclass
class Tally:
    labels: int = 0
    passages: int = 0
    ms: int = 0


def passage_time(
    map_: SpeakerMap, references: Sequence[ReferenceTranscript]
) -> tuple[Counter[str], Counter[str]]:
    """Passages and passage time per key, over every segment."""
    passages: Counter[str] = Counter()
    time: Counter[str] = Counter()
    for reference in references:
        for passage in reference.passages:
            key = _key(map_.resolve(reference.segment.index, passage.speaker))
            passages[key] += 1
            time[key] += _duration(passage.start_ms, passage.end_ms)
    return passages, time


def people(time: Counter[str], gm_ids: set[object]) -> People:
    """The GMs named `GM 1` and `GM 2` by passage time, most first."""
    ranked = sorted((f"p{user_id}" for user_id in gm_ids), key=lambda k: -time[k])
    return People({key: f"GM {n}" for n, key in enumerate(ranked, start=1)})


def session_tally(
    map_: SpeakerMap, passages: Counter[str], time: Counter[str], who: People
) -> dict[str, Tally]:
    tally = {group: Tally() for group in (*who.gms.values(), PLAYER, NOBODY)}
    for segment, label in map_.labels:
        tally[who.group(_key(map_.resolve(segment, label)))].labels += 1
    for key, n in passages.items():
        found = tally[who.group(key)]
        found.passages += n
        found.ms += time[key]
    return tally


def clip_counts(
    reference: ReferenceTranscript,
    hand: calibration.HandReference,
    clip: HandClip,
    map_: SpeakerMap,
    who: People,
) -> dict[str, Counter[str]]:
    """Per GM a hand speaker is mapped to: their exact words per relation."""
    segment = reference.segment.index
    pairs = Counter(
        {
            (speaker, key): n
            for (speaker, key), n in denoise.clip_pairs(
                reference,
                hand,
                clip,
                lambda word, passage: _key(map_.resolve(segment, passage.speaker)),
            ).items()
            if speaker != "S?"  # before any speaker line of the hand reference
        }
    )
    persons = sorted({key for _, key in pairs if key.startswith("p")})
    truths = sorted({speaker for speaker, _ in pairs})
    mapping = denoise.best_mapping(pairs, truths, persons)  # person key -> speaker
    found: dict[str, Counter[str]] = {}
    for key, speaker in mapping.items():
        gm = who.gms.get(key)
        if gm is None:
            continue
        counts = found.setdefault(gm, Counter())
        for (truth, other), n in pairs.items():
            if truth == speaker:
                counts[_relation(gm, who.group(other))] += n
    return found


def _relation(gm: str, group: str) -> str:
    if group == gm:
        return "same GM"
    return "other GM" if group.startswith("GM") else group


def _clock(ms: int) -> str:
    minutes = ms // 60_000
    return f"{minutes // 60}:{minutes % 60:02d}"


def print_tables(
    tally: Mapping[str, Tally],
    clips: Mapping[str, dict[str, Counter[str]]],
    findings: int,
) -> None:
    passages = sum(t.passages for t in tally.values())
    print("## Session, as the export shows it\n")
    print("| speaker | labels | passages | share | passage time (h:mm) |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for group, found in tally.items():
        print(
            f"| {group} | {found.labels} | {found.passages} "
            f"| {_share(found.passages, passages)} | {_clock(found.ms)} |"
        )
    print(f"\nassignment entries not applied: {findings}\n")
    print("## Words of each GM in the hand references\n")
    print("| clip | GM | words | " + " | ".join(RELATIONS) + " |")
    print("| --- | --- | ---: |" + " ---: |" * len(RELATIONS))
    total: dict[str, Counter[str]] = {}
    for name, per_gm in clips.items():
        if not per_gm:
            print(f"| {name} | none mapped | 0 |" + " – |" * len(RELATIONS))
        for gm, counts in sorted(per_gm.items()):
            total.setdefault(gm, Counter()).update(counts)
            print(_clip_row(name, gm, counts))
    for gm, counts in sorted(total.items()):
        print(_clip_row("all", gm, counts))


def _clip_row(name: str, gm: str, counts: Counter[str]) -> str:
    words = sum(counts.values())
    shares = " | ".join(_share(counts[r], words) for r in RELATIONS)
    return f"| {name} | {gm} | {words} | {shares} |"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("session", help="session key <group>/<ordinal>")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--clip",
        action="append",
        type=asr.parse_clip,
        help="NAME=FILE@H:MM:SS-H:MM:SS in segment 1 (default: pilot clips A and B)",
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        paths = config.session_paths(SessionKey.parse(args.session))
        references = load(paths)
        participants = load_snapshot(paths).participants
        gm_ids = {p.user_id for p in participants if p.role == "gm"}
        if len(gm_ids) < 2:
            raise SpikeError("the snapshot names fewer than two GMs")
        assignment = speakers.load_assignment(paths)
        if assignment is None:
            raise SpikeError("no speaker assignment; run `transcript speakers`")
        map_ = speakers.check(assignment, references, participants)
        passages, time = passage_time(map_, references)
        who = people(time, gm_ids)
        first = _first(references)
        clips = {
            clip.name: clip_counts(
                first,
                calibration.read_hand_reference(
                    paths.review_dir / "calibration" / clip.file
                ),
                clip,
                map_,
                who,
            )
            for clip in args.clip or CLIPS
        }
        tally = session_tally(map_, passages, time, who)
        print_tables(tally, clips, len(map_.findings))
    except (SpikeError, ValueError, OSError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
