"""Deterministic invariant tests for the tracked release catalog.

The checked-in file ``native-offline/releases/catalog.json`` is the release
catalog consumed by the offline packaging flow. These tests assert structural
invariants that every catalog entry must satisfy and, when an artifact binary
is actually present next to the catalog, that its byte size and per-file
``.sha256`` sidecar still match the recorded metadata.

Nothing here mutates the catalog or the release directory; missing local
binaries are skipped explicitly rather than treated as failures.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASES_DIR = ROOT / "native-offline" / "releases"
CATALOG_PATH = RELEASES_DIR / "catalog.json"

REQUIRED_ARTIFACT_KEYS = ("version", "platform", "format", "filename", "size", "sha256")
REQUIRED_STAGING_FORMATS = frozenset({"DMG", "APK", "DEB", "Flatpak"})
PATH_SEPARATORS = ("/", "\\")


def load_catalog():
    """Return the parsed catalog JSON. Raises on malformed JSON."""
    with CATALOG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class ReleaseCatalogInvariantTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            CATALOG_PATH.is_file(), "tracked release catalog is missing: %s" % CATALOG_PATH
        )
        self.catalog = load_catalog()

    def test_catalog_is_dict_with_non_empty_artifacts(self):
        self.assertIsInstance(self.catalog, dict, "catalog root must be a JSON object")
        self.assertIn("artifacts", self.catalog, "catalog must contain an 'artifacts' key")
        artifacts = self.catalog["artifacts"]
        self.assertIsInstance(artifacts, list, "'artifacts' must be a JSON array")
        self.assertTrue(artifacts, "'artifacts' must not be empty")

    def test_artifacts_have_required_keys(self):
        for artifact in self.catalog["artifacts"]:
            self.assertIsInstance(artifact, dict, "each artifact must be a JSON object")
            with self.subTest(filename=artifact.get("filename", "<missing>")):
                for key in REQUIRED_ARTIFACT_KEYS:
                    self.assertIn(key, artifact, "artifact is missing required key %r" % key)
                    self.assertNotEqual(
                        artifact[key], None, "artifact key %r must not be null" % key
                    )
                self.assertIsInstance(artifact["size"], int, "'size' must be an integer")
                self.assertGreater(artifact["size"], 0, "'size' must be positive")

    def test_version_appears_in_filename(self):
        for artifact in self.catalog["artifacts"]:
            with self.subTest(filename=artifact.get("filename", "<missing>")):
                version = artifact["version"]
                self.assertIsInstance(version, str, "'version' must be a string")
                self.assertTrue(version, "'version' must not be empty")
                self.assertIn(
                    version,
                    artifact["filename"],
                    "artifact version %r is not present in filename %r"
                    % (version, artifact["filename"]),
                )

    def test_filenames_are_unique_and_contain_no_path_separators(self):
        seen = {}
        for artifact in self.catalog["artifacts"]:
            name = artifact["filename"]
            with self.subTest(filename=name):
                self.assertIsInstance(name, str, "'filename' must be a string")
                self.assertTrue(name, "'filename' must not be empty")
                self.assertEqual(
                    Path(name).name,
                    name,
                    "filename must be a bare file name, not a path: %r" % name,
                )
                for separator in PATH_SEPARATORS:
                    self.assertNotIn(
                        separator,
                        name,
                        "filename must not contain a path separator %r: %r"
                        % (separator, name),
                    )
                self.assertNotIn(
                    name, seen, "duplicate artifact filename %r" % name
                )
                seen[name] = artifact

    def test_required_fresh_staging_formats_are_present(self):
        present = {artifact["format"] for artifact in self.catalog["artifacts"]}
        missing = sorted(REQUIRED_STAGING_FORMATS - present)
        self.assertEqual(
            missing,
            [],
            "release catalog is missing required staging formats %s; present: %s"
            % (missing, sorted(present)),
        )

    def test_exe_entries_pass_release_gate(self):
        exe_artifacts = [
            artifact
            for artifact in self.catalog["artifacts"]
            if artifact.get("format") == "EXE"
        ]
        if not exe_artifacts:
            self.skipTest("no EXE artifacts recorded in the release catalog")
        for artifact in exe_artifacts:
            with self.subTest(filename=artifact["filename"]):
                self.assertEqual(
                    artifact.get("release_gate"),
                    "PASS",
                    "EXE artifact %r must have release_gate 'PASS'" % artifact["filename"],
                )

    def test_local_artifact_bytes_and_sidecar_match_catalog(self):
        artifacts = self.catalog["artifacts"]
        verified = []
        absent = []
        for artifact in artifacts:
            path = RELEASES_DIR / artifact["filename"]
            if not path.is_file():
                # Explicit guarded skip: the binary is not shipped in the repo.
                absent.append(artifact["filename"])
                continue
            verified.append(artifact["filename"])
            with self.subTest(filename=artifact["filename"]):
                self.assertEqual(
                    path.stat().st_size,
                    artifact["size"],
                    "on-disk size for %r does not match catalog 'size'"
                    % artifact["filename"],
                )
                sidecar = path.with_name(path.name + ".sha256")
                self.assertTrue(
                    sidecar.is_file(),
                    "missing sha256 sidecar for local artifact: %s" % sidecar,
                )
                tokens = sidecar.read_text(encoding="utf-8").split()
                self.assertTrue(
                    tokens, "sha256 sidecar is empty: %s" % sidecar
                )
                self.assertEqual(
                    tokens[0].strip().lower(),
                    artifact["sha256"].strip().lower(),
                    "sha256 sidecar does not match catalog 'sha256' for %r"
                    % artifact["filename"],
                )
        if not verified:
            self.skipTest(
                "no catalog artifact binaries are present in %s; skipped size/sha256 "
                "verification for %d recorded entries" % (RELEASES_DIR, len(absent))
            )


if __name__ == "__main__":
    unittest.main()
