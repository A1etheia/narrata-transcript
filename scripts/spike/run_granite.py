"""Transcribe with IBM Granite Speech via transformers. TOOL-62 spike, not pipeline code.

Expects 16 kHz mono WAV from cut.sh. The model card names 9 minutes as the working
limit, but 480 s blocks loop on this material, so audio goes through in short fixed
blocks. The plain ASR task yields no word timestamps and no confidence.

The card recommends repetition penalty 2.0; on German session audio that yields
non-repeating garbage, while 1.0 loops, even in 90 s blocks. 1.2 stops the loops but
may drop common words.
"""

from time import perf_counter

import numpy as np
import torch
import transformers
from common import SAMPLE_RATE, VramPeak, finish, parse_args, read_keywords, wav_blocks
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

TOKENS_PER_SECOND = 12
NUM_BEAMS = 1
SYSTEM_PROMPT = (
    "Knowledge Cutoff Date: April 2024.\nToday's Date: December 19, 2024.\n"
    "You are Granite, developed by IBM. You are a helpful AI assistant"
)


def to_tensor(pcm: bytes) -> torch.Tensor:
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    return torch.from_numpy(samples).unsqueeze(0)


def build_prompt(keywords: list[str]) -> str:
    prompt = "<|audio|> can you transcribe the speech into a written format?"
    if keywords:
        prompt += " Keywords: " + ", ".join(keywords)
    return prompt


@torch.inference_mode()
def transcribe(model, processor, audio: torch.Tensor, prompt: str, penalty: float):
    tokenizer = processor.tokenizer
    chat = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    prompt_text = tokenizer.apply_chat_template(
        chat, tokenize=False, add_generation_prompt=True
    )
    inputs = processor(prompt_text, audio, device=model.device, return_tensors="pt").to(
        model.device
    )
    limit = max(256, int(TOKENS_PER_SECOND * audio.shape[-1] / SAMPLE_RATE))
    outputs = model.generate(
        **inputs,
        max_new_tokens=limit,
        do_sample=False,
        num_beams=NUM_BEAMS,
        repetition_penalty=penalty,
    )
    new_tokens = outputs[0, inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True)


def main() -> None:
    args = parse_args(__doc__, block_seconds=90, repetition_penalty=1.2)
    keywords = read_keywords(args.keywords)
    prompt = build_prompt(keywords)
    segments = []
    with VramPeak() as vram:
        start = perf_counter()
        processor = AutoProcessor.from_pretrained(args.model)
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            args.model, device_map="cuda", dtype=torch.bfloat16
        )
        model.eval()
        loaded = perf_counter()
        for offset, pcm in wav_blocks(args.audio, args.block_seconds):
            audio = to_tensor(pcm)
            text = transcribe(model, processor, audio, prompt, args.repetition_penalty)
            segments.append(
                {
                    "start": offset,
                    "end": offset + audio.shape[-1] / SAMPLE_RATE,
                    "text": text.strip(),
                    "signals": {},
                    "words": [],
                }
            )
        finished = perf_counter()
    meta = {
        "backend": "transformers",
        "version": transformers.__version__,
        "settings": {
            "block_seconds": args.block_seconds,
            "num_beams": NUM_BEAMS,
            "repetition_penalty": args.repetition_penalty,
        },
        "load_seconds": loaded - start,
        "transcribe_seconds": finished - loaded,
        "peak_vram_mib": vram.peak_mib,
    }
    finish(args, "granite", segments, meta, len(keywords))


if __name__ == "__main__":
    main()
