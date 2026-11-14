"""ASR quality spike (TOOL-93): Whisper variants on segment 1, one root per seed.

    asr.py prepare <group>/<ordinal> <variant>... [--seeds N]
    asr.py run <group>/<ordinal> <variant>... [--seeds N] [--diarize]
    asr.py score <group>/<ordinal> <variant>... [--seeds N] [--clip ...]
    asr.py windows <group>/<ordinal> <variant> [--seed N]

A variant is a hotword base (`base`, `pchw`, `nohw`, `nohw-hp`) followed by
modifiers joined with `+`, e.g. `nohw+vad-t35+beam10`. `prepare` makes
`work/<s>/experiments/asr/<variant>.seed<n>/` its own `paths.root`, as
`denoise.py` does: copies of manifest, `audio.json` and `narrata/`, a config with
`paths.root` and `asr.model`, and a hard link to the raw or filtered WAV. `pchw`
sets every glossary budget to 0 and builds the snapshot of its root again, so only
`pc` entries become hotwords. `run` transcribes each root one after the other with
a fixed CTranslate2 seed, the variant's hotword switch and Whisper settings, all
recorded in `asr.settings`; it skips the diarization unless `--diarize` is given
and writes peak RAM and VRAM to `<root>/run.json`. `score` prints Markdown tables
per seed and as mean and range per variant. `windows` proposes calm 3-minute
windows for a new hand reference from counts only.

Privacy (TOOL-66): every file stays under `work/`; the console gets no text, no
names and no speaker labels of people.
"""

import argparse
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import denoise
import yaml
from denoise import RATE, SEGMENT, Chain, SpikeError, _pct, _per_hour, _seconds

from transcript import calibration, diarization, knowledge
from transcript.config import DEFAULT_CONFIG, DEFAULT_KEYWORD_BUDGET, load_config
from transcript.hints import stored_hints
from transcript.jsonfile import DataFileError
from transcript.reference import load_reference
from transcript.session import SessionKey, SessionPaths
from transcript.timecode import format_clock
from transcript.uncertainty import segment_assessment

TURBO = "large-v3-turbo"
WINDOW_MS = 180_000  # length of a proposed hand-reference window
WINDOW_STEP_MS = 60_000
WINDOW_PROPOSALS = 3
VRAM_POLL_S = 1.0


@dataclass(frozen=True)
class Variant:
    model: str = TURBO
    hotwords: bool = True
    pc_only: bool = False  # hotwords from `pc` entries only (budget 0 per type)
    chain: Chain = field(default_factory=Chain)
    # added to the fixed Whisper settings; a dict value merges with the base's
    asr: Mapping[str, object] = field(default_factory=dict)
    # `asr.*` keys of the root's config, for what the backend takes from there
    config: Mapping[str, object] = field(default_factory=dict)


BASES = {
    "base": Variant(),
    "pchw": Variant(pc_only=True),
    "nohw": Variant(hotwords=False),
    "nohw-hp": Variant(hotwords=False, chain=Chain(before=denoise._HP)),
}
# one factor each; stage 3 adds models
MODIFIERS: dict[str, Mapping[str, object]] = {
    "novad": {"vad_filter": False},
    "vad-t35": {"vad_parameters": {"threshold": 0.35}},
    "vad-pad800": {"vad_parameters": {"speech_pad_ms": 800}},
    "vad-sil500": {"vad_parameters": {"min_silence_duration_ms": 500}},
    "beam10": {"beam_size": 10},
    "nospeech-off": {"no_speech_threshold": None},
    "logprob-lax": {"log_prob_threshold": -1.5},
    "cond-prev": {"condition_on_previous_text": True},
    # changes nothing but the root: checks that a seed reproduces a run
    "twin": {},
}
MODELS = frozenset({"large-v3"})
# the backend passes these itself, so they go into the config, not FIXED_SETTINGS
CONFIG_KEYS = frozenset({"beam_size"})


