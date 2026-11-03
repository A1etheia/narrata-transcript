"""Transcribe with NVIDIA Parakeet TDT via NeMo. TOOL-62 spike, not pipeline code.

Expects 16 kHz mono WAV from cut.sh. Local attention, because the model card limits full
attention to 24 minutes on far larger GPUs. A 26-minute file still crashes the encoder
here with "device not ready", so audio goes through in fixed blocks.
"""

import wave
from time import perf_counter

import nemo
import nemo.collections.asr as nemo_asr
from common import SAMPLE_RATE, VramPeak, finish, parse_args, scratch_dir, wav_blocks
from omegaconf import open_dict

ATT_CONTEXT = [256, 256]


def enable_word_confidence(model) -> None:
    decoding = model.cfg.decoding
    with open_dict(decoding):
        decoding.confidence_cfg = {
            "preserve_word_confidence": True,
            "preserve_token_confidence": True,
            "preserve_frame_confidence": True,
            "aggregation": "mean",
        }
    model.change_decoding_strategy(decoding)


def block_segments(hypothesis, offset: float) -> list[dict]:
    stamps = hypothesis.timestamp
    confidences = list(hypothesis.word_confidence or [])
    words = [
        {
            "start": stamp["start"] + offset,
            "end": stamp["end"] + offset,
            "word": stamp["word"],
            "confidence": (
                float(confidences[index]) if index < len(confidences) else None
            ),
        }
        for index, stamp in enumerate(stamps["word"])
    ]
    segments = []
    for stamp in stamps["segment"]:
        start, end = stamp["start"] + offset, stamp["end"] + offset
        segments.append(
            {
                "start": start,
                "end": end,
                "text": stamp["segment"],
                "signals": {},
                "words": [w for w in words if start <= w["start"] < end],
            }
        )
    return segments


def write_block(path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(pcm)


def main() -> None:
    args = parse_args(__doc__, block_seconds=300)
    if args.keywords:
        raise SystemExit("Parakeet has no documented keyword biasing")
    segments = []
    with VramPeak() as vram, scratch_dir(args.out) as scratch:
        start = perf_counter()
        model = nemo_asr.models.ASRModel.from_pretrained(model_name=args.model)
        model.change_attention_model(
            self_attention_model="rel_pos_local_attn", att_context_size=ATT_CONTEXT
        )
        enable_word_confidence(model)
        loaded = perf_counter()
        block = scratch / "block.wav"
        for offset, pcm in wav_blocks(args.audio, args.block_seconds):
            write_block(block, pcm)
            hypothesis = model.transcribe(
                [str(block)], timestamps=True, return_hypotheses=True
            )[0]
            segments.extend(block_segments(hypothesis, offset))
        finished = perf_counter()
    meta = {
        "backend": "nemo",
        "version": nemo.__version__,
        "settings": {
            "att_context_size": ATT_CONTEXT,
            "block_seconds": args.block_seconds,
        },
        "load_seconds": loaded - start,
        "transcribe_seconds": finished - loaded,
        "peak_vram_mib": vram.peak_mib,
    }
    finish(args, "parakeet", segments, meta, 0)


if __name__ == "__main__":
    main()
