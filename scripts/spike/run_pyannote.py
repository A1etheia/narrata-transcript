"""Diarize with pyannote.audio. TOOL-20 spike, not pipeline code.

Expects 16 kHz mono WAV from cut.sh. The audio is handed over in memory, so pyannote
needs no audio decoder. The model is gated: download it once with a Hugging Face token
(read from the local token cache), then run with HF_HUB_OFFLINE=1.
"""

from time import perf_counter

import numpy as np
import pyannote.audio
import torch
from common import SAMPLE_RATE, VramPeak, finish_diarization, parse_args, read_wav
from pyannote.audio import Pipeline


def load_waveform(path) -> torch.Tensor:
    """Scaled in place: five hours are 1.1 GB as float32, so no second copy."""
    samples = np.frombuffer(read_wav(path), dtype=np.int16).astype(np.float32)
    samples /= 32768
    return torch.from_numpy(samples).unsqueeze(0)


def turns_of(annotation) -> list[dict]:
    return [
        {"start": turn.start, "end": turn.end, "label": label}
        for turn, _, label in annotation.itertracks(yield_label=True)
    ]


def main() -> None:
    args = parse_args(__doc__, keywords=False, num_speakers=True)
    waveform = load_waveform(args.audio)
    with VramPeak() as vram:
        start = perf_counter()
        pipeline = Pipeline.from_pretrained(args.model)
        pipeline.to(torch.device("cuda"))
        loaded = perf_counter()
        output = pipeline(
            {"waveform": waveform, "sample_rate": SAMPLE_RATE},
            num_speakers=args.num_speakers,
        )
        finished = perf_counter()
    # pyannote 4 returns both the overlapping and an exclusive (one speaker at a
    # time) diarization; 3.x returns a single annotation.
    overlapping = getattr(output, "speaker_diarization", output)
    exclusive = getattr(output, "exclusive_speaker_diarization", None)
    meta = {
        "backend": "pyannote",
        "version": pyannote.audio.__version__,
        "settings": {"device": "cuda"},
        "load_seconds": loaded - start,
        "diarize_seconds": finished - loaded,
        "peak_vram_mib": vram.peak_mib,
    }
    finish_diarization(
        args,
        "pyannote",
        turns_of(overlapping),
        meta,
        turns_of(exclusive) if exclusive is not None else None,
    )


if __name__ == "__main__":
    main()