def variant(name: str) -> Variant:
    """`<base>[+<modifier>…]`; each modifier at most once, at most one model."""
    head, *mods = name.split("+")
    if head not in BASES:
        raise SpikeError(f"{name}: unknown base {head!r}, one of {sorted(BASES)}")
    if len(set(mods)) != len(mods):
        raise SpikeError(f"{name}: a modifier repeats")
    base = BASES[head]
    asr: dict[str, object] = {}
    config: dict[str, object] = {}
    model = base.model
    for mod in mods:
        if mod in MODELS:
            if model != base.model:
                raise SpikeError(f"{name}: more than one model")
            model = mod
        elif mod in MODIFIERS:
            for key, value in MODIFIERS[mod].items():
                if key in CONFIG_KEYS:
                    config[key] = value
            asr = merge(
                asr, {k: v for k, v in MODIFIERS[mod].items() if k not in CONFIG_KEYS}
            )
        else:
            known = sorted([*MODIFIERS, *MODELS])
            raise SpikeError(f"{name}: unknown modifier {mod!r}, one of {known}")
    return dataclasses.replace(base, model=model, asr=asr, config=config)


def merge(base: Mapping[str, object], extra: Mapping[str, object]) -> dict[str, object]:
    """`base` with `extra` on top; a dict value merges with the dict it replaces."""
    merged = dict(base)
    for key, value in extra.items():
        old = merged.get(key)
        if isinstance(value, Mapping) and isinstance(old, Mapping):
            value = {**old, **value}
        merged[key] = value
    return merged


def _variant_arg(name: str) -> str:
    try:
        variant(name)
    except SpikeError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return name


# --- prepare ------------------------------------------------------------------------


def shadow_root(paths: SessionPaths, name: str, seed: int) -> Path:
    return paths.work_dir / "experiments" / "asr" / f"{name}.seed{seed}"


