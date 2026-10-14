# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for documented paths excluded by repository ignore rules."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check-docs-refs.py"


class DocumentationReferenceTests(unittest.TestCase):
    def test_ignored_path_is_valid_when_directory_is_not_materialized(self):
        with tempfile.TemporaryDirectory(prefix="an3-doc-refs-") as temporary:
            repo = Path(temporary)
            (repo / "tools").mkdir()
            (repo / "native-offline").mkdir()
            (repo / ".gitignore").write_text("data/\n", encoding="utf-8")
            (repo / "native-offline/THIRD_PARTY_NOTICES.md").write_text(
                "Runtime files are stored under `data/`.\n", encoding="utf-8"
            )
            checker = repo / "tools/check-docs-refs.py"
            shutil.copyfile(CHECKER, checker)

            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "add",
                    ".gitignore",
                    "native-offline/THIRD_PARTY_NOTICES.md",
                    "tools/check-docs-refs.py",
                ],
                check=True,
            )
            self.assertFalse((repo / "data").exists())
            ignored_status = subprocess.run(
                ["git", "-C", str(repo), "status", "--porcelain", "--ignored=matching"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertNotIn("data/", ignored_status.stdout)

            result = subprocess.run(
                ["python3", str(checker)],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
