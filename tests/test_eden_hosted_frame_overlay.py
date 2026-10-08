# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Overlay presentation contracts and runtime guard (M2).

Source contracts always run. The runtime guard compiles the standalone overlay
self-test with the *real* app consumer source and drives it against a running
Eden companion: the consumer imports IOSurface frames and renders the newest one
into a real (off-screen, backed) MTKView drawable via CIContext. Skipped when the
compiler, the companion or the legal homebrew fixture is unavailable.
"""
import json
import os
import pathlib
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TAURI = ROOT / "native-offline" / "src-tauri"
HEADER = (TAURI / "src" / "hosted_frame_consumer.h").read_text(encoding="utf-8")
CONSUMER = (TAURI / "src" / "hosted_frame_consumer.mm").read_text(encoding="utf-8")
SELFTEST = (TAURI / "tests" / "hosted_frame_overlay_selftest.mm").read_text(
    encoding="utf-8"
)

COMPANION_CANDIDATES = [
    os.environ.get("AN3_SWITCH_COMPANION", ""),
    "/tmp/eden-build/bin/an3_switch_companion",
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


class HostedFrameOverlayContractTests(unittest.TestCase):
    def test_01_single_frame_draw_hook_exists(self):
        self.assertIn("an3_eden_hosted_consumer_present_draw", HEADER)
        self.assertIn("an3_eden_hosted_consumer_present_draw", CONSUMER)

    def test_02_overlay_letterboxes_aspect_fit(self):
        # scale = min(fit) applied via an affine matrix, with a black clear for
        # the unused bars.
        self.assertIn("MIN(drawable_size.width / image_width", CONSUMER)
        self.assertIn("CGAffineTransformMake(scale, 0, 0, scale, offset_x, offset_y)", CONSUMER)
        self.assertIn("MTLLoadActionClear", CONSUMER)

    def test_03_overlay_is_still_pointer_inert(self):
        self.assertIn("hitTest:(NSPoint)point", CONSUMER)
        self.assertIn("acceptsFirstResponder", CONSUMER)

    def test_04_selftest_drives_a_real_backed_window(self):
        self.assertIn("AN3CTL_OVERLAY", SELFTEST)
        self.assertIn("orderFrontRegardless", SELFTEST)
        self.assertIn("-32000", SELFTEST)  # off-screen but real
        self.assertIn("CFRunLoopRunInMode", SELFTEST)
        self.assertIn("an3_eden_hosted_consumer_present_start", SELFTEST)


class HostedFrameOverlayRuntimeTests(unittest.TestCase):
    def test_20_overlay_renders_a_real_companion_frame(self):
        compiler = shutil.which("clang++")
        companion = _first_existing(COMPANION_CANDIDATES)
        homebrew = _homebrew()
        if compiler is None:
            self.skipTest("no clang++ available for the overlay self-test")
        if companion is None:
            self.skipTest("Eden companion is not built in this environment")
        if homebrew is None:
            self.skipTest("No legal homebrew fixture (set AN3_SWITCH_HOMEBREW to an .nro)")

        env = dict(os.environ)
        moltenvk = _first_existing(MOLTENVK_CANDIDATES)
        if moltenvk is not None:
            env["LIBVULKAN_PATH"] = str(moltenvk)

        with tempfile.TemporaryDirectory() as tmp:
            binary = pathlib.Path(tmp) / "an3_hosted_frame_overlay_selftest"
            compile_result = subprocess.run(
                [
                    compiler,
                    "-std=c++20",
                    "-fobjc-arc",
                    "-mmacosx-version-min=13.4",
                    "-I",
                    str(ROOT / "native" / "eden-bridge" / "include"),
                    "-I",
                    str(TAURI / "src"),
                    str(TAURI / "tests" / "hosted_frame_overlay_selftest.mm"),
                    str(TAURI / "src" / "hosted_frame_consumer.mm"),
                    str(ROOT / "native" / "eden-bridge" / "src" / "an3_eden_hosted_frame.c"),
                    str(ROOT / "native" / "eden-bridge" / "src" / "an3_eden_hosted_frame_shm.c"),
                    "-framework", "AppKit",
                    "-framework", "Foundation",
                    "-framework", "Metal",
                    "-framework", "MetalKit",
                    "-framework", "CoreImage",
                    "-framework", "IOSurface",
                    "-framework", "QuartzCore",
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr[-800:])

            proc = subprocess.Popen(
                [str(companion), "--no-stdin", "--frames", "900", str(homebrew)],
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
                    [str(binary), shm_name, "--wait-ms", "15000"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout[-800:] + result.stderr[-800:])
                status = None
                for line in reversed(result.stdout.splitlines()):
                    if "AN3CTL_OVERLAY " in line:
                        status = _json_after(line, "AN3CTL_OVERLAY ")
                        break
                self.assertIsNotNone(status, result.stdout[-800:])
                self.assertEqual(status["result"], "PASS")
                self.assertEqual(status["drawn"], 1)
                self.assertGreaterEqual(status["presented"], 1)
                self.assertGreater(status["nonzero"], 0, "presented frame was empty")
                self.assertEqual(status["width"], 1280)
                self.assertEqual(status["height"], 720)
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
