"""Shared helpers for the TOOL-62 ASR and TOOL-20 diarization runners. Standard library only, one venv per runner.

Privacy: nothing here prints transcript text. Console output carries timings and counts.
"""

import argparse
import json
import os
import resource
import subprocess
import tempfile
import threading
import wave
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

SAMPLE_RATE = 16000


def parse_args(
    description: str,
    block_seconds: int | None = None,
    repetition_penalty: float | None = None,
    keywords: bool = True,
    num_speakers: bool = False,
) -> argparse.Namespace:
    """Common flags; a runner opts into the flags it understands."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="directory under work/")
    parser.add_argument("--model", required=True)
    if keywords:
        parser.add_argument(
            "--keywords", type=Path, help="local file, one term per line"
        )
    if num_speakers:
        parser.add_argument("--num-speakers", type=int, help="known speaker count")
    if block_seconds is not None:
        parser.add_argument("--block-seconds", type=int, default=block_seconds)
    if repetition_penalty is not None:
        parser.add_argument(
            "--repetition-penalty", type=float, default=repetition_penalty
        )
    return parser.parse_args()


def read_keywords(path: Path | None) -> list[str]:
    if path is None:
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


@contextmanager
def open_wav(path: Path) -> Iterator[wave.Wave_read]:
    """Open a 16 kHz mono WAV from cut.sh; anything else stops the run."""
    with wave.open(str(path), "rb") as source:
        if source.getframerate() != SAMPLE_RATE or source.getnchannels() != 1:
            raise SystemExit("expected 16 kHz mono WAV, use cut.sh")
        yield source


def read_wav(path: Path) -> bytes:
    """The whole file as 16-bit PCM."""
    with open_wav(path) as source:
        return source.readframes(source.getnframes())


def wav_blocks(path: Path, seconds: int) -> Iterator[tuple[float, bytes]]:
    """Yield (offset in seconds, 16-bit PCM) per block, reading one block at a time.

    Blocks do not overlap, so a word at a boundary can be split.
    """
    with open_wav(path) as source:
        frames = seconds * SAMPLE_RATE
        offset = 0
        while pcm := source.readframes(frames):
            yield offset / SAMPLE_RATE, pcm
            offset += frames


@contextmanager
def scratch_dir(out: Path) -> Iterator[Path]:
    """Temporary directory under `out`: blocks of real audio stay under work/."""
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as directory:
        yield Path(directory)


def audio_seconds(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


class VramPeak:
    """Samples GPU memory in the background; the whole GPU, so start from an idle one."""

    def __init__(self) -> None:
        self.peak_mib = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self._stop.wait(1.0):
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                self.peak_mib = max(self.peak_mib, int(result.stdout.split()[0]))

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join()


def _common_meta(args: argparse.Namespace) -> dict:
    return {
        "model": args.model,
        "audio_seconds": audio_seconds(args.audio),
        "peak_ram_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
        "offline": os.environ.get("HF_HUB_OFFLINE") == "1",
    }


def _write_run(out: Path, label: str, filename: str, run: dict) -> Path:
    """A new directory per run, so results are never overwritten."""
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_dir = out / f"{stamp}-{label}"
    run_dir.mkdir(parents=True)
    (run_dir / filename).write_text(
        json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return run_dir


def _report(run_dir: Path, counts: str, seconds: float, meta: dict) -> None:
    speed = meta["audio_seconds"] / seconds
    print(
        f"{run_dir.name}: {counts}, {seconds:.0f} s ({speed:.1f}x realtime), "
        f"peak VRAM {meta['peak_vram_mib']} MiB, peak RAM {meta['peak_ram_mib']} MiB"
    )


def finish(
    args: argparse.Namespace,
    label: str,
    segments: list[dict],
    meta: dict,
    keyword_count: int,
) -> None:
    """Write a finished ASR run as `run.json` and print its counts.

    `meta` carries backend, version, settings, timings and peak VRAM from the runner.
    """
    meta |= _common_meta(args) | {"keyword_count": keyword_count}
    run_dir = _write_run(
        args.out, label, "run.json", {"meta": meta, "segments": segments}
    )
    words = sum(len(segment["words"]) for segment in segments)
    counts = f"{len(segments)} segments, {words} words"
    _report(run_dir, counts, meta["transcribe_seconds"], meta)


def finish_diarization(
    args: argparse.Namespace,
    label: str,
    turns: list[dict],
    meta: dict,
    exclusive_turns: list[dict] | None = None,
) -> None:
    """Write a finished diarization run as `diar.json` and print its counts.

    `turns` may overlap; `exclusive_turns`, if the backend has them, never do.
    Each turn is `{"start", "end", "label"}` in seconds. Labels are generic
    backend labels, never names.
    """
    meta |= _common_meta(args) | {"num_speakers": args.num_speakers}
    run = {"meta": meta, "turns": turns}
    if exclusive_turns is not None:
        run["exclusive_turns"] = exclusive_turns
    run_dir = _write_run(args.out, label, "diar.json", run)
    labels = len({turn["label"] for turn in turns})
    counts = f"{len(turns)} turns, {labels} labels"
    _report(run_dir, counts, meta["diarize_seconds"], meta)
