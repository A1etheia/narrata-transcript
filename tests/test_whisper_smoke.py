"""Opt-in smoke test with the real Whisper model; see README, "Spracherkennung".

Runs only with TRANSCRIPT_WHISPER_SMOKE=1, the `whisper` extra and an ffmpeg built
with flite. Once opted in, a model missing from the cache or missing CUDA libraries
fail the test instead of skipping it. TRANSCRIPT_WHISPER_DEVICE picks the
device (default: auto). The speech is synthesized at runtime from a made-up
sentence; flite speaks English, so this run uses language "en".
"""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from media import flite_missing, speech, synth
from test_reference import MANIFEST, SEGMENT

from transcript.asr.whisper import WhisperBackend
from transcript.reference import load_reference
from transcript.session import SessionPaths
from transcript.transcription import transcribe_session

SENTENCE = "The dragon sleeps on a hoard of gold in the old tower."


def _skip_reason() -> str:
    if os.environ.get("TRANSCRIPT_WHISPER_SMOKE") != "1":
        return "set TRANSCRIPT_WHISPER_SMOKE=1 to run the real model"
    if importlib.util.find_spec("faster_whisper") is None:
        return "install the whisper extra: pip install -e '.[whisper]'"
    return flite_missing()


SKIP_REASON = _skip_reason()


@unittest.skipIf(SKIP_REASON, SKIP_REASON)
class WhisperSmokeTest(unittest.TestCase):
    def test_short_speech_is_transcribed_locally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = SessionPaths(MANIFEST.key, root)
            paths.audio_dir.mkdir(parents=True)
            synth(
                paths.segment_wav(SEGMENT.index),
                *speech(SENTENCE),
                *("-ar", "16000", "-ac", "1"),
            )
            device = os.environ.get("TRANSCRIPT_WHISPER_DEVICE", "auto")
            # a missing model or CUDA library fails here
            run = transcribe_session(
                paths,
                MANIFEST,
                WhisperBackend(device=device),
                "en",
                keywords=("hoard",),
            )
            summary = run.outcomes[0]
            self.assertEqual(summary.status, "transcribed")

            reference = load_reference(paths, SEGMENT.index)
            self.assertEqual(reference.status, "transcribed")
            self.assertIn("dragon", reference.text.lower())
            words = reference.words
            self.assertTrue(words)
            self.assertEqual(summary.words, len(words))
            for word in words:
                self.assertLessEqual(word.start_ms, word.end_ms)
                self.assertTrue(0 <= word.confidence <= 1)
            self.assertEqual(reference.asr.keywords_used, ("hoard",))
            self.assertIsNotNone(reference.asr.model_version)
            self.assertIsNotNone(reference.asr.runtime_version)
            self.assertGreater(reference.processing.elapsed_ms, 0)
            self.assertTrue(paths.reference_raw(SEGMENT.index).is_file())


if __name__ == "__main__":
    unittest.main()
