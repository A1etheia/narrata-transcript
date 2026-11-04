"""Diarize with the NeMo clustering diarizer. TOOL-20 spike, not pipeline code.

Runs in the Parakeet venv. MarbleNet VAD, multi-scale TitaNet embeddings and long-form
clustering, so five hours fit into memory. Settings follow NeMo's meeting preset.
All intermediate files (VAD frames, embeddings) stay in a scratch directory under
`--out` and are deleted afterwards.
"""

import json
from pathlib import Path
from time import perf_counter

import nemo
from common import VramPeak, finish_diarization, parse_args, scratch_dir
from nemo.collections.asr.models import ClusteringDiarizer
from nemo.utils import logging as nemo_logging
from omegaconf import OmegaConf

VAD_MODEL = "vad_multilingual_marblenet"
VAD = {
    "window_length_in_sec": 0.63,
    "shift_length_in_sec": 0.08,
    "smoothing": False,
    "overlap": 0.5,
    "onset": 0.9,
    "offset": 0.5,
    "pad_onset": 0.0,
    "pad_offset": 0.0,
    "min_duration_on": 0.0,
    "min_duration_off": 0.6,
    "filter_speech_first": True,
}
EMBEDDINGS = {
    "window_length_in_sec": [3.0, 2.5, 2.0, 1.5, 1.0, 0.5],
    "shift_length_in_sec": [1.5, 1.25, 1.0, 0.75, 0.5, 0.25],
    "multiscale_weights": [1, 1, 1, 1, 1, 1],
    "save_embeddings": False,
}
CLUSTERING = {
    "max_num_speakers": 8,
    "enhanced_count_thres": 80,
    "max_rp_threshold": 0.25,
    "sparse_search_volume": 30,
    "maj_vote_spk_count": False,
    "chunk_cluster_count": 50,
    "embeddings_per_chunk": 10000,
}


def config(manifest: Path, out_dir: Path, embedding_model: str, oracle: bool):
    return OmegaConf.create(
        {
            "num_workers": 0,
            "sample_rate": 16000,
            "batch_size": 64,
            "device": "cuda",
            "verbose": False,
            "diarizer": {
                "manifest_filepath": str(manifest),
                "out_dir": str(out_dir),
                "oracle_vad": False,
                "collar": 0.25,
                "ignore_overlap": True,
                "vad": {
                    "model_path": VAD_MODEL,
                    "external_vad_manifest": None,
                    "parameters": VAD,
                },
                "speaker_embeddings": {
                    "model_path": embedding_model,
                    "parameters": EMBEDDINGS,
                },
                "clustering": {
                    "parameters": CLUSTERING | {"oracle_num_speakers": oracle}
                },
            },
        }
    )


def read_rttm(path: Path) -> list[dict]:
    turns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        start, duration = float(fields[3]), float(fields[4])
        turns.append({"start": start, "end": start + duration, "label": fields[7]})
    return sorted(turns, key=lambda turn: turn["start"])


def main() -> None:
    args = parse_args(__doc__, keywords=False, num_speakers=True)
    nemo_logging.setLevel(nemo_logging.ERROR)
    with VramPeak() as vram, scratch_dir(args.out) as scratch:
        manifest = scratch / "manifest.json"
        entry = {
            "audio_filepath": str(args.audio.resolve()),
            "offset": 0,
            "duration": None,
            "label": "infer",
            "text": "-",
            "num_speakers": args.num_speakers,
            "rttm_filepath": None,
            "uem_filepath": None,
        }
        manifest.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        cfg = config(manifest, scratch, args.model, args.num_speakers is not None)
        start = perf_counter()
        diarizer = ClusteringDiarizer(cfg=cfg)
        loaded = perf_counter()
        diarizer.diarize()
        finished = perf_counter()
        turns = read_rttm(scratch / "pred_rttms" / f"{args.audio.stem}.rttm")
    meta = {
        "backend": "nemo-clustering",
        "version": nemo.__version__,
        "settings": {
            "vad_model": VAD_MODEL,
            "vad": VAD,
            "embeddings": EMBEDDINGS,
            "clustering": CLUSTERING,
        },
        "load_seconds": loaded - start,
        "diarize_seconds": finished - loaded,
        "peak_vram_mib": vram.peak_mib,
    }
    finish_diarization(args, "nemo-diar", turns, meta)


if __name__ == "__main__":
    main()
