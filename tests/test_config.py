import tempfile
import unittest
from pathlib import Path

from transcript.config import Config, ConfigError, format_config, load_config
from transcript.session import SessionKey

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
            audio_sample_rate=22050,
            audio_channels=2,
            asr_model="/models/whisper",
            asr_device="cuda",
            asr_compute_type="int8_float16",
            asr_beam_size=3,
            asr_retries=0,
            diarization_model="/models/pyannote",
            diarization_device="cpu",
            diarization_retries=5,
            narrata_url="https://narrata.example",
            narrata_groups={"beispielgruppe": 12},
        )

        self.assertEqual(self.load(format_config(config)), config)

    def test_audio_defaults_to_16_khz_mono(self) -> None:
        config = self.load(MINIMAL)

        self.assertEqual((config.audio_sample_rate, config.audio_channels), (16000, 1))

    def test_audio_values_are_read(self) -> None:
        config = self.load(MINIMAL + "audio:\n  sample_rate: 22050\n  channels: 2\n")

        self.assertEqual((config.audio_sample_rate, config.audio_channels), (22050, 2))

    def test_audio_values_are_validated(self) -> None:
        for text, key in (
            ("sample_rate: 0", "audio.sample_rate"),
            ("sample_rate: 16000.5", "audio.sample_rate"),
            ("sample_rate: true", "audio.sample_rate"),
            ("channels: 3", "audio.channels"),
            ("channels: 0", "audio.channels"),
            ("channels: '1'", "audio.channels"),
        ):
            with self.subTest(text=text):
                self.assert_rejected(
                    MINIMAL + f"audio:\n  {text}\n", f"invalid value for {key}"
                )

    def test_asr_defaults_to_whisper_turbo_on_any_device(self) -> None:
        config = self.load(MINIMAL)

        self.assertEqual(
            (
                config.asr_model,
                config.asr_device,
                config.asr_compute_type,
                config.asr_beam_size,
            ),
            ("large-v3-turbo", "auto", None, 5),
        )

    def test_asr_values_are_read(self) -> None:
        config = self.load(
            MINIMAL
            + "asr:\n  model: /models/whisper\n  device: cpu\n"
            + "  compute_type: int8\n  beam_size: 1\n"
        )

        self.assertEqual(
            (
                config.asr_model,
                config.asr_device,
                config.asr_compute_type,
                config.asr_beam_size,
            ),
            ("/models/whisper", "cpu", "int8", 1),
        )

    def test_asr_values_are_validated(self) -> None:
        for text, key in (
            ("model: ''", "asr.model"),
            ("model: 3", "asr.model"),
            ("device: gpu", "asr.device"),
            ("device: null", "asr.device"),
            ("compute_type: 16", "asr.compute_type"),
            ("compute_type: ''", "asr.compute_type"),
            ("beam_size: 0", "asr.beam_size"),
            ("beam_size: 2.5", "asr.beam_size"),
            ("beam_size: true", "asr.beam_size"),
        ):
            with self.subTest(text=text):
                self.assert_rejected(
                    MINIMAL + f"asr:\n  {text}\n", f"invalid value for {key}"
                )

    def test_retries_default_to_two_and_are_read(self) -> None:
        defaults = self.load(MINIMAL)
        self.assertEqual((defaults.asr_retries, defaults.diarization_retries), (2, 2))
        config = self.load(MINIMAL + "asr:\n  retries: 0\ndiarization:\n  retries: 5\n")
        self.assertEqual((config.asr_retries, config.diarization_retries), (0, 5))

    def test_retries_are_bounded(self) -> None:
        for section in ("asr", "diarization"):
            for value in ("-1", "6", "1.5", "true"):
                with self.subTest(section=section, value=value):
                    self.assert_rejected(
                        MINIMAL + f"{section}:\n  retries: {value}\n",
                        f"invalid value for {section}.retries",
                    )

    def test_diarization_defaults_to_pyannote_community_on_any_device(self) -> None:
        config = self.load(MINIMAL)

        self.assertEqual(
            (config.diarization_model, config.diarization_device),
            ("pyannote/speaker-diarization-community-1", "auto"),
        )

    def test_diarization_values_are_read(self) -> None:
        config = self.load(
            MINIMAL + "diarization:\n  model: /models/pyannote\n  device: cuda\n"
        )

        self.assertEqual(
            (config.diarization_model, config.diarization_device),
            ("/models/pyannote", "cuda"),
        )

    def test_diarization_values_are_validated(self) -> None:
        for text, key in (
            ("model: ''", "diarization.model"),
            ("model: 3", "diarization.model"),
            ("device: gpu", "diarization.device"),
            ("device: null", "diarization.device"),
        ):
            with self.subTest(text=text):
                self.assert_rejected(
                    MINIMAL + f"diarization:\n  {text}\n",
                    f"invalid value for {key}",
                )

    def test_narrata_defaults_to_no_url_and_no_groups(self) -> None:
        config = self.load(MINIMAL)

        self.assertEqual((config.narrata_url, config.narrata_groups), (None, {}))

    def test_narrata_values_are_read(self) -> None:
        for url in (
            "https://narrata.example",
            "https://narrata.example:8443/narrata/",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://[::1]:8000",
        ):
            with self.subTest(url=url):
                config = self.load(
                    MINIMAL + f"narrata:\n  url: '{url}'\n"
                    "  groups:\n    beispielgruppe: 12\n    zweite-runde: 3\n"
                )

                self.assertEqual(config.narrata_url, url)
                self.assertEqual(
                    config.narrata_groups, {"beispielgruppe": 12, "zweite-runde": 3}
                )

    def test_narrata_values_are_validated(self) -> None:
        for text, key in (
            ("url: ''", "narrata.url"),
            ("url: 3", "narrata.url"),
            ("url: narrata.example", "narrata.url"),
            ("url: 'http://narrata.example'", "narrata.url"),
            ("url: 'ftp://narrata.example'", "narrata.url"),
            ("url: 'https://user:pw@narrata.example'", "narrata.url"),
            ("url: 'https://narrata.example/?n=3'", "narrata.url"),
            ("url: 'https://narrata.example:port'", "narrata.url"),
            ("groups: [beispielgruppe]", "narrata.groups"),
            ("groups:\n    Beispiel Gruppe: 12", "narrata.groups"),
            ("groups:\n    3: 12", "narrata.groups"),
            ("groups:\n    beispielgruppe: 0", "narrata.groups.beispielgruppe"),
            ("groups:\n    beispielgruppe: '12'", "narrata.groups.beispielgruppe"),
            ("groups:\n    beispielgruppe: true", "narrata.groups.beispielgruppe"),
        ):
            with self.subTest(text=text):
                self.assert_rejected(
                    MINIMAL + f"narrata:\n  {text}\n",
                    f"invalid value for {key}",
                )

    def test_session_paths_use_the_configured_root(self) -> None:
        paths = self.load(MINIMAL).session_paths(SessionKey("beispielgruppe", 42))

        self.assertEqual(paths.work_dir, Path("/data/work/beispielgruppe/042"))

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
            (MINIMAL + "audio:\n  codec: flac\n", "audio.codec"),
            (MINIMAL + "asr:\n  vad: false\n", "asr.vad"),
            (
                MINIMAL + "diarization:\n  num_speakers: 4\n",
                "diarization.num_speakers",
            ),
        ):
            with self.subTest(key=key):
                self.assert_rejected(text, f"unknown key: {key}")


if __name__ == "__main__":
    unittest.main()
