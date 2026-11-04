import unittest
from pathlib import Path

from transcript.session import SessionKey, SessionPaths


class SessionKeyTest(unittest.TestCase):
    def test_parse_normalizes_the_ordinal(self) -> None:
        self.assertEqual(
            SessionKey.parse("beispielgruppe/42"),
            SessionKey.parse("beispielgruppe/042"),
        )

    def test_str_pads_to_three_digits_without_truncating(self) -> None:
        self.assertEqual(str(SessionKey("beispielgruppe", 42)), "beispielgruppe/042")
        self.assertEqual(str(SessionKey("beispielgruppe", 1000)), "beispielgruppe/1000")

    def test_parse_rejects_invalid_keys(self) -> None:
        for raw in (
            "",
            "beispielgruppe",
            "beispielgruppe/",
            "/042",
            "../042",
            "a/b/042",
            "Beispielgruppe/042",
            "beispiel--gruppe/042",
            "-beispiel/042",
            "beispielgruppe/0",
            "beispielgruppe/-1",
            "beispielgruppe/abc",
            "beispielgruppe/٤٢",
            "beispielgruppe/042\n",
            "beispielgruppe\n/042",
            f"{'a' * 65}/042",
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                SessionKey.parse(raw)

    def test_constructor_applies_the_same_rules(self) -> None:
        for group, ordinal in (("..", 1), ("a/b", 1), ("beispielgruppe", 0)):
            with (
                self.subTest(group=group, ordinal=ordinal),
                self.assertRaises(ValueError),
            ):
                SessionKey(group, ordinal)


class SessionPathsTest(unittest.TestCase):
    def test_directories_follow_the_layout(self) -> None:
        paths = SessionPaths(SessionKey("beispielgruppe", 42), Path("/data"))

        self.assertEqual(paths.input_dir, Path("/data/input/beispielgruppe/042"))
        self.assertEqual(paths.work_dir, Path("/data/work/beispielgruppe/042"))
        self.assertEqual(paths.output_dir, Path("/data/output/beispielgruppe/042"))
        self.assertEqual(
            paths.debug_log, Path("/data/work/beispielgruppe/042/debug.log")
        )
        self.assertEqual(paths.audio_dir, Path("/data/work/beispielgruppe/042/audio"))
        self.assertEqual(
            paths.segment_wav(1),
            Path("/data/work/beispielgruppe/042/audio/segment-01.wav"),
        )
        self.assertEqual(paths.segment_wav(12).name, "segment-12.wav")
        with self.assertRaises(ValueError):
            paths.segment_wav(0)
        self.assertEqual(paths.audio_metadata.parent, paths.audio_dir)
        self.assertEqual(
            paths.manifest, Path("/data/work/beispielgruppe/042/manifest.json")
        )
        self.assertEqual(paths.asr_dir, Path("/data/work/beispielgruppe/042/asr"))
        self.assertEqual(
            paths.reference(3),
            Path("/data/work/beispielgruppe/042/asr/segment-03.json"),
        )
        self.assertEqual(paths.reference_raw(3).name, "segment-03.raw.json")
        self.assertEqual(
            paths.diarization_raw(3),
            Path("/data/work/beispielgruppe/042/diarization/segment-03.json"),
        )
        for invalid in (paths.reference, paths.reference_raw, paths.diarization_raw):
            with self.subTest(path=invalid.__name__), self.assertRaises(ValueError):
                invalid(0)
        self.assertEqual(
            paths.narrata_context,
            Path("/data/work/beispielgruppe/042/narrata/transcription-context.json"),
        )

    def test_equal_sessions_resolve_to_the_same_directory(self) -> None:
        first = SessionPaths(SessionKey.parse("beispielgruppe/42"), Path("/data"))
        second = SessionPaths(SessionKey.parse("beispielgruppe/042"), Path("/data"))

        self.assertEqual(first.work_dir, second.work_dir)

    def test_different_sessions_share_no_directory(self) -> None:
        keys = (
            SessionKey("foo", 1),
            SessionKey("foo", 2),
            SessionKey("foo-1", 1),
            SessionKey("bar", 1),
        )
        directories = {SessionPaths(key, Path("/data")).work_dir for key in keys}

        self.assertEqual(len(directories), len(keys))


if __name__ == "__main__":
    unittest.main()