def prepare(paths: SessionPaths, name: str, seed: int, config_path: Path) -> None:
    spec = variant(name)
    label = f"{name}#{seed}"
    root = shadow_root(paths, name, seed)
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
    settings.setdefault("asr", {}).update(model=spec.model, **spec.config)
    budget = dict.fromkeys(DEFAULT_KEYWORD_BUDGET, 0)  # every type, for pchw
    if spec.pc_only:
        settings.setdefault("knowledge", {})["keyword_budget"] = budget
    (root / "config.yaml").write_text(
        yaml.safe_dump(settings, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    if spec.pc_only:
        snapshot = knowledge.load_snapshot(shadow)
        if dict(snapshot.keyword_budget) != dict(budget):
            snapshot = knowledge.build_snapshot(shadow, budget)
        pc = sum(e.relevance == "pc" for e in snapshot.keyword_entries)
        print(
            f"{label}: snapshot with {len(snapshot.keyword_entries)} keyword "
            f"entries ({pc} pc)"
        )
    _link_audio(paths, shadow, spec.chain, label)


def _link_audio(
    paths: SessionPaths, shadow: SessionPaths, chain: Chain, label: str
) -> None:
    """The raw WAV, or one filtered copy per chain that every root links."""
    target = shadow.segment_wav(SEGMENT)
    frames = denoise._manifest_frames(paths)
    if chain == Chain():
        source = paths.segment_wav(SEGMENT)
    else:
        store = paths.work_dir / "experiments" / "asr" / "audio" / chain.describe()
        source = store / "segment.wav"
        record = store / "filter.json"
        if not denoise._reusable(record, source, chain, frames):
            store.mkdir(parents=True, exist_ok=True)
            started = time.monotonic()
            denoise._filter(paths.segment_wav(SEGMENT), source, chain, frames, store)
            elapsed = time.monotonic() - started
            record.write_text(
                json.dumps(
                    {
                        "chain": chain.describe(),
                        "frames": frames,
                        "filter_seconds": round(elapsed, 1),
                        "tools": denoise._tool_versions(chain),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"{label}: {chain.describe()} in {elapsed:.0f} s")
        shutil.copy2(record, shadow.root / "filter.json")
    if target.is_file() and os.path.samefile(source, target):
        return
    target.unlink(missing_ok=True)
    os.link(source, target)  # never written by the pipeline


# --- run ----------------------------------------------------------------------------


_WITH_VARIANT = "_with-variant"  # internal: the transcript CLI with a variant


def run(paths: SessionPaths, name: str, seed: int, diarize: bool) -> int:
    root = shadow_root(paths, name, seed)
    config = root / "config.yaml"
    if not config.is_file():
        raise SpikeError(f"{name}#{seed}: run prepare first")
    spec = variant(name)
    print(f"{name}#{seed}: transcribe", flush=True)
    options = {"seed": seed, "hotwords": spec.hotwords, "asr": dict(spec.asr)}
    command = [sys.executable, str(Path(__file__).resolve()), _WITH_VARIANT]
    command += [json.dumps(options), "transcribe", str(paths.key)]
    command += ["--segment", str(SEGMENT), "--config", str(config)]
    if not diarize:
        command.append("--no-diarize")
    reference = SessionPaths(paths.key, root).reference(SEGMENT)
    before = _mtime(reference)
    vram = _VramPoll()
    started = time.monotonic()
    process = subprocess.Popen(command)
    vram.start()
    _, status, usage = os.wait4(process.pid, 0)  # rusage of this child alone
    code = os.waitstatus_to_exitcode(status)
    vram.stop()
    elapsed = time.monotonic() - started
    if code == 0 and _mtime(reference) != before:
        # a reused transcript keeps the measurements of the run that made it
        record = root / "run.json"
        runs = _read_json(record)
        runs["diarize" if diarize else "asr"] = {
            "wall_seconds": round(elapsed, 1),
            "peak_ram_mib": round(usage.ru_maxrss / 1024),  # ru_maxrss is KiB
            "peak_vram_mib": vram.peak,
            "idle_vram_mib": vram.idle,
        }
        record.write_text(json.dumps(runs, indent=2), encoding="utf-8")
    return code


def _mtime(path: Path) -> int | None:
    return path.stat().st_mtime_ns if path.is_file() else None


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


class _VramPoll:
    """Peak GPU memory in use (MiB) during a run, polled from nvidia-smi.

    Counts the whole GPU, since WSL gives no per-process numbers; `idle` is the
    reading before the run started.
    """

    def __init__(self) -> None:
        self.idle = _vram_used()
        self.peak = self.idle
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._poll, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._done.set()
        self._thread.join()

    def _poll(self) -> None:
        while not self._done.wait(VRAM_POLL_S):
            used = _vram_used()
            if used is not None and (self.peak is None or used > self.peak):
                self.peak = used


def _vram_used() -> int | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return sum(int(line) for line in out.split() if line.strip().isdigit()) or None


def _cli_with_variant(options: str, argv: Sequence[str]) -> int:
    """The transcript CLI with a seed, a hotword switch and added Whisper settings.

    `seed` and `hotwords` go into `asr.settings`, so resume tells the runs apart;
    only the Whisper settings reach `transcribe`.
    """
    import ctranslate2

    from transcript.__main__ import main as cli
    from transcript.asr import whisper
    from transcript.asr.backend import BackendIdentity

    spec = json.loads(options)
    seed = spec["seed"]
    whisper.FIXED_SETTINGS.update(merge(whisper.FIXED_SETTINGS, spec["asr"]))
    if not spec["hotwords"]:
        whisper.takes_hotwords = lambda model: False
    extra = {"seed": seed, "hotwords": spec["hotwords"]}

    backend = whisper.WhisperBackend
    original_prepare, original_transcribe = backend._prepare, backend.transcribe

    def prepare(self):
        runtime, model_path, identity = original_prepare(self)
        settings = {**identity.settings, **extra}
        return runtime, model_path, BackendIdentity(identity.info, settings)

    def transcribe(self, request):
        ctranslate2.set_random_seed(seed)
        return original_transcribe(self, request)

    backend._prepare = prepare
    backend.transcribe = transcribe
    return cli(list(argv))


# --- score --------------------------------------------------------------------------


@dataclass(frozen=True)
class Score:
    root: str  # `<variant>#<seed>`
    name: str
    model: str
    model_version: str | None
    snapshot: str | None
    keywords: int
    wer: dict[str, Counter[str]]  # per clip: substitutions, deletions, ...
    words: dict[str, int]  # per clip: reference words
    missed: dict[str, int]  # per clip: errors inside confident passages
    wder: dict[str, tuple[float | None, int]]  # per clip with several speakers
    tokens: int
    repetition: float
    distinct: float
    levels: Counter[str]
    flagged_time: float
    labels: int | None
    unlabelled: float | None
    turns: tuple[diarization.Turn, ...]
    asr_ms: int | None
    diarization_ms: int | None
    measured: Mapping[str, Mapping[str, float | None]]  # run.json


def parse_clip(text: str) -> denoise.HandClip:
    """`NAME=FILE@H:MM:SS-H:MM:SS`, FILE under review/calibration/."""
    try:
        name, rest = text.split("=", 1)
        file, span = rest.rsplit("@", 1)
        start, end = (_ms(part) for part in span.split("-"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"{text!r}: expected NAME=FILE@H:MM:SS-H:MM:SS"
        ) from error
    if not name or not file or end <= start:
        raise argparse.ArgumentTypeError(f"{text!r}: empty name, file or span")
    return denoise.HandClip(name, file, start, end)


def _ms(clock: str) -> int:
    h, m, s = clock.split(":")
    return (int(h) * 3600 + int(m) * 60) * 1000 + round(float(s) * 1000)


def score(
    paths: SessionPaths, name: str, seed: int, clips: Sequence[denoise.HandClip]
) -> Score:
    label = f"{name}#{seed}"
    root = shadow_root(paths, name, seed)
    shadow = SessionPaths(paths.key, root)
    thresholds = load_config(root / "config.yaml").review_uncertainty
    reference = load_reference(shadow, SEGMENT)
    if reference.status != "transcribed":
        raise SpikeError(f"{label}: segment {SEGMENT} is not transcribed")
    spec = variant(name)
    settings = reference.asr.settings
    wanted = {
        "seed": seed,
        "hotwords": spec.hotwords,
        "model": spec.model,
        **spec.config,
    }
    if any(settings.get(k) != v for k, v in wanted.items()):
        raise SpikeError(f"{label}: transcript lacks the variant's seed or model")
    for key, value in spec.asr.items():
        stored = settings.get(key)
        if isinstance(value, Mapping):
            stored = {k: (stored or {}).get(k) for k in value}
        if stored != value:
            raise SpikeError(f"{label}: transcript lacks the variant's {key}")
    stored_run = diarization.load_run(shadow, SEGMENT)

    wer: dict[str, Counter[str]] = {}
    words: dict[str, int] = {}
    missed: dict[str, int] = {}
    wder: dict[str, tuple[float | None, int]] = {}
    for clip in clips:
        hand = calibration.read_hand_reference(
            paths.review_dir / "calibration" / clip.file
        )
        report = calibration.measure(
            shadow, SEGMENT, hand, clip.start_ms, clip.end_ms, thresholds
        )
        wer[clip.name], words[clip.name] = report.counts, report.words
        missed[clip.name] = report.by_level["confident"].errors
        if reference.diarization is not None and len(set(hand.speakers) - {"S?"}) > 1:
            wder[clip.name] = denoise._wder(reference, hand, clip)

    assessment = segment_assessment(
        reference, stored_hints(shadow, SEGMENT), thresholds
    )
    spans = {
        p.index: denoise._duration(p.start_ms, p.end_ms) for p in reference.passages
    }
    flagged_ms = sum(
        spans[r.passage] for r in assessment.ratings if r.level != "confident"
    )
    tokens = calibration.tokens(reference.text)
    labelled = [w.speaker for w in reference.words]
    found = reference.diarization
    labels, unlabelled = (
        (None, None)
        if found is None
        else (len(found.labels), labelled.count(None) / (len(labelled) or 1))
    )
    return Score(
        root=label,
        name=name,
        model=spec.model,
        model_version=reference.asr.model_version,
        snapshot=reference.asr.knowledge_snapshot_id,
        keywords=len(reference.asr.keywords_used),
        wer=wer,
        words=words,
        missed=missed,
        wder=wder,
        tokens=len(tokens),
        repetition=denoise._repetition(tokens),
        distinct=len(set(tokens)) / len(tokens) if tokens else 0.0,
        levels=assessment.counts(),
        flagged_time=flagged_ms / (sum(spans.values()) or 1),
        labels=labels,
        unlabelled=unlabelled,
        turns=() if stored_run is None else stored_run.exclusive_turns,
        asr_ms=reference.processing.elapsed_ms,
        diarization_ms=None if stored_run is None else stored_run.elapsed_ms,
        measured=_read_json(root / "run.json"),
    )


def check_provenance(scores: Sequence[Score]) -> None:
    """Within a variant, model revision and snapshot must agree; print both."""
    for name in dict.fromkeys(s.name for s in scores):
        found = {(s.model_version, s.snapshot) for s in scores if s.name == name}
        if len(found) > 1:
            raise SpikeError(f"{name}: model revision or snapshot differ between seeds")
    print("| Modell | Revision | Snapshot | Varianten |")
    print("| --- | --- | --- | --- |")
    groups: dict[tuple[str, str | None, str | None], dict[str, None]] = {}
    for s in scores:  # a dict as an ordered set of names
        groups.setdefault((s.model, s.model_version, s.snapshot), {})[s.name] = None
    for (model, revision, snapshot), names in groups.items():
        print(
            f"| {model} | {(revision or 'n/a')[:12]} | {(snapshot or 'n/a')[:12]} | "
            f"{', '.join(names)} |"
        )
    print()


def _rate(s: Score, clip: denoise.HandClip) -> float:
    return denoise._errors(s, clip) / s.words[clip.name]  # reads only `.wer`


def _spread(values: Sequence[float], fmt: Callable[[float], str] = _pct) -> str:
    mean = sum(values) / len(values)
    return f"{fmt(mean)} ({fmt(min(values))}–{fmt(max(values))})"


def print_tables(
    scores: Sequence[Score],
    clips: Sequence[denoise.HandClip],
    baseline: str,
    frames: int,
) -> None:
    hours = frames / RATE / 3600
    check_provenance(scores)
    names = list(dict.fromkeys(s.name for s in scores))

    print(
        "| Variante | Seeds | Hotwords | "
        + " | ".join(
            f"WER {c.name} Mittel (Spanne) | Auslassungen {c.name}" for c in clips
        )
        + " | Wörter | Wiederholung |"
    )
    print("| --- | --- | --- |" + " --- | --- |" * len(clips) + " --- | --- |")
    for name in names:
        runs = [s for s in scores if s.name == name]
        cells = [
            f"{_spread([_rate(s, c) for s in runs])} | "
            + "/".join(str(s.wer[c.name]["deletions"]) for s in runs)
            for c in clips
        ]
        keywords = "/".join(dict.fromkeys(str(s.keywords) for s in runs))
        tokens = _spread([s.tokens for s in runs], lambda v: f"{v:.0f}")
        repetition = _spread([s.repetition for s in runs])
        print(
            f"| {name} | {len(runs)} | {keywords} | "
            + " | ".join(cells)
            + f" | {tokens} | {repetition} |"
        )
    print()

    print("| Lauf | " + " | ".join(f"WER {c.name} (E/A/Ei)" for c in clips) + " |")
    print("| --- |" + " --- |" * len(clips))
    for s in scores:
        cells = []
        for clip in clips:
            c = s.wer[clip.name]
            cells.append(
                f"{_pct(_rate(s, clip))} ({c['substitutions']}/"
                f"{c['deletions']}/{c['insertions']})"
            )
        print(f"| {s.root} | " + " | ".join(cells) + " |")
    print()

    print(
        "| Lauf | Wörter | Wiederholung | verschiedene Wörter | confident / "
        "needs_review / uncertain | markierte Zeit | "
        + " | ".join(f"übersehen {c.name}" for c in clips)
        + " |"
    )
    print("| --- |" + " --- |" * (5 + len(clips)))
    for s in scores:
        lv = s.levels
        missed = " | ".join(str(s.missed[c.name]) for c in clips)
        print(
            f"| {s.root} | {s.tokens} | {_pct(s.repetition)} | "
            f"{_pct(s.distinct)} | {lv['confident']} / {lv['needs_review']} / "
            f"{lv['uncertain']} | {_pct(s.flagged_time)} | {missed} |"
        )
    print()

    diarized = [s for s in scores if s.labels is not None]
    if diarized:
        base = next((s for s in diarized if s.root == f"{baseline}#1"), None)
        wder_clips = [c for c in clips if any(c.name in s.wder for s in diarized)]
        print(
            "| Lauf | Labels | Wörter ohne Label | "
            + "".join(f"WDER {c.name} (Wörter) | " for c in wder_clips)
            + f"Übereinstimmung mit {baseline} |"
        )
        print("| --- | --- | --- |" + " --- |" * (len(wder_clips) + 1))
        for s in diarized:
            agree = (
                None
                if base is None
                else denoise.agreement(base.turns, s.turns, frames * 1000 // RATE)
            )
            cells = ""
            for c in wder_clips:
                value, count = s.wder.get(c.name, (None, 0))
                cells += f"{'n/a' if value is None else _pct(value)} ({count}) | "
            print(
                f"| {s.root} | {s.labels} | {_pct(s.unlabelled or 0.0)} | {cells}"
                f"{'n/a' if agree is None else _pct(agree)} |"
            )
        print()

    print(
        "| Lauf | ASR (min/h) | Diarisierung (min/h) | Peak-RAM (GiB) | "
        "Peak-VRAM (GiB, davor) |"
    )
    print("| --- | --- | --- | --- | --- |")
    for s in scores:
        step = s.measured.get("asr") or s.measured.get("diarize") or {}
        print(
            f"| {s.root} | {_per_hour(_seconds(s.asr_ms), hours)} | "
            f"{_per_hour(_seconds(s.diarization_ms), hours)} | "
            f"{_gib(step.get('peak_ram_mib'))} | {_gib(step.get('peak_vram_mib'))} "
            f"({_gib(step.get('idle_vram_mib'))}) |"
        )


def _gib(mib: float | None) -> str:
    return "n/a" if mib is None else f"{mib / 1024:.1f}".replace(".", ",")


# --- windows ------------------------------------------------------------------------


@dataclass(frozen=True)
class Window:
    start_ms: int
    words: int
    labels: int
    unlabelled: float
    flagged: float  # share of words in passages not rated confident


def windows(paths: SessionPaths, name: str, seed: int) -> list[Window]:
    """Calm 3-minute windows for a hand reference: steady speech, few speakers,
    few flagged passages. Counts only, never text or labels."""
    root = shadow_root(paths, name, seed)
    shadow = SessionPaths(paths.key, root)
    reference = load_reference(shadow, SEGMENT)
    if reference.diarization is None:
        raise SpikeError(f"{name}#{seed}: run with --diarize first")
    thresholds = load_config(root / "config.yaml").review_uncertainty
    assessment = segment_assessment(
        reference, stored_hints(shadow, SEGMENT), thresholds
    )
    level = {r.passage: r.level for r in assessment.ratings}
    timed = [
        (w.start_ms, w.speaker, level.get(p.index) != "confident")
        for p in reference.passages
        for w in p.words
        if w.start_ms is not None
    ]
    end = denoise._manifest_frames(paths) * 1000 // RATE
    found = []
    for start in range(0, end - WINDOW_MS + 1, WINDOW_STEP_MS):
        inside = [t for t in timed if start <= t[0] < start + WINDOW_MS]
        if not inside:
            continue
        speakers = Counter(s for _, s, _ in inside if s is not None)
        found.append(
            Window(
                start_ms=start,
                words=len(inside),
                labels=sum(1 for n in speakers.values() if n >= 10),
                unlabelled=sum(s is None for _, s, _ in inside) / len(inside),
                flagged=sum(f for _, _, f in inside) / len(inside),
            )
        )
    if not found:
        return []
    # steady speech: at least the median word count, so pauses do not win
    median = sorted(w.words for w in found)[len(found) // 2]
    ranked = sorted(
        (w for w in found if w.words >= median and 2 <= w.labels <= 4),
        key=lambda w: (w.flagged + w.unlabelled, w.labels),
    )
    chosen: list[Window] = []
    for w in ranked:
        if all(abs(w.start_ms - c.start_ms) >= WINDOW_MS for c in chosen):
            chosen.append(w)
        if len(chosen) == WINDOW_PROPOSALS:
            break
    return chosen


def print_windows(found: Sequence[Window]) -> None:
    minutes = WINDOW_MS / 60_000
    print("| Fenster | Wörter/min | Sprecher (≥10 Wörter) | ohne Label | markiert |")
    print("| --- | --- | --- | --- | --- |")
    for w in found:
        print(
            f"| {format_clock(w.start_ms)}–{format_clock(w.start_ms + WINDOW_MS)} | "
            f"{w.words / minutes:.0f} | {w.labels} | {_pct(w.unlabelled)} | "
            f"{_pct(w.flagged)} |"
        )


# --- main ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == [_WITH_VARIANT]:
        return _cli_with_variant(argv[1], argv[2:])
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("command", choices=("prepare", "run", "score", "windows"))
    parser.add_argument("session", help="session key <group>/<ordinal>")
    parser.add_argument("variants", nargs="+", type=_variant_arg)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--seeds", type=int, default=1, help="seeds 1..N per variant")
    parser.add_argument("--seed", type=int, default=1, help="windows: the root to read")
    parser.add_argument("--diarize", action="store_true", help="run: also diarize")
    parser.add_argument("--baseline", default="base")
    parser.add_argument(
        "--clip",
        action="append",
        type=parse_clip,
        help="score: NAME=FILE@H:MM:SS-H:MM:SS (default: pilot clips A and B)",
    )
    args = parser.parse_args(argv)
    jobs = [(v, n) for v in args.variants for n in range(1, args.seeds + 1)]
    try:
        paths = load_config(args.config).session_paths(SessionKey.parse(args.session))
        if args.command == "prepare":
            for name, seed in jobs:
                prepare(paths, name, seed, args.config)
        elif args.command == "run":
            failed = [f"{v}#{n}" for v, n in jobs if run(paths, v, n, args.diarize)]
            if failed:
                print(f"failed: {', '.join(failed)}", file=sys.stderr)
                return 1
        elif args.command == "score":
            clips = args.clip or denoise.CLIPS
            scores = [score(paths, v, n, clips) for v, n in jobs]
            print_tables(scores, clips, args.baseline, denoise._manifest_frames(paths))
        else:
            if len(args.variants) != 1:
                raise SpikeError("windows reads exactly one variant")
            print_windows(windows(paths, args.variants[0], args.seed))
    except (SpikeError, ValueError, OSError, DataFileError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
