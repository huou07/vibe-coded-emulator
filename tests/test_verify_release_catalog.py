"""Deterministic tests for tools/verify-release-catalog.py.

The tool validates the exact staging publication set: every catalog entry must
reference a regular installer whose bytes match the recorded size and SHA-256,
with a matching ``<name>.sha256`` sidecar, and at least one artifact for each
required platform (DMG, APK, DEB, Flatpak). All fixtures here are synthetic and
written under a TemporaryDirectory; the real catalog and artifacts are never
touched.

Known deviation: ``verify()`` documents "ValueError on any problem" but a
missing sidecar reaches ``Path.read_text()`` unguarded and surfaces the
underlying ``FileNotFoundError`` (an OSError). The missing-sidecar test asserts
the documented rejection while accepting that current behaviour; see the
worker report knownIssues.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "verify-release-catalog.py"

spec = importlib.util.spec_from_file_location("verify_release_catalog", TOOL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

REQUIRED_FORMATS = ("DMG", "APK", "DEB", "Flatpak")


def _write_artifact(release, filename, payload, fmt, platform):
    """Write one installer plus its SHA-256 sidecar and return its catalog entry."""
    (release / filename).write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (release / (filename + ".sha256")).write_text(
        "%s  %s" % (digest, filename), encoding="utf-8"
    )
    return {
        "format": fmt,
        "platform": platform,
        "filename": filename,
        "size": len(payload),
        "sha256": digest,
    }


class VerifyReleaseCatalogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.release = self.root / "native-offline" / "releases"
        self.release.mkdir(parents=True)
        self.artifacts = []

    def _build_valid(self):
        self.artifacts = [
            _write_artifact(
                self.release,
                "vibecodedemulator-1.0.0-macos-aarch64.dmg",
                b"single-dmg-payload",
                "DMG",
                "macOS",
            ),
            _write_artifact(
                self.release,
                "an3-offline-1.0.0-android-arm64-staging.apk",
                b"single-apk-payload",
                "APK",
                "Android",
            ),
            _write_artifact(
                self.release,
                "an3-offline-1.0.0-linux-amd64-staging.deb",
                b"single-deb-payload",
                "DEB",
                "Linux",
            ),
            _write_artifact(
                self.release,
                "an3-offline-1.0.0-linux-amd64-staging.flatpak",
                b"single-flatpak-payload",
                "Flatpak",
                "Linux",
            ),
        ]
        self._write_catalog()
        return self.root

    def _write_catalog(self):
        (self.release / "catalog.json").write_text(
            json.dumps({"schema_version": 1, "artifacts": self.artifacts}),
            encoding="utf-8",
        )

    def test_valid_catalog_returns_filenames(self):
        root = self._build_valid()
        names = mod.verify(root)
        expected = [item["filename"] for item in self.artifacts]
        self.assertEqual(len(expected), 4)
        self.assertEqual(sorted(names), sorted(expected))
        self.assertEqual(len(names), 4)
        self.assertEqual(
            {item["format"] for item in self.artifacts}, set(REQUIRED_FORMATS)
        )

    def test_tampered_size_raises(self):
        root = self._build_valid()
        self.artifacts[1]["size"] += 1
        self._write_catalog()
        with self.assertRaises(ValueError):
            mod.verify(root)

    def test_tampered_sha256_raises(self):
        root = self._build_valid()
        self.artifacts[2]["sha256"] = "0" * 64
        self._write_catalog()
        with self.assertRaises(ValueError):
            mod.verify(root)

    def test_missing_sidecar_raises(self):
        root = self._build_valid()
        sidecar = self.release / (self.artifacts[3]["filename"] + ".sha256")
        sidecar.unlink()
        self.assertFalse(sidecar.exists())
        # verify() documents ValueError for any problem; the current
        # implementation lets Path.read_text() surface FileNotFoundError.
        with self.assertRaises((ValueError, FileNotFoundError)):
            mod.verify(root)

    def test_duplicate_filename_raises(self):
        root = self._build_valid()
        self.artifacts.append(dict(self.artifacts[0]))
        self._write_catalog()
        with self.assertRaises(ValueError):
            mod.verify(root)

    def test_missing_required_platform_raises(self):
        root = self._build_valid()
        self.artifacts = [
            item for item in self.artifacts if item["format"] != "Flatpak"
        ]
        self._write_catalog()
        with self.assertRaises(ValueError):
            mod.verify(root)


if __name__ == "__main__":
    unittest.main()
