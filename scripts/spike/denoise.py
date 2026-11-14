"""Denoising spike (TOOL-92): filter segment 1 into a shadow root per candidate.

    denoise.py prepare <group>/<ordinal> <candidate>... [--runs N]
    denoise.py run <group>/<ordinal> <candidate>... [--runs N]
    denoise.py score <group>/<ordinal> <candidate>... [--runs N] [--baseline base]

`prepare` makes `work/<s>/experiments/denoise/<candidate>/` its own `paths.root`:
copies of the manifest, `audio.json` and `narrata/`, a config that differs from
the project config only in `paths.root`, and the filtered `segment-01.wav` with
exactly the frames the manifest expects. With `--runs N`, runs 2..N get their own
roots `<candidate>.run<n>` that link the WAV of the first. `run` calls
`transcript transcribe` for segment 1 in each root, one after the other, never in
parallel; a candidate with ASR settings (e.g. `base-t0`) runs the same CLI with
those settings added to the fixed Whisper settings, where the transcript records
them. `score` prints Markdown tables of counts, shares and times, per run and as
mean and range per candidate.

Privacy (TOOL-66): every file stays under `work/`; the console gets no text, no
names and no speaker labels of people.
"""

import argparse
import bisect
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import permutations
from pathlib import Path

import yaml

from transcript import audio, calibration, diarization, manifest
from transcript.config import DEFAULT_CONFIG, PROJECT_ROOT, load_config
from transcript.hints import stored_hints
from transcript.jsonfile import DataFileError
from transcript.reference import ReferenceTranscript, load_reference
from transcript.session import SessionKey, SessionPaths
from transcript.uncertainty import segment_assessment

SEGMENT = 1
RATE = 16000
CACHE = Path.home() / ".cache" / "narrata-spike" / "denoise"
RNNOISE_MODEL = CACHE / "lq.rnnn"  # leavened-quisling: voice under general noise
DEEP_FILTER = CACHE / "deep-filter"
TRANSCRIPT = PROJECT_ROOT / ".venv" / "bin" / "transcript"
GRID_MS = 100  # time step for comparing two diarizations
NGRAM = 5  # repetition: share of tokens in 5-grams that occur at least 3 times
NGRAM_MIN = 3


@dataclass(frozen=True)
class HandClip:
    name: str
    file: str  # under review/calibration/
    start_ms: int
    end_ms: int


CLIPS = (
    HandClip("A", "reference-1.txt", 0, 246_000),
    HandClip("B", "reference-2.txt", 4_800_000, 4_980_000),
)


@dataclass(frozen=True)
class Chain:
    """`before` and `after` run in ffmpeg at 16 kHz; `rate` is where the denoiser
    runs; `deep_filter` runs DeepFilterNet between two ffmpeg passes."""

    before: str | None = None
    denoise: str | None = None  # an ffmpeg filter at `rate`
    rate: int = RATE
    deep_filter: bool = False

    def describe(self) -> str:
        parts = [self.before, self.denoise and f"{self.denoise}@{self.rate}"]
        if self.deep_filter:
            parts.append(f"deep-filter -D@{self.rate}")
        return ",".join(p for p in parts if p) or "raw"


@dataclass(frozen=True)
class Candidate:
    chain: Chain
    # added to the fixed Whisper settings; empty: the pipeline as it is
    asr: Mapping[str, object] = field(default_factory=dict)


_RNN = f"arnndn=m={RNNOISE_MODEL}"
_HP = "highpass=f=80"
CANDIDATES = {
    "base": Candidate(Chain()),
    # no sampling fallback: shows whether it causes the run-to-run differences
    "base-t0": Candidate(Chain(), {"temperature": 0.0}),
    "hp": Candidate(Chain(before=_HP)),
    "hp-afftdn": Candidate(Chain(before=f"{_HP},afftdn=nf=-25")),
    "arnndn": Candidate(Chain(denoise=_RNN, rate=48000)),
    "hp-arnndn": Candidate(Chain(before=_HP, denoise=_RNN, rate=48000)),
    "dfn": Candidate(Chain(rate=48000, deep_filter=True)),
    "hp-dfn": Candidate(Chain(before=_HP, rate=48000, deep_filter=True)),
}


class SpikeError(Exception):
    pass


# --- prepare ------------------------------------------------------------------------


def shadow_root(paths: SessionPaths, candidate: str, number: int = 1) -> Path:
    name = candidate if number == 1 else f"{candidate}.run{number}"
    return paths.work_dir / "experiments" / "denoise" / name


