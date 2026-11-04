"""Opt-in end-to-end smoke test: Whisper, then pyannote, on synthesized speech.

Runs only with TRANSCRIPT_DIARIZATION_SMOKE=1, the `whisper` and `diarization`
extras and an ffmpeg built with flite; see README, "Diarisierung". Once opted in,
a model missing from the cache fails the test instead of skipping it.
TRANSCRIPT_DIARIZATION_DEVICE picks the device for both models (default: auto).

Two made-up sentences are spoken with two flite voices. pyannote does not
reliably tell these synthetic voices apart on a few seconds of audio, so the test
checks that words get labels, not how many speakers it finds.
"""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from media import flite_missing, speech, synth
from test_reference import MANIFEST, SEGMENT

from transcript.asr import TranscriptionRequest, opened, transcribe
from transcript.asr.whisper import WhisperBackend
from transcript.diarization import diarize_session, load_run
from transcript.diarization.pyannote import PyannoteDiarizer
from transcript.reference import from_backend_result, load_reference, write_reference
from transcript.session import SessionPaths

SENTENCES = (
    ("The dragon sleeps on a hoard of gold in the old tower.", "kal"),
    ("We should wait until morning before we climb the stairs.", "slt"),
)


def _skip_reason() -> str:
    if os.environ.get("TRANSCRIPT_DIARIZATION_SMOKE") != "1":
        return "set TRANSCRIPT_DIARIZATION_SMOKE=1 to run the real models"
    for module, extra in (("faster_whisper", "whisper"), ("pyannote", "diarization")):
        if importlib.util.find_spec(module) is None:
            return f"install the {extra} extra: pip install -e '.[{extra}]'"
    return flite_missing()


SKIP_REASON = _skip_reason()


@unittest.skipIf(SKIP_REASON, SKIP_REASON)
class DiarizationSmokeTest(unittest.TestCase):
    def test_session_runs_from_transcription_to_labelled_words(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = SessionPaths(MANIFEST.key, Path(directory))
            audio = paths.segment_wav(SEGMENT.index)
            audio.parent.mkdir(parents=True)
            (first, first_voice), (second, second_voice) = SENTENCES
            synth(
                audio,
                *speech(first, first_voice),
                *speech(second, second_voice),
                *("-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1"),
                *("-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le"),
            )
            device = os.environ.get("TRANSCRIPT_DIARIZATION_DEVICE", "auto")

            backend = WhisperBackend(device=device)
            with opened(backend):  # closed before pyannote needs the memory
                result = transcribe(backend, TranscriptionRequest(audio, "en"))
            transcribed = from_backend_result(result, backend, MANIFEST, SEGMENT)
            write_reference(paths, transcribed, result.raw)

            summaries = diarize_session(
                paths, MANIFEST, PyannoteDiarizer(device=device)
            )

            self.assertEqual([s.outcome for s in summaries], ["diarized"])
            self.assertGreater(summaries[0].labelled_words, 0)
            labelled = load_reference(paths, SEGMENT.index)
            self.assertEqual(labelled.text, transcribed.text)
            diarization = labelled.diarization
            self.assertIsNotNone(diarization.model_version)
            self.assertTrue(diarization.labels)
            speakers = {
                word.speaker for passage in labelled.passages for word in passage.words
            }
            self.assertTrue(speakers - {None} <= set(diarization.labels))
            stored = load_run(paths, SEGMENT.index)

            again = diarize_session(paths, MANIFEST, PyannoteDiarizer(device=device))

            self.assertEqual([s.outcome for s in again], ["reused"])
            self.assertEqual(load_run(paths, SEGMENT.index), stored)
            self.assertEqual(load_reference(paths, SEGMENT.index), labelled)


if __name__ == "__main__":
    unittest.main()
