import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from test_reference import KEY, MANIFEST, SEGMENT, minimal

from transcript.asr import BackendInfo, ResourceError
from transcript.audio import sha256_file
from transcript.diarization import (
    DIARIZATION_FORMAT_VERSION,
    DiarizationError,
    DiarizationRun,
    SegmentSummary,
    Turn,
    assign_speakers,
    diarize_session,
    load_run,
    overlaps,
    to_json,
    write_run,
)
from transcript.reference import (
    Diarization,
    Failure,
    Overlap,
    Passage,
    ReferenceTranscript,
    Word,
    load_reference,
    update_reference,
)
from transcript.reference import (
    to_json as reference_json,
)
from transcript.session import SessionPaths

SECRET = "Drachenhort"  # stands in for text that must not reach a message
INFO = BackendInfo(
    backend_id="fake-diar",
    model="fake-diar",
    model_version="rev-1",
    runtime_version="1",
)
AUDIO = "cd" * 32


def reference(*passages: Passage, **changes: Any) -> ReferenceTranscript:
    return minimal(passages=passages, **changes)


def run(*exclusive: Turn, turns: tuple[Turn, ...] | None = None, **changes: Any):
    values: dict[str, Any] = {
        "info": INFO,
        "audio_sha256": AUDIO,
        "turns": exclusive if turns is None else turns,
        "exclusive_turns": exclusive,
        "settings": {"device": "auto"},
    }
    values.update(changes)
    return DiarizationRun(**values)


def words_of(result: ReferenceTranscript) -> list[str | None]:
    return [word.speaker for passage in result.passages for word in passage.words]


class AssignSpeakersTest(unittest.TestCase):
    def test_word_takes_the_turn_its_midpoint_lies_in(self) -> None:
        passage = Passage(
            index=1,
            text=" Wir betreten den Hort.",
            words=(
                Word("Wir", 0, 400),  # midpoint 200 in A
                Word("betreten", 900, 1300),  # midpoint 1100 in B, starts in A
                Word("den", 1300, 1500),  # midpoint 1400 in B
                Word(f"{SECRET}.", 1500, 2000),  # midpoint 1750 in B
            ),
        )
        result = assign_speakers(
            reference(passage),
            run(Turn(0, 1000, "SPEAKER_00"), Turn(1000, 3000, "SPEAKER_01")),
        )

        self.assertEqual(
            words_of(result), ["SPEAKER_00", "SPEAKER_01", "SPEAKER_01", "SPEAKER_01"]
        )
        self.assertEqual(result.passages[0].speaker, "SPEAKER_01")

    def test_turns_are_half_open(self) -> None:
        passage = Passage(
            index=1,
            text=" a b",
            words=(Word("a", 900, 1100), Word("b", 1900, 2100)),  # midpoints 1000, 2000
        )
        result = assign_speakers(
            reference(passage),
            run(Turn(0, 1000, "SPEAKER_00"), Turn(1000, 2000, "SPEAKER_01")),
        )

        self.assertEqual(words_of(result), ["SPEAKER_01", None])

    def test_word_outside_every_turn_stays_unlabelled(self) -> None:
        passage = Passage(
            index=1,
            text=" a b c",
            words=(Word("a", 0, 100), Word("b", 2000, 2200), Word("c", 5000, 5200)),
        )
        result = assign_speakers(
            reference(passage),
            run(Turn(1000, 3000, "SPEAKER_00")),
        )

        self.assertEqual(words_of(result), [None, "SPEAKER_00", None])

    def test_word_without_times_stays_unlabelled(self) -> None:
        passage = Passage(
            index=1, text=" a b", words=(Word("a"), Word("b", start_ms=10))
        )
        result = assign_speakers(reference(passage), run(Turn(0, 1000, "SPEAKER_00")))

        self.assertEqual(words_of(result), [None, None])
        self.assertIsNone(result.passages[0].speaker)

    def test_passage_speaker_is_the_word_majority_or_none_on_a_tie(self) -> None:
        tie = Passage(
            index=1, text=" a b", words=(Word("a", 0, 100), Word("b", 1000, 1100))
        )
        empty = Passage(index=2, text=" Ja.")
        result = assign_speakers(
            reference(tie, empty),
            run(Turn(0, 500, "SPEAKER_00"), Turn(500, 2000, "SPEAKER_01")),
        )

        self.assertEqual(words_of(result), ["SPEAKER_00", "SPEAKER_01"])
        self.assertEqual([p.speaker for p in result.passages], [None, None])

    def test_only_speaker_fields_change(self) -> None:
        passage = Passage(
            index=1,
            text=f" Wir betreten den {SECRET}.",
            start_ms=0,
            end_ms=2000,
            speaker="OLD",
            signals={"avg_logprob": -0.2},
            words=(Word("Wir", 0, 300, 0.9, "OLD"), Word(SECRET, 300, 2000, 0.3)),
        )
        before = reference(passage)
        result = assign_speakers(before, run(Turn(0, 2000, "SPEAKER_00")))

        def without_speakers(transcript: ReferenceTranscript) -> ReferenceTranscript:
            return dataclasses.replace(
                transcript,
                diarization=None,
                passages=tuple(
                    dataclasses.replace(
                        p,
                        speaker=None,
                        words=tuple(
                            dataclasses.replace(w, speaker=None) for w in p.words
                        ),
                    )
                    for p in transcript.passages
                ),
            )

        self.assertEqual(without_speakers(result), without_speakers(before))
        self.assertEqual(words_of(result), ["SPEAKER_00", "SPEAKER_00"])

    def test_diarization_block_holds_run_metadata_labels_and_overlaps(self) -> None:
        result = assign_speakers(
            reference(),
            run(
                Turn(0, 1000, "SPEAKER_01"),
                Turn(1200, 2000, "SPEAKER_00"),
                turns=(
                    Turn(0, 1100, "SPEAKER_01"),
                    Turn(900, 2000, "SPEAKER_00"),
                    Turn(2500, 2600, "SPEAKER_02"),
                ),
                num_speakers=3,
            ),
        )

        self.assertEqual(
            result.diarization,
            Diarization(
                backend_id="fake-diar",
                model="fake-diar",
                model_version="rev-1",
                settings={"device": "auto"},
                num_speakers=3,
                labels=("SPEAKER_00", "SPEAKER_01", "SPEAKER_02"),
                overlaps=(Overlap(900, 1100),),
            ),
        )

    def test_failed_segment_is_rejected(self) -> None:
        failed = reference(
            status="failed", error=Failure(category="ResourceError", retryable=True)
        )
        with self.assertRaises(ValueError):
            assign_speakers(failed, run(Turn(0, 1000, "SPEAKER_00")))


