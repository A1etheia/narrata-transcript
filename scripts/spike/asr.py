"""ASR quality spike (TOOL-93, TOOL-81): Whisper variants on segment 1, one root
per seed.

    asr.py prepare <group>/<ordinal> <variant>... [--seeds N]
    asr.py run <group>/<ordinal> <variant>... [--seeds N] [--diarize]
    asr.py score <group>/<ordinal> <variant>... [--seeds N] [--clip ...]
    asr.py windows <group>/<ordinal> <variant> [--seed N]
    asr.py sections <group>/<ordinal> <variant>... [--seeds N] [--against V]
    asr.py decode <group>/<ordinal> <variant>... [--seeds N] [--against V]

A variant is a hotword base (`base`, `pchw`, `nohw`, `nohw-hp`, `kw<N>`,
`neutral9`, `neutral`) or a level-normalising base with all hotwords (TOOL-103:
`dyn`, `dynx`, `comp`, `loud`, `spn`, each also as `<name>-hp` behind a high-pass;
`prepare` records offset, gain range and clipping of the filtered WAV in
`filter.json`), followed by modifiers joined with `+`, e.g.
`nohw+vad-t35+beam10`. `+fill` appends everyday words to the list until the
token budget is full. `+guard` keeps the pipeline's guard, which passes no list
under 110 tokens; without it every variant gets its list as given, so
`base+guard` is the pipeline as shipped. `+batched` decodes with faster-whisper's
`BatchedInferencePipeline`, one chunk of at most 30 s per VAD range and no
temperature fallback; `+batched+ts` lets it sample timestamp tokens (TOOL-104).
`kw<N>` passes the first N snapshot
keywords; `neutral9` and `neutral` pass fixed everyday words instead of the
snapshot's, 9 or as many as fit the token budget (TOOL-81). Two ways change the keywords: `pchw` builds the
root's snapshot again with other budgets, so it gets its own snapshot id; `kw<N>`
and `neutral*` keep the snapshot and change the list in the transcribe child,
recorded in `asr.settings`. A list from other budgets takes the first way, any
other list the second. `prepare` makes
`work/<s>/experiments/asr/<variant>.seed<n>/` its own `paths.root`, as
`denoise.py` does: copies of manifest, `audio.json` and `narrata/`, a config with
`paths.root` and `asr.model`, and a hard link to the raw or filtered WAV. `pchw`
sets every glossary budget to 0 and builds the snapshot of its root again, so only
`pc` entries become hotwords. `run` transcribes each root one after the other with
a fixed CTranslate2 seed, the variant's hotword switch and Whisper settings, all
recorded in `asr.settings`; it skips the diarization unless `--diarize` is given
and writes peak RAM and VRAM to `<root>/run.json`. `score` prints Markdown tables
per seed and as mean and range per variant. `windows` proposes calm 3-minute
windows for a new hand reference from counts only. `sections` counts the words per
5 minutes against seed 1 of `--against` (default `nohw`) and names the sections
with clearly fewer words. `decode` counts Whisper's 30-second decoding windows
from the raw form: temperature fallback, segments per window, compression.

Privacy (TOOL-66): every file stays under `work/`; the console gets no text, no
names and no speaker labels of people.
"""

import argparse
import dataclasses
import itertools
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import wave
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import denoise
import numpy as np
import yaml
from denoise import RATE, SEGMENT, Chain, SpikeError, _pct, _per_hour, _seconds

from transcript import calibration, diarization, knowledge
from transcript.config import DEFAULT_CONFIG, DEFAULT_KEYWORD_BUDGET, load_config
from transcript.hints import stored_hints
from transcript.jsonfile import DataFileError
from transcript.reference import ReferenceTranscript, load_reference
from transcript.session import SessionKey, SessionPaths
from transcript.timecode import format_clock, frames_to_ms, seconds_to_ms
from transcript.uncertainty import segment_assessment

TURBO = "large-v3-turbo"
MODEL_CACHE = Path.home() / ".cache" / "narrata-spike" / "asr"
GERMAN_REV = "9e7012dad924"  # primeline/whisper-large-v3-turbo-german, converted
WINDOW_MS = 180_000  # length of a proposed hand-reference window
WINDOW_STEP_MS = 60_000
WINDOW_PROPOSALS = 3
VRAM_POLL_S = 1.0
# TOOL-81: a 5-minute section has clearly fewer words than the comparison run
# when it lacks at least this share and this many of the comparison's words
SECTION_MS = 300_000
DEFICIT_SHARE = 0.2
DEFICIT_WORDS = 30
DEFAULT_AGAINST = "nohw"
# decoding windows: faster-whisper's `seek` counts 10 ms frames; a window that
# consumes audio but yields fewer words per second than this skipped speech
SEEK_FRAMES_PER_S = 100
SPARSE_WORDS_PER_S = 0.5


