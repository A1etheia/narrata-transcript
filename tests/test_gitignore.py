import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

IGNORED = (
    ".env",
    ".env.local",
    "config/config.yaml",
    "config/local.yaml",
    "input/beispielgruppe/042/aufnahme.mp4",
    "work/beispielgruppe/042/asr/segment-001.json",
    "work/beispielgruppe/042/snapshot/wissen.json",
    "output/beispielgruppe/042/transkript.json",
    "tests/fixtures/input/aufnahme.json",
    "tests/fixtures/aufnahme.wav",
    "aufnahme.mp4",
    "aufnahme.m4a",
    "aufnahme.mp3",
    "aufnahme.wav",
    "aufnahme.flac",
    "aufnahme.ogg",
    "aufnahme.aac",
    "aufnahme.opus",
    "aufnahme.wma",
    "aufnahme.aiff",
    "aufnahme.webm",
    "aufnahme.mkv",
    "aufnahme.mov",
    "transkript.srt",
    "transkript.vtt",
    "transkript.docx",
)

NOT_IGNORED = (
    ".env.example",
    "config/example.yaml",
    "tests/fixtures/contract-v1.json",
)


def is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git check-ignore failed for {path}")
    return result.returncode == 0


class GitignoreTest(unittest.TestCase):
    def test_sensitive_paths_are_ignored(self) -> None:
        for path in IGNORED:
            with self.subTest(path=path):
                self.assertTrue(is_ignored(path))

    def test_fixture_and_example_paths_stay_versionable(self) -> None:
        for path in NOT_IGNORED:
            with self.subTest(path=path):
                self.assertFalse(is_ignored(path))


if __name__ == "__main__":
    unittest.main()
