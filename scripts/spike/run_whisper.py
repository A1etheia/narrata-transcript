"""Transcribe with faster-whisper. TOOL-62 spike, not pipeline code."""

from time import perf_counter

import faster_whisper
from common import VramPeak, finish, parse_args, read_keywords

SETTINGS = {
    "language": "de",
    "beam_size": 5,
    "vad_filter": True,
    "word_timestamps": True,
    "condition_on_previous_text": False,
}


def main() -> None:
    args = parse_args(__doc__)
    keywords = read_keywords(args.keywords)
    with VramPeak() as vram:
        start = perf_counter()
        model = faster_whisper.WhisperModel(
            args.model, device="cuda", compute_type="float16"
        )
        loaded = perf_counter()
        raw_segments, info = model.transcribe(
            str(args.audio), hotwords=" ".join(keywords) or None, **SETTINGS
        )
        segments = [
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "signals": {
                    "avg_logprob": segment.avg_logprob,
                    "no_speech_prob": segment.no_speech_prob,
                    "compression_ratio": segment.compression_ratio,
                },
                "words": [
                    {
                        "start": word.start,
                        "end": word.end,
                        "word": word.word.strip(),
                        "confidence": word.probability,
                    }
                    for word in segment.words
                ],
            }
            for segment in raw_segments
        ]
        finished = perf_counter()
    meta = {
        "backend": "faster-whisper",
        "version": faster_whisper.__version__,
        "settings": SETTINGS,
        "language_probability": info.language_probability,
        "load_seconds": loaded - start,
        "transcribe_seconds": finished - loaded,
        "peak_vram_mib": vram.peak_mib,
    }
    finish(args, f"whisper-{args.model}", segments, meta, len(keywords))


if __name__ == "__main__":
    main()
