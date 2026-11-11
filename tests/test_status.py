import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from media import TOOLS, needs_media, sine, synth
from test_narrata import CHARACTER, NAME, context, encoded
from test_narrata import participant as participant_json
from test_reference import KEY, SECRET, minimal

from transcript import knowledge, status
from transcript.audio import extract, find_recordings, probe
from transcript.config import UncertaintyThresholds, load_config
from transcript.knowledge import build_snapshot, load_snapshot
from transcript.manifest import build_manifest
from transcript.narrata import store_context
from transcript.reference import (
    AsrInfo,
    Diarization,
    Failure,
    Passage,
    Processing,
    SegmentRef,
    Word,
    write_reference,
)
from transcript.session import SessionPaths
from transcript.uncertainty import assess_session


@needs_media
class StatusTestCase(unittest.TestCase):
    """Real ffmpeg for the recordings; Narrata context and names are made up."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config_path = self.root / "config.yaml"
        self.config_path.write_text(
            f"language: de\npaths:\n  root: {self.root}\n", encoding="utf-8"
        )
        self.config = load_config(self.config_path)
        self.paths = SessionPaths(KEY, self.root)

    def recording(self, name: str = "aufnahme 1.mp3", seconds: float = 1) -> Path:
        self.paths.input_dir.mkdir(parents=True, exist_ok=True)
        return synth(self.paths.input_dir / name, *sine(seconds))

    def store_context(self, **session: object) -> None:
        store_context(
            self.paths, encoded(context(participants=[participant_json()], **session))
        )

    def extract(self) -> None:
        assert TOOLS is not None
        infos = [probe(path, TOOLS) for path in find_recordings(self.paths)]
        extract(infos, self.paths, self.config, TOOLS)

    def prepared(self, recordings: int = 1) -> None:
        """Recordings, context, snapshot, extracted audio and the manifest."""
        for number in range(1, recordings + 1):
            self.recording(f"aufnahme {number}.mp3")
        self.store_context()
        build_snapshot(self.paths, self.config.keyword_budget)
        self.extract()
        build_manifest(self.paths, consent=True)

    def reference(
        self,
        index: int = 1,
        diarized: bool = True,
        processed_at: str = "2026-11-04T20:00:00+01:00",
        **changes: Any,
    ) -> None:
        """A transcribed segment as `transcribe` stores it, rated."""
        values: dict[str, Any] = {
            "segment": SegmentRef(index, f"segment-{index:02d}.wav", "ab" * 32),
            "asr": AsrInfo(
                backend_id="fake",
                model="fake",
                knowledge_snapshot_id=load_snapshot(self.paths).snapshot_id,
            ),
            "processing": Processing(
                pipeline_version="0.0.1", processed_at=processed_at
            ),
            "passages": (
                Passage(
                    index=1,
                    text=f" Zum {SECRET}.",
                    start_ms=0,
                    end_ms=900,
                    words=(Word(f" {SECRET}", 0, 900, 0.9, "SPEAKER_00"),),
                    speaker="SPEAKER_00",
                ),
            ),
        }
        if diarized:
            values["diarization"] = Diarization(
                backend_id="fake", model="fake", labels=("SPEAKER_00",)
            )
        else:
            values["passages"] = ()
        values.update(changes)
        write_reference(self.paths, minimal(**values), {})
        assess_session(self.paths, [index], UncertaintyThresholds())

    def failed(self, index: int = 1) -> None:
        write_reference(
            self.paths,
            minimal(
                segment=SegmentRef(index, f"segment-{index:02d}.wav", "ab" * 32),
                status="failed",
                error=Failure(category="ResourceError", retryable=True),
            ),
            None,
        )

    def statuses(self) -> dict[str, tuple[str, str]]:
        found = status.inspect(self.paths, self.config)
        for step in found:
            for secret in (SECRET, NAME, CHARACTER, "SPEAKER_"):
                self.assertNotIn(secret, step.detail)
        return {step.step: (step.state, step.detail) for step in found}

    def state(self, step: str) -> str:
        return self.statuses()[step][0]


class OrderTest(StatusTestCase):
    def test_lists_the_preparation_and_asr_steps_in_run_order(self) -> None:
        self.assertEqual(
            list(self.statuses()),
            ["extract", "context", "snapshot", "manifest", "transcribe"],
        )

    def test_a_prepared_session_has_nothing_transcribed(self) -> None:
        self.prepared()

        self.assertEqual(
            {step: state for step, (state, _) in self.statuses().items()},
            {
                "extract": "done",
                "context": "done",
                "snapshot": "done",
                "manifest": "done",
                "transcribe": "pending",
            },
        )


class ExtractTest(StatusTestCase):
    def test_without_recordings_it_fails(self) -> None:
        self.assertEqual(self.state("extract"), "failed")

    def test_a_recording_alone_is_pending(self) -> None:
        self.recording()

        self.assertEqual(self.state("extract"), "pending")

    def test_extracted_audio_is_done(self) -> None:
        self.recording()
        self.extract()

        self.assertEqual(self.statuses()["extract"], ("done", "1 recording(s)"))

    def test_a_changed_recording_makes_it_stale(self) -> None:
        self.recording()
        self.extract()
        self.recording(seconds=2)

        state, detail = self.statuses()["extract"]

        self.assertEqual(state, "stale")
        self.assertIn("does not match the recordings", detail)

    def test_a_missing_segment_wav_makes_it_stale(self) -> None:
        self.recording()
        self.extract()
        self.paths.segment_wav(1).unlink()

        self.assertEqual(self.state("extract"), "stale")


class ContextSnapshotManifestTest(StatusTestCase):
    def test_missing_files_are_pending(self) -> None:
        for step in ("context", "snapshot", "manifest"):
            self.assertEqual(self.state(step), "pending", step)

    def test_an_unreadable_context_is_stale(self) -> None:
        self.store_context()
        self.paths.narrata_context.write_text("{}", encoding="utf-8")

        self.assertEqual(self.state("context"), "stale")

    def test_a_snapshot_behind_the_context_is_still_done_with_a_note(self) -> None:
        self.store_context()
        build_snapshot(self.paths, self.config.keyword_budget)
        short = load_snapshot(self.paths).snapshot_id[: knowledge.SHORT_ID]
        self.assertEqual(self.statuses()["snapshot"], ("done", f"snapshot {short}"))

        self.store_context(session_date="2026-11-05")

        state, detail = self.statuses()["snapshot"]
        self.assertEqual(state, "done")
        self.assertIn(knowledge.BEHIND_CONTEXT, detail)

    def test_an_unreadable_snapshot_is_stale(self) -> None:
        self.store_context()
        build_snapshot(self.paths, self.config.keyword_budget)
        self.paths.knowledge_snapshot.write_text("{}", encoding="utf-8")

        self.assertEqual(self.state("snapshot"), "stale")

    def test_the_manifest_counts_segments_and_names_a_missing_consent(self) -> None:
        self.prepared()
        self.assertEqual(self.statuses()["manifest"], ("done", "1 segment(s)"))

        data = json.loads(self.paths.manifest.read_text(encoding="utf-8"))
        data["consent"] = None
        self.paths.manifest.write_text(json.dumps(data), encoding="utf-8")

        self.assertEqual(
            self.statuses()["manifest"], ("done", "1 segment(s), no consent note")
        )

    def test_an_unreadable_manifest_is_stale(self) -> None:
        self.prepared()
        self.paths.manifest.write_text("{}", encoding="utf-8")

        self.assertEqual(self.state("manifest"), "stale")
        self.assertEqual(self.state("transcribe"), "stale")


class TranscribeTest(StatusTestCase):
    def test_without_a_manifest_it_waits_for_it(self) -> None:
        self.assertEqual(
            self.statuses()["transcribe"], ("pending", "needs the manifest")
        )

    def test_a_rated_and_diarized_segment_is_done(self) -> None:
        self.prepared()
        self.reference()

        self.assertEqual(
            self.statuses()["transcribe"],
            ("done", "1 of 1 segment(s) transcribed"),
        )

    def test_a_segment_without_speaker_labels_is_partial(self) -> None:
        self.prepared()
        self.reference(diarized=False)

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "partial")
        self.assertIn("no speaker labels: 1", detail)

    def test_a_missing_segment_among_transcribed_ones_is_partial(self) -> None:
        self.prepared(recordings=2)
        self.reference(index=1)

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "partial")
        self.assertIn("1 of 2 segment(s) transcribed", detail)
        self.assertIn("missing: 2", detail)

    def test_a_failed_segment_fails_the_step(self) -> None:
        self.prepared(recordings=2)
        self.reference(index=1)
        self.failed(index=2)

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "failed")
        self.assertIn("failed: 2", detail)

    def test_a_transcript_of_another_snapshot_is_stale(self) -> None:
        self.prepared()
        self.reference()
        self.store_context(session_date="2026-11-05")
        build_snapshot(self.paths, self.config.keyword_budget)

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "stale")
        self.assertIn("other snapshot: 1", detail)

    def test_a_rating_of_an_earlier_transcript_is_stale(self) -> None:
        self.prepared()
        self.reference()
        assessment = self.paths.review_uncertainty(1).read_bytes()
        self.reference(processed_at="2026-11-05T20:00:00+01:00")
        self.paths.review_uncertainty(1).write_bytes(assessment)

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "stale")
        self.assertIn("rating outdated: 1", detail)

    def test_a_missing_rating_is_stale(self) -> None:
        self.prepared()
        self.reference()
        self.paths.review_uncertainty(1).unlink()

        self.assertEqual(self.state("transcribe"), "stale")

    def test_an_unreadable_transcript_is_stale(self) -> None:
        self.prepared()
        self.reference()
        self.paths.reference(1).write_text("{}", encoding="utf-8")

        state, detail = self.statuses()["transcribe"]

        self.assertEqual(state, "stale")
        self.assertIn("unreadable: 1", detail)


if __name__ == "__main__":
    unittest.main()
