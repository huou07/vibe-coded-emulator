#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression contracts for the browser 3DS delivery path.

Browser 3DS was not playable for two reasons, both reproduced live on
2026-10-18 before anything was changed:

1. ``/emulatorjs/latest/data-v2/cores/azahar-thread-wasm.data`` and
   ``.../cores/reports/azahar.json`` answered **502**. The repaired Azahar
   runtime is published only by a pinned project build — the public EmulatorJS
   CDN has no ``latest/data-v2`` path at all — so on a host whose server cache
   has not been seeded by ``deploy/seed-azahar-core.sh`` the core never loaded
   and the player never left the asset stage. The same bytes were already
   tracked in-tree and pinned by ``native-offline/shared/web-runtime-lock.json``.

2. The playable check required a running ``AudioContext`` reachable from
   ``EJS_emulator``, which this runtime never exposes: the core creates its
   context in its own glue (``RWebAudioInit``), so the check could never pass and
   the overlay stayed on "did not reach ... running audio output" while frames
   were already presenting.

These checks are behavioural and need no ROM, firmware, key or save. They are
what a hosted runner can hold on to; the frame-presenting run itself needs a
lawful user-owned fixture and stays ``UNVERIFIED`` without one.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
LOCK = ROOT / "native-offline/shared/web-runtime-lock.json"
VENDORED = ROOT / "native-offline/src-tauri/gen/android/app/src/main/assets/emulatorjs"
PLAYER = ROOT / "static/player.js"
PORT = 18996

DATA_V2_CORE = "cores/azahar-thread-wasm.data"
DATA_V2_REPORT = "cores/reports/azahar.json"


def load_app():
    spec = importlib.util.spec_from_file_location("an3_app_3ds_runtime", APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VendoredRuntimeDeliveryTests(unittest.TestCase):
    """The server must reach its own lock-verified runtime before the network."""

    def test_the_vendored_runtime_still_matches_the_frozen_lock(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        repaired = {name: digest for name, digest in lock.items() if name.startswith("latest/data-v2/")}
        self.assertEqual(len(repaired), 9, "the repaired data-v2 runtime is nine locked assets")
        for name, digest in repaired.items():
            with self.subTest(asset=name):
                payload = (VENDORED / name).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)

    def test_a_cold_cache_is_served_from_the_vendored_runtime(self):
        app = load_app()
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="an3-cold-cache-") as cache:
            with mock.patch.object(app, "EMULATOR_CACHE_DIR", cache):
                for relative in (DATA_V2_CORE, DATA_V2_REPORT):
                    with self.subTest(asset=relative):
                        served = app.install_vendored_emulator_asset("latest", relative)
                        self.assertIsNotNone(served)
                        payload = Path(served).read_bytes()
                        self.assertEqual(
                            hashlib.sha256(payload).hexdigest(), lock[f"latest/data-v2/{relative}"]
                        )
                        # The cache keeps the unversioned layout the deploy seed
                        # helper writes, so both delivery paths agree.
                        self.assertEqual(Path(served).parent, Path(cache) / "latest" / Path(relative).parent)

    def test_a_vendored_asset_that_drifts_from_the_lock_is_rejected(self):
        app = load_app()
        with tempfile.TemporaryDirectory(prefix="an3-drift-") as root:
            vendored = Path(root) / "emulatorjs"
            target = vendored / "latest/data-v2" / DATA_V2_CORE
            target.parent.mkdir(parents=True)
            target.write_bytes(b"drifted bytes that are not the locked runtime")
            with mock.patch.object(app, "EMULATOR_VENDORED_RUNTIME", str(vendored)):
                with mock.patch.object(app, "EMULATOR_CACHE_DIR", str(Path(root) / "cache")):
                    self.assertIsNone(app.install_vendored_emulator_asset("latest", DATA_V2_CORE))
                    self.assertFalse((Path(root) / "cache").exists(), "a rejected asset must not populate the cache")

    def test_the_plain_data_channel_is_untouched(self):
        app = load_app()
        with tempfile.TemporaryDirectory(prefix="an3-plain-") as cache:
            with mock.patch.object(app, "EMULATOR_CACHE_DIR", cache):
                # Only `latest/data-v2` is pinned; the ordinary CDN channel keeps
                # its existing cache-then-network behaviour.
                self.assertIsNone(app.install_vendored_emulator_asset("latest", "cores/mgba-wasm.data"))
                self.assertIsNone(app.install_vendored_emulator_asset("stable", DATA_V2_CORE))

    def test_a_missing_native_tree_is_not_an_error(self):
        app = load_app()
        with tempfile.TemporaryDirectory(prefix="an3-absent-") as root:
            with mock.patch.object(app, "EMULATOR_RUNTIME_LOCK", str(Path(root) / "absent.json")):
                self.assertEqual(app.emulator_runtime_lock(), {})
            with mock.patch.object(app, "EMULATOR_VENDORED_RUNTIME", str(Path(root) / "absent")):
                with mock.patch.object(app, "EMULATOR_CACHE_DIR", str(Path(root) / "cache")):
                    self.assertIsNone(app.install_vendored_emulator_asset("latest", DATA_V2_CORE))


