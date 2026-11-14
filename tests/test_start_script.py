"""Tests for scripts/transcript against a fake project with a stub CLI."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "transcript"

STUB = """#!/usr/bin/env bash
echo "cwd=$PWD"
echo "ld=$LD_LIBRARY_PATH"
echo "args=$*"
"""


class StartScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.project = self.base / "project"
        (self.project / "scripts").mkdir(parents=True)
        self.script = self.project / "scripts" / "transcript"
        shutil.copy2(SCRIPT, self.script)
        self.elsewhere = self.base / "elsewhere"
        self.elsewhere.mkdir()

    def add_venv(self, cublas: bool = True) -> Path:
        bin_dir = self.project / ".venv" / "bin"
        bin_dir.mkdir(parents=True)
        stub = bin_dir / "transcript"
        stub.write_text(STUB)
        stub.chmod(0o755)
        lib = self.project / ".venv/lib/python3.10/site-packages/nvidia/cublas/lib"
        if cublas:
            lib.mkdir(parents=True)
        return lib

    def run_script(self, command: Path, ld: str | None = None):
        env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
        if ld is not None:
            env["LD_LIBRARY_PATH"] = ld
        return subprocess.run(
            [str(command), "status", "beispielgruppe/042"],
            cwd=self.elsewhere,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def output(self, result) -> dict[str, str]:
        self.assertEqual(result.returncode, 0, result.stderr)
        return dict(line.split("=", 1) for line in result.stdout.splitlines())

    def test_runs_in_project_folder_with_cublas_on_path(self) -> None:
        lib = self.add_venv()
        out = self.output(self.run_script(self.script))
        self.assertEqual(out["cwd"], str(self.project))
        self.assertEqual(out["ld"], str(lib))
        self.assertEqual(out["args"], "status beispielgruppe/042")

    def test_keeps_an_existing_library_path(self) -> None:
        lib = self.add_venv()
        out = self.output(self.run_script(self.script, ld="/opt/other"))
        self.assertEqual(out["ld"], f"{lib}:/opt/other")

    def test_works_through_a_symlink(self) -> None:
        self.add_venv()
        link = self.base / "bin" / "transcript"
        link.parent.mkdir()
        link.symlink_to(self.script)
        out = self.output(self.run_script(link))
        self.assertEqual(out["cwd"], str(self.project))

    def test_runs_without_cublas_package(self) -> None:
        self.add_venv(cublas=False)
        out = self.output(self.run_script(self.script))
        self.assertEqual(out["ld"], "")

    def test_missing_venv_exits_2(self) -> None:
        result = self.run_script(self.script)
        self.assertEqual(result.returncode, 2)
        self.assertIn("setup", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
