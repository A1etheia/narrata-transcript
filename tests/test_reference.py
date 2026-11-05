import datetime
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

import transcript
from transcript import jsonfile
from transcript.asr import (
    BackendResult,
    Capabilities,
    ResourceError,
    ResultSegment,
    ResultWord,
    TranscriptionRequest,
    opened,
    transcribe,
)
from transcript.asr.fake import FAKE_INFO, FakeBackend
from transcript.jsonfile import DataFileError
from transcript.manifest import Manifest, Segment, SourceRecording
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
    failed_reference,
    from_backend_result,
    load_reference,
    majority_speaker,
    to_json,
    write_reference,
)
from transcript.session import SessionKey, SessionPaths

KEY = SessionKey("beispielgruppe", 42)
PLAY_SESSION_ID = 4711  # made up; real ids never enter the repo
SECRET = "Drachenhort"  # stands in for text that must not reach a message
NOW = datetime.datetime(2026, 11, 4, 20, 0, tzinfo=datetime.timezone.utc)
SEGMENT = Segment(
    index=2,
    file="segment-02.wav",
    source=SourceRecording(
        file="aufnahme 2.m4a",
        size_bytes=1000,
        sha256="ef" * 32,
        container="mov,mp4,m4a,3gp,3g2,mj2",
        audio_index=0,
        stream_index=0,
    ),
    frames=160000,
    start_ms=3_600_000,
    end_ms=3_610_000,
    overlap_before_ms=0,
)
MANIFEST = Manifest(
    key=KEY,
    play_session_id=PLAY_SESSION_ID,
    session_date=datetime.date(2026, 11, 4),
    consent=None,
    sample_rate=16000,
    channels=1,
    segments=(SEGMENT,),
)


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
            knowledge_snapshot_id="ab" * 32,
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

    def test_version_1_is_read_without_a_snapshot_id(self) -> None:
        data = to_json(full())
        data["format_version"] = 1
        del data["asr"]["knowledge_snapshot_id"]
        self.store(data)

        loaded = load_reference(self.paths, 1)

        self.assertIsNone(loaded.asr.knowledge_snapshot_id)
        self.assertEqual(loaded.asr.keywords_used, full().asr.keywords_used)

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
            "snapshot id not a string": lambda d: d["asr"].update(
                knowledge_snapshot_id=1
            ),
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