class BrowserThreeDsDeliveryTests(unittest.TestCase):
    """The served bytes, over HTTP, on a cold cache with the network unplugged."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.mkdtemp(prefix="an3-web-3ds-")
        cls.data = os.path.join(cls.temp, "data")
        env = os.environ.copy()
        env.update(
            {
                "AN3_DATA_DIR": cls.data,
                "AN3_PORT": str(PORT),
                "AN3_HOST": "127.0.0.1",
                "AN3_ENVIRONMENT": "staging",
                "AN3_ADMIN_NAME": "fixture-admin",
                "AN3_ADMIN_PASSWORD": "synthetic-fixture-only",
                "AN3_COOKIE_SECURE": "0",
            }
        )
        cls.env = env
        cls.server = subprocess.Popen(
            [sys.executable, "app.py"], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2):
                    return
            except Exception:
                time.sleep(0.2)
        cls.tearDownClass()
        raise AssertionError("fixture server did not become ready")

    @classmethod
    def tearDownClass(cls):
        server = getattr(cls, "server", None)
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
        shutil.rmtree(cls.temp, ignore_errors=True)

    def test_the_3ds_core_asset_is_served_from_a_cold_cache(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        cache = Path(self.data) / "emulatorjs-cache"
        self.assertEqual(list(cache.rglob("*")) if cache.exists() else [], [], "the fixture cache must start cold")
        for relative in (DATA_V2_CORE, DATA_V2_REPORT):
            with self.subTest(asset=relative):
                url = f"http://127.0.0.1:{PORT}/emulatorjs/latest/data-v2/{relative}"
                with urllib.request.urlopen(url, timeout=30) as response:
                    self.assertEqual(response.status, 200)
                    payload = response.read()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), lock[f"latest/data-v2/{relative}"])

    def test_the_player_observes_the_audio_context_the_core_creates(self):
        """The 3DS gate must read a real context, not an unreachable handle.

        The runtime creates its Web Audio context inside the core glue, so the
        gate records the contexts the platform constructs. This asserts the
        recording is installed before the core loads and that the gate consults
        it; it is a source contract, not a playback claim.
        """
        source = PLAYER.read_text(encoding="utf-8")
        self.assertIn("__AN3AudioContextRecorder", source)
        self.assertIn("threeDsAudioContexts.slice().reverse()", source)
        record_at = source.index("recordThreeDsAudioContext();")
        boot_at = source.index("\n  boot();")
        self.assertLess(record_at, boot_at, "the recorder must be installed before the core boots")
        self.assertIn('audioContext?.state === "running"', source)


if __name__ == "__main__":
    unittest.main()


class CoreRefreshContractTests(unittest.TestCase):
    """A rebuilt core must not stay pinned in the browser.

    The core binary and its build report are the only emulator assets this
    service replaces in place. Served `immutable`, a returning player kept the
    previous interpreter for a week and the service worker's cache-first policy
    would have kept it longer still, so both now have to revalidate.
    """

    def test_the_server_makes_core_binaries_revalidate(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn('revisable = relative.endswith(".data") or (', source)
        self.assertIn('relative.startswith("cores/reports/")', source)
        self.assertIn('"public,max-age=0,must-revalidate" if revisable', source)

    def test_the_service_worker_refreshes_a_core_before_using_its_cache(self):
        worker = (ROOT / "static/service-worker.js").read_text(encoding="utf-8")
        self.assertIn("refreshableCore", worker)
        self.assertIn(r"/\/cores\/(?:reports\/[^/]+\.json|[^/]+\.data)$/", worker)
        self.assertIn('fetch(event.request, {cache: "no-cache"})', worker)
        # The offline path must survive a failed refresh.
        self.assertIn("cache.match(event.request).then(cached => cached || fetch(event.request))", worker)

    def test_the_android_mirror_carries_the_same_worker(self):
        mirror = ROOT / "native-offline/src-tauri/gen/android/app/src/main/assets/static/service-worker.js"
        if not mirror.exists():
            self.skipTest("the Android asset mirror is not present in this tree")
        self.assertEqual(mirror.read_bytes(), (ROOT / "static/service-worker.js").read_bytes())