@dataclass(frozen=True)
class Variant:
    model: str = TURBO
    hotwords: bool = True
    pc_only: bool = False  # hotwords from `pc` entries only (budget 0 per type)
    keyword_limit: int | None = None  # kw<N>: the first N snapshot keywords
    neutral: int | None = None  # this many NEUTRAL_WORDS instead of the snapshot's
    fill: bool = False  # NEUTRAL_WORDS after the list, cut at the token budget
    guard: bool = False  # keep the pipeline's TOOL-81 guard against short lists
    chain: Chain = field(default_factory=Chain)
    # added to the fixed Whisper settings; a dict value merges with the base's
    asr: Mapping[str, object] = field(default_factory=dict)
    # `asr.*` keys of the root's config, for what the backend takes from there
    config: Mapping[str, object] = field(default_factory=dict)

    @property
    def batched(self) -> bool:
        """Decoded by the BatchedInferencePipeline, not the sequential loop."""
        return BATCH_SIZE in self.asr


# Everyday German words with no tie to a game or a group: a prompt of the same
# form as hotwords but without domain content (TOOL-81). More than fit the token
# budget, so `neutral` is cut there like a full snapshot list.
NEUTRAL_WORDS = [
    "Tisch",
    "Stuhl",
    "Fenster",
    "Tür",
    "Wasser",
    "Brot",
    "Apfel",
    "Garten",
    "Straße",
    "Wetter",
    "Regen",
    "Sonne",
    "Wolke",
    "Morgen",
    "Abend",
    "Woche",
    "Monat",
    "Jahr",
    "Stunde",
    "Minute",
    "Küche",
    "Zimmer",
    "Treppe",
    "Keller",
    "Dach",
    "Wand",
    "Lampe",
    "Teller",
    "Tasse",
    "Gabel",
    "Löffel",
    "Messer",
    "Kanne",
    "Schrank",
    "Regal",
    "Bett",
    "Decke",
    "Kissen",
    "Teppich",
    "Vorhang",
    "Schlüssel",
    "Tasche",
    "Jacke",
    "Mantel",
    "Schuh",
    "Hose",
    "Hemd",
    "Mütze",
    "Schal",
    "Handschuh",
    "Zeitung",
    "Brief",
    "Karte",
    "Heft",
    "Stift",
    "Papier",
    "Buch",
    "Seite",
    "Bild",
    "Uhr",
    "Kalender",
    "Telefon",
    "Radio",
    "Auto",
    "Fahrrad",
    "Bus",
    "Bahn",
    "Bahnhof",
    "Brücke",
    "Fluss",
    "Wiese",
    "Feld",
    "Baum",
    "Blume",
    "Gras",
    "Vogel",
    "Hund",
    "Katze",
    "Pferd",
    "Kuh",
    "Schaf",
    "Bäcker",
    "Markt",
    "Laden",
    "Kasse",
    "Preis",
    "Rechnung",
    "Arbeit",
    "Pause",
    "Urlaub",
    "Reise",
    "Koffer",
    "Ausflug",
    "Spaziergang",
    "Frühstück",
    "Mittag",
    "Suppe",
    "Kartoffel",
    "Möhre",
    "Zwiebel",
    "Käse",
    "Butter",
    "Milch",
    "Zucker",
    "Salz",
]
NEUTRAL_SHORT = 9  # as many as the `pc` hotwords of the pilot snapshot
BASES = {
    "base": Variant(),
    "pchw": Variant(pc_only=True),
    "nohw": Variant(hotwords=False),
    "nohw-hp": Variant(hotwords=False, chain=Chain(before=denoise._HP)),
    "neutral9": Variant(neutral=NEUTRAL_SHORT),
    "neutral": Variant(neutral=len(NEUTRAL_WORDS)),
}
# TOOL-103: level normalisation before the recognition, hotwords as in `base`.
# `loudnorm` runs in two passes: `_two_pass` adds what the first pass measured.
LOUDNORM = "loudnorm="
LOUDNORM_TARGET = {"I": -16.0, "TP": -1.5, "LRA": 11.0}
# loudnorm option -> the key of the first pass's statistics that fills it
LOUDNORM_MEASURED = {
    "measured_I": "input_i",
    "measured_LRA": "input_lra",
    "measured_TP": "input_tp",
    "measured_thresh": "input_thresh",
    "offset": "target_offset",
}
LEVELLERS = {
    "dyn": "dynaudnorm=f=500:g=31:m=5",  # mild: slow, at most 14 dB
    "dynx": "dynaudnorm=f=200:g=11:m=30",  # strong: fast, up to 30 dB
    "comp": (
        "acompressor=threshold=0.05:ratio=4:attack=5:release=200:makeup=4,"
        "alimiter=limit=0.95:level=false"
    ),
    "loud": LOUDNORM + ":".join(f"{k}={v:g}" for k, v in LOUDNORM_TARGET.items()),
    "spn": "speechnorm=e=12.5:r=0.0001:l=1",  # "strong and fast" of the ffmpeg docs
    # control: the median gain of `loud` without its levelling; the limiter only
    # catches the peaks that would clip
    "gain": "volume=12dB,alimiter=limit=0.95:level=false",
}
for _name, _leveller in LEVELLERS.items():
    BASES[_name] = Variant(chain=Chain(before=_leveller))
    BASES[f"{_name}-hp"] = Variant(chain=Chain(before=f"{denoise._HP},{_leveller}"))
