import datetime
import itertools
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from transcript.jsonfile import DataFileError
from transcript.manifest import (
    ManifestError,
    build_manifest,
    load_manifest,
    timeline,
)
from transcript.session import SessionKey, SessionPaths
from transcript.timecode import format_ms

RATE = 16000
PLAY_SESSION_ID = 4711  # made up; real ids never enter the repo
NOW = datetime.datetime(2026, 11, 4, 20, 0, tzinfo=datetime.timezone.utc)


class ManifestTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = SessionPaths(
            SessionKey("beispielgruppe", 42), Path(directory.name)
        )

    def write_session(self, *frames: int) -> None:
        """Segment WAVs of silence plus the `audio.json` that `extract` would write."""
        self.paths.audio_dir.mkdir(parents=True, exist_ok=True)
        segments = []
        for index, count in enumerate(frames, start=1):
            path = self.paths.segment_wav(index)
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(RATE)
                wav.writeframes(b"\0\0" * count)
            segments.append(
                {
                    "index": index,
                    "file": path.name,
                    "frames": count,
                    "source": {
                        "file": f"teil {index}.mp3",
                        "size_bytes": 1000 + index,
                        "sha256": f"{index:064x}",
                        "container": "mp3",
                        "duration_seconds": count / RATE,
                        "has_video": False,
                        "audio_streams": [],
                    },
                    "selected_stream": {"audio_index": 0, "stream_index": 0},
                }
            )
        self.write_json(
            self.paths.audio_metadata,
            {
                "format_version": 2,
                "output_format": {
                    "codec": "pcm_s16le",
                    "sample_rate": RATE,
                    "channels": 1,
                },
                "tools": {"ffmpeg": "x", "ffprobe": "x"},
                "segments": segments,
            },
        )

    def write_context(self, **session: object) -> None:
        values = {
            "play_session_id": PLAY_SESSION_ID,
            "ordinal": 42,
            "session_date": "2026-10-30",
            "title": "Beispielabend",
        }
        values.update(session)
        self.write_json(
            self.paths.narrata_context,
            {
                "contract_version": "1.0",
                "session": values,
                "participants": [{"display_name": "Erika Beispiel"}],
            },
        )

    def write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def assert_fails(self, expected: str, **kwargs: object) -> str:
        with self.assertRaises(DataFileError) as caught:
            build_manifest(self.paths, consent=False, now=NOW, **kwargs)
        message = str(caught.exception)
        self.assertIn(expected, message)
        return message


