import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from transcript import jsonfile
from transcript.jsonfile import DataFileError
from transcript.reference import (
    REFERENCE_FORMAT_VERSION,
    AsrInfo,
    Diarization,
    Failure,
    Overlap,
    Passage,
    Processing,
    ReferenceError,
    ReferenceTranscript,
    SegmentRef,
    Word,
    load_reference,
    majority_speaker,
    to_json,
)
from transcript.session import SessionKey, SessionPaths

KEY = SessionKey("beispielgruppe", 42)
PLAY_SESSION_ID = 4711  # made up; real ids never enter the repo
SECRET = "Drachenhort"  # stands in for text that must not reach a message


def minimal(**changes: Any) -> ReferenceTranscript:
    """A transcript with every optional field left empty."""
    values: dict[str, Any] = {
        "key": KEY,
        "play_session_id": PLAY_SESSION_ID,
        "segment": SegmentRef(index=1, file="segment-01.wav", source_sha256="ab" * 32),
        "status": "transcribed",
        "asr": AsrInfo(backend_id="fake", model="fake"),
        "processing": Processing(
            pipeline_version="0.0.1", processed_at="2026-11-04T20:00:00+01:00"
        ),
    }
    values.update(changes)
    return ReferenceTranscript(**values)


def full() -> ReferenceTranscript:
    """A transcript with every optional field filled."""
    return minimal(
        asr=AsrInfo(
            backend_id="fake",
            model="fake-large",
            model_version="rev-1",
            runtime_version="1.2.3",
            capabilities={"word_timestamps": True, "devices": ["cpu"]},
            settings={"beam_size": 5},
            language="de",
            language_probability=0.98,
            keywords_used=(SECRET, "Beispielfigur"),
        ),
        processing=Processing(
            pipeline_version="0.0.1",
            processed_at="2026-11-04T20:00:00+01:00",
            elapsed_ms=1234,
        ),
        diarization=Diarization(
            backend_id="fake-diar",
            model="fake-diar",
            model_version="rev-2",
            settings={"min_duration_off": 0.0},
            num_speakers=2,
            labels=("SPEAKER_00", "SPEAKER_01"),
            overlaps=(Overlap(start_ms=900, end_ms=1100),),
        ),
        passages=(
            Passage(
                index=1,
                text=f" Wir betreten den {SECRET}.",
                start_ms=0,
                end_ms=1500,
                speaker="SPEAKER_00",
                signals={"avg_logprob": -0.21, "no_speech_prob": 0.01},
                words=(
                    Word("Wir", 0, 300, 0.95, "SPEAKER_00"),
                    Word("betreten", 300, 800, 0.9, "SPEAKER_00"),
                    Word("den", 800, 1000, 0.5, None),
                    Word(f"{SECRET}.", 1000, 1500, 0.3, "SPEAKER_01"),
                ),
            ),
            Passage(index=2, text=" Ja."),
        ),
    )


class ReferenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(KEY, Path(directory.name))

    def store(self, data: dict[str, Any], index: int = 1) -> None:
        jsonfile.write_atomic(self.paths.reference(index), data)

    def assert_rejected(self, data: dict[str, Any], index: int = 1) -> str:
        self.store(data, index)
        with self.assertRaises(ReferenceError) as caught:
            load_reference(self.paths, index)
        message = str(caught.exception)
        self.assertNotIn(SECRET, message)
        self.assertNotIn("SPEAKER_", message)
        return message


