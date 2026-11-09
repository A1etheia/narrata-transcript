import tempfile
import unittest
from pathlib import Path

from test_audio_tools import working_stub

from transcript import preflight
from transcript.asr.backend import BackendInfo, BackendUnavailableError
from transcript.asr.fake import FakeBackend

ASR_INFO = BackendInfo(backend_id="fake", model="tiny", model_version="abc123")
DIARIZATION_INFO = BackendInfo(backend_id="pyannote", model="fake-diarization")


class FakeDiarizer:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    def identity(self) -> BackendInfo:
        if self._error is not None:
            raise self._error
        return DIARIZATION_INFO


class UnavailableBackend(FakeBackend):
    """A backend whose identity fails, as when its runtime or model is missing."""

    def __init__(self, error: Exception) -> None:
        super().__init__(info=ASR_INFO)
        self._identity_error = error

    def identity(self):
        raise self._identity_error


def fake_asr(device: str = "cuda"):
    return lambda config: FakeBackend(info=ASR_INFO, settings={"device": device})


class PreflightTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        working_stub(self.bin, "ffmpeg")
        working_stub(self.bin, "ffprobe")
        self.config = self.root / "config.yaml"
        self.write_config()
        self.asr = fake_asr()
        self.diarizer = FakeDiarizer()

    def write_config(self, extra: str = "") -> None:
        self.config.write_text(
            f"language: de\npaths:\n  root: {self.root}\n{extra}", encoding="utf-8"
        )

    def probes(self) -> preflight.Probes:
        return preflight.Probes(
            search_path=str(self.bin),
            asr=self.asr,
            diarizer=lambda config: self.diarizer,
        )

    def run_preflight(self, **options: object) -> list[preflight.Finding]:
        return preflight.run(self.config, probes=self.probes(), **options)

    def by_check(self, findings, check: str) -> list[preflight.Finding]:
        return [finding for finding in findings if finding.check == check]

    def levels(self, findings, check: str) -> list[str]:
        return [finding.level for finding in self.by_check(findings, check)]


class EnvironmentTest(PreflightTestCase):
    def test_everything_in_place_has_no_error_or_warning(self) -> None:
        findings = self.run_preflight()

        self.assertEqual(preflight.errors(findings), 0)
        self.assertEqual(preflight.warnings(findings), 0)
        self.assertEqual(
            [finding.check for finding in findings],
            ["audio-tools", "config", "asr", "diarization"],
        )
        (asr,) = self.by_check(findings, "asr")
        self.assertEqual(asr.message, "fake tiny (abc123) on cuda")

    def test_missing_ffprobe_is_an_error_and_the_other_checks_still_run(self) -> None:
        (self.bin / "ffprobe").unlink()

        findings = self.run_preflight()

        (tools,) = self.by_check(findings, "audio-tools")
        self.assertEqual(tools.level, "error")
        self.assertIn("ffprobe not found", tools.message)
        self.assertEqual(self.levels(findings, "asr"), ["ok"])
        self.assertEqual(preflight.errors(findings), 1)

    def test_missing_ffmpeg_is_an_error(self) -> None:
        (self.bin / "ffmpeg").unlink()

        findings = self.run_preflight()

        (tools,) = self.by_check(findings, "audio-tools")
        self.assertEqual(tools.level, "error")
        self.assertIn("ffmpeg not found", tools.message)

    def test_unusable_asr_backend_is_an_error(self) -> None:
        self.asr = lambda config: UnavailableBackend(
            BackendUnavailableError("fake: model tiny not in the local cache")
        )

        findings = self.run_preflight()

        (asr,) = self.by_check(findings, "asr")
        self.assertEqual(asr.level, "error")
        self.assertIn("not in the local cache", asr.message)
        self.assertEqual(self.levels(findings, "diarization"), ["ok"])

    def test_any_failure_of_the_asr_identity_is_reported_not_raised(self) -> None:
        self.asr = lambda config: UnavailableBackend(OSError("disk"))

        findings = self.run_preflight()

        self.assertEqual(self.levels(findings, "asr"), ["error"])

    def test_auto_device_on_the_cpu_is_a_warning(self) -> None:
        self.asr = fake_asr(device="cpu")

        findings = self.run_preflight()

        self.assertEqual(self.levels(findings, "asr"), ["ok", "warning"])
        self.assertEqual(preflight.errors(findings), 0)

    def test_cpu_chosen_in_the_config_is_no_warning(self) -> None:
        self.write_config("asr:\n  device: cpu\n")
        self.asr = fake_asr(device="cpu")

        findings = self.run_preflight()

        self.assertEqual(self.levels(findings, "asr"), ["ok"])

    def test_missing_diarization_runtime_is_an_error(self) -> None:
        self.diarizer = FakeDiarizer(
            BackendUnavailableError("pyannote: runtime missing")
        )

        findings = self.run_preflight()

        self.assertEqual(self.levels(findings, "diarization"), ["error"])

    def test_diarization_is_left_out_on_request(self) -> None:
        self.diarizer = FakeDiarizer(
            BackendUnavailableError("pyannote: runtime missing")
        )

        findings = self.run_preflight(diarize=False)

        self.assertEqual(self.by_check(findings, "diarization"), [])
        self.assertEqual(preflight.errors(findings), 0)

    def test_invalid_config_is_an_error_and_skips_the_checks_that_need_it(
        self,
    ) -> None:
        self.config.write_text("paths:\n  root: .\n", encoding="utf-8")

        findings = self.run_preflight()

        self.assertEqual(
            [(finding.check, finding.level) for finding in findings],
            [("audio-tools", "ok"), ("config", "error")],
        )
        self.assertIn("language", findings[1].message)
        self.assertIn("skipped", findings[1].message)

    def test_missing_config_file_is_an_error(self) -> None:
        self.config.unlink()

        findings = self.run_preflight()

        self.assertEqual(self.levels(findings, "config"), ["error"])


if __name__ == "__main__":
    unittest.main()
