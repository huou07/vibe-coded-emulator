"""Regression: the coordinated release train must derive artifact names from
version metadata, never from a hard-coded version literal.

Historical failure: `tools/release-train.sh --coordinated` carried stale
`0.4.5` artifact filenames long after the app moved on, so a bump could copy a
leftover file under the wrong name.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
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


class ReleaseTrainStorageLifecycleTests(unittest.TestCase):
    def cleanup_harness(
        self,
        root: Path,
        keep_local: bool = False,
        keep_remote: bool = False,
        exit_code: int = 0,
    ):
        text = RELEASE_TRAIN.read_text(encoding="utf-8")
        start = text.index("coordinated_cleanup() {")
        end = text.index("\n}\ntrap coordinated_cleanup EXIT", start) + 2
        function = text[start:end]
        scratch = root / "run" / "macos-source"
        scratch.mkdir(parents=True)
        artifacts = root / "run" / "artifacts"
        artifacts.mkdir()
        (artifacts / "ARTIFACTS.sha256").write_text("preserved\n", encoding="utf-8")
        bin_dir = root / "bin"
        bin_dir.mkdir()
        ssh = bin_dir / "ssh"
        ssh.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$SSH_RECORD\"\n", encoding="utf-8")
        ssh.chmod(0o755)
        env = os.environ.copy()
        env.update({"PATH": f"{bin_dir}:{env['PATH']}", "SSH_RECORD": str(root / "ssh.log")})
        if keep_local:
            env["AN3_KEEP_LOCAL_BUILD_ROOTS"] = "1"
        else:
            env.pop("AN3_KEEP_LOCAL_BUILD_ROOTS", None)
        if keep_remote:
            env["AN3_KEEP_REMOTE_BUILD_ROOTS"] = "1"
        else:
            env.pop("AN3_KEEP_REMOTE_BUILD_ROOTS", None)
        shell = f"""set -euo pipefail
note() {{ :; }}
windows_ps() {{ printf '%s\\n' "$2" >> "$WINDOWS_RECORD"; }}
ssh_cmd=(ssh)
linux_builder=linux-builder
windows_builder=windows-builder
cleanup_local_source={str(scratch)!r}
cleanup_failed_root={str(root / 'run')!r}
cleanup_linux_root=/tmp/an3-release-train-storage-test
cleanup_windows_root=C:/AN3/release-train-storage-test
WINDOWS_RECORD={str(root / 'windows.log')!r}
{function}
trap coordinated_cleanup EXIT
exit {exit_code}
"""
        result = subprocess.run(["bash", "-c", shell], env=env, capture_output=True, text=True)
        return scratch, result, root

    def test_exit_cleanup_removes_scratch_but_preserves_verified_outputs(self):
        with tempfile.TemporaryDirectory(prefix="an3-release-cleanup-") as temp:
            scratch, result, root = self.cleanup_harness(Path(temp))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(scratch.exists())
            self.assertEqual((root / "run" / "artifacts" / "ARTIFACTS.sha256").read_text(), "preserved\n")
            self.assertIn("/tmp/an3-release-train-storage-test", (root / "ssh.log").read_text())
            self.assertIn("C:/AN3/release-train-storage-test", (root / "windows.log").read_text())

    def test_explicit_keep_flags_retain_local_and_remote_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="an3-release-cleanup-") as temp:
            scratch, result, root = self.cleanup_harness(Path(temp), keep_local=True, keep_remote=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(scratch.exists())
            self.assertFalse((root / "ssh.log").exists())
            self.assertFalse((root / "windows.log").exists())

    def test_failed_build_removes_owned_attempt_root_and_preserves_failure_status(self):
        with tempfile.TemporaryDirectory(prefix="an3-release-cleanup-") as temp:
            scratch, result, root = self.cleanup_harness(Path(temp), exit_code=7)
            self.assertEqual(result.returncode, 7)
            self.assertFalse(scratch.exists())
            self.assertFalse((root / "run").exists())

    def test_keep_local_flag_retains_failed_attempt_for_diagnosis(self):
        with tempfile.TemporaryDirectory(prefix="an3-release-cleanup-") as temp:
            scratch, result, root = self.cleanup_harness(Path(temp), keep_local=True, exit_code=7)
            self.assertEqual(result.returncode, 7)
            self.assertTrue(scratch.exists())
            self.assertTrue((root / "run" / "artifacts" / "ARTIFACTS.sha256").exists())


if __name__ == "__main__":
    unittest.main()
