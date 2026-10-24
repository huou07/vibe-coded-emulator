# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The verify gate must publish what it skipped, with reasons and counts.

A green run once hid 20 Python skips (and several Node skips) behind a single
`OK (skipped=20)` line. tools/verify-project.sh now captures each suite's output
and prints `VERIFY_SKIPS=<json>` from tools/verify-skip-manifest.py. These tests
pin the parsing and the fail-closed behaviour on synthetic logs.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/verify-skip-manifest.py"
GATE = ROOT / "tools/verify-project.sh"

PYTHON_LOG = """\
test_alpha (tests.test_alpha.Alpha.test_alpha) ... ok
test_beta (tests.test_beta.Beta.test_beta) ... skipped 'no C++ compiler available'
test_gamma (tests.test_gamma.Gamma.test_gamma) ... skipped 'fixture is unavailable'
RG-111: Eden's ErrorVideoCore path terminates in a noexcept destructor. ... skipped 'No legal homebrew fixture (set AN3_SWITCH_HOMEBREW to an .nro)'

----------------------------------------------------------------------
Ran 4 tests in 0.10s

OK (skipped=3)
"""

NODE_LOG = """\
✔ targets: discovery returns an envelope with every target (248.682821ms)
﹣ android: structured tree and a semantic click (283.234ms) # no Android device/emulator connected
﹣ emulator: deterministic status, and diff detects a frame change (0.222514ms) # set AN3_PLAYER or AN3_PLAYER_TARGET to exercise the emulator plane
ℹ tests 5
ℹ pass 3
ℹ skipped 2
"""


class SkipManifestTests(unittest.TestCase):
    def run_tool(self, python_log: str, node_log: str, out: Path | None = None, write: bool = True):
        with tempfile.TemporaryDirectory(prefix="an3-skip-manifest-") as temporary:
            root = Path(temporary)
            py = root / "python.log"
            node = root / "node.log"
            if write:
                py.write_text(python_log, encoding="utf-8")
                node.write_text(node_log, encoding="utf-8")
            args = [sys.executable, str(TOOL), "--python-log", str(py), "--node-log", str(node)]
            if out is not None:
                args += ["--out", str(out)]
            return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=120)

    def test_manifest_carries_counts_tests_and_reasons(self):
        out = Path(tempfile.mkdtemp(prefix="an3-skip-out-")) / "skip-manifest.json"
        result = self.run_tool(PYTHON_LOG, NODE_LOG, out=out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("VERIFY_SKIPS=", result.stdout)

        payload = json.loads(result.stdout.split("VERIFY_SKIPS=", 1)[1].strip())
        self.assertEqual(payload["gate"], "verify-project")
        self.assertEqual(payload["skips"]["python"]["count"], 3)
        self.assertEqual(
            [entry["test"] for entry in payload["skips"]["python"]["tests"]],
            [
                "test_beta",
                "test_gamma",
                "RG-111: Eden's ErrorVideoCore path terminates in a noexcept destructor.",
            ],
            "a bare-function skip has no class locator and must still be reported",
        )
        self.assertEqual(payload["skips"]["python"]["tests"][0]["reason"], "no C++ compiler available")
        self.assertEqual(payload["skips"]["javascript"]["count"], 2)
        reasons = [entry.get("reason", "") for entry in payload["skips"]["javascript"]["tests"]]
        self.assertIn("no Android device/emulator connected", reasons)
        self.assertTrue(any("AN3_PLAYER" in reason for reason in reasons))
        self.assertEqual(payload["total"], 5)

        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(written, payload)

    def test_node_skip_names_drop_the_duration(self):
        result = self.run_tool(PYTHON_LOG, NODE_LOG)
        payload = json.loads(result.stdout.split("VERIFY_SKIPS=", 1)[1].strip())
        names = [entry["test"] for entry in payload["skips"]["javascript"]["tests"]]
        self.assertIn("android: structured tree and a semantic click", names)
        self.assertFalse(any("ms)" in name for name in names))

    def test_unreadable_logs_are_not_a_clean_manifest(self):
        result = self.run_tool("", "", write=False)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("VERIFY_SKIPS=", result.stdout)

    def test_gate_prints_the_manifest_and_fails_closed_without_it(self):
        gate = GATE.read_text(encoding="utf-8")
        self.assertIn("verify-skip-manifest.py", gate)
        self.assertIn("--out \"$LOG_DIR/skip-manifest.json\"", gate)
        manifest_step = gate.find("verify-skip-manifest.py")
        verdict = gate.find("PROJECT_VERIFY=PASS")
        self.assertNotEqual(verdict, -1)
        self.assertLess(manifest_step, verdict, "the manifest must be part of the verdict, not after it")
        self.assertIn("skip manifest could not be produced", gate)
        # The Python suite must report skip reasons for the manifest to read.
        self.assertIn("python3 -m unittest discover -s tests -v", gate)


if __name__ == "__main__":
    unittest.main()
