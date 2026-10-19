"""Deterministic tests for tools/release-evidence.py.

The tool produces the release evidence bundle from inputs already committed to
the repository (``THIRD_PARTY_NOTICES.md``, npm and Cargo lockfiles) plus an
optional directory of release artifacts. This suite pins the observable
contract:

* every input parser keeps its meaning (SPDX expressions vs. license names,
  npm ``integrity`` -> SHA hash, Cargo ``checksum`` -> SHA-256),
* the SBOM is a valid CycloneDX 1.5 document whose component set matches the
  license inventory,
* identical inputs always produce byte-identical evidence (no hidden
  timestamp), and
* ``SHA256SUMS`` covers exactly the regular artifacts and is written in GNU
  ``sha256sum`` format.

Parsers are exercised against the real repository files so a future lockfile or
notice-table change is caught here; the ``generate``/``SHA256SUMS`` tests use
synthetic fixtures under a TemporaryDirectory and never touch the release
directory.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "release-evidence.py"

spec = importlib.util.spec_from_file_location("release_evidence", TOOL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

HEX512 = re.compile(r"^[0-9a-f]{128}$")
HEX256 = re.compile(r"^[0-9a-f]{64}$")


class LicenseFieldTests(unittest.TestCase):
    """Notice-table license text must map to valid CycloneDX license fields."""

    def test_spdx_expression_uses_expression_form(self):
        self.assertEqual(mod._license_field("MIT"), {"expression": "MIT"})
        self.assertEqual(
            mod._license_field("Apache-2.0 OR MIT"), {"expression": "Apache-2.0 OR MIT"}
        )

    def test_known_alias_maps_to_spdx_id(self):
        self.assertEqual(
            mod._license_field("SIL OFL 1.1"), {"license": {"id": "OFL-1.1"}}
        )

    def test_name_only_license_is_not_guessed_into_an_expression(self):
        for text in ("Public domain", "BSD family"):
            with self.subTest(text=text):
                self.assertEqual(
                    mod._license_field(text), {"license": {"name": text}}
                )

    def test_prose_license_stays_a_name(self):
        field = mod._license_field("Permissive (MIT-style), see libretro.h.LICENSE.txt")
        self.assertEqual(
            field,
            {"license": {"name": "Permissive (MIT-style), see libretro.h.LICENSE.txt"}},
        )

    def test_empty_cell_has_no_license_field(self):
        self.assertIsNone(mod._license_field(""))


class NoticeParsingTests(unittest.TestCase):
    def setUp(self):
        self.components = mod.parse_notices(ROOT / "THIRD_PARTY_NOTICES.md")
        self.assertTrue(self.components, "notices table produced no components")
        self.by_name = {item["name"]: item for item in self.components}

    def test_bundled_cores_and_licenses_are_captured(self):
        for needle, license_text in (
            ("mGBA", "MPL-2.0"),
            ("Azahar", "GPL-2.0-or-later"),
            ("melonDS DS", "GPL-3.0-or-later"),
            ("MoltenVK", "Apache-2.0"),
        ):
            with self.subTest(component=needle):
                match = next(
                    (item for name, item in self.by_name.items() if needle in name), None
                )
                self.assertIsNotNone(match, f"{needle} missing from notices parse")
                self.assertEqual(match["license"], license_text)
                self.assertEqual(match["ecosystem"], "bundled-notices")

    def test_markdown_and_backticks_are_stripped(self):
        joined = " ".join(self.by_name)
        self.assertNotIn("**", joined)
        self.assertNotIn("`", joined)

    def test_missing_notices_file_yields_nothing(self):
        self.assertEqual(mod.parse_notices(ROOT / "does-not-exist.md"), [])


class NpmLockTests(unittest.TestCase):
    def setUp(self):
        self.components = mod.parse_npm_lock(ROOT / "native-offline" / "package-lock.json")

    def test_committed_lockfile_parses_named_licensed_components(self):
        self.assertTrue(self.components)
        for component in self.components:
            self.assertTrue(component["name"])
            self.assertEqual(component["ecosystem"], "npm")
            self.assertTrue(component.get("version"))

    def test_integrity_becomes_a_sha512_hash(self):
        hashed = [item for item in self.components if item.get("hashes")]
        self.assertTrue(hashed, "no npm integrity hashes were parsed")
        for component in hashed:
            digest = component["hashes"][0]
            self.assertEqual(digest["alg"], "SHA-512")
            self.assertRegex(digest["content"], HEX512)

    def test_root_project_entry_is_skipped(self):
        # The "" package key is the project itself, represented by SBOM metadata.
        self.assertNotIn("", [item["name"] for item in self.components])

    def test_missing_lockfile_yields_nothing(self):
        self.assertEqual(mod.parse_npm_lock(ROOT / "nope.lock"), [])


class CargoLockTests(unittest.TestCase):
    LOCK = """\
[[package]]
name = "serde"
version = "1.0.200"
source = "registry+https://github.com/rust-lang/crates.io-index"
checksum = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

[[package]]
name = "local-crate"
version = "0.1.0"

