import json
import os
import tempfile
import unittest
from pathlib import Path

from media import TOOLS, needs_media, sine, synth
from test_audio_tools import working_stub
from test_narrata import CHARACTER, NAME, context, encoded
from test_narrata import participant as participant_json
from test_reference import KEY, minimal

from transcript import preflight
from transcript.asr.backend import BackendInfo, BackendUnavailableError
from transcript.asr.fake import FakeBackend
from transcript.audio import extract, find_recordings, probe
from transcript.config import load_config
from transcript.knowledge import build_snapshot, load_snapshot
from transcript.manifest import build_manifest
from transcript.narrata import store_context
from transcript.reference import AsrInfo, SegmentRef, write_reference
from transcript.session import SessionPaths

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
        self.search_path: str | None = str(self.bin)
        self.environ: dict[str, str] = {}
        self.free_bytes = 10**12

    def write_config(self, extra: str = "") -> None:
        self.config.write_text(
            f"language: de\npaths:\n  root: {self.root}\n{extra}", encoding="utf-8"
        )

    def probes(self) -> preflight.Probes:
        return preflight.Probes(
            search_path=self.search_path,
            asr=self.asr,
            diarizer=lambda config: self.diarizer,
            environ=self.environ,
            dotenv=self.root / ".env",
            disk_free=lambda path: self.free_bytes,
        )

    def run_preflight(self, key=None, **options: object) -> list[preflight.Finding]:
        return preflight.run(self.config, key, probes=self.probes(), **options)

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


