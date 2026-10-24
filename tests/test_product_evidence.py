# SPDX-License-Identifier: GPL-3.0-or-later
"""Adversarial admission checks; fixtures here are validator tests, never product evidence."""
import copy
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("product_evidence", ROOT / "tools/verify-product-evidence.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
REV = "a" * 40


class ProductEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        evidence = self.base / "observations.json"
        evidence.write_text('{"test_fixture_only": true}\n')
        self.digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
        self.record = dict(schema=1, revision=REV, dirty=False, build="source fixture",
                           platform="test host", backend="Chromium", timestamp="2026-10-20",
                           command="test fixture only", runtime="browser-ui",
                           claim="ui-journey", checks=self.checks("ui-journey"))

    def checks(self, claim):
        return {name: dict(result="PASS", action="validator test action", observed="validator test observation",
                           evidence="observations.json", sha256=self.digest)
                for name in module.REQUIRED[claim]}

    def evaluate(self, record=None):
        return module.evaluate(self.record if record is None else record, self.base, REV)

    def native(self, claim):
        self.record.update(claim=claim, runtime="native-package",
                           package=dict(sha256="b" * 64, revision=REV, distribution=True),
                           checks=self.checks(claim))

    def test_complete_narrow_claim_is_admissible(self):
        self.assertEqual(self.evaluate()["verdict"], "PASS")

    def test_flag_compiled_backend_without_interface_is_rejected(self):
        self.native("experimental")
        self.record["checks"]["interface"]["result"] = "NOT RUN"
        self.assertEqual(self.evaluate()["verdict"], "BLOCKED")
        self.record["checks"]["interface"]["result"] = "FAIL"
        self.assertEqual(self.evaluate()["verdict"], "FAIL")

    def test_build_or_mock_success_cannot_substitute_for_app(self):
        for runtime in ("build", "mock", "browser-ui", "native-test"):
            with self.subTest(runtime=runtime):
                self.native("experimental")
                self.record["runtime"] = runtime
                self.assertEqual(self.evaluate()["verdict"], "BLOCKED")

    def test_source_or_package_mismatch_and_dirty_source_are_blocked(self):
        self.native("packaged")
        for field in ("revision", "package", "dirty"):
            bad = copy.deepcopy(self.record)
            bad[field] = {"revision": "c" * 40, "distribution": True, "sha256": "b" * 64} if field == "package" else (
                True if field == "dirty" else "c" * 40)
            self.assertEqual(self.evaluate(bad)["verdict"], "BLOCKED")

    def test_missing_tampered_or_external_observation_is_rejected(self):
        check = self.record["checks"]["navigation"]
        check["sha256"] = "0" * 64
        self.assertEqual(self.evaluate()["verdict"], "FAIL")
        check["sha256"] = self.digest
        check["evidence"] = "missing.log"
        self.assertEqual(self.evaluate()["verdict"], "BLOCKED")
        check["evidence"] = "../outside.log"
        self.assertEqual(self.evaluate()["verdict"], "BLOCKED")

    def test_performance_rejects_synthetic_and_missing_measurements(self):
        self.record.update(claim="gameplay-performance", runtime="browser-wasm",
                           checks=self.checks("gameplay-performance"),
                           fixture=dict(name="animation", kind="synthetic-animation", sha256="f" * 64))
        result = self.evaluate()
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertTrue(any("synthetic" in gap for gap in result["gaps"]))

    def test_failing_measured_rate_dominates_other_green_results(self):
        self.record.update(claim="gameplay-performance", runtime="browser-wasm",
                           checks=self.checks("gameplay-performance"),
                           fixture=dict(name="homebrew", kind="homebrew", sha256="f" * 64),
                           performance=dict(baseline="test baseline", conditions="test conditions",
                           representative=True, unique_display_frames="test", cpu="test", gpu="test",
                           memory="test", main_thread="test", workers="test", metrics={
                               "core_fps": dict(actual=20, limit=55, direction="min"),
                               "presentation_p95_ms": dict(actual=17, limit=25, direction="max"),
                               "audio_underruns": dict(actual=0, limit=0, direction="max")}))
        self.assertEqual(self.evaluate()["verdict"], "FAIL")
        self.record["performance"]["metrics"]["core_fps"]["actual"] = float("nan")
        self.assertEqual(self.evaluate()["verdict"], "BLOCKED")

    def test_skips_unknown_results_and_missing_outcomes_are_never_pass(self):
        for result in ("SKIP", "BLOCKED", "UNVERIFIED", "NOT RUN", None):
            self.record["checks"]["navigation"]["result"] = result
            self.assertEqual(self.evaluate()["verdict"], "BLOCKED")

    def test_acceptance_without_evidence_blocks_before_running_source_gate(self):
        result = subprocess.run(["bash", "tools/acceptance.sh"], cwd=ROOT,
                                capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("PROJECT_ACCEPTANCE=BLOCKED", result.stdout)
        self.assertNotIn("== Source gate", result.stdout)

    def test_malformed_record_returns_blocked_without_traceback(self):
        record = self.base / "bad.json"
        record.write_text(json.dumps({"checks": []}))
        result = subprocess.run(["python3", "tools/verify-product-evidence.py", str(record),
                                 "--revision", REV], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "BLOCKED")
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