class AdapterTest(ReferenceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.audio = self.paths.audio_dir / SEGMENT.file
        self.audio.parent.mkdir(parents=True)
        self.audio.touch()

    def run_backend(self, backend: FakeBackend) -> BackendResult:
        request = TranscriptionRequest(self.audio, language="de", keywords=(SECRET,))
        with opened(backend):
            return transcribe(backend, request)

    def store_result(self, backend: FakeBackend) -> BackendResult:
        result = self.run_backend(backend)
        reference = from_backend_result(
            result, backend, MANIFEST, SEGMENT, elapsed_ms=812, now=NOW
        )
        write_reference(self.paths, reference, result.raw)
        return result

    def test_backend_with_times_and_confidence(self) -> None:
        answer = BackendResult(
            info=FAKE_INFO,
            language="de",
            language_probability=0.97,
            keywords_used=(SECRET,),
            settings={"beam_size": 5},
            raw={"segments": [{"text": f" Zum {SECRET}.", "avg_logprob": -0.2}]},
            segments=(
                ResultSegment(
                    text=f" Zum {SECRET}.",
                    start=0.25,
                    end=1.5,
                    signals={"avg_logprob": -0.2},
                    words=(
                        ResultWord("Zum", 0.25, 0.6, 0.91),
                        ResultWord(f"{SECRET}.", 0.6, 1.5, 0.42),
                    ),
                ),
            ),
        )
        backend = FakeBackend(
            answer,
            capabilities=Capabilities(
                word_timestamps=True,
                segment_timestamps=True,
                keyword_biasing=True,
                word_confidence=True,
                segment_signals=True,
            ),
        )
        self.store_result(backend)

        reference = load_reference(self.paths, 2)
        passage = reference.passages[0]
        self.assertEqual(reference.status, "transcribed")
        self.assertEqual(reference.segment.source_sha256, "ef" * 32)
        self.assertEqual((passage.start_ms, passage.end_ms), (250, 1500))
        self.assertEqual(passage.text, f" Zum {SECRET}.")
        self.assertEqual(passage.words[1], Word(f"{SECRET}.", 600, 1500, 0.42))
        self.assertEqual(passage.signals, {"avg_logprob": -0.2})
        self.assertEqual(reference.asr.keywords_used, (SECRET,))
        self.assertTrue(reference.asr.capabilities["word_confidence"])
        self.assertEqual(reference.asr.language_probability, 0.97)
        self.assertEqual(reference.processing.elapsed_ms, 812)
        self.assertEqual(reference.processing.processed_at, "2026-11-04T20:00:00+00:00")
        self.assertEqual(reference.processing.pipeline_version, transcript.__version__)
        self.assertIsNone(reference.diarization)

    def test_backend_without_times_lands_in_the_same_format(self) -> None:
        answer = BackendResult(
            info=FAKE_INFO, segments=(ResultSegment(text="Nur Text."),)
        )
        self.store_result(FakeBackend(answer))

        passage = load_reference(self.paths, 2).passages[0]
        self.assertEqual(passage, Passage(index=1, text="Nur Text."))

    def test_backend_speaker_label_is_kept_without_word_labels(self) -> None:
        segment = ResultSegment(text="Hallo.", speaker="SPEAKER_00")
        self.store_result(FakeBackend(BackendResult(FAKE_INFO, (segment,))))

        self.assertEqual(
            load_reference(self.paths, 2).passages[0].speaker, "SPEAKER_00"
        )

    def test_raw_answer_is_stored_apart_and_unchanged(self) -> None:
        raw = {"hypotheses": [{"text": SECRET, "timestamp": {"word": []}}]}
        answer = BackendResult(info=FAKE_INFO, segments=(), raw=raw)
        self.store_result(FakeBackend(answer))

        stored = jsonfile.read_object(self.paths.reference_raw(2), "raw")
        normal = self.paths.reference(2).read_text(encoding="utf-8")
        self.assertEqual(stored, {"backend_id": "fake", "raw": raw})
        self.assertNotIn("hypotheses", normal)
        self.assertEqual(
            load_reference(self.paths, 2).raw_file, self.paths.reference_raw(2).name
        )

    def test_a_backend_error_becomes_a_failed_segment_without_message(self) -> None:
        backend = FakeBackend(error=ResourceError(f"fake: {SECRET}"))
        with self.assertRaises(ResourceError) as caught:
            self.run_backend(backend)
        reference = failed_reference(
            caught.exception, backend, MANIFEST, SEGMENT, now=NOW
        )
        write_reference(self.paths, reference, None)

        loaded = load_reference(self.paths, 2)
        self.assertEqual(loaded.status, "failed")
        self.assertEqual(loaded.error, Failure("ResourceError", retryable=True))
        self.assertEqual(loaded.passages, ())
        self.assertEqual(loaded.asr.backend_id, "fake")
        self.assertNotIn(SECRET, self.paths.reference(2).read_text(encoding="utf-8"))

    def test_raw_is_written_before_the_transcript(self) -> None:
        reference = from_backend_result(
            BackendResult(FAKE_INFO, ()), FakeBackend(), MANIFEST, SEGMENT, now=NOW
        )
        written = []
        original = jsonfile.write_atomic

        def record(path: Path, data: dict[str, Any]) -> None:
            written.append(path.name)
            original(path, data)

        with unittest.mock.patch.object(jsonfile, "write_atomic", record):
            write_reference(self.paths, reference, None)

        self.assertEqual(written, ["segment-02.raw.json", "segment-02.json"])

    def test_writing_into_another_session_is_refused(self) -> None:
        reference = from_backend_result(
            BackendResult(FAKE_INFO, ()), FakeBackend(), MANIFEST, SEGMENT, now=NOW
        )
        other = SessionPaths(SessionKey("andere-gruppe", 1), self.paths.root)

        with self.assertRaises(ValueError):
            write_reference(other, reference, None)
        self.assertFalse(other.asr_dir.exists())


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
