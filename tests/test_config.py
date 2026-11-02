import tempfile
import unittest
from pathlib import Path

from transcript.config import Config, ConfigError, format_config, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
MINIMAL = "language: de\npaths:\n  root: /data\n"


class LoadConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "config.yaml"

    def load(self, text: str) -> Config:
        self.path.write_text(text, encoding="utf-8")
        return load_config(self.path)

    def assert_rejected(self, text: str, expected: str) -> None:
        with self.assertRaises(ConfigError) as caught:
            self.load(text)
        self.assertIn(str(self.path), str(caught.exception))
        self.assertIn(expected, str(caught.exception))

    def test_example_file_loads(self) -> None:
        config = load_config(REPO_ROOT / "config" / "example.yaml")

        self.assertEqual(config.language, "de")
        self.assertEqual(config.root, Path("."))

    def test_defaults_apply_to_optional_values(self) -> None:
        self.assertEqual(
            self.load(MINIMAL),
            Config(language="de", root=Path("/data")),
        )

    def test_optional_values_are_read(self) -> None:
        config = self.load(
            MINIMAL
            + "debug: true\nsegmentation:\n"
            + "  length_seconds: 600\n  overlap_seconds: 2.5\n"
        )

        self.assertTrue(config.debug)
        self.assertEqual(config.segment_length_seconds, 600)
        self.assertEqual(config.segment_overlap_seconds, 2.5)

    def test_formatted_config_loads_back_unchanged(self) -> None:
        config = Config(
            language="de",
            root=Path("/data"),
            debug=True,
            segment_length_seconds=600,
            segment_overlap_seconds=2.5,
        )

        self.assertEqual(self.load(format_config(config)), config)

    def test_missing_file_is_reported(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            load_config(self.path)

        self.assertIn(str(self.path), str(caught.exception))

    def test_broken_yaml_is_reported(self) -> None:
        self.assert_rejected("language: [de\n", "invalid YAML")

    def test_top_level_must_be_a_mapping(self) -> None:
        for text in ("", "- de\n"):
            with self.subTest(text=text):
                self.assert_rejected(text, "top level")

    def test_missing_required_values_name_the_key(self) -> None:
        for text, key in (
            ("paths:\n  root: /data\n", "language"),
            ("language: de\n", "paths.root"),
            ("language: de\npaths:\n", "paths.root"),
            ("language: de\npaths:\n  root:\n", "paths.root"),
        ):
            with self.subTest(key=key, text=text):
                self.assert_rejected(text, f"missing required key: {key}")

    def test_invalid_values_name_the_key(self) -> None:
        for text, key in (
            ("language: deutsch\npaths:\n  root: /data\n", "language"),
            ("language: 42\npaths:\n  root: /data\n", "language"),
            ("language: de\npaths: /data\n", "paths"),
            ("language: de\npaths:\n  root: 1\n", "paths.root"),
            ("language: de\npaths:\n  root: ''\n", "paths.root"),
            (MINIMAL + "debug: 'yes'\n", "debug"),
            (MINIMAL + "debug: 1\n", "debug"),
            (MINIMAL + "segmentation: 600\n", "segmentation"),
        ):
            with self.subTest(key=key, text=text):
                self.assert_rejected(text, f"invalid value for {key}")

    def test_segment_values_must_be_positive_numbers(self) -> None:
        for value in ("0", "-1", "true", "'600'", ".nan", ".inf"):
            with self.subTest(value=value):
                self.assert_rejected(
                    MINIMAL + f"segmentation:\n  length_seconds: {value}\n",
                    "invalid value for segmentation.length_seconds",
                )

    def test_overlap_must_stay_below_length(self) -> None:
        for overlap in (10, 20):
            with self.subTest(overlap=overlap):
                self.assert_rejected(
                    MINIMAL
                    + "segmentation:\n"
                    + f"  length_seconds: 10\n  overlap_seconds: {overlap}\n",
                    "invalid value for segmentation.overlap_seconds",
                )

    def test_unknown_keys_are_rejected(self) -> None:
        for text, key in (
            (MINIMAL + "debgu: true\n", "debgu"),
            ("language: de\npaths:\n  root: /data\n  out: /x\n", "paths.out"),
            (MINIMAL + "segmentation:\n  length: 1\n", "segmentation.length"),
        ):
            with self.subTest(key=key):
                self.assert_rejected(text, f"unknown key: {key}")


if __name__ == "__main__":
    unittest.main()
