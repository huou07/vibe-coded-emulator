# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep published workflow triggers and test commands aligned with the tree."""
from fnmatch import fnmatch
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
NATIVE_WORKFLOW = (ROOT / "tools/publication/.github/workflows/native-build.yml").read_text(encoding="utf-8")
PORTABLE_WORKFLOW = (ROOT / "tools/publication/.github/workflows/ci.yml").read_text(encoding="utf-8")


def event_paths(source: str, event: str) -> set[str]:
    if event == "pull_request":
        match = re.search(r"(?ms)^  pull_request:\n    paths:\n((?:      - .*\n)+)", source)
    else:
        match = re.search(r"(?ms)^  push:\n    branches:.*\n    paths:\n((?:      - .*\n)+)", source)
    if not match:
        raise AssertionError(f"{event} must define explicit path filters")
    return set(re.findall(r"^      - ['\"]([^'\"]+)['\"]\s*$", match.group(1), re.MULTILINE))


class PublishedWorkflowTests(unittest.TestCase):
    def test_native_build_runs_for_every_shared_or_native_input(self):
        expected = {
            ".gitattributes",
            ".github/workflows/**",
            "native/**",
            "native-offline/**",
            "static/**",
            "tests/**",
            "tools/android/**",
            "tools/release-train.sh",
            "tools/testrom/**",
        }
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                self.assertTrue(expected <= event_paths(NATIVE_WORKFLOW, event))

    def test_node_workflow_globs_match_suites_in_this_checkout(self):
        patterns = ("tests/*.test.js", "tests/*.test.mjs")
        actual = {
            str(path.relative_to(ROOT))
            for pattern in patterns
            for path in (ROOT / "tests").glob(pattern.split("/", 1)[1])
        }
        self.assertTrue(actual, "the published Node test patterns must match files")
        for pattern in patterns:
            self.assertTrue(any(fnmatch(path, pattern) for path in actual), pattern)

        for workflow in (NATIVE_WORKFLOW, PORTABLE_WORKFLOW):
            node_commands = [line for line in workflow.splitlines() if line.strip().startswith("run: node --test")]
            self.assertTrue(node_commands, "workflow must run Node suites")
            self.assertTrue(all(all(pattern in line for pattern in patterns) for line in node_commands))
            self.assertFalse(any("native-offline/tests/*.test." in line for line in node_commands))

        native_node_tests = [
            path for path in (ROOT / "native-offline/tests").iterdir()
            if path.name.endswith((".test.js", ".test.mjs"))
        ]
        self.assertEqual(native_node_tests, [], "native-offline/tests currently contains native sources, not Node suites")


if __name__ == "__main__":
    unittest.main()