class BuildManifestTest(ManifestTestCase):
    def test_segments_follow_each_other_without_gap(self) -> None:
        self.write_session(RATE + 7, 2 * RATE + 3)
        self.write_context()

        manifest = build_manifest(self.paths, consent=True, now=NOW)

        first, second = manifest.segments
        self.assertEqual((first.start_ms, first.end_ms), (0, 1000))
        self.assertEqual(second.start_ms, first.end_ms)
        self.assertEqual(second.end_ms, 3001)
        self.assertEqual(second.overlap_before_ms, 0)
        self.assertEqual(manifest.duration_ms, 3001)
        self.assertEqual(second.source.file, "teil 2.mp3")
        self.assertEqual(second.source.sha256, f"{2:064x}")

    def test_manifest_carries_identity_and_consent(self) -> None:
        self.write_session(RATE)
        self.write_context()

        build_manifest(self.paths, consent=True, now=NOW)

        data = json.loads(self.paths.manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["format_version"], 1)
        self.assertEqual(data["session"], {"group": "beispielgruppe", "ordinal": 42})
        self.assertEqual(data["play_session_id"], PLAY_SESSION_ID)
        self.assertEqual(data["session_date"], "2026-10-30")
        self.assertEqual(
            data["consent"], {"oral": True, "noted_at": "2026-11-04T20:00:00+00:00"}
        )
        self.assertEqual(data["segments"][0]["duration_ms"], 1000)

    def test_only_the_session_block_of_the_context_is_used(self) -> None:
        self.write_session(RATE)
        self.write_context()

        build_manifest(self.paths, consent=False, now=NOW)

        text = self.paths.manifest.read_text(encoding="utf-8")
        self.assertNotIn("Erika", text)
        self.assertNotIn("Beispielabend", text)

    def test_consent_is_null_without_flag_and_kept_on_rebuild(self) -> None:
        self.write_session(RATE)
        self.write_context()

        self.assertIsNone(build_manifest(self.paths, consent=False).consent)
        build_manifest(self.paths, consent=True, now=NOW)
        rebuilt = build_manifest(self.paths, consent=False)

        self.assertEqual(rebuilt.consent.noted_at, "2026-11-04T20:00:00+00:00")

    def test_string_play_session_id_is_accepted(self) -> None:
        self.write_session(RATE)
        self.write_context(play_session_id="0b0e-example")

        manifest = build_manifest(self.paths, consent=False)

        self.assertEqual(manifest.play_session_id, "0b0e-example")

    def test_reassigned_ordinal_is_rejected(self) -> None:
        self.write_session(RATE)
        self.write_context()
        build_manifest(self.paths, consent=True, now=NOW)
        self.write_context(play_session_id=PLAY_SESSION_ID + 1)

        self.assert_fails("was reassigned in Narrata")

    def test_ordinal_must_match_the_key(self) -> None:
        self.write_session(RATE)
        self.write_context(ordinal=43)

        self.assert_fails("session.ordinal is 43, but the session key is")

    def test_invalid_context_fields_are_named_without_values(self) -> None:
        self.write_session(RATE)
        for field, value, expected in (
            ("play_session_id", None, "session.play_session_id"),
            ("play_session_id", True, "session.play_session_id"),
            ("session_date", "30.10.2026", "session.session_date"),
        ):
            with self.subTest(field=field, value=value):
                self.write_context(**{field: value})

                message = self.assert_fails(expected)

                self.assertNotIn("30.10.2026", message)

    def test_missing_inputs_are_reported(self) -> None:
        self.write_session(RATE)

        self.assert_fails("Narrata transcription context not found")

        self.write_context()
        self.paths.audio_metadata.unlink()

        self.assert_fails("audio metadata not found")

    def test_old_audio_metadata_is_rejected(self) -> None:
        self.write_session(RATE)
        self.write_context()
        self.write_json(self.paths.audio_metadata, {"format_version": 1})

        self.assert_fails("run transcript extract again")

    def test_wav_must_match_audio_metadata(self) -> None:
        self.write_session(RATE, RATE)
        self.write_context()
        with wave.open(str(self.paths.segment_wav(2)), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(b"\0\0" * 10)

        self.assert_fails("segment-02.wav: does not match audio.json")

    def test_failed_write_keeps_the_previous_manifest(self) -> None:
        self.write_session(RATE)
        self.write_context()
        build_manifest(self.paths, consent=True, now=NOW)
        before = self.paths.manifest.read_bytes()

        with (
            mock.patch("transcript.jsonfile.os.replace", side_effect=OSError("full")),
            self.assertRaises(OSError),
        ):
            build_manifest(self.paths, consent=False)

        self.assertEqual(self.paths.manifest.read_bytes(), before)
        self.assertEqual(
            [path.name for path in self.paths.work_dir.iterdir() if path.is_file()],
            ["manifest.json"],
        )


class LoadManifestTest(ManifestTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_session(RATE, RATE // 2)
        self.write_context()
        self.built = build_manifest(self.paths, consent=True, now=NOW)

    def test_round_trip_needs_no_audio(self) -> None:
        for path in self.paths.segment_wavs():
            path.unlink()
        self.paths.audio_metadata.unlink()

        self.assertEqual(load_manifest(self.paths), self.built)

    def test_local_time_becomes_session_time(self) -> None:
        second = load_manifest(self.paths).segments[1]

        self.assertEqual(second.to_absolute_ms(0.25), 1250)
        self.assertEqual(second.to_absolute_ms(0.5), 1500)
        for local in (-0.001, 0.502):
            with self.subTest(local=local), self.assertRaises(ValueError):
                second.to_absolute_ms(local)

    def test_reassigned_ordinal_is_detected_on_read(self) -> None:
        self.write_context(play_session_id=PLAY_SESSION_ID + 1)

        with self.assertRaises(ManifestError) as caught:
            load_manifest(self.paths)

        self.assertIn("was reassigned in Narrata", str(caught.exception))

    def test_context_is_optional_on_read(self) -> None:
        self.paths.narrata_context.unlink()

        self.assertEqual(load_manifest(self.paths), self.built)

    def test_gaps_and_overlaps_are_rejected(self) -> None:
        data = json.loads(self.paths.manifest.read_text(encoding="utf-8"))
        for field, value in (("start_ms", 1001), ("overlap_before_ms", 1)):
            with self.subTest(field=field):
                broken = json.loads(json.dumps(data))
                broken["segments"][1][field] = value
                self.write_json(self.paths.manifest, broken)

                with self.assertRaises(ManifestError) as caught:
                    load_manifest(self.paths)

                self.assertIn("segment 2 is out of order", str(caught.exception))

    def test_declared_overlap_is_recognized(self) -> None:
        data = json.loads(self.paths.manifest.read_text(encoding="utf-8"))
        data["segments"][1]["start_ms"] = 900
        data["segments"][1]["overlap_before_ms"] = 100
        self.write_json(self.paths.manifest, data)

        second = load_manifest(self.paths).segments[1]

        self.assertEqual(second.overlap_before_ms, 100)
        self.assertEqual(second.start_ms, 900)

    def test_unknown_format_version_is_rejected(self) -> None:
        data = json.loads(self.paths.manifest.read_text(encoding="utf-8"))
        data["format_version"] = 2
        self.write_json(self.paths.manifest, data)

        with self.assertRaises(ManifestError):
            load_manifest(self.paths)

    def test_manifest_of_another_session_is_rejected(self) -> None:
        other = SessionPaths(SessionKey("beispielgruppe", 43), self.paths.root)
        other.work_dir.mkdir(parents=True)
        other.manifest.write_bytes(self.paths.manifest.read_bytes())

        with self.assertRaises(ManifestError) as caught:
            load_manifest(other)

        self.assertIn("belongs to session beispielgruppe/042", str(caught.exception))


class TimelineTest(unittest.TestCase):
    def test_two_five_hour_parts(self) -> None:
        five_hours = 5 * 3600 * RATE + 11  # not a whole number of milliseconds

        bounds = timeline([five_hours, five_hours], RATE)

        self.assertEqual(bounds[0][1], bounds[1][0])
        self.assertEqual(format_ms(bounds[1][1]), "10:00:00.001")
        self.assertTrue(all(0 <= start <= end for start, end in bounds))

    def test_many_short_parts_do_not_drift(self) -> None:
        bounds = timeline([7] * 1000, RATE)

        self.assertEqual(bounds[0][0], 0)
        self.assertEqual(bounds[-1][1], 438)  # 7000 frames = 437.5 ms, rounded up
        for (_, end), (start, _) in itertools.pairwise(bounds):
            self.assertEqual(end, start)


if __name__ == "__main__":
    unittest.main()