# what `prepare` checks on a filtered WAV against the raw one (TOOL-103)
CHECK_PLACES = (0.1, 0.5, 0.9)  # where in the segment
CHECK_MS = 60_000
ENVELOPE_MS = 5  # resolution of the offset
MAX_OFFSET_MS = 10  # beyond this, word times and diarization no longer fit
AUDIBLE = 1e-3  # a second of raw audio below this RMS has no gain to speak of
KEYWORD_LIMIT_PREFIX = "kw"  # kw<N>, parsed by `variant`
# fills a short list with NEUTRAL_WORDS up to the token budget (TOOL-81)
FILL = "fill"
# keeps the pipeline's guard: a list under HOTWORD_MIN_TOKENS reaches no Whisper;
# without it the variants measure the list as given (TOOL-81, acceptance)
GUARD = "guard"
# TOOL-104: faster-whisper's BatchedInferencePipeline. It cuts the audio at the
# VAD ranges into chunks of at most 30 s, decodes each on its own and only at the
# first temperature; `ts` turns its `without_timestamps` default off
BATCHED = "batched"
TIMESTAMPS = "ts"
BATCH_SIZE = "batch_size"  # the setting that marks a batched run
# one factor each; stage 3 adds models
MODIFIERS: dict[str, Mapping[str, object]] = {
    BATCHED: {BATCH_SIZE: 8},  # the library's default
    TIMESTAMPS: {"without_timestamps": False},
    "novad": {"vad_filter": False},
    "vad-t35": {"vad_parameters": {"threshold": 0.35}},
    "vad-pad800": {"vad_parameters": {"speech_pad_ms": 800}},
    "vad-sil500": {"vad_parameters": {"min_silence_duration_ms": 500}},
    "beam10": {"beam_size": 10},
    "nospeech-off": {"no_speech_threshold": None},
    "logprob-lax": {"log_prob_threshold": -1.5},
    "cond-prev": {"condition_on_previous_text": True},
    # no temperature fallback: the seed acts only while sampling (TOOL-81)
    "temp0": {"temperature": 0.0},
    # changes nothing but the root: checks that a seed reproduces a run
    "twin": {},
}
# modifier -> `asr.model`: a faster-whisper name, a Hub id or a local CT2 directory
MODELS = {
    "large-v3": "large-v3",
    # primeline/whisper-large-v3-turbo-german, converted (README); "turbo" in the
    # name gives it hotwords unless the base is nohw
    "de-turbo": str(MODEL_CACHE / f"whisper-large-v3-turbo-german-ct2-{GERMAN_REV}"),
    "crisper": "nyralabs/faster_CrisperWhisper",  # CrisperWhisper 1.0, CT2
}
# filler, hesitation and dialect words: their omissions are counted apart and a
# second WER leaves them out on both sides (a rough list, named in the report)
FILLERS = frozenset(
    {"äh", "ähm", "öh", "hm", "mhm", "ja", "also", "halt", "dann", "des", "ne"}
    | {"gell", "mal", "eben", "naja"}
)
# the backend passes these itself, so they go into the config, not FIXED_SETTINGS
CONFIG_KEYS = frozenset({"beam_size"})


def variant(name: str) -> Variant:
    """`<base>[+<modifier>…]`; each modifier at most once, at most one model."""
    head, *mods = name.split("+")
    if len(set(mods)) != len(mods):
        raise SpikeError(f"{name}: a modifier repeats")
    base = _base(name, head)
    asr: dict[str, object] = {}
    config: dict[str, object] = {}
    model = base.model
    fill = guard = False
    for mod in mods:
        if mod == FILL:
            fill = True
        elif mod == GUARD:
            guard = True
        elif mod in MODELS:
            if model != base.model:
                raise SpikeError(f"{name}: more than one model")
            model = MODELS[mod]
        elif mod in MODIFIERS:
            for key, value in MODIFIERS[mod].items():
                if key in CONFIG_KEYS:
                    config[key] = value
            asr = merge(
                asr, {k: v for k, v in MODIFIERS[mod].items() if k not in CONFIG_KEYS}
            )
        else:
            known = sorted([*MODIFIERS, *MODELS, FILL, GUARD])
            raise SpikeError(f"{name}: unknown modifier {mod!r}, one of {known}")
    if BATCHED in mods:
        asr.setdefault("without_timestamps", True)  # the library's default, recorded
    elif TIMESTAMPS in mods:
        raise SpikeError(f"{name}: +{TIMESTAMPS} needs +{BATCHED}")
    return dataclasses.replace(
        base, model=model, asr=asr, config=config, fill=fill, guard=guard
    )


