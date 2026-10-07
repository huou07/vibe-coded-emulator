# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The release catalog must be generated, never hand-edited.

The catalog drives the download page and the Linux installers, so a hand-edited
or stale entry silently serves a wrong hash. These checks pin the generator's
contract: it derives the version from the same `tauri.conf.json` the release
train uses for artifact names, hashes real bytes, writes matching sidecars, and
refuses a partial artifact set or a non-commit identity.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build-release-catalog.py"
CATALOG = ROOT / "native-offline" / "releases" / "catalog.json"
TAURI_CONF = ROOT / "native-offline" / "src-tauri" / "tauri.conf.json"

FILENAMES = (
    "vibecodedemulator-{v}-macos-aarch64.dmg",
    "vibecodedemulator-{v}-android-arm64-staging.apk",
    "vibecodedemulator-{v}-android-arm64-staging.aab",
    "vibecodedemulator-{v}-linux-amd64.deb",
    "an3-offline-{v}-linux-amd64-staging.flatpak",
    "vibecodedemulator-{v}-windows-x64-staging.exe",
)


def desktop_version() -> str:
    return json.loads(TAURI_CONF.read_text(encoding="utf-8"))["version"]


class ReleaseCatalogGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="an3-catalog-"))
        self.tree = self.scratch / "tree"
        archive = self.scratch / "src.tar"
        with archive.open("wb") as handle:
            subprocess.run(
                ["git", "archive", "HEAD"], cwd=ROOT, check=True, stdout=handle
            )
        self.tree.mkdir()
        subprocess.run(["tar", "-xf", str(archive), "-C", str(self.tree)], check=True)
        shutil.copy(BUILDER, self.tree / "tools" / "build-release-catalog.py")
        self.releases = self.tree / "native-offline" / "releases"
        self.releases.mkdir(parents=True, exist_ok=True)
        # The archive ships the tracked catalog; the generator is the only
        # writer of it, so start from an empty release directory.
        (self.releases / "catalog.json").unlink(missing_ok=True)
        self.version = desktop_version()
        self.commit = "0" * 39 + "1"

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)

    def run_builder(self, *args, expect_success=True):
        result = subprocess.run(
            [sys.executable, "tools/build-release-catalog.py", *args],
            cwd=self.tree, capture_output=True, text=True,
        )
        if expect_success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def stage_artifacts(self, count=6):
        for template in FILENAMES[:count]:
            (self.releases / template.format(v=self.version)).write_bytes(
                os.urandom(2048)
            )

    def test_generated_catalog_verifies_and_carries_matching_sidecars(self):
        self.stage_artifacts()
        self.run_builder("--source-commit", self.commit)
        verify = subprocess.run(
            [sys.executable, "tools/verify-release-catalog.py"],
            cwd=self.tree, capture_output=True, text=True,
        )
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        self.assertIn("RELEASE_CATALOG=PASS", verify.stdout)
        catalog = json.loads((self.releases / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["source_commit"], self.commit)
        self.assertEqual(len(catalog["artifacts"]), 6)
        for entry in catalog["artifacts"]:
            with self.subTest(format=entry["format"]):
                self.assertIn(self.version, entry["filename"])
                sidecar = (self.releases / (entry["filename"] + ".sha256")).read_text()
                self.assertEqual(
                    sidecar.strip(), f"{entry['sha256']}  {entry['filename']}"
                )

    def test_generator_derives_the_version_the_release_train_uses(self):
        self.stage_artifacts()
        self.run_builder("--source-commit", self.commit)
        catalog = json.loads((self.releases / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual({entry["version"] for entry in catalog["artifacts"]}, {self.version})
        # Every filename must match tools/release-train.sh's naming scheme.
        for template in FILENAMES:
            self.assertTrue(
                any(entry["filename"] == template.format(v=self.version)
                    for entry in catalog["artifacts"]),
                f"missing {template}",
            )

    def test_generator_refuses_a_partial_artifact_set(self):
        self.stage_artifacts(count=3)
        result = self.run_builder("--source-commit", self.commit, expect_success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing installers", result.stdout)
        # The previous catalog must be left untouched rather than half-written.
        self.assertFalse((self.releases / "catalog.json").exists())

    def test_generator_rejects_a_non_commit_identity_and_bad_version(self):
        self.stage_artifacts()
        for bad in ("HEAD", "not-a-sha", "0" * 39):
            with self.subTest(commit=bad):
                result = self.run_builder("--source-commit", bad, expect_success=False)
                self.assertNotEqual(result.returncode, 0)
        result = self.run_builder("--source-commit", self.commit, "--version", "3.x",
                                  expect_success=False)
        self.assertNotEqual(result.returncode, 0)

    def test_releases_and_tauri_conf_overrides_are_honoured(self):
        """The tag workflow points --releases at its download directory.

        The catalog must land there, not beside the script, and the version must
        come from the requested tauri.conf.json rather than a path relative to
        the repository.
        """
        self.stage_artifacts()
        scratch = self.scratch / "dist"
        scratch.mkdir()
        for template in FILENAMES:
            (scratch / template.format(v="9.9.9")).write_bytes(os.urandom(2048))
        elsewhere = self.scratch / "conf"
        elsewhere.mkdir()
        (elsewhere / "tauri.conf.json").write_text(
            json.dumps({"version": "9.9.9"}), encoding="utf-8"
        )
        result = subprocess.run(
            [sys.executable, "tools/build-release-catalog.py",
             "--source-commit", self.commit,
             "--releases", str(scratch),
             "--tauri-conf", str(elsewhere / "tauri.conf.json"),
             "--release-candidate", "v9.9.9-staging"],
            cwd=self.tree, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((scratch / "catalog.json").is_file())
        catalog = json.loads((scratch / "catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["release_candidate"], "v9.9.9-staging")
        self.assertEqual(
            {entry["version"] for entry in catalog["artifacts"]}, {"9.9.9"}
        )
        # Nothing was written beside the script.
        self.assertFalse((self.tree / "native-offline/releases/catalog.json").exists())
        self.assertFalse((self.tree.parent / "catalog.json").exists())

    def test_dry_run_writes_nothing(self):
        self.stage_artifacts()
        before = sorted(path.name for path in self.releases.iterdir())
        self.run_builder("--source-commit", self.commit, "--dry-run")
        self.assertEqual(sorted(path.name for path in self.releases.iterdir()), before)
        self.assertNotIn("RELEASE_CATALOG_WRITTEN",
                         self.run_builder("--source-commit", self.commit, "--dry-run").stdout)


if __name__ == "__main__":
    unittest.main()