def prepare(
    paths: SessionPaths, candidate: str, number: int, config_path: Path
) -> None:
    chain = CANDIDATES[candidate].chain
    label = f"{candidate}#{number}"
    root = shadow_root(paths, candidate, number)
    shadow = SessionPaths(paths.key, root)
    shadow.audio_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths.manifest, shadow.manifest)
    shutil.copy2(paths.audio_metadata, shadow.audio_metadata)
    shutil.copytree(
        paths.knowledge_snapshot.parent,
        shadow.knowledge_snapshot.parent,
        dirs_exist_ok=True,
    )
    settings = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    settings.setdefault("paths", {})["root"] = str(root)
    (root / "config.yaml").write_text(
        yaml.safe_dump(settings, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    frames = _manifest_frames(paths)
    source, target = paths.segment_wav(SEGMENT), shadow.segment_wav(SEGMENT)
    record = root / "filter.json"
    if _reusable(record, target, chain, frames):
        print(f"{label}: filtered audio reused")
        return
    target.unlink(missing_ok=True)
    if number > 1:  # a repeat run: the very same input as the first run
        first = shadow_root(paths, candidate)
        if not _reusable(first / "filter.json", _wav(paths, first), chain, frames):
            raise SpikeError(f"{label}: prepare run 1 first")
        os.link(_wav(paths, first), target)
        shutil.copy2(first / "filter.json", record)
        print(f"{label}: audio of run 1 linked")
        return
    started = time.monotonic()
    if chain == Chain():
        os.link(source, target)  # the raw WAV, never written by the pipeline
    else:
        _filter(source, target, chain, frames, root)
    elapsed = time.monotonic() - started
    record.write_text(
        json.dumps(
            {
                "chain": chain.describe(),
                "frames": frames,
                "filter_seconds": round(elapsed, 1),
                "tools": _tool_versions(chain),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"{label}: {chain.describe()} in {elapsed:.0f} s")


def _wav(paths: SessionPaths, root: Path) -> Path:
    return SessionPaths(paths.key, root).segment_wav(SEGMENT)


def _manifest_frames(paths: SessionPaths) -> int:
    for segment in manifest.load_manifest(paths).segments:
        if segment.index == SEGMENT:
            return segment.frames
    raise SpikeError(f"segment {SEGMENT} not in the manifest")


def _reusable(record: Path, target: Path, chain: Chain, frames: int) -> bool:
    if not record.is_file() or not target.is_file():
        return False
    stored = json.loads(record.read_text(encoding="utf-8"))
    return stored.get("chain") == chain.describe() and audio.wav_frames(target) == (
        frames,
        RATE,
    )


def _filter(source: Path, target: Path, chain: Chain, frames: int, root: Path) -> None:
    """Filter into a temporary file, check the length, then move it into place."""
    scratch = root / "tmp"
    scratch.mkdir(exist_ok=True)
    try:
        filters = [chain.before] if chain.before else []
        if chain.rate != RATE:
            filters.append(f"aresample={chain.rate}")
        if chain.denoise:
            filters.append(chain.denoise)
        current = source
        if chain.deep_filter:
            staged = scratch / "deep-in.wav"
            _ffmpeg(current, staged, filters or ["anull"], chain.rate)
            out_dir = scratch / "deep-out"
            out_dir.mkdir(exist_ok=True)
            _call([str(DEEP_FILTER), "-D", "-o", str(out_dir), str(staged)])
            current, filters = out_dir / staged.name, []
        filters += [
            f"aresample={RATE}",
            f"apad=whole_len={frames}",
            f"atrim=end_sample={frames}",
        ]
        pending = scratch / "segment.wav"
        _ffmpeg(current, pending, filters, RATE)
        if audio.wav_frames(pending) != (frames, RATE):
            raise SpikeError("filtered audio does not keep the frame count")
        pending.replace(target)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _ffmpeg(source: Path, target: Path, filters: Sequence[str], rate: int) -> None:
    _call(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            ",".join(filters),
            "-ar",
            str(rate),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-map_metadata",
            "-1",
            str(target),
        ]
    )


def _call(command: Sequence[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise SpikeError(f"{Path(command[0]).name} failed: {' '.join(tail)}")


def _tool_versions(chain: Chain) -> dict[str, str]:
    if chain == Chain():
        return {}
    versions = {"ffmpeg": _version(["ffmpeg", "-version"])}
    if chain.deep_filter:
        versions["deep-filter"] = _version([str(DEEP_FILTER), "--version"])
    return versions


def _version(command: Sequence[str]) -> str:
    out = subprocess.run(command, capture_output=True, text=True, check=False)
    return out.stdout.split("\n", 1)[0].strip()


# --- run ----------------------------------------------------------------------------


def run(paths: SessionPaths, candidate: str, number: int) -> int:
    config = shadow_root(paths, candidate, number) / "config.yaml"
    if not config.is_file():
        raise SpikeError(f"{candidate}#{number}: run prepare first")
    print(f"{candidate}#{number}: transcribe", flush=True)
    asr = CANDIDATES[candidate].asr
    command = (
        [sys.executable, str(Path(__file__).resolve()), _WITH_ASR, json.dumps(asr)]
        if asr
        else [str(TRANSCRIPT)]
    )
    command += ["transcribe", str(paths.key)]
    command += ["--segment", str(SEGMENT), "--config", str(config)]
    return subprocess.run(command, check=False).returncode


_WITH_ASR = "_with-asr"  # internal: the transcript CLI with added Whisper settings


def _cli_with_asr(settings: str, argv: Sequence[str]) -> int:
    from transcript.__main__ import main as cli
    from transcript.asr import whisper

    whisper.FIXED_SETTINGS.update(json.loads(settings))
    return cli(list(argv))


# --- score --------------------------------------------------------------------------


@dataclass(frozen=True)
class Score:
    candidate: str  # `<name>#<run>`
    name: str
    model_version: str | None
    snapshot: str | None
    wer: dict[str, Counter[str]]  # per clip: substitutions, deletions, ...
    words: dict[str, int]  # per clip: reference words
    missed: dict[str, int]  # per clip: errors inside confident passages
    tokens: int
    repetition: float
    distinct: float
    levels: Counter[str]
    flagged_time: float
    labels: int
    unlabelled: float
    wder: float | None
    wder_words: int
    turns: tuple[diarization.Turn, ...]
    filter_seconds: float | None
    asr_ms: int | None
    diarization_ms: int | None


def score(paths: SessionPaths, candidate: str, number: int) -> Score:
    label = f"{candidate}#{number}"
    root = shadow_root(paths, candidate, number)
    shadow = SessionPaths(paths.key, root)
    thresholds = load_config(root / "config.yaml").review_uncertainty
    reference = load_reference(shadow, SEGMENT)
    if reference.status != "transcribed":
        raise SpikeError(f"{label}: segment {SEGMENT} is not transcribed")
    stored = diarization.load_run(shadow, SEGMENT)
    if stored is None or reference.diarization is None:
        raise SpikeError(f"{label}: segment {SEGMENT} is not diarized")
    asr = CANDIDATES[candidate].asr
    if any(reference.asr.settings.get(k) != v for k, v in asr.items()):
        raise SpikeError(f"{label}: transcript lacks the candidate's ASR settings")

    wer: dict[str, Counter[str]] = {}
    words: dict[str, int] = {}
    missed: dict[str, int] = {}
    wder = None
    wder_words = 0
    for clip in CLIPS:
        hand = calibration.read_hand_reference(
            paths.review_dir / "calibration" / clip.file
        )
        report = calibration.measure(
            shadow, SEGMENT, hand, clip.start_ms, clip.end_ms, thresholds
        )
        wer[clip.name], words[clip.name] = report.counts, report.words
        missed[clip.name] = report.by_level["confident"].errors
        if len(set(hand.speakers) - {"S?"}) > 1:
            wder, wder_words = _wder(reference, hand, clip)

    assessment = segment_assessment(
        reference, stored_hints(shadow, SEGMENT), thresholds
    )
    spans = {p.index: _duration(p.start_ms, p.end_ms) for p in reference.passages}
    flagged_ms = sum(
        spans[r.passage] for r in assessment.ratings if r.level != "confident"
    )
    tokens = calibration.tokens(reference.text)
    labelled = [w.speaker for w in reference.words]
    record = root / "filter.json"
    filter_seconds = (
        json.loads(record.read_text(encoding="utf-8")).get("filter_seconds")
        if record.is_file()
        else None
    )
    return Score(
        candidate=label,
        name=candidate,
        model_version=reference.asr.model_version,
        snapshot=reference.asr.knowledge_snapshot_id,
        wer=wer,
        words=words,
        missed=missed,
        tokens=len(tokens),
        repetition=_repetition(tokens),
        distinct=len(set(tokens)) / len(tokens) if tokens else 0.0,
        levels=assessment.counts(),
        flagged_time=flagged_ms / (sum(spans.values()) or 1),
        labels=len(reference.diarization.labels),
        unlabelled=labelled.count(None) / (len(labelled) or 1),
        wder=wder,
        wder_words=wder_words,
        turns=stored.exclusive_turns,
        filter_seconds=filter_seconds,
        asr_ms=reference.processing.elapsed_ms,
        diarization_ms=stored.elapsed_ms,
    )


def _duration(start: int | None, end: int | None) -> int:
    return 0 if start is None or end is None else end - start


def _repetition(tokens: Sequence[str]) -> float:
    grams = [tuple(tokens[i : i + NGRAM]) for i in range(len(tokens) - NGRAM + 1)]
    counts = Counter(grams)
    covered = set()
    for i, gram in enumerate(grams):
        if counts[gram] >= NGRAM_MIN:
            covered.update(range(i, i + NGRAM))
    return len(covered) / len(tokens) if tokens else 0.0


def _wder(
    reference: ReferenceTranscript, hand: calibration.HandReference, clip: HandClip
) -> tuple[float | None, int]:
    """TOOL-20: words recognised exactly, label mapped 1:1 to the hand speakers."""
    texts: list[str] = []
    labels: list[str | None] = []
    for word in reference.words:
        if word.start_ms is None or not clip.start_ms <= word.start_ms < clip.end_ms:
            continue
        for token in calibration.tokens(word.text):
            texts.append(token)
            labels.append(word.speaker)
    pairs: Counter[tuple[str, str]] = Counter()
    matcher = SequenceMatcher(a=hand.tokens, b=texts, autojunk=False)
    for block in matcher.get_matching_blocks():
        for n in range(block.size):
            label = labels[block.b + n]
            if label is not None:
                pairs[(hand.speakers[block.a + n], label)] += 1
    share = _mapped_share(pairs)
    return (None, 0) if share is None else (1 - share, sum(pairs.values()))


def best_mapping(
    counts: Counter[tuple[str, str]], truths: list[str], labels: list[str]
) -> dict[str, str]:
    """One-to-one label -> truth mapping with the most agreeing items (TOOL-20)."""
    best: dict[str, str] = {}
    best_score = -1
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
        value = sum(counts[(truth, label)] for label, truth in mapping.items())
        if value > best_score:
            best, best_score = mapping, value
    return best


def agreement(
    base: Sequence[diarization.Turn], other: Sequence[diarization.Turn], end_ms: int
) -> float | None:
    """Share of the time both label where the labels agree after a 1:1 mapping."""
    pairs: Counter[tuple[str, str]] = Counter()
    base_starts = [turn.start_ms for turn in base]  # exclusive turns are sorted
    other_starts = [turn.start_ms for turn in other]
    for t in range(0, end_ms, GRID_MS):
        a, b = _label_at(base, base_starts, t), _label_at(other, other_starts, t)
        if a is not None and b is not None:
            pairs[(a, b)] += 1
    return _mapped_share(pairs)


def _mapped_share(pairs: Counter[tuple[str, str]]) -> float | None:
    """Share of (truth, label) items that agree under the best 1:1 mapping."""
    total = sum(pairs.values())
    if not total:
        return None
    mapping = best_mapping(
        pairs, sorted({t for t, _ in pairs}), sorted({label for _, label in pairs})
    )
    return sum(pairs[(truth, label)] for label, truth in mapping.items()) / total


def _label_at(
    turns: Sequence[diarization.Turn], starts: Sequence[int], ms: int
) -> str | None:
    n = bisect.bisect_right(starts, ms) - 1
    if n >= 0 and ms < turns[n].end_ms:
        return turns[n].label
    return None


def _errors(score: Score, clip: HandClip) -> int:
    c = score.wer[clip.name]
    return c["substitutions"] + c["deletions"] + c["insertions"]


def print_summary(scores: Sequence[Score]) -> None:
    """Mean and range of the WER per candidate over its runs."""
    print(
        "| Kandidat | Läufe | "
        + " | ".join(
            f"WER {c.name} Mittel (Spanne) | Auslassungen {c.name}" for c in CLIPS
        )
        + " |"
    )
    print("| --- | --- |" + " --- | --- |" * len(CLIPS))
    for name in dict.fromkeys(s.name for s in scores):
        runs = [s for s in scores if s.name == name]
        cells = []
        for clip in CLIPS:
            rates = [_errors(s, clip) / s.words[clip.name] for s in runs]
            deletions = [s.wer[clip.name]["deletions"] for s in runs]
            cells.append(
                f"{_pct(sum(rates) / len(rates))} ({_pct(min(rates))}–"
                f"{_pct(max(rates))}) | {'/'.join(map(str, deletions))}"
            )
        print(f"| {name} | {len(runs)} | " + " | ".join(cells) + " |")
    print()


def print_tables(scores: Sequence[Score], baseline: str, frames: int) -> None:
    hours = frames / RATE / 3600
    if len({(s.model_version, s.snapshot) for s in scores}) > 1:
        raise SpikeError("model revision or knowledge snapshot differ between roots")
    print_summary(scores)
    print("| Kandidat | " + " | ".join(f"WER {c.name} (E/A/Ei)" for c in CLIPS) + " |")
    print("| --- |" + " --- |" * len(CLIPS))
    for s in scores:
        cells = []
        for clip in CLIPS:
            c = s.wer[clip.name]
            cells.append(
                f"{_pct(_errors(s, clip) / s.words[clip.name])} ({c['substitutions']}/"
                f"{c['deletions']}/{c['insertions']})"
            )
        print(f"| {s.candidate} | " + " | ".join(cells) + " |")
    print()
    print(
        "| Kandidat | Wörter | Wiederholung | verschiedene Wörter | confident / "
        "needs_review / uncertain | markierte Zeit | "
        + " | ".join(f"übersehen {c.name}" for c in CLIPS)
        + " |"
    )
    print("| --- |" + " --- |" * (5 + len(CLIPS)))
    for s in scores:
        lv = s.levels
        missed = " | ".join(str(s.missed[c.name]) for c in CLIPS)
        print(
            f"| {s.candidate} | {s.tokens} | {_pct(s.repetition)} | "
            f"{_pct(s.distinct)} | {lv['confident']} / {lv['needs_review']} / "
            f"{lv['uncertain']} | {_pct(s.flagged_time)} | {missed} |"
        )
    print()
    base = next((s for s in scores if s.candidate == f"{baseline}#1"), None)
    print(
        "| Kandidat | Labels | Wörter ohne Label | WDER A (Wörter) | "
        f"Übereinstimmung mit {baseline} |"
    )
    print("| --- | --- | --- | --- | --- |")
    for s in scores:
        agree = (
            None
            if base is None
            else agreement(base.turns, s.turns, frames * 1000 // RATE)
        )
        wder = "n/a" if s.wder is None else _pct(s.wder)
        print(
            f"| {s.candidate} | {s.labels} | {_pct(s.unlabelled)} | "
            f"{wder} ({s.wder_words}) | {'n/a' if agree is None else _pct(agree)} |"
        )
    print()
    print("| Kandidat | Filter (min/h) | ASR (min/h) | Diarisierung (min/h) |")
    print("| --- | --- | --- | --- |")
    for s in scores:
        print(
            f"| {s.candidate} | {_per_hour(s.filter_seconds, hours)} | "
            f"{_per_hour(_seconds(s.asr_ms), hours)} | "
            f"{_per_hour(_seconds(s.diarization_ms), hours)} |"
        )


def _seconds(ms: int | None) -> float | None:
    return None if ms is None else ms / 1000


def _per_hour(seconds: float | None, hours: float) -> str:
    return "n/a" if seconds is None else f"{seconds / 60 / hours:.2f}"


def _pct(value: float) -> str:
    return f"{value:.1%}".replace(".", ",")


# --- main ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == [_WITH_ASR]:
        return _cli_with_asr(argv[1], argv[2:])
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("command", choices=("prepare", "run", "score"))
    parser.add_argument("session", help="session key <group>/<ordinal>")
    parser.add_argument("candidates", nargs="+", choices=sorted(CANDIDATES))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runs", type=int, default=1, help="runs per candidate")
    parser.add_argument("--baseline", default="base")
    args = parser.parse_args(argv)
    jobs = [(c, n) for c in args.candidates for n in range(1, args.runs + 1)]
    try:
        paths = load_config(args.config).session_paths(SessionKey.parse(args.session))
        if args.command == "prepare":
            for candidate, number in jobs:
                prepare(paths, candidate, number, args.config)
            return 0
        if args.command == "run":
            failed = [f"{c}#{n}" for c, n in jobs if run(paths, c, n)]
            if failed:
                print(f"failed: {', '.join(failed)}", file=sys.stderr)
            return 1 if failed else 0
        scores = [score(paths, c, n) for c, n in jobs]
        print_tables(scores, args.baseline, _manifest_frames(paths))
    except (SpikeError, ValueError, OSError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