def _base(name: str, head: str) -> Variant:
    if head in BASES:
        return BASES[head]
    count = head.removeprefix(KEYWORD_LIMIT_PREFIX)
    if head.startswith(KEYWORD_LIMIT_PREFIX) and count.isdigit() and int(count) > 0:
        return Variant(keyword_limit=int(count))
    known = [*sorted(BASES), f"{KEYWORD_LIMIT_PREFIX}<N>"]
    raise SpikeError(f"{name}: unknown base {head!r}, one of {known}")


def keyword_settings(spec: Variant) -> dict[str, int | bool]:
    """What a variant changes in the keyword list, as it goes into `asr.settings`.

    Empty for the TOOL-93 bases, so their transcripts stay reusable.
    """
    found = {"keyword_limit": spec.keyword_limit, "neutral": spec.neutral}
    changed = {key: value for key, value in found.items() if value is not None}
    return {**changed, FILL: True} if spec.fill else changed


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
    source = chain_wav(paths, chain)
    if chain != Chain():
        store = source.parent
        record = store / "filter.json"
        if not denoise._reusable(record, source, chain, frames):
            store.mkdir(parents=True, exist_ok=True)
            raw = paths.segment_wav(SEGMENT)
            started = time.monotonic()
            applied, measured = _two_pass(raw, chain)
            denoise._filter(raw, source, applied, frames, store)
            elapsed = time.monotonic() - started
            check = filter_check(raw, source, frames)
            if max(abs(ms) for ms in check["offset_ms"]) > MAX_OFFSET_MS:
                source.unlink()
                raise SpikeError(f"{label}: filtered audio is shifted against the raw")
            found = {
                "chain": chain.describe(),
                "frames": frames,
                "filter_seconds": round(elapsed, 1),
                "tools": denoise._tool_versions(chain),
                "check": check,
            }
            if measured:
                found["loudnorm"] = measured
            record.write_text(json.dumps(found, indent=2), encoding="utf-8")
            gain = check["gain_db"]
            print(
                f"{label}: {chain.describe()} in {elapsed:.0f} s, offset "
                f"{check['offset_ms']} ms, gain {gain['median']} dB "
                f"({gain['p10']} to {gain['p90']}), at full scale "
                f"{check['full_scale_share']:.4%}"
            )
        shutil.copy2(record, shadow.root / "filter.json")
    if target.is_file() and os.path.samefile(source, target):
        return
    target.unlink(missing_ok=True)
    os.link(source, target)  # never written by the pipeline


def chain_wav(paths: SessionPaths, chain: Chain) -> Path:
    """Segment 1 as the roots of `chain` link it: raw, or the one filtered copy."""
    if chain == Chain():
        return paths.segment_wav(SEGMENT)
    store = paths.work_dir / "experiments" / "asr" / "audio" / chain.describe()
    return store / "segment.wav"


