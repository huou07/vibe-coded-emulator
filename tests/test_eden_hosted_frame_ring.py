# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Behavioral tests for the Eden hosted-frame ring contract.

Compiles the pure-C ring model with the system C compiler and runs its
assertion harness. Skipped when no C compiler is available so it never produces
a false red on machines without a toolchain.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "native" / "eden-bridge"
INCLUDE = BRIDGE / "include"
SOURCE = BRIDGE / "src" / "an3_eden_hosted_frame.c"
TEST = BRIDGE / "tests" / "hosted_frame_test.c"


def _compiler():
    return shutil.which("clang") or shutil.which("cc") or shutil.which("gcc")


class EdenHostedFrameRingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = _compiler()
        if cls.compiler is None:
            raise unittest.SkipTest("no C compiler available for the hosted-frame ring test")

    def test_ring_contract_is_compiled_and_verified(self):
        self.assertTrue(SOURCE.is_file(), "ring implementation must exist")
        self.assertTrue(TEST.is_file(), "ring test harness must exist")
        with tempfile.TemporaryDirectory() as tmp:
            binary = pathlib.Path(tmp) / "hosted_frame_test"
            compile_result = subprocess.run(
                [
                    self.compiler,
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(INCLUDE),
                    str(SOURCE),
                    str(TEST),
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run_result.returncode, 0, run_result.stdout + run_result.stderr)
            self.assertIn("0 failures", run_result.stdout)


if __name__ == "__main__":
    unittest.main()