[metadata]
checksum = "ignored-outside-package"
"""

    def test_fields_and_checksum_are_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Cargo.lock"
            path.write_text(self.LOCK, encoding="utf-8")
            parsed = {item["name"]: item for item in mod.parse_cargo_lock(path)}
        serde = parsed["serde"]
        self.assertEqual(serde["version"], "1.0.200")
        self.assertEqual(serde["license"], None)
        self.assertEqual(serde["ecosystem"], "cargo")
        self.assertEqual(serde["hashes"][0]["alg"], "SHA-256")
        self.assertRegex(serde["hashes"][0]["content"], HEX256)
        # A path dependency without a checksum gets no hashes entry.
        self.assertNotIn("hashes", parsed["local-crate"])

    def test_metadata_section_is_not_treated_as_a_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Cargo.lock"
            path.write_text(self.LOCK, encoding="utf-8")
            names = [item["name"] for item in mod.parse_cargo_lock(path)]
        self.assertEqual(names, ["serde", "local-crate"])

    def test_committed_lockfiles_parse_and_sort_deterministically(self):
        for relative in (
            "native-offline/src-tauri/Cargo.lock",
            "rust-gateway/Cargo.lock",
        ):
            with self.subTest(lockfile=relative):
                components = mod.parse_cargo_lock(ROOT / relative)
                self.assertTrue(components)
                self.assertEqual(
                    components, mod.parse_cargo_lock(ROOT / relative)
                )


class Sha256SumsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()

    def _digest(self, payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def test_regular_artifacts_get_gnu_sha256sum_lines(self):
        (self.artifacts / "app.dmg").write_bytes(b"dmg-bytes")
        (self.artifacts / "app.apk").write_bytes(b"apk-bytes")
        names = mod.write_sha256sums(self.artifacts, self.root / "SHA256SUMS")
        self.assertEqual(names, ["app.apk", "app.dmg"])
        lines = (self.root / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            lines,
            [
                f"{self._digest(b'apk-bytes')}  app.apk",
                f"{self._digest(b'dmg-bytes')}  app.dmg",
            ],
        )

    def test_evidence_and_metadata_files_are_excluded(self):
        (self.artifacts / "installer.exe").write_bytes(b"exe")
        for excluded in (
            "catalog.json",
            "SHA256SUMS",
            "installer.exe.sha256",
            "installer.exe.sig",
            "installer.exe.asc",
        ):
            (self.artifacts / excluded).write_text("not an artifact", encoding="utf-8")
        (self.artifacts / ".hidden").write_text("hidden", encoding="utf-8")
        (self.artifacts / "subdir").mkdir()
        names = mod.write_sha256sums(self.artifacts, self.root / "SHA256SUMS")
        self.assertEqual(names, ["installer.exe"])

    def test_empty_artifact_directory_is_rejected(self):
        with self.assertRaises(ValueError):
            mod.write_sha256sums(self.artifacts, self.root / "SHA256SUMS")


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _generate(self, name, **kwargs):
        out = self.root / name
        inventory, sbom, checksummed = mod.generate(ROOT, out, **kwargs)
        return out, inventory, sbom, checksummed

    def test_output_is_byte_identical_for_identical_inputs(self):
        first, _, _, _ = self._generate("first")
        second, _, _, _ = self._generate("second")
        for filename in ("LICENSE_INVENTORY.json", "sbom.cdx.json"):
            with self.subTest(filename=filename):
                self.assertEqual(
                    (first / filename).read_bytes(), (second / filename).read_bytes()
                )
        self.assertNotIn("timestamp", json.loads((first / "sbom.cdx.json").read_text())["metadata"])

    def test_inventory_counts_are_internally_consistent(self):
        _, inventory, sbom, _ = self._generate("inv")
        summary = inventory["summary"]
        self.assertEqual(summary["total"], len(inventory["components"]))
        self.assertEqual(
            summary["with_license"] + summary["unknown_license"], summary["total"]
        )
        self.assertEqual(sum(summary["by_license"].values()), summary["total"])
        self.assertEqual(summary["unknown_license"], sum(summary["unknown_by_ecosystem"].values()))
        self.assertEqual(summary["total"], len(sbom["components"]))

    def test_sbom_is_cyclonedx_1_5_application_document(self):
        _, _, sbom, _ = self._generate("sbom")
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["specVersion"], "1.5")
        self.assertEqual(sbom["version"], 1)
        metadata = sbom["metadata"]
        self.assertEqual(metadata["tools"][0]["name"], mod.TOOL_NAME)
        component = metadata["component"]
        self.assertEqual(component["type"], "application")
        self.assertEqual(component["licenses"], [{"expression": "GPL-3.0-or-later"}])
        props = {item["name"]: item["value"] for item in component["properties"]}
        self.assertEqual(props["an3:licenseAudit"], "docs/licensing/license-audit.md")

    def test_sbom_components_have_refs_names_and_ecosystems(self):
        _, inventory, sbom, _ = self._generate("comps")
        self.assertGreater(len(sbom["components"]), 0)
        refs = [item["bom-ref"] for item in sbom["components"]]
        self.assertEqual(len(refs), len(set(refs)), "duplicate bom-ref in SBOM")
        for entry in sbom["components"]:
            self.assertTrue(entry["bom-ref"])
            self.assertTrue(entry["name"])
            props = {item["name"]: item["value"] for item in entry["properties"]}
            self.assertIn(props["an3:ecosystem"], {"bundled-notices", "npm", "cargo"})
        # Notice-table components surface in the SBOM with their license field.
        names = {entry["name"] for entry in sbom["components"]}
        self.assertTrue(any("mGBA" in name for name in names))

    def test_known_cores_carry_a_license_entry_into_the_sbom(self):
        _, _, sbom, _ = self._generate("licenses")
        licensed = [
            entry for entry in sbom["components"] if entry.get("licenses")
        ]
        self.assertGreater(len(licensed), 0)
        mgba = next(
            entry for entry in sbom["components"] if "mGBA" in entry["name"]
        )
        self.assertEqual(mgba["licenses"], [{"expression": "MPL-2.0"}])

    def test_timestamp_is_only_recorded_when_explicit(self):
        stamp = "2026-09-19T00:00:00Z"
        without, _, _, _ = self._generate("no-stamp")
        with_stamp, _, _, _ = self._generate("with-stamp", timestamp=stamp)
        self.assertNotIn("timestamp", json.loads((without / "sbom.cdx.json").read_text())["metadata"])
        self.assertEqual(
            json.loads((with_stamp / "sbom.cdx.json").read_text())["metadata"]["timestamp"],
            stamp,
        )

    def test_non_iso_timestamp_is_rejected(self):
        # The release train must not pass its directory stamp or run id here:
        # CycloneDX metadata.timestamp has to be an ISO-8601 date-time.
        with self.assertRaises(SystemExit) as caught:
            mod.main(
                [
                    "--root",
                    str(self.root),
                    "--out",
                    str(self.root / "bad-stamp"),
                    "--timestamp",
                    "20260919T000000Z-12345",
                ]
            )
        self.assertEqual(caught.exception.code, 2)

    def test_iso_timestamp_with_offset_is_accepted(self):
        stamp = "2026-09-19T15:55:00+02:00"
        out, _, sbom, _ = self._generate("offset-stamp", timestamp=stamp)
        self.assertEqual(sbom["metadata"]["timestamp"], stamp)

    def test_artifacts_option_writes_sha256sums(self):
        artifacts = self.root / "release"
        artifacts.mkdir()
        (artifacts / "installer.dmg").write_bytes(b"payload")
        out, _, _, checksummed = self._generate("artifacts", artifacts=artifacts)
        self.assertEqual(checksummed, ["installer.dmg"])
        self.assertEqual(
            (out / "SHA256SUMS").read_text(encoding="utf-8"),
            f"{hashlib.sha256(b'payload').hexdigest()}  installer.dmg\n",
        )

    def test_no_sha256sums_without_artifacts_option(self):
        out, _, _, checksummed = self._generate("no-artifacts")
        self.assertEqual(checksummed, [])
        self.assertFalse((out / "SHA256SUMS").exists())


class UnknownLicenseGateTests(unittest.TestCase):
    """``--fail-on-unknown`` is the fail-closed publication gate.

    A release may not be published while any bundled component still has no
    license value, so the gate must exit non-zero and name the ecosystems that
    need reconciliation. This is the documented policy in
    ``docs/licensing/distribution-compliance.md``.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.out = self.root / "out"

    def _write_notices(self, license_cell: str):
        (self.root / "THIRD_PARTY_NOTICES.md").write_text(
            "| Component | License |\n| --- | --- |\n"
            f"| Example Core | {license_cell} |\n",
            encoding="utf-8",
        )

    def test_summary_breaks_unknowns_down_by_ecosystem(self):
        self._write_notices("")
        inventory, _, _ = mod.generate(self.root, self.out)
        summary = inventory["summary"]
        self.assertEqual(summary["unknown_license"], 1)
        self.assertEqual(summary["unknown_by_ecosystem"], {"bundled-notices": 1})

    def test_gate_fails_when_a_component_has_no_license(self):
        self._write_notices("")
        code = mod.main(
            ["--root", str(self.root), "--out", str(self.out), "--fail-on-unknown"]
        )
        self.assertEqual(code, 3)
        inventory = json.loads((self.out / "LICENSE_INVENTORY.json").read_text())
        self.assertEqual(inventory["summary"]["unknown_license"], 1)

    def test_gate_passes_when_every_component_is_licensed(self):
        self._write_notices("MIT")
        code = mod.main(
            ["--root", str(self.root), "--out", str(self.out), "--fail-on-unknown"]
        )
        self.assertEqual(code, 0)

    def test_gate_is_off_by_default(self):
        self._write_notices("")
        self.assertEqual(mod.main(["--root", str(self.root), "--out", str(self.out)]), 0)


if __name__ == "__main__":
    unittest.main()
