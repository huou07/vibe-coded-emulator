# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-process hosted-frame transport (M2) contracts and runtime guard.

Source contracts always run. The runtime guard launches the real Eden companion,
reads the shared-memory ring name it publishes, runs the separate consumer
harness against that ring, and asserts the consumer imported real frames into
Metal textures. It is skipped when the companion, the consumer or the legal
homebrew fixture is not built in this environment.
"""
import json
import os
import pathlib
import queue
import subprocess
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "native" / "eden-bridge"
SHM_HEADER = BRIDGE / "include" / "an3_eden_hosted_frame_shm.h"
SHM_SOURCE = BRIDGE / "src" / "an3_eden_hosted_frame_shm.c"
CONSUMER = BRIDGE / "tests" / "hosted_frame_consumer.mm"
PRODUCER = BRIDGE / "src" / "hosted_frame_producer.cpp"
INTEGRATION = BRIDGE / "integration" / "CMakeLists.txt"
STANDALONE = BRIDGE / "CMakeLists.txt"

COMPANION_CANDIDATES = [
    os.environ.get("AN3_SWITCH_COMPANION", ""),
    "/tmp/eden-build/bin/an3_switch_companion",
]
CONSUMER_CANDIDATES = [
    os.environ.get("AN3_HOSTED_CONSUMER", ""),
    str(BRIDGE / "build" / "an3_eden_hosted_consumer"),
    "/tmp/an3-hf-build-eden2/an3_eden_hosted_consumer",
]
MOLTENVK_CANDIDATES = [
    os.environ.get("LIBVULKAN_PATH", ""),
    "/tmp/eden/.cache/cpm/moltenvk/v1.4.1-ryujinx/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib",
]


def _first_existing(candidates):
    for raw in candidates:
        if raw and pathlib.Path(raw).exists():
            return pathlib.Path(raw)
    return None


def _homebrew():
    explicit = os.environ.get("AN3_SWITCH_HOMEBREW")
    if explicit and pathlib.Path(explicit).exists():
        return pathlib.Path(explicit)
    for candidate in (
        pathlib.Path("/tmp/an3-hbmenu/hbmenu.nro"),
        pathlib.Path("/tmp/hbmenu.nro"),
        pathlib.Path("/tmp/an3-switch/hbmenu.nro"),
    ):
        if candidate.exists():
            return candidate
    return None


def _json_after(line, marker):
    index = line.find(marker)
    if index < 0:
        return None
    try:
        return json.loads(line[index + len(marker):].strip())
    except json.JSONDecodeError:
        return None


class HostedFrameShmContractTests(unittest.TestCase):
    """Source contracts that hold without running Eden."""

    def test_01_transport_exists_and_is_versioned(self):
        header = SHM_HEADER.read_text(encoding="utf-8")
        self.assertIn("AN3_EDEN_HOSTED_SHM_MAGIC", header)
        self.assertIn("an3_eden_hosted_shm_create", header)
        self.assertIn("an3_eden_hosted_shm_attach", header)
        self.assertIn("PTHREAD_PROCESS_SHARED", SHM_SOURCE.read_text(encoding="utf-8"))

    def test_02_producer_publishes_the_ring_name(self):
        producer = PRODUCER.read_text(encoding="utf-8")
        self.assertIn("AN3CTL_HOSTED", producer)
        self.assertIn("an3_eden_hosted_shm_create", producer)
        # Never log a pointer.
        self.assertNotIn("%p", producer)

    def test_03_consumer_imports_the_iosurface_as_a_metal_texture(self):
        consumer = CONSUMER.read_text(encoding="utf-8")
        self.assertIn("IOSurfaceLookup", consumer)
        self.assertIn("newTextureWithDescriptor", consumer)
        self.assertIn("iosurface:surface", consumer)
        self.assertIn("MTLPixelFormatBGRA8Unorm", consumer)
        self.assertIn("AN3CTL_CONSUMER", consumer)
        # Consumer must not link the Eden bridge.
        self.assertNotIn("an3_eden_bridge.h", consumer)

    def test_04_consumer_is_built_standalone_not_against_eden(self):
        standalone = STANDALONE.read_text(encoding="utf-8")
        self.assertIn("an3_eden_hosted_consumer", standalone)
        integration = INTEGRATION.read_text(encoding="utf-8")
        self.assertIn("an3_eden_hosted_frame_shm.c", integration)
        self.assertNotIn("an3_eden_hosted_consumer", integration)

    def test_05_ring_lock_is_process_shared(self):
        header = SHM_HEADER.read_text(encoding="utf-8")
        self.assertIn("pthread_mutex_t mutex", header)
        self.assertIn("an3_eden_hosted_shm_lock", header)


class HostedFrameShmRuntimeTests(unittest.TestCase):
    """Runtime guard. Skipped without the companion, consumer and fixture."""

    def test_20_separate_process_imports_frames_over_shared_memory(self):
        companion = _first_existing(COMPANION_CANDIDATES)
        consumer = _first_existing(CONSUMER_CANDIDATES)
        homebrew = _homebrew()
        if companion is None or consumer is None:
            self.skipTest("Eden companion and/or hosted-frame consumer not built")
        if homebrew is None:
            self.skipTest("No legal homebrew fixture (set AN3_SWITCH_HOMEBREW to an .nro)")

        env = dict(os.environ)
        moltenvk = _first_existing(MOLTENVK_CANDIDATES)
        if moltenvk is not None:
            env["LIBVULKAN_PATH"] = str(moltenvk)

        proc = subprocess.Popen(
            [str(companion), "--no-stdin", "--frames", "400", str(homebrew)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        lines = queue.Queue()

        def _pump():
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)

        threading.Thread(target=_pump, daemon=True).start()
        try:
            shm_name = None
            deadline = time.time() + 25
            while time.time() < deadline and shm_name is None:
                try:
                    line = lines.get(timeout=0.5)
                except queue.Empty:
                    continue
                if line is None:
                    break
                if "AN3CTL_HOSTED" in line:
                    info = _json_after(line, "AN3CTL_HOSTED ")
                    if info:
                        shm_name = info.get("shm")
            self.assertIsNotNone(shm_name, "companion never published a shared-memory ring name")

            result = subprocess.run(
                [str(consumer), shm_name, "--frames", "5", "--timeout-ms", "20000"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout[-800:] + result.stderr[-800:])
            status = None
            for line in reversed(result.stdout.splitlines()):
                if "AN3CTL_CONSUMER " in line:
                    status = _json_after(line, "AN3CTL_CONSUMER ")
                    break
            self.assertIsNotNone(status, result.stdout[-800:])
            self.assertEqual(status["result"], "PASS")
            self.assertGreaterEqual(status["imported"], 5)
            self.assertEqual(status["texture_ok"], status["imported"])
            self.assertGreater(status["nonzero"], 0, "imported surface was empty")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            if proc.stdout is not None:
                proc.stdout.close()


if __name__ == "__main__":
    unittest.main()