class OverlapsTest(unittest.TestCase):
    def test_ranges_with_two_or_more_turns(self) -> None:
        cases = (
            ((), ()),
            (((0, 1000), (1000, 2000)), ()),  # touching is not overlapping
            (((0, 1000), (500, 1500)), ((500, 1000),)),
            (((0, 3000), (500, 1000), (800, 2000)), ((500, 2000),)),  # three at once
            (((0, 1000), (900, 2000), (1000, 1500)), ((900, 1500),)),  # adjacent
            (((0, 1000), (200, 400), (600, 800)), ((200, 400), (600, 800))),
            (((0, 1000), (500, 500)), ()),  # empty turn
        )
        for spans, expected in cases:
            with self.subTest(spans=spans):
                turns = [
                    Turn(start, end, f"S{i}") for i, (start, end) in enumerate(spans)
                ]
                self.assertEqual(
                    overlaps(turns), tuple(Overlap(s, e) for s, e in expected)
                )


class DiarizationRunTest(unittest.TestCase):
    def test_invalid_values_are_rejected(self) -> None:
        for build in (
            lambda: Turn(-1, 10, "S"),
            lambda: Turn(20, 10, "S"),
            lambda: Turn(0, 10, ""),
            lambda: run(Turn(0, 1000, "A"), Turn(900, 2000, "B")),
            lambda: run(num_speakers=0),
        ):
            with self.assertRaises(ValueError):
                build()

    def test_matches_only_the_same_inputs(self) -> None:
        stored = run(Turn(0, 1000, "SPEAKER_00"), num_speakers=4)
        same = (INFO, {"device": "auto"}, 4, AUDIO)

        self.assertTrue(stored.matches(*same))
        self.assertTrue(
            stored.matches(dataclasses.replace(INFO, runtime_version="2"), *same[1:])
        )
        for name, changed in (
            ("backend", (dataclasses.replace(INFO, backend_id="x"), *same[1:])),
            ("model", (dataclasses.replace(INFO, model="x"), *same[1:])),
            ("revision", (dataclasses.replace(INFO, model_version="rev-2"), *same[1:])),
            ("settings", (INFO, {"device": "cpu"}, 4, AUDIO)),
            ("num_speakers", (INFO, {"device": "auto"}, None, AUDIO)),
            ("audio", (INFO, {"device": "auto"}, 4, "ef" * 32)),
        ):
            with self.subTest(changed=name):
                self.assertFalse(stored.matches(*changed))


class StoredRunTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(KEY, Path(directory.name))

    def test_round_trip(self) -> None:
        stored = run(
            Turn(0, 1000, "SPEAKER_00"),
            Turn(1200, 2000, "SPEAKER_01"),
            turns=(Turn(0, 1100, "SPEAKER_00"), Turn(900, 2000, "SPEAKER_01")),
            num_speakers=2,
        )
        write_run(self.paths, 3, stored)

        self.assertEqual(load_run(self.paths, 3), stored)
        data = json.loads(self.paths.diarization_raw(3).read_text(encoding="utf-8"))
        self.assertEqual(next(iter(data)), "format_version")
        self.assertEqual(data["format_version"], DIARIZATION_FORMAT_VERSION)

    def test_missing_or_outdated_file_counts_as_absent(self) -> None:
        self.assertIsNone(load_run(self.paths, 1))

        data = to_json(run(Turn(0, 1000, "SPEAKER_00")))
        data["format_version"] = DIARIZATION_FORMAT_VERSION + 1
        self.write(data)
        self.assertIsNone(load_run(self.paths, 1))

    def test_invalid_file_names_path_and_field_but_no_label(self) -> None:
        cases = []
        for field_name in ("model", "audio_sha256", "settings", "turns"):
            data = to_json(run(Turn(0, 1000, SECRET)))
            del data[field_name]
            cases.append((field_name, data))
        data = to_json(run(Turn(0, 1000, SECRET)))
        data["turns"][0]["end_ms"] = -5
        cases.append(("turn time", data))

        for expected, data in cases:
            with self.subTest(expected=expected):
                self.write(data)
                with self.assertRaises(DiarizationError) as caught:
                    load_run(self.paths, 1)
                message = str(caught.exception)
                self.assertIn(str(self.paths.diarization_raw(1)), message)
                self.assertIn(expected, message)
                self.assertNotIn(SECRET, message)

    def test_unreadable_file_is_an_error(self) -> None:
        path = self.paths.diarization_raw(1)
        path.parent.mkdir(parents=True)
        path.write_text("{", encoding="utf-8")

        with self.assertRaises(DiarizationError):
            load_run(self.paths, 1)

    def write(self, data: dict[str, Any]) -> None:
        path = self.paths.diarization_raw(1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")


class FakeDiarizer:
    """Answers with fixed turns and counts what it was asked to do."""

    def __init__(self, info: BackendInfo = INFO) -> None:
        self.settings = {"device": "cpu"}
        self.info = info
        self.load_calls = 0
        self.close_calls = 0
        self.diarized: list[tuple[str, str, int | None]] = []

    def identity(self) -> BackendInfo:
        return self.info

    def load(self) -> None:
        self.load_calls += 1

    def diarize(
        self,
        audio: Path,
        info: BackendInfo,
        audio_sha256: str,
        num_speakers: int | None = None,
    ) -> DiarizationRun:
        assert self.load_calls == 1
        self.diarized.append((audio.name, audio_sha256, num_speakers))
        return DiarizationRun(
            info=info,
            audio_sha256=audio_sha256,
            turns=(Turn(0, 1000, "SPEAKER_00"), Turn(800, 2000, "SPEAKER_01")),
            exclusive_turns=(
                Turn(0, 800, "SPEAKER_00"),
                Turn(1000, 2000, "SPEAKER_01"),
            ),
            settings=self.settings,
            num_speakers=num_speakers,
        )

    def close(self) -> None:
        self.close_calls += 1


class DiarizeSessionTest(unittest.TestCase):
    """Segment 1 transcribed, 2 failed, 3 without transcript."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(KEY, Path(directory.name))
        self.manifest = dataclasses.replace(
            MANIFEST,
            segments=tuple(
                dataclasses.replace(SEGMENT, index=i, file=f"segment-0{i}.wav")
                for i in (1, 2, 3)
            ),
        )
        self.paths.audio_dir.mkdir(parents=True)
        for index in (1, 2, 3):
            self.paths.segment_wav(index).write_bytes(b"audio %d" % index)
        self.transcribed = minimal(
            passages=(
                Passage(
                    index=1,
                    text=f" Wir betreten den {SECRET}.",
                    words=(
                        Word("Wir", 0, 400),  # in SPEAKER_00
                        Word("den", 850, 950),  # in no exclusive turn
                        Word(SECRET, 1200, 1800),  # in SPEAKER_01
                    ),
                ),
            )
        )
        update_reference(self.paths, self.transcribed)
        update_reference(
            self.paths,
            minimal(
                segment=dataclasses.replace(self.transcribed.segment, index=2),
                status="failed",
                error=Failure(category="ResourceError", retryable=True),
            ),
        )

    def diarize(self, diarizer: FakeDiarizer, **options: Any) -> list[SegmentSummary]:
        return diarize_session(self.paths, self.manifest, diarizer, **options)

    def test_transcribed_segments_get_labels_and_others_are_skipped(self) -> None:
        diarizer = FakeDiarizer()

        summaries = self.diarize(diarizer, num_speakers=2)

        self.assertEqual(
            [(s.index, s.outcome, s.reason) for s in summaries],
            [
                (1, "diarized", None),
                (2, "skipped", "transcription failed"),
                (3, "skipped", "no transcript"),
            ],
        )
        first = summaries[0]
        self.assertEqual(
            (first.labels, first.turns, first.words, first.labelled_words),
            (2, 2, 3, 2),
        )
        self.assertIsNotNone(first.elapsed_ms)
        stored = load_reference(self.paths, 1)
        self.assertEqual(words_of(stored), ["SPEAKER_00", None, "SPEAKER_01"])
        self.assertEqual(stored.diarization.num_speakers, 2)
        self.assertEqual(stored.diarization.overlaps, (Overlap(800, 1000),))
        self.assertEqual(
            diarizer.diarized,
            [("segment-01.wav", sha256_file(self.paths.segment_wav(1)), 2)],
        )
        self.assertEqual((diarizer.load_calls, diarizer.close_calls), (1, 1))
        self.assertIsNotNone(load_run(self.paths, 1))

    def test_asr_result_and_raw_file_stay_as_they_were(self) -> None:
        raw = self.paths.reference_raw(1)
        raw.write_text('{"backend_id": "fake", "raw": {}}', encoding="utf-8")
        before = raw.read_bytes()

        self.diarize(FakeDiarizer())

        self.assertEqual(raw.read_bytes(), before)
        stored = load_reference(self.paths, 1)
        stripped = reference_json(dataclasses.replace(stored, diarization=None))
        for passage in stripped["passages"]:
            passage["speaker"] = None
            for word in passage["words"]:
                word["speaker"] = None
        self.assertEqual(stripped, reference_json(self.transcribed))

    def test_second_run_reuses_the_stored_diarization_without_loading(self) -> None:
        self.diarize(FakeDiarizer())
        update_reference(self.paths, self.transcribed)  # e.g. after a new ASR run
        again = FakeDiarizer()

        summaries = self.diarize(again)

        self.assertEqual(summaries[0].outcome, "reused")
        self.assertIsNone(summaries[0].elapsed_ms)
        self.assertEqual(
            (again.load_calls, again.close_calls, again.diarized), (0, 0, [])
        )
        self.assertEqual(
            words_of(load_reference(self.paths, 1)), ["SPEAKER_00", None, "SPEAKER_01"]
        )

    def test_changed_inputs_or_force_diarize_again(self) -> None:
        newer = dataclasses.replace(INFO, model_version="rev-2")
        for name, diarizer, options, new_audio in (
            ("force", FakeDiarizer(), {"force": True}, False),
            ("num_speakers", FakeDiarizer(), {"num_speakers": 3}, False),
            ("revision", FakeDiarizer(newer), {}, False),
            ("audio", FakeDiarizer(), {}, True),
        ):
            with self.subTest(changed=name):
                self.paths.segment_wav(1).write_bytes(b"audio 1")
                self.diarize(FakeDiarizer(), force=True)  # the stored baseline
                if new_audio:
                    self.paths.segment_wav(1).write_bytes(b"other audio")

                summaries = self.diarize(diarizer, **options)

                self.assertEqual(summaries[0].outcome, "diarized")
                self.assertEqual(len(diarizer.diarized), 1)

    def test_unchanged_reference_is_not_rewritten(self) -> None:
        self.diarize(FakeDiarizer())
        written = self.paths.reference(1).stat().st_mtime_ns

        with mock.patch("transcript.diarization.update_reference") as update:
            self.diarize(FakeDiarizer())
        update.assert_not_called()
        self.assertEqual(self.paths.reference(1).stat().st_mtime_ns, written)

    def test_diarizer_is_closed_when_a_segment_fails(self) -> None:
        diarizer = FakeDiarizer()
        diarizer.diarize = mock.Mock(side_effect=ResourceError("pyannote: oom"))

        with self.assertRaises(ResourceError):
            self.diarize(diarizer)
        self.assertEqual(diarizer.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