class RoundTripTest(ReferenceTestCase):
    def test_full_and_minimal_transcripts_survive_a_round_trip(self) -> None:
        for name, reference in (("full", full()), ("minimal", minimal())):
            with self.subTest(name):
                self.store(to_json(reference))

                self.assertEqual(load_reference(self.paths, 1), reference)

    def test_json_starts_with_the_version_and_names_the_raw_file(self) -> None:
        data = to_json(full())

        self.assertEqual(next(iter(data)), "format_version")
        self.assertEqual(data["format_version"], REFERENCE_FORMAT_VERSION)
        self.assertEqual(data["raw_file"], "segment-01.raw.json")
        self.assertNotIn("raw", data)
        json.dumps(data)

    def test_a_failed_segment_has_an_error_and_no_passages(self) -> None:
        reference = minimal(
            status="failed", error=Failure(category="ResourceError", retryable=True)
        )
        self.store(to_json(reference))

        self.assertEqual(load_reference(self.paths, 1), reference)

    def test_text_joins_the_passages(self) -> None:
        self.assertEqual(full().text, f"Wir betreten den {SECRET}. Ja.")
        self.assertEqual(minimal().text, "")


class InvalidFileTest(ReferenceTestCase):
    def test_missing_file_is_a_data_file_error(self) -> None:
        with self.assertRaises(DataFileError):
            load_reference(self.paths, 1)

    def test_other_version_asks_for_a_new_transcription(self) -> None:
        data = to_json(full())
        data["format_version"] = REFERENCE_FORMAT_VERSION + 1

        self.assertIn("transcribe the segment again", self.assert_rejected(data))

    def test_file_of_another_session_or_segment_is_rejected(self) -> None:
        other_session = to_json(minimal(key=SessionKey("andere-gruppe", 42)))
        self.assertIn("andere-gruppe/042", self.assert_rejected(other_session))

        other_segment = to_json(
            minimal(segment=SegmentRef(2, "segment-02.wav", "cd" * 32))
        )
        self.assertIn("segment 2", self.assert_rejected(other_segment))

    def test_invalid_content_is_rejected_without_text(self) -> None:
        def broken(change: Any) -> dict[str, Any]:
            data = to_json(full())
            change(data)
            return data

        def first_word(data: dict[str, Any]) -> dict[str, Any]:
            return data["passages"][0]["words"][0]

        cases = {
            "word ends before it starts": lambda d: first_word(d).update(
                start_ms=500, end_ms=100
            ),
            "negative passage time": lambda d: d["passages"][0].update(start_ms=-1),
            "confidence above one": lambda d: first_word(d).update(confidence=1.5),
            "confidence as boolean": lambda d: first_word(d).update(confidence=True),
            "label outside the diarization": lambda d: first_word(d).update(
                speaker="SPEAKER_07"
            ),
            "passage out of order": lambda d: d["passages"][1].update(index=5),
            "unknown status": lambda d: d.update(status="halb"),
            "failed without error": lambda d: d.update(status="failed"),
            "error while transcribed": lambda d: d.update(
                error={"category": "ResourceError", "retryable": True}
            ),
            "text missing": lambda d: d["passages"][0].pop("text"),
            "signal not a number": lambda d: d["passages"][0]["signals"].update(
                avg_logprob=SECRET
            ),
            "keyword not a string": lambda d: d["asr"].update(keywords_used=[1]),
            "repeated label": lambda d: d["diarization"].update(
                labels=["SPEAKER_00", "SPEAKER_00"]
            ),
            "play session id missing": lambda d: d.pop("play_session_id"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.assert_rejected(broken(change))

    def test_passage_errors_name_the_passage(self) -> None:
        data = to_json(full())
        data["passages"][1]["start_ms"] = -1

        self.assertIn("passage 2", self.assert_rejected(data))


class MajoritySpeakerTest(unittest.TestCase):
    def test_majority_wins_and_missing_labels_do_not_count(self) -> None:
        words = [
            Word("a", speaker="A"),
            Word("b", speaker="A"),
            Word("c"),
            Word("d", speaker="B"),
        ]

        self.assertEqual(majority_speaker(words), "A")

    def test_tie_or_no_labels_yield_none(self) -> None:
        self.assertIsNone(
            majority_speaker([Word("a", speaker="A"), Word("b", speaker="B")])
        )
        self.assertIsNone(majority_speaker([Word("a"), Word("b")]))
        self.assertIsNone(majority_speaker([]))


if __name__ == "__main__":
    unittest.main()
