"""Score diarization runs and print counts only. TOOL-20 spike, standard library only.

    speakers.py reference <reference.txt> <run.json> <diar.json>... --start <s> --end <s>
    speakers.py stats <diar.json>...
    speakers.py sample <run.json> --out <sample.csv>
    speakers.py score-sample <sample.csv> <diar.json>...

`reference` scores against a hand reference with a speaker label per line (see
compare.py). The reference has no times, so its words are aligned to the ASR words of
`run.json` and take their times; only exactly matched words are scored.
`sample` draws one ASR segment per window for listening; the CSV holds times only.
After `person` (and `nsc`, `mixed`) are filled in, `score-sample` scores it.

Privacy: no text and no names reach the console. Reference labels print as S1, S2, ...
and sample entries as SL or P<n> when written that way, otherwise as Person <n>.
"""

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from itertools import pairwise, permutations
from pathlib import Path
from statistics import median

from compare import in_range, speech_only, tokens

_SPEAKER = re.compile(r"^\s*([^\s:]+):(.*)$")
_CODE = re.compile(r"^(SL|P\d{1,2})$")


# --- shared -------------------------------------------------------------------------


def load_diar(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assignment_turns(diar: dict) -> list[dict]:
    """Turns for assigning one speaker per point in time: exclusive if available."""
    return sorted(
        diar.get("exclusive_turns") or diar["turns"], key=lambda t: t["start"]
    )


def label_at(turns: list[dict], time: float) -> str | None:
    for turn in turns:
        if turn["start"] <= time < turn["end"]:
            return turn["label"]
    return None


def label_seconds(turns: list[dict], start: float, end: float) -> Counter[str]:
    """Seconds per label inside the range."""
    seconds: Counter[str] = Counter()
    for turn in turns:
        covered = min(end, turn["end"]) - max(start, turn["start"])
        if covered > 0:
            seconds[turn["label"]] += covered
    return seconds


def dominant_label(turns: list[dict], start: float, end: float) -> str | None:
    seconds = label_seconds(turns, start, end)
    return seconds.most_common(1)[0][0] if seconds else None


def coverage(turns: list[dict], start: float, end: float) -> tuple[float, float]:
    """Seconds with at least one and with at least two active turns in the range."""
    events = []
    for turn in turns:
        lo, hi = max(start, turn["start"]), min(end, turn["end"])
        if hi > lo:
            events += [(lo, 1), (hi, -1)]
    speech = overlap = 0.0
    active, last = 0, start
    for time, step in sorted(events):
        if active >= 1:
            speech += time - last
        if active >= 2:
            overlap += time - last
        active, last = active + step, time
    return speech, overlap


def best_mapping(counts: Counter, truths: list, labels: list) -> dict:
    """One-to-one label -> truth mapping with the most agreeing items."""
    best, best_score = {}, -1
    if len(labels) >= len(truths):
        options = (
            dict(zip(chosen, truths, strict=True))
            for chosen in permutations(labels, len(truths))
        )
    else:
        options = (
            dict(zip(labels, chosen, strict=True))
            for chosen in permutations(truths, len(labels))
        )
    for mapping in options:
        score = sum(counts[(truth, label)] for label, truth in mapping.items())
        if score > best_score:
            best, best_score = mapping, score
    return best


def pct(part: float, whole: float) -> str:
    return f"{part / whole:.1%}" if whole else "n/a"


# --- reference ----------------------------------------------------------------------


def reference_words(text: str) -> list[tuple[str, int | None]]:
    """Reference tokens with a speaker index; S1 is the first label in the file."""
    speakers: dict[str, int] = {}
    current, words = None, []
    for line in text.splitlines():
        if match := _SPEAKER.match(line):
            current = speakers.setdefault(match[1], len(speakers))
            line = match[2]
        words += [(token, current) for token in tokens(speech_only(line))]
    return words


def run_words(path: Path, start: float, end: float) -> list[tuple[str, float, float]]:
    """ASR tokens that start in the range, each with the times of its word."""
    run = json.loads(path.read_text(encoding="utf-8"))
    kept = []
    for segment in run["segments"]:
        for word in segment.get("words", []):
            if in_range(word["start"], start, end):
                kept += [(t, word["start"], word["end"]) for t in tokens(word["word"])]
    return kept


def timed_reference(
    reference: list[tuple[str, int | None]], hypothesis: list[tuple[str, float, float]]
) -> list[tuple[int, float, float]]:
    """(speaker, start, end) for every reference word matched exactly in the ASR run."""
    matcher = SequenceMatcher(
        a=[w for w, _ in reference], b=[w for w, _, _ in hypothesis], autojunk=False
    )
    timed = []
    for ref_at, hyp_at, size in matcher.get_matching_blocks():
        for offset in range(size):
            speaker = reference[ref_at + offset][1]
            if speaker is not None:
                _, start, end = hypothesis[hyp_at + offset]
                timed.append((speaker, start, end))
    return timed


def change_times(items: list[tuple]) -> list[float]:
    """Times between consecutive (key, start, end) items whose key differs."""
    return [
        (prev[2] + nxt[1]) / 2 for prev, nxt in pairwise(items) if prev[0] != nxt[0]
    ]


def score_reference(
    timed: list[tuple[int, float, float]],
    diar: dict,
    start: float,
    end: float,
    tolerance: float,
) -> str:
    turns = assignment_turns(diar)
    in_range = [t for t in turns if t["end"] > start and t["start"] < end]
    labelled = [(label_at(in_range, (s + e) / 2), speaker) for speaker, s, e in timed]
    assigned = [(label, speaker) for label, speaker in labelled if label is not None]
    counts = Counter((speaker, label) for label, speaker in assigned)
    truths = sorted({speaker for _, speaker in assigned})
    labels = sorted({label for label, _ in assigned})
    mapping = best_mapping(counts, truths, labels)
    wrong = sum(mapping.get(label) != speaker for label, speaker in assigned)

    truth_changes = change_times(timed)
    diar_changes = [
        t
        for t in change_times([(x["label"], x["start"], x["end"]) for x in in_range])
        if start <= t < end
    ]
    found = sum(
        any(abs(t - d) <= tolerance for d in diar_changes) for t in truth_changes
    )
    spurious = sum(
        not any(abs(d - t) <= tolerance for t in truth_changes) for d in diar_changes
    )
    _, overlap = coverage(diar["turns"], start, end)
    return (
        f"labels {len({t['label'] for t in in_range})}, "
        f"WDER {pct(wrong, len(assigned))}, "
        f"unassigned {pct(len(labelled) - len(assigned), len(labelled))}, "
        f"changes found {found}/{len(truth_changes)}, spurious {spurious}, "
        f"overlap {pct(overlap, end - start)}"
    )


def cmd_reference(args: argparse.Namespace) -> None:
    reference = reference_words(args.reference.read_text(encoding="utf-8-sig"))
    hypothesis = run_words(args.run, args.start, args.end)
    timed = timed_reference(reference, hypothesis)
    speakers = len({speaker for _, speaker in reference if speaker is not None})
    print(
        f"reference: {len(reference)} words, {speakers} speakers (S1-S{speakers}), "
        f"{len(timed)} matched to ASR times"
    )
    for path in args.diar:
        result = score_reference(
            timed, load_diar(path), args.start, args.end, args.tolerance
        )
        print(f"{path.parent.name}: {result}")


# --- stats --------------------------------------------------------------------------


def cmd_stats(args: argparse.Namespace) -> None:
    for path in args.diar:
        diar = load_diar(path)
        audio = diar["meta"]["audio_seconds"]
        talk: Counter[str] = Counter()
        for turn in diar["turns"]:
            talk[turn["label"]] += turn["end"] - turn["start"]
        total = sum(talk.values())
        shares = [seconds / total for _, seconds in talk.most_common()]
        speech, overlap = coverage(diar["turns"], 0, audio)
        turns = assignment_turns(diar)
        per_window = [
            sum(
                s >= args.min_seconds
                for s in label_seconds(turns, lo, lo + args.window).values()
            )
            for lo in range(0, int(audio), args.window)
        ]
        print(
            f"{path.parent.name}: labels {len(talk)} "
            f"(under 1 %: {sum(s < 0.01 for s in shares)}), "
            f"shares {'/'.join(f'{s:.0%}' for s in shares)}, "
            f"turns {len(turns)}, median turn "
            f"{median(t['end'] - t['start'] for t in turns):.1f} s, "
            f"speech {pct(speech, audio)} of audio, overlap {pct(overlap, speech)} "
            f"of speech, labels per {args.window // 60} min "
            f"{'/'.join(map(str, per_window))}"
        )


# --- sample -------------------------------------------------------------------------


def clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600}:{whole // 60 % 60:02d}:{whole % 60:02d}"


def cmd_sample(args: argparse.Namespace) -> None:
    if args.out.exists():
        raise SystemExit(f"{args.out.name} exists, refusing to overwrite a sample")
    run = json.loads(args.run.read_text(encoding="utf-8"))
    segments = [
        (s["start"], s["end"])
        for s in run["segments"]
        if args.min_length <= s["end"] - s["start"] <= args.max_length
    ]
    rng = random.Random(args.seed)
    rows, empty = [], 0
    last = max(end for _, end in segments)
    for lo in range(0, int(last) + 1, args.window):
        options = [s for s in segments if lo <= s[0] < lo + args.window]
        if not options:
            empty += 1
            continue
        start, end = rng.choice(options)
        rows.append(
            {
                "id": len(rows) + 1,
                "start": f"{start:.2f}",
                "end": f"{end:.2f}",
                "at": clock(start),
                "person": "",
                "nsc": "",
                "mixed": "",
                "note": "",
            }
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{args.out.name}: {len(rows)} segments, {empty} windows without a candidate")


def flag(value: str) -> bool:
    return value.strip().casefold() not in ("", "0", "no", "nein", "n", "-")


def read_sample(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    return list(csv.DictReader(text.splitlines(), dialect=dialect))


def cmd_score_sample(args: argparse.Namespace) -> None:
    rows = read_sample(args.sample)
    filled = [r for r in rows if r["person"].strip()]
    clean = [r for r in filled if not flag(r.get("mixed", ""))]
    names: dict[str, str] = {}
    uncoded = 0
    for row in clean:
        code = row["person"].strip()
        if code in names:
            continue
        if _CODE.match(code.upper()):
            names[code] = code.upper()
        else:
            uncoded += 1
            names[code] = f"Person {uncoded}"
    print(
        f"sample: {len(rows)} rows, {len(filled)} filled, "
        f"{len(filled) - len(clean)} mixed (excluded), {len(names)} people, "
        f"{sum(flag(r.get('nsc', '')) for r in clean)} NSC"
    )
    for path in args.diar:
        turns = assignment_turns(load_diar(path))
        scored = [
            (
                dominant_label(turns, float(r["start"]), float(r["end"])),
                names[r["person"].strip()],
                flag(r.get("nsc", "")),
            )
            for r in clean
        ]
        votes: dict[str, Counter] = defaultdict(Counter)
        per_person: dict[str, set] = defaultdict(set)
        rows_per_person: Counter[str] = Counter()
        # An NSC voice is split off when its label never carries the same person's
        # own voice in the sample.
        own_voice: dict[str, set] = defaultdict(set)
        for label, person, is_nsc in scored:
            rows_per_person[person] += 1
            if not is_nsc:
                own_voice[person].add(label)
            if label is not None:
                votes[label][person] += 1
                per_person[person].add(label)
        owner = {label: c.most_common(1)[0][0] for label, c in votes.items()}
        wrong = sum(
            label is None or owner[label] != person for label, person, _ in scored
        )
        nsc = [(label, person) for label, person, is_nsc in scored if is_nsc]
        nsc_split = sum(
            label is None or label not in own_voice[person] for label, person in nsc
        )
        people = ", ".join(
            f"{person} {rows_per_person[person]} rows/{len(per_person[person])} labels"
            for person in sorted(rows_per_person)
        )
        print(
            f"{path.parent.name}: misassigned {wrong}/{len(scored)} "
            f"({pct(wrong, len(scored))}), unassigned "
            f"{sum(label is None for label, _, _ in scored)}, labels used {len(owner)}; "
            f"{people}; NSC split off {nsc_split}/{len(nsc)}"
        )


# --- main ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    reference = commands.add_parser("reference")
    reference.add_argument("reference", type=Path)
    reference.add_argument("run", type=Path, help="ASR run.json with word times")
    reference.add_argument("diar", type=Path, nargs="+")
    reference.add_argument("--start", type=float, required=True)
    reference.add_argument("--end", type=float, required=True)
    reference.add_argument("--tolerance", type=float, default=0.5)
    reference.set_defaults(func=cmd_reference)

    stats = commands.add_parser("stats")
    stats.add_argument("diar", type=Path, nargs="+")
    stats.add_argument("--window", type=int, default=3600)
    stats.add_argument("--min-seconds", type=float, default=30)
    stats.set_defaults(func=cmd_stats)

    sample = commands.add_parser("sample")
    sample.add_argument("run", type=Path, help="ASR run.json over the full recording")
    sample.add_argument("--out", type=Path, required=True)
    sample.add_argument("--window", type=int, default=600)
    sample.add_argument("--min-length", type=float, default=2)
    sample.add_argument("--max-length", type=float, default=10)
    sample.add_argument("--seed", type=int, default=20)
    sample.set_defaults(func=cmd_sample)

    score = commands.add_parser("score-sample")
    score.add_argument("sample", type=Path)
    score.add_argument("diar", type=Path, nargs="+")
    score.set_defaults(func=cmd_score_sample)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
