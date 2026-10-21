# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned browser runtime delivery and update-check failure handling."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "verification"
VENDORED = Path(app.EMULATOR_VENDORED_RUNTIME)
UPDATE_FILE = "emulator.min.js"
ORIGINAL_SUFFIX = b"})})}versionAsInt(t){"
PATCHED_SUFFIX = b"})}).catch(()=>{})}versionAsInt(t){"


class WebRuntimeDeliveryTests(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="web-runtime-delivery-", dir=WORK)
        self.cache = Path(self.temp.name) / "cache"

    def tearDown(self):
        self.temp.cleanup()

    def require_vendored_runtime(self, keys):
        missing = [key for key in keys if not (VENDORED / key).is_file()]
        if missing:
            self.skipTest(
                "source-only snapshot omits generated runtime assets restored from "
                "the checksum-locked package cache"
            )

    def read_locked_source(self, relative):
        key = f"latest/data-v2/{relative}"
        expected = app.emulator_runtime_lock()[key]
        payload = (VENDORED / key).read_bytes()
        if relative == UPDATE_FILE and hashlib.sha256(payload).hexdigest() != expected:
            self.assertEqual(payload.count(PATCHED_SUFFIX), 1)
            payload = payload.replace(PATCHED_SUFFIX, ORIGINAL_SUFFIX, 1)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), expected, relative)
        return payload, expected

    def test_data_v2_lock_covers_the_complete_vendored_runtime(self):
        lock = app.emulator_runtime_lock()
        entries = {name: digest for name, digest in lock.items() if name.startswith("latest/data-v2/")}
        self.assertEqual(len(entries), 9)
        self.require_vendored_runtime(entries)
        for name, expected in entries.items():
            with self.subTest(asset=name):
                payload = (VENDORED / name).read_bytes()
                if name.endswith(f"/{UPDATE_FILE}") and hashlib.sha256(payload).hexdigest() != expected:
                    self.assertEqual(payload.count(PATCHED_SUFFIX), 1)
                    payload = payload.replace(PATCHED_SUFFIX, ORIGINAL_SUFFIX, 1)
                self.assertEqual(hashlib.sha256(payload).hexdigest(), expected)

    def test_cold_cache_serves_locked_runtime_without_cdn_access(self):
        self.require_vendored_runtime([
            f"latest/data-v2/{UPDATE_FILE}",
            "latest/data-v2/cores/reports/azahar.json",
        ])
        _raw, script_hash = self.read_locked_source(UPDATE_FILE)
        with mock.patch.object(app, "EMULATOR_CACHE_DIR", str(self.cache)):
            with mock.patch.object(app, "urlopen", side_effect=AssertionError("CDN should not be called")):
                script = app.cached_emulator_asset("latest", UPDATE_FILE, "-v2")
                report = app.cached_emulator_asset("latest", "cores/reports/azahar.json", "-v2")
        script_bytes = Path(script).read_bytes()
        self.assertEqual(script_bytes.count(PATCHED_SUFFIX), 1)
        self.assertNotIn(ORIGINAL_SUFFIX, script_bytes)
        self.assertEqual(
            hashlib.sha256(script_bytes.replace(PATCHED_SUFFIX, ORIGINAL_SUFFIX, 1)).hexdigest(),
            script_hash,
        )
        report_key = "latest/data-v2/cores/reports/azahar.json"
        self.assertEqual(
            hashlib.sha256(Path(report).read_bytes()).hexdigest(),
            app.emulator_runtime_lock()[report_key],
        )

    def test_existing_unpatched_update_bundle_is_migrated_from_the_exact_lock(self):
        self.require_vendored_runtime([f"latest/data-v2/{UPDATE_FILE}"])
        raw, script_hash = self.read_locked_source(UPDATE_FILE)
        target = self.cache / "latest" / UPDATE_FILE
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        with mock.patch.object(app, "EMULATOR_CACHE_DIR", str(self.cache)):
            served = app.cached_emulator_asset("latest", UPDATE_FILE, "-v2")
        payload = Path(served).read_bytes()
        self.assertEqual(payload.count(PATCHED_SUFFIX), 1)
        self.assertEqual(
            hashlib.sha256(payload.replace(PATCHED_SUFFIX, ORIGINAL_SUFFIX, 1)).hexdigest(),
            script_hash,
        )

    def test_cache_path_rejects_symlink_that_escapes_cache_root(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        self.cache.mkdir()
        try:
            (self.cache / "latest").symlink_to(outside, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"directory symlinks are unavailable: {error}")
        with mock.patch.object(app, "EMULATOR_CACHE_DIR", str(self.cache)):
            with self.assertRaises(ValueError):
                app.cached_emulator_asset("latest", UPDATE_FILE, "-v2")
        self.assertEqual(list(outside.iterdir()), [])

    def test_vendored_runtime_rejects_symlink_that_escapes_vendor_root(self):
        vendor = Path(self.temp.name) / "vendor"
        outside = Path(self.temp.name) / "outside-vendor"
        vendor.mkdir()
        outside.mkdir()
        try:
            (vendor / "latest").symlink_to(outside, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"directory symlinks are unavailable: {error}")
        with mock.patch.object(app, "EMULATOR_CACHE_DIR", str(self.cache)):
            with mock.patch.object(app, "EMULATOR_VENDORED_RUNTIME", str(vendor)):
                with self.assertRaises(ValueError):
                    app.install_vendored_emulator_asset("latest", UPDATE_FILE, "-v2")
        self.assertFalse(self.cache.exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_drifted_vendored_script_is_not_installed(self):
        root = Path(self.temp.name) / "vendor"
        source = root / "latest" / "data-v2" / UPDATE_FILE
        source.parent.mkdir(parents=True)
        source.write_bytes(b"unlocked runtime bytes")
        with mock.patch.object(app, "EMULATOR_CACHE_DIR", str(self.cache)):
            with mock.patch.object(app, "EMULATOR_VENDORED_RUNTIME", str(root)):
                self.assertIsNone(app.install_vendored_emulator_asset("latest", UPDATE_FILE, "-v2"))
        self.assertFalse(self.cache.exists())

    def test_native_packager_applies_the_same_update_check_patch_after_locking(self):
        source = (ROOT / "native-offline" / "scripts" / "prepare-web.mjs").read_text(encoding="utf-8")
        self.assertIn('relativePath === "latest/data-v2/emulator.min.js"', source)
        self.assertIn('const patched = "})}).catch(()=>{})}versionAsInt(t){"', source)
        self.assertIn("frozen dependency lock", source)


if __name__ == "__main__":
    unittest.main()
