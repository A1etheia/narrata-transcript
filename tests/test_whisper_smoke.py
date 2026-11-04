"""Opt-in smoke test with the real Whisper model; see README, "Spracherkennung".

Runs only with TRANSCRIPT_WHISPER_SMOKE=1, the `whisper` extra and an ffmpeg built
with flite. Once opted in, a model missing from the cache or missing CUDA libraries
fail the test instead of skipping it. TRANSCRIPT_WHISPER_DEVICE picks the
device (default: auto). The speech is synthesized at runtime from a made-up
sentence; flite speaks English, so this run uses language "en".
"""

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from media import TOOLS, synth
from test_reference import MANIFEST, SEGMENT

from transcript.asr import TranscriptionRequest, opened, transcribe
from transcript.asr.whisper import WhisperBackend
from transcript.reference import from_backend_result, load_reference, write_reference
from transcript.session import SessionPaths

SENTENCE = "The dragon sleeps on a hoard of gold in the old tower."


def _skip_reason() -> str:
    if os.environ.get("TRANSCRIPT_WHISPER_SMOKE") != "1":
        return "set TRANSCRIPT_WHISPER_SMOKE=1 to run the real model"
    if importlib.util.find_spec("faster_whisper") is None:
        return "install the whisper extra: pip install -e '.[whisper]'"
    if TOOLS is None:
        return "ffmpeg is needed to synthesize speech"
    filters = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if " flite " not in filters:
        return "ffmpeg lacks the flite filter"
    return ""


SKIP_REASON = _skip_reason()


@unittest.skipIf(SKIP_REASON, SKIP_REASON)
class WhisperSmokeTest(unittest.TestCase):
    def test_short_speech_is_transcribed_locally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = synth(
                root / "speech.wav",
                *("-f", "lavfi", "-i", f"flite=text='{SENTENCE}'"),
                *("-ar", "16000", "-ac", "1"),
            )
            device = os.environ.get("TRANSCRIPT_WHISPER_DEVICE", "auto")
            backend = WhisperBackend(device=device)
            request = TranscriptionRequest(audio, language="en", keywords=("hoard",))
            with opened(backend):  # a missing model or CUDA library fails here
                result = transcribe(backend, request)

            text = " ".join(segment.text for segment in result.segments).lower()
            self.assertIn("dragon", text)
            words = [word for segment in result.segments for word in segment.words]
            self.assertTrue(words)
            for word in words:
                self.assertLessEqual(word.start, word.end)
                self.assertTrue(0 <= word.confidence <= 1)
            self.assertEqual(result.keywords_used, ("hoard",))
            self.assertIsNotNone(result.info.model_version)
            self.assertIsNotNone(result.info.runtime_version)

            paths = SessionPaths(MANIFEST.key, root)
            reference = from_backend_result(result, backend, MANIFEST, SEGMENT)
            write_reference(paths, reference, result.raw)
            self.assertEqual(load_reference(paths, SEGMENT.index), reference)


if __name__ == "__main__":
    unittest.main()