@needs_media
class SessionTest(PreflightTestCase):
    """Real ffmpeg for the recordings; Narrata context and names are made up."""

    def setUp(self) -> None:
        super().setUp()
        self.search_path = None  # the real tools synthesize and probe
        self.paths = SessionPaths(KEY, self.root)

    def preflight(self) -> list[preflight.Finding]:
        return self.run_preflight(KEY)

    def recording(self, name: str = "aufnahme 1.mp3", seconds: float = 1) -> Path:
        self.paths.input_dir.mkdir(parents=True, exist_ok=True)
        return synth(self.paths.input_dir / name, *sine(seconds))

    def store_context(self, **session: object) -> None:
        store_context(
            self.paths, encoded(context(participants=[participant_json()], **session))
        )

    def snapshot(self) -> None:
        build_snapshot(self.paths, load_config(self.config).keyword_budget)

    def extract(self) -> None:
        """What `transcript extract` and `transcript manifest --consent` write."""
        assert TOOLS is not None
        recordings = find_recordings(self.paths)
        infos = [probe(recording, TOOLS) for recording in recordings]
        extract(infos, self.paths, load_config(self.config), TOOLS)
        build_manifest(self.paths, consent=True)

    def prepared(self) -> None:
        """A session ready to transcribe: recording, context, snapshot."""
        self.recording()
        self.store_context()
        self.snapshot()

    def reference(self, **asr: object) -> None:
        """A stored result `transcribe` would reuse, unless `asr` changes it."""
        values: dict[str, object] = {
            "backend_id": "fake",
            "model": "tiny",
            "model_version": "abc123",
            "settings": {"device": "cuda"},
            "language": "de",
            "knowledge_snapshot_id": load_snapshot(self.paths).snapshot_id,
        }
        values.update(asr)
        write_reference(
            self.paths,
            minimal(
                segment=SegmentRef(1, "segment-01.wav", "ab" * 32),
                asr=AsrInfo(**values),  # type: ignore[arg-type]
            ),
            {},
        )

    def problems(self, findings) -> list[tuple[str, str]]:
        return [
            (finding.check, finding.level)
            for finding in findings
            if finding.level != "ok"
        ]

    def message(self, findings, check: str, level: str) -> str:
        (found,) = [f for f in self.by_check(findings, check) if f.level == level]
        return found.message

    def test_prepared_session_passes_without_token_and_old_transcript(self) -> None:
        self.prepared()

        findings = self.preflight()

        self.assertEqual(self.problems(findings), [])
        self.assertEqual(
            list(dict.fromkeys(f.check for f in findings)),
            [
                "audio-tools",
                "config",
                "asr",
                "diarization",
                "session-input",
                "paths",
                "disk",
                "knowledge",
                "resume",
            ],
        )
        self.assertIn(
            "1 recording(s), 00:00:01", self.message(findings, "session-input", "ok")
        )

    def test_preflight_changes_no_file(self) -> None:
        self.prepared()
        self.extract()
        self.reference(model="other")
        before = _tree(self.root)

        self.preflight()

        self.assertEqual(_tree(self.root), before)

    def test_messages_name_no_participant(self) -> None:
        self.prepared()
        self.extract()

        findings = self.preflight()

        for finding in findings:
            self.assertNotIn(NAME, finding.message)
            self.assertNotIn(CHARACTER, finding.message)

    def test_missing_input_directory_is_an_error(self) -> None:
        self.store_context()

        findings = self.preflight()

        self.assertIn(
            "no input directory", self.message(findings, "session-input", "error")
        )

    def test_empty_input_directory_is_an_error(self) -> None:
        self.paths.input_dir.mkdir(parents=True)
        self.store_context()

        findings = self.preflight()

        self.assertIn(
            "no recording found", self.message(findings, "session-input", "error")
        )

    def test_unusable_recording_is_an_error(self) -> None:
        self.paths.input_dir.mkdir(parents=True)
        (self.paths.input_dir / "aufnahme.mp3").write_text("no audio")
        self.store_context()

        findings = self.preflight()

        self.assertEqual(self.levels(findings, "session-input"), ["error"])
        self.assertEqual(self.by_check(findings, "disk"), [])

    def test_several_recordings_are_a_warning_about_the_contract(self) -> None:
        self.prepared()
        self.recording("aufnahme 2.mp3")

        findings = self.preflight()

        self.assertIn("IOA-1287", self.message(findings, "session-input", "warning"))
        self.assertEqual(preflight.errors(findings), 0)

    def test_work_path_that_is_a_file_is_an_error(self) -> None:
        self.prepared()
        (self.root / "output").write_text("")

        findings = self.preflight()

        self.assertIn("not a directory", self.message(findings, "paths", "error"))

    @unittest.skipIf(os.geteuid() == 0, "root writes everywhere")
    def test_read_only_work_path_is_an_error(self) -> None:
        self.prepared()
        work = self.paths.work_dir
        work.chmod(0o555)
        self.addCleanup(work.chmod, 0o755)

        findings = self.preflight()

        self.assertIn("not writable", self.message(findings, "paths", "error"))

    def test_too_little_disk_space_for_the_wavs_is_an_error(self) -> None:
        self.prepared()
        self.free_bytes = 1000

        findings = self.preflight()

        self.assertIn("the WAVs need", self.message(findings, "disk", "error"))

    def test_extracted_audio_needs_no_disk_space(self) -> None:
        self.prepared()
        self.extract()
        self.free_bytes = 0

        findings = self.preflight()

        self.assertEqual(self.levels(findings, "disk"), ["ok"])

    def test_no_context_and_no_access_is_one_error_naming_what_is_missing(
        self,
    ) -> None:
        self.recording()

        findings = self.preflight()

        message = self.message(findings, "knowledge", "error")
        self.assertIn("narrata.url is not set", message)
        self.assertIn("narrata.groups has no group id for beispielgruppe", message)
        self.assertIn("NARRATA_TOKEN is not set", message)
        self.assertIn("--from-file", message)

    def test_no_context_with_access_is_fine_and_the_token_stays_hidden(
        self,
    ) -> None:
        self.recording()
        self.write_config(
            "narrata:\n  url: https://narrata.example\n"
            "  groups:\n    beispielgruppe: 3\n"
        )
        self.environ = {"NARRATA_TOKEN": "geheim-123"}

        findings = self.preflight()

        self.assertIn("fetches it", self.message(findings, "knowledge", "ok"))
        self.assertFalse(any("geheim-123" in f.message for f in findings))

    def test_missing_snapshot_is_a_warning(self) -> None:
        self.recording()
        self.store_context()

        findings = self.preflight()

        self.assertIn(
            "without keywords", self.message(findings, "knowledge", "warning")
        )
        self.assertEqual(preflight.errors(findings), 0)

    def test_damaged_snapshot_is_an_error(self) -> None:
        self.prepared()
        self.paths.knowledge_snapshot.write_text("{}")

        findings = self.preflight()

        self.assertEqual(self.levels(findings, "knowledge"), ["ok", "error"])

    def test_snapshot_behind_context_or_budget_is_a_warning(self) -> None:
        self.prepared()
        self.store_context(title="Ein anderer Abend")
        self.write_config("knowledge:\n  keyword_budget:\n    person: 1\n")

        findings = self.preflight()

        warnings = [
            f.message
            for f in self.by_check(findings, "knowledge")
            if f.level == "warning"
        ]
        self.assertEqual(len(warnings), 2)
        self.assertIn("predates the stored Narrata context", warnings[0])
        self.assertIn("keyword_budget changed", warnings[1])

    def test_extracted_session_is_ready_to_resume(self) -> None:
        self.prepared()
        self.extract()
        self.reference()

        findings = self.preflight()

        self.assertEqual(self.problems(findings), [])
        self.assertIn("1 transcribed", self.message(findings, "resume", "ok"))

    def test_changed_recording_does_not_match_the_extracted_audio(self) -> None:
        self.prepared()
        self.extract()
        self.recording(seconds=2)

        findings = self.preflight()

        self.assertIn(
            "does not match the recordings", self.message(findings, "resume", "error")
        )

    def test_missing_segment_wav_is_an_error(self) -> None:
        self.prepared()
        self.extract()
        self.paths.segment_wav(1).unlink()

        findings = self.preflight()

        self.assertIn(
            "segment 1 audio not found", self.message(findings, "resume", "error")
        )

    def test_unreadable_reference_is_an_error(self) -> None:
        self.prepared()
        self.extract()
        self.paths.asr_dir.mkdir(parents=True)
        self.paths.reference(1).write_text("{}")

        findings = self.preflight()

        self.assertEqual(self.levels(findings, "resume"), ["error", "ok"])

    def test_reference_of_another_model_is_transcribed_again(self) -> None:
        self.prepared()
        self.extract()
        self.reference(model="other")

        findings = self.preflight()

        self.assertIn(
            "segment(s) 1 are transcribed again",
            self.message(findings, "resume", "warning"),
        )

    def test_reference_of_another_snapshot_is_transcribed_again(self) -> None:
        """The same rule as `transcribe`: new knowledge means a new run."""
        self.prepared()
        self.extract()
        self.reference(knowledge_snapshot_id="0" * 64)

        findings = self.preflight()

        self.assertIn(
            "1 are transcribed again", self.message(findings, "resume", "warning")
        )

    def test_manifest_without_consent_is_a_warning(self) -> None:
        self.prepared()
        self.extract()
        build_manifest(self.paths, consent=False)  # keeps the earlier note
        data = json.loads(self.paths.manifest.read_text())
        data["consent"] = None
        self.paths.manifest.write_text(json.dumps(data))

        findings = self.preflight()

        self.assertIn("consent", self.message(findings, "resume", "warning"))


def _tree(root: Path) -> dict[str, tuple[bytes, int]]:
    """Content and modification time of every file below `root`."""
    return {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


if __name__ == "__main__":
    unittest.main()
