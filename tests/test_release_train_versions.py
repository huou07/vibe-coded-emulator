"""Regression: the coordinated release train must derive artifact names from
version metadata, never from a hard-coded version literal.

Historical failure: `tools/release-train.sh --coordinated` carried stale
`0.4.5` artifact filenames long after the app moved on, so a bump could copy a
leftover file under the wrong name.
"""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_TRAIN = ROOT / "tools" / "release-train.sh"

# Any artifact-like name carrying a literal semver (vibecodedemulator-1.2.3-...).
HARDCODED_ARTIFACT = re.compile(
    r"(?i)(vibecodedemulator|an3-offline)[-_][0-9]+\.[0-9]+\.[0-9]+"
)


class ReleaseTrainVersionDerivationTests(unittest.TestCase):
    def test_native_release_version_sources_are_consistent(self):
        native = ROOT / "native-offline"
        package = json.loads((native / "package.json").read_text(encoding="utf-8"))
        package_lock = json.loads((native / "package-lock.json").read_text(encoding="utf-8"))
        desktop = json.loads(
            (native / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
        )
        android = json.loads(
            (native / "src-tauri" / "tauri.android.conf.json").read_text(encoding="utf-8")
        )
        cargo = (native / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
        cargo_version = re.search(r'(?m)^version\s*=\s*"([^"]+)"', cargo)
        self.assertIsNotNone(cargo_version, "native Cargo.toml package version is missing")
        versions = {
            package["version"],
            package_lock["version"],
            package_lock["packages"][""]["version"],
            desktop["version"],
            android["version"],
            cargo_version.group(1),
        }
        self.assertEqual(len(versions), 1, "native app version sources have drifted: %s" % versions)

        version = desktop["version"]
        flatpak = (native / "flatpak" / "space.an3tocom.offline.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            f"vibecodedemulator-{version}-linux-amd64.deb",
            flatpak,
            "Flatpak must consume the DEB produced for the current desktop version",
        )
        metainfo = (native / "flatpak" / "space.an3tocom.offline.metainfo.xml").read_text(
            encoding="utf-8"
        )
        latest_release = re.search(r'<release version="([^"]+)"', metainfo)
        self.assertIsNotNone(latest_release, "Flatpak release metadata is missing")
        self.assertEqual(latest_release.group(1), version)

    def test_no_hardcoded_artifact_version_literals(self):
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        hits = sorted(set(HARDCODED_ARTIFACT.findall(text)))
        self.assertEqual(
            hits, [],
            "release-train.sh hard-codes artifact version literals; derive them "
            "from tauri.conf.json / tauri.android.conf.json instead: %s" % hits,
        )

    def test_derives_versions_from_metadata(self):
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        self.assertIn("tauri.conf.json", text)
        self.assertIn("tauri.android.conf.json", text)
        self.assertIn("desktop_version", text)
        self.assertIn("android_version", text)

    def test_android_aab_is_required_and_checksummed(self):
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        self.assertIn(
            'aab_name="vibecodedemulator-${android_version}-android-arm64-staging.aab"',
            text,
        )
        self.assertIn(
            'for expected in "$mac_name" "$apk_name" "$aab_name"',
            text,
        )
        self.assertIn('      "$aab_name" \\', text)


class ReleaseTrainEvidenceWiringTests(unittest.TestCase):
    """The frozen snapshot must ship machine-readable release evidence.

    Both ``freeze`` and the coordinated build call the shared
    ``emit_release_evidence`` helper so LICENSE_INVENTORY.json, sbom.cdx.json
    and SHA256SUMS land next to SOURCE_FROZEN.json. This is a static contract
    check plus a real syntax check; the freeze/coordinated paths themselves need
    the macOS builder and a verified dependency cache and are not run here.
    """

    def test_bash_syntax_is_valid(self):
        result = subprocess.run(
            ["bash", "-n", str(RELEASE_TRAIN)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_freeze_and_coordinated_build_emit_evidence(self):
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        self.assertIn("tools/release-evidence.py", text)
        self.assertEqual(
            text.count('emit_release_evidence "'),
            2,
            "freeze and coordinated build must both call emit_release_evidence",
        )
        self.assertIn("--artifacts", text)
        self.assertIn("--fail-on-unknown", text)
        self.assertIn("AN3_REQUIRE_KNOWN_LICENSES", text)
        self.assertIn("SOURCE_FROZEN.json", text)

    def test_linux_builder_uses_the_installed_rustup_toolchain(self):
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        self.assertIn(
            r'export PATH=\"\$HOME/.cargo/bin:\$PATH\"',
            text,
            "the coordinated Linux SSH command must select rustup's compatible toolchain",
        )

    def test_freeze_evidence_reads_frozen_version_metadata(self):
        # The SBOM metadata component carries the desktop and Android versions,
        # so the freeze snapshot must extract those config files from the
        # archive instead of reading the mutable working tree.
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        for relative in (
            "native-offline/src-tauri/tauri.conf.json",
            "native-offline/src-tauri/tauri.android.conf.json",
        ):
            self.assertIn(relative, text)

    def test_evidence_timestamp_is_iso_8601_not_a_directory_stamp(self):
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        iso = 'evidence_timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"'
        self.assertEqual(
            text.count(iso),
            2,
            "freeze and the coordinated build must both derive an ISO-8601 timestamp",
        )
        self.assertEqual(text.count('"$evidence_timestamp"'), 2)
        # A raw directory stamp or run id must never be handed to --timestamp.
        self.assertNotIn(
            '"$freeze_dir" "$freeze_dir" "$stamp"', text
        )
        self.assertNotIn(
            '"$run_root" "$artifacts" "$run_id"', text
        )


if __name__ == "__main__":
    unittest.main()