def _two_pass(raw: Path, chain: Chain) -> tuple[Chain, dict[str, object]]:
    """`chain` with what a first `loudnorm` pass measured, and those values.

    The store and its record keep the name of the chain as given, so a filtered
    WAV is reused without measuring again.
    """
    parts = (chain.before or "").split(",")
    at = next((n for n, p in enumerate(parts) if p.startswith(LOUDNORM)), None)
    if at is None:
        return chain, {}
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "info", "-i", str(raw)]
    command += ["-af", ",".join(parts[: at + 1]) + ":print_format=json"]
    command += ["-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    start, end = result.stderr.rfind("{"), result.stderr.rfind("}")
    if result.returncode or start < 0 or end < start:
        raise SpikeError("loudnorm: the measuring pass failed")
    stats = json.loads(result.stderr[start : end + 1])
    measured: dict[str, object] = {
        key: float(stats[key]) for key in LOUDNORM_MEASURED.values()
    }
    # af_loudnorm.c: a fixed gain if it keeps the true peak and the range fits
    target = LOUDNORM_TARGET
    peak = measured["input_tp"] + target["I"] - measured["input_i"]
    keeps_peak = peak <= target["TP"]
    range_fits = measured["input_lra"] <= target["LRA"]
    measured["linear_expected"] = keeps_peak and range_fits
    options = [f"{o}={stats[key]}" for o, key in LOUDNORM_MEASURED.items()]
    parts[at] = ":".join([parts[at], *options, "linear=true"])
    return dataclasses.replace(chain, before=",".join(parts)), measured


def _read_wav(wav: Path, start: int, count: int) -> np.ndarray:
    """`count` samples of a segment WAV from frame `start` on, as floats in -1..1."""
    with wave.open(str(wav), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (
            RATE,
            1,
            2,
        ):
            raise SpikeError("segment WAV is not 16 kHz mono 16 bit")
        source.setpos(min(start, source.getnframes()))
        data = source.readframes(count)
    samples = np.frombuffer(data, dtype="<i2").astype(np.float32)
    samples *= 1 / 32768  # in place: omissions.py reads the whole segment
    return samples


def filter_check(raw: Path, filtered: Path, frames: int) -> dict[str, object]:
    """What a filter did, from numbers alone (TOOL-103).

    At `CHECK_PLACES`: the offset of the envelope against the raw WAV (positive:
    the filtered audio is late) and the gain of each second the raw WAV is
    audible in. A leveller shows as a wide gain range, a fixed gain as none. Over
    the whole file: the share of samples at full scale.
    """
    step = RATE * ENVELOPE_MS // 1000
    count = min(CHECK_MS * RATE // 1000, frames) // RATE * RATE
    offsets: list[int] = []
    gains: list[float] = []
    for place in CHECK_PLACES:
        start = min(int(frames * place), frames - count)
        before, after = (_read_wav(wav, start, count) for wav in (raw, filtered))
        a, b = (np.abs(x).reshape(-1, step).mean(axis=1) for x in (before, after))
        lag = int(np.argmax(np.correlate(b - b.mean(), a - a.mean(), mode="full")))
        offsets.append((lag - (len(a) - 1)) * ENVELOPE_MS)
        was, now = (
            np.sqrt((x.reshape(-1, RATE) ** 2).mean(axis=1)) for x in (before, after)
        )
        heard = was > AUDIBLE
        gains += (20 * np.log10(np.maximum(now[heard], 1e-9) / was[heard])).tolist()
    full = 0
    with wave.open(str(filtered), "rb") as source:
        while data := source.readframes(RATE * 600):
            full += int((np.abs(np.frombuffer(data, dtype="<i2")) >= 32767).sum())
    return {
        "offset_ms": offsets,
        "gain_db": {
            name: round(float(np.percentile(gains, q)), 1) if gains else None
            for name, q in (("median", 50), ("p10", 10), ("p90", 90))
        },
        "full_scale_share": full / frames,
    }


# --- run ----------------------------------------------------------------------------


_WITH_VARIANT = "_with-variant"  # internal: the transcript CLI with a variant


def run(paths: SessionPaths, name: str, seed: int, diarize: bool) -> int:
    root = shadow_root(paths, name, seed)
    config = root / "config.yaml"
    if not config.is_file():
        raise SpikeError(f"{name}#{seed}: run prepare first")
    spec = variant(name)
    print(f"{name}#{seed}: transcribe", flush=True)
    options = {
        "seed": seed,
        "hotwords": spec.hotwords,
        "keywords": keyword_settings(spec),
        "asr": dict(spec.asr),
        "guard": spec.guard,
    }
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
    """The transcript CLI with a seed, a hotword switch, a changed keyword list and
    added Whisper settings.

    `seed`, `hotwords` and the keyword change go into `asr.settings`, so resume
    tells the runs apart; only the Whisper settings reach `transcribe`. The keyword
    list changes where the CLI reads it from the snapshot, so its counts, resume
    and `keywords_used` all see the list Whisper got.
    """
    import ctranslate2

    from transcript.__main__ import main as cli
    from transcript.asr import whisper
    from transcript.asr.backend import BackendIdentity
    from transcript.domain import DomainContext

    spec = json.loads(options)
    seed = spec["seed"]
    whisper.FIXED_SETTINGS.update(merge(whisper.FIXED_SETTINGS, spec["asr"]))
    # The variants measure short lists, so the pipeline's TOOL-81 guard stays off
    # and its settings key stays out, which keeps earlier roots reusable; `+guard`
    # runs the pipeline as shipped and records the threshold.
    guard = spec["guard"]
    if not guard:
        whisper.HOTWORD_MIN_TOKENS = 0
    if not spec["hotwords"]:
        whisper.takes_hotwords = lambda model: False
    changed = spec["keywords"]
    snapshot_keywords = DomainContext.transcription_keywords

    def keywords(self):
        if "neutral" in changed:
            found = tuple(NEUTRAL_WORDS[: changed["neutral"]])
        else:
            found = snapshot_keywords(self)[: changed.get("keyword_limit")]
        if not changed.get(FILL):
            return found
        # `fit_hotwords` cuts the filled list at the token budget
        return found + tuple(word for word in NEUTRAL_WORDS if word not in found)

    DomainContext.transcription_keywords = keywords
    # the batched pipeline takes its settings as the sequential call would
    batched = BATCH_SIZE in spec["asr"]
    extra = {"seed": seed, "hotwords": spec["hotwords"], **changed}

    backend = whisper.WhisperBackend
    original_prepare, original_transcribe = backend._prepare, backend.transcribe

    def prepare(self):
        runtime, model_path, identity = original_prepare(self)
        settings = {**identity.settings, **extra}
        if not guard:
            settings.pop("hotword_min_tokens", None)
        return runtime, model_path, BackendIdentity(identity.info, settings)

    def transcribe(self, request):
        ctranslate2.set_random_seed(seed)
        model = self._model
        if not batched or model is None:
            return original_transcribe(self, request)
        self._model = _Batched(model)
        try:
            return original_transcribe(self, request)
        finally:
            self._model = model

    backend._prepare = prepare
    backend.transcribe = transcribe
    return cli(list(argv))


class _Batched:
    """Stands in for the loaded model while the backend transcribes: the same
    call and the same tokenizer, decoded by the batched pipeline."""

    def __init__(self, model) -> None:
        from faster_whisper import BatchedInferencePipeline

        self.hf_tokenizer = model.hf_tokenizer
        self.transcribe = BatchedInferencePipeline(model).transcribe


# --- score --------------------------------------------------------------------------


@dataclass(frozen=True)
class FillerCount:
    in_reference: int  # filler tokens in the hand reference
    deleted: int  # omissions that are fillers
    plain: Counter[str]  # alignment counts with fillers removed on both sides
    plain_rate: float  # WER with fillers removed on both sides


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
    fillers: dict[str, FillerCount]  # per clip
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


def count_fillers(
    reference: ReferenceTranscript,
    hand: calibration.HandReference,
    clip: denoise.HandClip,
) -> FillerCount:
    """Split the omissions of `clip` into fillers and the rest, as `measure` aligns."""
    texts, _, _ = calibration._clip_tokens(reference, clip.start_ms, clip.end_ms)
    deleted = calibration.align(hand, texts).deletions
    keep = [token not in FILLERS for token in hand.tokens]
    kept_before = list(itertools.accumulate(keep, initial=0))
    stripped = calibration.HandReference(
        tuple(itertools.compress(hand.tokens, keep)),
        tuple(itertools.compress(hand.speakers, keep)),
        frozenset(kept_before[gap] for gap in hand.gaps),
    )
    plain = calibration.align(stripped, [t for t in texts if t not in FILLERS]).counts
    errors = sum(plain[k] for k in ("substitutions", "deletions", "insertions"))
    return FillerCount(
        in_reference=len(keep) - sum(keep),
        deleted=sum(hand.tokens[position] in FILLERS for position, _ in deleted),
        plain=plain,
        plain_rate=errors / (len(stripped.tokens) or 1),
    )


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
    reference = transcribed(paths, name, seed)
    stored_run = diarization.load_run(shadow, SEGMENT)

    wer: dict[str, Counter[str]] = {}
    words: dict[str, int] = {}
    missed: dict[str, int] = {}
    fillers: dict[str, FillerCount] = {}
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
        fillers[clip.name] = count_fillers(reference, hand, clip)
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
        model=variant(name).model,
        model_version=reference.asr.model_version,
        snapshot=reference.asr.knowledge_snapshot_id,
        keywords=len(reference.asr.keywords_used),
        wer=wer,
        words=words,
        missed=missed,
        fillers=fillers,
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


def transcribed(paths: SessionPaths, name: str, seed: int) -> ReferenceTranscript:
    """Segment 1 of the root, made with the variant's seed, model and settings."""
    label = f"{name}#{seed}"
    reference = load_reference(
        SessionPaths(paths.key, shadow_root(paths, name, seed)), SEGMENT
    )
    if reference.status != "transcribed":
        raise SpikeError(f"{label}: segment {SEGMENT} is not transcribed")
    spec = variant(name)
    settings = reference.asr.settings
    wanted = {
        "seed": seed,
        "hotwords": spec.hotwords,
        "model": spec.model,
        **spec.config,
        **keyword_settings(spec),
    }
    if any(settings.get(k) != v for k, v in wanted.items()):
        raise SpikeError(f"{label}: transcript lacks the variant's seed or model")
    for key, value in spec.asr.items():
        stored = settings.get(key)
        if isinstance(value, Mapping):
            stored = {k: (stored or {}).get(k) for k in value}
        if stored != value:
            raise SpikeError(f"{label}: transcript lacks the variant's {key}")
    return reference


class _Provenance(Protocol):
    name: str
    model: str
    model_version: str | None
    snapshot: str | None


def check_provenance(scores: Sequence[_Provenance]) -> None:
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
            f"| {Path(model).name} | {(revision or 'n/a')[:12]} | {(snapshot or 'n/a')[:12]} | "
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
        "| Lauf | "
        + " | ".join(
            f"Füllwörter in {c.name} | Auslassungen {c.name} (Füllwörter / übrige) | "
            f"WER {c.name} ohne Füllwörter (E/A/Ei)"
            for c in clips
        )
        + " |"
    )
    print("| --- |" + " --- | --- | --- |" * len(clips))
    for s in scores:
        cells = []
        for clip in clips:
            f, deletions = s.fillers[clip.name], s.wer[clip.name]["deletions"]
            p = f.plain
            cells.append(
                f"{f.in_reference} von {s.words[clip.name]} | {f.deleted} / "
                f"{deletions - f.deleted} | {_pct(f.plain_rate)} "
                f"({p['substitutions']}/{p['deletions']}/{p['insertions']})"
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
    return "n/a" if mib is None else _decimal(mib / 1024)


def _decimal(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


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
    end = _end_ms(paths)
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


def _end_ms(paths: SessionPaths) -> int:
    """The end of segment 1 on its own timeline."""
    return frames_to_ms(denoise._manifest_frames(paths), RATE)


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


# --- sections -----------------------------------------------------------------------


@dataclass(frozen=True)
class Sections:
    root: str  # `<variant>#<seed>`
    name: str
    model: str
    model_version: str | None
    snapshot: str | None
    counts: tuple[int, ...]  # words starting in each 5-minute section
    untimed: int  # words with neither their own nor their passage's start


def sections(
    paths: SessionPaths,
    name: str,
    seed: int,
    reference: ReferenceTranscript | None = None,
) -> Sections:
    """Words per 5 minutes of segment 1; a word counts where it starts.

    `reference` is the root's transcript when the caller has already loaded it.
    """
    reference = reference or transcribed(paths, name, seed)
    counts = [0] * -(-_end_ms(paths) // SECTION_MS)
    untimed = 0
    for passage in reference.passages:
        for word in passage.words:
            start = word.start_ms if word.start_ms is not None else passage.start_ms
            if start is None:
                untimed += 1
            else:
                counts[min(start // SECTION_MS, len(counts) - 1)] += 1
    return Sections(
        root=f"{name}#{seed}",
        name=name,
        model=variant(name).model,
        model_version=reference.asr.model_version,
        snapshot=reference.asr.knowledge_snapshot_id,
        counts=tuple(counts),
        untimed=untimed,
    )


def deficits(run: Sections, against: Sections) -> list[int]:
    """The sections where `run` clearly has fewer words than `against`."""
    return [
        index
        # both from the same manifest, so of the same length
        for index, (own, theirs) in enumerate(
            zip(run.counts, against.counts, strict=True)
        )
        if theirs - own >= DEFICIT_WORDS and own <= (1 - DEFICIT_SHARE) * theirs
    ]


def print_sections(runs: Sequence[Sections], against: Sections) -> None:
    check_provenance([*runs, against])
    print(
        f"Vergleich: {against.root}, Abschnitte à {SECTION_MS // 60_000} min, Defizit "
        f"ab {DEFICIT_SHARE:.0%} und {DEFICIT_WORDS} Wörtern weniger"
    )
    print()
    print(
        "| Lauf | Wörter | ohne Zeit | Abschnitte | mit Defizit | fehlende Wörter "
        "darin | größtes Defizit |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- |")
    found = {run.root: deficits(run, against) for run in runs}
    for run in runs:
        gaps = [against.counts[i] - run.counts[i] for i in found[run.root]]
        shares = [1 - run.counts[i] / against.counts[i] for i in found[run.root]]
        largest = _pct(max(shares)) if shares else "–"
        print(
            f"| {run.root} | {sum(run.counts)} | {run.untimed} | {len(run.counts)} | "
            f"{len(gaps)} | {sum(gaps)} | {largest} |"
        )
    if not any(found.values()):
        return
    print()
    print(f"| Lauf | Abschnitt | Wörter | {against.root} |")
    print("| --- | --- | --- | --- |")
    for run in runs:
        for index in found[run.root]:
            start = index * SECTION_MS
            print(
                f"| {run.root} | {format_clock(start)}–"
                f"{format_clock(start + SECTION_MS)} | {run.counts[index]} | "
                f"{against.counts[index]} |"
            )


# --- decode -------------------------------------------------------------------------


@dataclass(frozen=True)
class DecodeWindow:
    """One 30-second decoding window, from the raw form; counts only."""

    start_ms: int  # where its first segment starts, on the segment's timeline
    temperature: float  # the highest of its segments: > 0 means fallback
    segment_lengths: tuple[float, ...]  # seconds
    words: int
    # audio the decoder moved on by; a window that yields no segment at all adds
    # its audio to the window before, which then turns sparse
    consumed_s: float
    compression: float  # the highest compression ratio of its segments

    @property
    def fallback(self) -> bool:
        return self.temperature > 0

    @property
    def sparse(self) -> bool:
        return self.words < SPARSE_WORDS_PER_S * self.consumed_s

    @property
    def section(self) -> int:
        return self.start_ms // SECTION_MS


def decode_windows(paths: SessionPaths, name: str, seed: int) -> list[DecodeWindow]:
    """The windows of segment 1 in decoding order. Text and tokens stay unread.

    The caller checks the transcript the raw form belongs to (`transcribed`).
    """
    shadow = SessionPaths(paths.key, shadow_root(paths, name, seed))
    raw = _read_json(shadow.reference_raw(SEGMENT)).get("raw", {})  # write_reference
    if not raw.get("segments"):
        raise SpikeError(f"{name}#{seed}: no raw segments for segment {SEGMENT}")
    grouped: dict[int, list[Mapping[str, object]]] = {}
    for segment in raw["segments"]:
        grouped.setdefault(int(segment["seek"]), []).append(segment)
    seeks = sorted(grouped)
    end = (raw["info"]["duration_after_vad"] or 0) * SEEK_FRAMES_PER_S
    found = []
    for seek, after in zip(seeks, [*seeks[1:], max(end, seeks[-1])], strict=True):
        window = grouped[seek]
        found.append(
            DecodeWindow(
                start_ms=seconds_to_ms(min(float(s["start"]) for s in window)),
                temperature=max(float(s["temperature"] or 0) for s in window),
                segment_lengths=tuple(
                    float(s["end"]) - float(s["start"]) for s in window
                ),
                words=sum(len(s["words"] or ()) for s in window),
                consumed_s=(after - seek) / SEEK_FRAMES_PER_S,
                compression=max(float(s["compression_ratio"]) for s in window),
            )
        )
    return found


def print_decode(
    paths: SessionPaths,
    jobs: Sequence[tuple[str, int]],
    against: Sections | None,
) -> None:
    """Per run: fallback, segments per window and skipped audio; with `against`,
    the fallback share inside and outside the sections with a word deficit."""
    headers = [
        "Lauf",
        "Fenster",
        "mit Fallback",
        "Wörter in Fallback-Fenstern",
        "Segmente je Fenster",
        "Segmentlänge Median (s)",
        "dünne Fenster",
        "Kompression über der Schwelle",
        *(["Fallback im Defizit / sonst"] if against else []),
    ]
    print("| " + " | ".join(headers) + " |")
    print("|" + " --- |" * len(headers))
    for name, seed in jobs:
        reference = transcribed(paths, name, seed)
        limit = load_config(
            shadow_root(paths, name, seed) / "config.yaml"
        ).review_uncertainty.compression_ratio  # as the assessment flags passages
        found = decode_windows(paths, name, seed)
        fallback = [w for w in found if w.fallback]
        lengths = sorted(n for w in found for n in w.segment_lengths)
        cells = [
            str(len(found)),
            f"{len(fallback)} ({_pct(len(fallback) / len(found))})",
            _pct(sum(w.words for w in fallback) / (sum(w.words for w in found) or 1)),
            _decimal(len(lengths) / len(found)),
            _decimal(lengths[len(lengths) // 2]),
            str(sum(w.sparse for w in found)),
            str(sum(w.compression >= limit for w in found)),
        ]
        if against is not None:
            short = set(deficits(sections(paths, name, seed, reference), against))
            inside = [w for w in found if w.section in short]
            outside = [w for w in found if w.section not in short]
            cells.append(f"{_fallback_share(inside)} / {_fallback_share(outside)}")
        print(f"| {name}#{seed} | " + " | ".join(cells) + " |")


def _fallback_share(found: Sequence[DecodeWindow]) -> str:
    return _pct(sum(w.fallback for w in found) / len(found)) if found else "–"


# --- main ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == [_WITH_VARIANT]:
        return _cli_with_variant(argv[1], argv[2:])
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "command",
        choices=("prepare", "run", "score", "windows", "sections", "decode"),
    )
    parser.add_argument("session", help="session key <group>/<ordinal>")
    parser.add_argument("variants", nargs="+", type=_variant_arg)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--seeds", type=int, default=1, help="seeds 1..N per variant")
    parser.add_argument("--seed", type=int, default=1, help="windows: the root to read")
    parser.add_argument("--diarize", action="store_true", help="run: also diarize")
    parser.add_argument("--baseline", default="base")
    parser.add_argument(
        "--against",
        type=_variant_arg,
        help=f"sections, decode: seed 1 of this variant to compare with "
        f"(sections: default {DEFAULT_AGAINST})",
    )
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
        elif args.command == "sections":
            runs = [sections(paths, v, n) for v, n in jobs]
            name = args.against or DEFAULT_AGAINST
            listed = [s for s in runs if s.root == f"{name}#1"]
            print_sections(runs, listed[0] if listed else sections(paths, name, 1))
        elif args.command == "decode":
            against = sections(paths, args.against, 1) if args.against else None
            print_decode(paths, jobs, against)
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
